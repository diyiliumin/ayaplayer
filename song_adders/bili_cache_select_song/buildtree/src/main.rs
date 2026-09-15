use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::Read;
use std::path::PathBuf;
use walkdir::WalkDir;
use std::sync::atomic::{AtomicUsize, Ordering};
use rayon::prelude::*;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use std::sync::atomic::AtomicBool;

/// 中间结构：保存每个视频条目 + 所属 title 的 ep_p（如果有的话）
#[derive(Debug, Clone)]
struct ParsedEntry {
    item: Item,
    ep_p: Option<u32>, // 这个 title 的序号（来自 epInfo.p）
}

#[derive(Debug, Serialize, Clone)]
struct Item {
    p: u32,                // ← 外层 p（tab 内分 P）
    title: String,         // ← 优先 epInfo.title
    duration: u32,
    loaded_size: u64,
    bvid: String,
    cid: u64,
    group_title: String,   // ← 优先 epInfo.groupTitle
    tab_name: String,      // ← 始终外层 tabName
    scheme: String,
}

#[derive(Debug, Serialize)]
struct TabNode {
    name: String,
    items: Vec<Item>,
}

#[derive(Debug, Serialize)]
struct TitleNode {
    name: String,
    p: Option<u32>,        // ← 来自 epInfo.p（title 的序号）
    tabs: Vec<TabNode>,
}

#[derive(Debug, Serialize)]
struct GroupNode {
    name: String,
    titles: Vec<TitleNode>,
}

fn extract_str(obj: &serde_json::Value, ep_info: Option<&serde_json::Value>, key: &str) -> String {
    if let Some(ep) = ep_info {
        if let Some(v) = ep.get(key).and_then(|v| v.as_str()) {
            return v.to_string();
        }
    }
    obj.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("<unknown>")
        .to_string()
}

fn extract_u32_from_obj(obj: &serde_json::Value, key: &str) -> u32 {
    obj.get(key)
        .and_then(|v| v.as_u64())
        .and_then(|x| u32::try_from(x).ok())
        .unwrap_or(0)
}

fn extract_u64_from_obj(obj: &serde_json::Value, key: &str) -> u64 {
    obj.get(key)
        .and_then(|v| v.as_u64())
        .unwrap_or(0)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {

 // === 新增：用于显示“当前扫描位置”的共享状态 ===
let current_dir = Arc::new(Mutex::new(None::<PathBuf>));
let current_dir_clone = current_dir.clone();
let scanning = Arc::new(AtomicBool::new(true));
let scanning_clone = scanning.clone();

// 启动后台刷新线程：每 1 秒打印一次当前目录（如果变了）
std::thread::spawn(move || {
    let mut last_printed: Option<PathBuf> = None;
    while scanning_clone.load(Ordering::Relaxed) {
        if let Ok(dir_opt) = current_dir_clone.lock() {
            if let Some(ref current) = *dir_opt {
                // 只有当目录变化时才打印，避免重复刷屏
                if last_printed.as_ref().map_or(true, |p| p != current) {
                    eprintln!("扫描中: {}", current.display());
                    last_printed = Some(current.clone());
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100)); // 每秒检查一次
    }
});

   let cfg_path = {
        let mut p = std::env::current_exe()?;
        p.pop(); p.pop(); p.pop();
        p.push("config.json");
        p
    };
    eprintln!("config: {:?}", cfg_path);
    let cfg: serde_json::Value = serde_json::from_reader(File::open(&cfg_path)?)?;
    let root: PathBuf = cfg["root"].as_str().unwrap().into();
    eprintln!("root  : {:?}", root);

let candidates: Vec<_> = WalkDir::new(&root)
    .follow_links(false)
    .into_iter()
    .par_bridge()
    .filter_map(|e| {
        let entry = match e {
            Ok(e) => e,
            Err(_) => return None,
        };

        // === 新增：更新当前目录（用于进度提示）===
        if entry.file_type().is_dir() {
            if let Ok(mut dir_guard) = current_dir.lock() {
                *dir_guard = Some(entry.path().to_path_buf());
            }
        }

        if !entry.file_type().is_file() {
            return None;
        }

        if entry.path().ends_with("videoInfo.json") {
            Some(entry)
        } else {
            None
        }
    })
    .collect();
    eprintln!("共找到 {} 个 videoInfo 文件", candidates.len());

    let read_err = AtomicUsize::new(0);
    let parse_err = AtomicUsize::new(0);

    // 先并行解析所有 entry（允许重复）
    let raw_entries: Vec<ParsedEntry> = candidates
        .par_iter()
        .filter_map(|entry| {
            let mut buf = Vec::with_capacity(16 * 1024);
            if File::open(entry.path())
                .and_then(|mut f| f.read_to_end(&mut buf))
                .is_err()
            {
                read_err.fetch_add(1, Ordering::Relaxed);
                return None;
            }

            match serde_json::from_slice::<serde_json::Value>(&buf) {
                Ok(root_obj) => {
                    let ep_info = root_obj.get("epInfo");

                    // --- group_title 和 title：优先 epInfo ---
                    let group_title = extract_str(&root_obj, ep_info, "groupTitle");
                    let title = extract_str(&root_obj, ep_info, "title");

                    // --- tab_name：始终用外层 ---
                    let tab_name = root_obj
                        .get("tabName")
                        .and_then(|v| v.as_str())
                        .unwrap_or("<unknown_tab>")
                        .to_string();

                    // --- p_in_tab：外层 p（Item 用）---
                    let outer_p = extract_u32_from_obj(&root_obj, "p");

                    // --- ep_p：如果有 epInfo，取它的 p（用于 TitleNode）---
                    // --- TitleNode 的 p 逻辑 ---
                    let title_p = if let Some(ep) = ep_info {
                        // 尝试从 epInfo 取 p，失败则 fallback 到 outer_p（推荐）
                        ep.get("p")
                            .and_then(|v| v.as_u64())
                            .and_then(|x| u32::try_from(x).ok())
                            .or(Some(outer_p))
                    } else {
                        Some(outer_p)
                    };

                    let item = Item {
                        p: outer_p,
                        title: title.clone(),
                        duration: extract_u32_from_obj(&root_obj, "duration"),
                        loaded_size: extract_u64_from_obj(&root_obj, "loadedSize"),
                        bvid: extract_str(&root_obj, ep_info, "bvid"),
                        cid: extract_u64_from_obj(&root_obj, "cid"),
                        group_title: group_title.clone(),
                        tab_name: tab_name.clone(),
                        scheme: "bilicache".to_string()
                    };

                    Some(ParsedEntry { item, ep_p: title_p })
                }
                Err(e) => {
                    eprintln!("JSON 错误: {}  {:?}", entry.path().display(), e);
                    parse_err.fetch_add(1, Ordering::Relaxed);
                    None
                }
            }
        })
        .collect();

    // 去重：按 (bvid, cid, p) 去重（p 是 outer_p）
   // let mut seen = HashSet::new();
    let mut unique_entries = Vec::new();
    for entry in raw_entries {
       // let key = (entry.item.bvid.clone(), entry.item.cid, entry.item.p);
       // if seen.insert(key) {
            unique_entries.push(entry);
       // }
    }

    eprintln!(
        "解析完成  读取失败: {}  解析失败: {}  成功条数: {}",
        read_err.load(Ordering::Relaxed),
        parse_err.load(Ordering::Relaxed),
        unique_entries.len()
    );

    if unique_entries.is_empty() {
        eprintln!("⚠️  没有成功解析到任何条目，退出");
        return Ok(());
    }

    /* 
       现在要按 (group_title, title) 聚合，
       同时记录该 title 的 ep_p（如果有多个，取第一个）
    */
    let mut groups: HashMap<
        String, // group_title
        HashMap<
            (String, Option<u32>), // (title, ep_p) —— 注意：我们把 ep_p 作为 key 的一部分，避免同名 title 冲突
            HashMap<String, Vec<Item>>, // tab_name -> items
        >,
    > = Default::default();

    // 但我们其实希望：同一个 (group, title) 只有一个 ep_p（即使多个文件），所以先收集每个 (g,t) 的 ep_p
    let mut title_ep_p_map: HashMap<(String, String), Option<u32>> = HashMap::new();

    for entry in &unique_entries {
        let key = (entry.item.group_title.clone(), entry.item.title.clone());
        // 如果还没记录 ep_p，就记下来（后续相同 title 不覆盖）
        title_ep_p_map.entry(key).or_insert(entry.ep_p);
    }

    // 再聚合 items
    for entry in &unique_entries {
        let gt = entry.item.group_title.clone();
        let tt = entry.item.title.clone();
        let tab = entry.item.tab_name.clone();

        let ep_p = *title_ep_p_map.get(&(gt.clone(), tt.clone())).unwrap_or(&None);
        let title_key = (tt, ep_p);

        groups
            .entry(gt)
            .or_default()
            .entry(title_key)
            .or_default()
            .entry(tab)
            .or_default()
            .push(entry.item.clone());
    }

    /* 转输出结构 */
/* 转输出结构 */
/* 转输出结构 */
let mut tree: Vec<GroupNode> = groups
    .into_iter()
    .map(|(gt, titles_map)| {
        let mut titles: Vec<TitleNode> = titles_map
            .into_iter()
            .map(|((name, p), tabs_map)| {
                let mut tabs: Vec<TabNode> = tabs_map
                    .into_iter()
                    .map(|(tab, items)| TabNode { name: tab, items })
                    .collect();

                tabs.sort_by(|a, b| {
                    let pa = a.items.first().map_or(0, |item| item.p);
                    let pb = b.items.first().map_or(0, |item| item.p);
                    pa.cmp(&pb)
                });

                TitleNode { name, p, tabs }
            })
            .collect();

        titles.sort_by(|a, b| {
            match (a.p, b.p) {
                (Some(pa), Some(pb)) => pa.cmp(&pb),
                (Some(_), None) => std::cmp::Ordering::Less,
                (None, Some(_)) => std::cmp::Ordering::Greater,
                (None, None) => a.name.cmp(&b.name),
            }
        });

        GroupNode { name: gt, titles }
    })
    .collect();

// === 新增：顶层 group 按 group_title 字母序排序 ===
tree.sort_by(|a, b| a.name.cmp(&b.name));
    // 写文件
    let out = File::create("tree.json")?;
    serde_json::to_writer_pretty(out, &tree)?;
    eprintln!("🎉 tree.json 已写入（{} 个顶层 group）", tree.len());
    Ok(())
}
