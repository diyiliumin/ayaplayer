use std::cell::{Cell, RefCell};
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::rc::Rc;
use std::sync::mpsc::{self, TryRecvError};
use std::time::Duration;

use libadwaita::prelude::*;
use gtk4::{gio, glib};

const CONTROL_PATH: &str = "/com/ayaplayer/Control";
const IFACE: &str = "com.ayaplayer.Interface";

#[derive(Debug)]
struct Status {
    pid: i32,
    title: String,
    cover: String,
    songleft: i32,
    paused: bool,
}

enum Event {
    Status(Status),
    CoverLoaded(Option<PathBuf>),
}

fn main() -> glib::ExitCode {
    libadwaita::init().expect("failed to initialize libadwaita");

    let app = gtk4::Application::builder()
        .application_id("com.ayaplayer.desktop")
        .build();
    app.connect_activate(build_ui);
    app.run()
}

fn build_ui(app: &gtk4::Application) {
    load_css();

    let window = libadwaita::ApplicationWindow::new(app);
    window.set_title(Some("AyaPlayer"));
    window.set_default_size(420, 640);

    // Header bar with title + subtitle
    let title_label = gtk4::Label::new(Some("AyaPlayer"));
    title_label.add_css_class("title");
    let subtitle_label = gtk4::Label::new(Some("播放控制"));
    subtitle_label.add_css_class("subtitle");
    subtitle_label.add_css_class("dim-label");
    let title_box = gtk4::Box::new(gtk4::Orientation::Vertical, 0);
    title_box.append(&title_label);
    title_box.append(&subtitle_label);

    let header = libadwaita::HeaderBar::new();
    header.set_title_widget(Some(&title_box));
    header.set_hexpand(true);

    // Cover art (Picture scales automatically)
    let cover = gtk4::Picture::new();
    cover.set_content_fit(gtk4::ContentFit::Cover);
    cover.set_can_shrink(true);
    cover.set_size_request(240, 240);
    cover.add_css_class("cover-art");

    let placeholder = gtk4::Image::from_icon_name("audio-x-generic-symbolic");
    placeholder.set_pixel_size(96);

    let cover_stack = gtk4::Stack::new();
    cover_stack.set_transition_type(gtk4::StackTransitionType::Crossfade);
    cover_stack.set_transition_duration(300);
    cover_stack.set_interpolate_size(true);
    cover_stack.add_named(&placeholder, Some("placeholder"));
    cover_stack.add_named(&cover, Some("cover"));
    cover_stack.set_visible_child_name("placeholder");
    cover_stack.set_halign(gtk4::Align::Center);

    // Now playing labels
    let now_title = gtk4::Label::new(Some("等待播放..."));
    now_title.set_wrap(true);
    now_title.set_justify(gtk4::Justification::Center);
    now_title.set_wrap_mode(gtk4::pango::WrapMode::Char);
    now_title.add_css_class("now-title");

    let now_status = gtk4::Label::new(Some("无播放"));
    now_status.add_css_class("dim-label");

    // Controls
    let play_icon = gtk4::Image::from_icon_name("media-playback-start-symbolic");
    play_icon.set_pixel_size(28);
    let play_button = gtk4::ToggleButton::new();
    play_button.set_child(Some(&play_icon));
    play_button.add_css_class("circular");
    play_button.add_css_class("suggested-action");
    play_button.add_css_class("play-btn");

    let skip_button = icon_button("media-skip-forward-symbolic");
    let quit_button = icon_button("application-exit-symbolic");

    let controls = gtk4::Box::new(gtk4::Orientation::Horizontal, 16);
    controls.set_halign(gtk4::Align::Center);
    controls.append(&play_button);
    controls.append(&skip_button);
    controls.append(&quit_button);

    // Repeat count picker (x1 .. x9)
    let repeat_box = gtk4::Box::new(gtk4::Orientation::Horizontal, 6);
    repeat_box.set_halign(gtk4::Align::Center);

    let mut count_buttons: Vec<gtk4::ToggleButton> = Vec::new();
    let mut group: Option<gtk4::ToggleButton> = None;
    for n in 1..=9 {
        let b = gtk4::ToggleButton::with_label(&format!("×{n}"));
        b.add_css_class("count-btn");
        b.set_group(group.as_ref());
        if group.is_none() {
            group = Some(b.clone());
        }
        repeat_box.append(&b);
        count_buttons.push(b);
    }
    count_buttons[0].set_active(true);

    // Main content
    let content = gtk4::Box::new(gtk4::Orientation::Vertical, 20);
    content.set_margin_top(24);
    content.set_margin_bottom(24);
    content.set_valign(gtk4::Align::Center);
    content.append(&cover_stack);
    content.append(&now_title);
    content.append(&now_status);
    content.append(&controls);
    content.append(&repeat_box);

    let clamp = libadwaita::Clamp::new();
    clamp.set_maximum_size(460);
    clamp.set_hexpand(true);
    clamp.set_vexpand(true);
    clamp.set_child(Some(&content));

    let root = gtk4::Box::new(gtk4::Orientation::Vertical, 0);
    root.append(&header);
    root.append(&clamp);

    window.set_content(Some(&root));
    window.present();

    // Event channel: dbus status + cover downloads -> main thread
    let (tx, rx) = mpsc::channel::<Event>();

    let paused = Rc::new(Cell::new(false));
    let current_cover = Rc::new(RefCell::new(String::new()));

    let ui = Ui {
        cover_stack,
        cover,
        now_title,
        now_status,
        play_icon,
        play_button,
        count_buttons,
        paused: paused.clone(),
        current_cover: current_cover.clone(),
        tx: tx.clone(),
    };

    // Play / pause
    ui.play_button.connect_clicked({
        let paused = paused.clone();
        move |_| {
            let is_paused = paused.get();
            send_control("pause", if is_paused { "false" } else { "true" });
        }
    });

    // Repeat count
    for (i, b) in ui.count_buttons.iter().enumerate() {
        let data = i.to_string();
        b.connect_clicked(move |_| send_control("number", &data));
    }

    // Skip / quit
    skip_button.connect_clicked(|_| send_control("skip", ""));
    quit_button.connect_clicked(|_| send_control("quit", ""));

    // Listen for StatusChanged via dbus-monitor
    let tx_db = tx.clone();
    std::thread::spawn(move || monitor_dbus(tx_db));

    // Request current status shortly after startup
    std::thread::spawn(|| {
        std::thread::sleep(Duration::from_millis(700));
        send_control("ui_started", &std::process::id().to_string());
    });

    // Apply events on the main thread
    let ui_rx = ui.clone();
    glib::timeout_add_local(Duration::from_millis(100), move || {
        loop {
            match rx.try_recv() {
                Ok(event) => match event {
                    Event::Status(s) => ui_rx.update(&s),
                    Event::CoverLoaded(p) => ui_rx.apply_cover(p),
                },
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => return glib::ControlFlow::Break,
            }
        }
        glib::ControlFlow::Continue
    });

    // Breathing glow on the play button while playing
    let pulse_btn = ui.play_button.clone();
    let pulse_paused = ui.paused.clone();
    let pulse_start = std::time::Instant::now();
    glib::timeout_add_local(Duration::from_millis(40), move || {
        if pulse_paused.get() {
            pulse_btn.set_opacity(1.0);
        } else {
            let phase = (pulse_start.elapsed().as_secs_f64() * 1.6).fract();
            let tri = 1.0 - (2.0 * phase - 1.0).abs();
            pulse_btn.set_opacity(0.80 + 0.20 * tri);
        }
        glib::ControlFlow::Continue
    });
}

#[derive(Clone)]
struct Ui {
    cover_stack: gtk4::Stack,
    cover: gtk4::Picture,
    now_title: gtk4::Label,
    now_status: gtk4::Label,
    play_icon: gtk4::Image,
    play_button: gtk4::ToggleButton,
    count_buttons: Vec<gtk4::ToggleButton>,
    paused: Rc<Cell<bool>>,
    current_cover: Rc<RefCell<String>>,
    tx: mpsc::Sender<Event>,
}

impl Ui {
    fn update(&self, s: &Status) {
        let title = if s.title.is_empty() {
            "等待播放...".to_string()
        } else {
            s.title.clone()
        };
        self.now_title.set_text(&title);

        if s.pid == 0 {
            self.now_status.set_text("无播放");
        } else {
            let state = if s.paused { "已暂停" } else { "播放中" };
            self.now_status.set_text(&format!("{state} · 剩余 {} 次", s.songleft));
        }

        let (icon, active) = if s.paused {
            ("media-playback-start-symbolic", false)
        } else {
            ("media-playback-pause-symbolic", true)
        };
        self.play_icon.set_icon_name(Some(icon));
        self.play_button.set_active(active);
        self.paused.set(s.paused);
        if s.paused {
            self.play_button.remove_css_class("playing");
        } else {
            self.play_button.add_css_class("playing");
        }

        let idx = (s.songleft as usize).min(8);
        for (i, b) in self.count_buttons.iter().enumerate() {
            b.set_active(i == idx);
        }

        if self.current_cover.borrow().as_str() != s.cover.as_str() {
            *self.current_cover.borrow_mut() = s.cover.clone();
            self.load_cover(&s.cover);
        }
    }

    fn load_cover(&self, cover: &str) {
        if cover.is_empty() {
            self.cover_stack.set_visible_child_name("placeholder");
            return;
        }
        if cover.starts_with("http://") || cover.starts_with("https://") {
            let url = cover.to_string();
            let tx = self.tx.clone();
            std::thread::spawn(move || {
                let path = download_cover(&url);
                let _ = tx.send(Event::CoverLoaded(path));
            });
        } else {
            let file = gio::File::for_path(cover);
            self.cover.set_file(Some(&file));
            self.cover_stack.set_visible_child_name("cover");
        }
    }

    fn apply_cover(&self, path: Option<PathBuf>) {
        match path {
            Some(p) => {
                let file = gio::File::for_path(&p);
                self.cover.set_file(Some(&file));
                self.cover_stack.set_visible_child_name("cover");
            }
            None => self.cover_stack.set_visible_child_name("placeholder"),
        }
    }
}

fn icon_button(icon: &str) -> gtk4::Button {
    let img = gtk4::Image::from_icon_name(icon);
    img.set_pixel_size(20);
    let b = gtk4::Button::new();
    b.set_child(Some(&img));
    b.add_css_class("circular");
    b.add_css_class("icon-btn");
    b
}

fn load_css() {
    let css = r#"
    .cover-art {
        border-radius: 20px;
        box-shadow: 0 6px 24px alpha(black, 0.35);
    }
    .now-title {
        font-size: 1.25em;
        font-weight: 600;
    }
    .play-btn {
        min-width: 68px;
        min-height: 68px;
        border-radius: 34px;
    }
    .play-btn.playing {
        box-shadow: 0 0 20px alpha(@accent_bg_color, 0.45);
    }
    .icon-btn {
        min-width: 48px;
        min-height: 48px;
        border-radius: 24px;
    }
    .icon-btn:hover {
        box-shadow: 0 2px 10px alpha(currentColor, 0.25);
    }
    .count-btn {
        border-radius: 999px;
        padding-left: 12px;
        padding-right: 12px;
    }
    .count-btn:hover {
        box-shadow: 0 2px 10px alpha(currentColor, 0.25);
    }
    "#;

    let provider = gtk4::CssProvider::new();
    provider.load_from_string(css);
    if let Some(display) = gtk4::gdk::Display::default() {
        gtk4::style_context_add_provider_for_display(
            &display,
            &provider,
            gtk4::STYLE_PROVIDER_PRIORITY_APPLICATION,
        );
    }
}

fn send_control(action: &str, data: &str) {
    let member = format!("{IFACE}.Control");
    let a = format!("string:{action}");
    let d = format!("string:{data}");

    let _ = Command::new("dbus-send")
        .arg("--session")
        .arg("--type=signal")
        .arg(CONTROL_PATH)
        .arg(&member)
        .arg(&a)
        .arg(&d)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}

fn monitor_dbus(tx: mpsc::Sender<Event>) {
    let mut child = match Command::new("dbus-monitor")
        .args([
            "--session",
            "type='signal',interface='com.ayaplayer.Interface',member='StatusChanged'",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(c) => c,
        Err(_) => return,
    };

    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => return,
    };

    let reader = BufReader::new(stdout);
    let mut expecting = 0usize;
    let mut args: Vec<String> = Vec::new();

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        if t.contains("member=StatusChanged") {
            args.clear();
            expecting = 5;
            continue;
        }
        if expecting > 0 {
            args.push(t.to_string());
            expecting -= 1;
            if expecting == 0 {
                if let Some(status) = parse_status(&args) {
                    let _ = tx.send(Event::Status(status));
                }
            }
        }
    }
}

fn parse_status(args: &[String]) -> Option<Status> {
    let pid = parse_i32(args.get(0)?)?;
    let title = parse_string(args.get(1)?);
    let cover = parse_string(args.get(2)?);
    let songleft = parse_i32(args.get(3)?)?;
    let paused = parse_bool(args.get(4)?)?;
    Some(Status {
        pid,
        title,
        cover,
        songleft,
        paused,
    })
}

fn parse_i32(line: &str) -> Option<i32> {
    line.split_whitespace().last()?.parse().ok()
}

fn parse_bool(line: &str) -> Option<bool> {
    match line.split_whitespace().last()? {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    }
}

fn parse_string(line: &str) -> String {
    let rest = line.trim();
    let rest = rest.strip_prefix("string").unwrap_or(rest);
    let rest = rest.trim();
    let inner = rest
        .strip_prefix('"')
        .and_then(|s| s.strip_suffix('"'))
        .unwrap_or(rest);
    inner.replace("\\\"", "\"").replace("\\\\", "\\")
}

fn download_cover(url: &str) -> Option<PathBuf> {
    let path = std::env::temp_dir().join("ayaplayer-cover");
    let out = path.to_str()?;
    let ok = Command::new("curl")
        .args(["-s", "-L", "--max-time", "20", "-o", out, url])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .ok()?
        .success();
    if ok && path.is_file() {
        Some(path)
    } else {
        None
    }
}
