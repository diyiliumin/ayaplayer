package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/godbus/dbus/v5"
	"github.com/gorilla/websocket"
)

//go:embed static/*
var staticFS embed.FS

// ============================================
// 状态
// ============================================
type PlayerState struct {
	PID      int    `json:"pid"`
	Title    string `json:"title"`
	Cover    string `json:"cover"`
	SongLeft int    `json:"songleft"`
	Paused   bool   `json:"paused"`
	Updated  int64  `json:"updated"`
}

var (
	state     = PlayerState{Title: "等待播放...", Updated: time.Now().Unix()}
	stateMu   sync.RWMutex
	clients   = make(map[*websocket.Conn]bool)
	clientsMu sync.RWMutex
	broadcast = make(chan []byte, 100)
	upgrader  = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}
	dbusConn *dbus.Conn
)

// ============================================
// WebSocket 广播
// ============================================
func broadcaster() {
	for msg := range broadcast {
		clientsMu.RLock()
		for client := range clients {
			err := client.WriteMessage(websocket.TextMessage, msg)
			if err != nil {
				client.Close()
				delete(clients, client)
			}
		}
		clientsMu.RUnlock()
	}
}

func pushState() {
	stateMu.RLock()
	data, _ := json.Marshal(state)
	stateMu.RUnlock()
	select {
	case broadcast <- data:
	default:
	}
}

// ============================================
// DBus 监听
// ============================================
func initDBus() {
	var err error
	dbusConn, err = dbus.SessionBus()
	if err != nil {
		log.Fatal("DBus 连接失败:", err)
	}

	err = dbusConn.AddMatchSignal(
		dbus.WithMatchInterface("com.ayaplayer.Interface"),
		dbus.WithMatchMember("StatusChanged"),
		dbus.WithMatchObjectPath("/com/ayaplayer/Status"),
	)
	if err != nil {
		log.Fatal("AddMatchSignal 失败:", err)
	}

	c := make(chan *dbus.Signal, 10)
	dbusConn.Signal(c)

	go func() {
		for sig := range c {
			if sig.Name != "com.ayaplayer.Interface.StatusChanged" {
				continue
			}
			handleStatusSignal(sig.Body)
		}
	}()

	log.Println("📡 已连接 DBus，监听 StatusChanged")
}

// sig.Body 类型是 []interface{}
func handleStatusSignal(body []interface{}) {
	defer func() {
		if r := recover(); r != nil {
			log.Println("解析信号失败:", r)
		}
	}()

	if len(body) < 5 {
		log.Printf("⚠️ 信号参数不足: %d", len(body))
		return
	}

	// 类型断言（dbus 传的是 int32 / string / bool）
	pid, _ := body[0].(int32)
	title, _ := body[1].(string)
	cover, _ := body[2].(string)
	songleft, _ := body[3].(int32)
	paused, _ := body[4].(bool)

	stateMu.Lock()
	state.PID = int(pid)
	state.Title = title
	state.Cover = cover
	state.SongLeft = int(songleft)
	state.Paused = paused
	state.Updated = time.Now().Unix()
	stateMu.Unlock()

	t := title
	if t == "" {
		t = "(无标题)"
	}
	log.Printf("🎵 %s  [剩余 %d 次]  暂停=%v", t, songleft, paused)

	pushState()
}

// ============================================
// DBus 控制信号发送
// ============================================
func sendControl(action, data string) error {
	if dbusConn == nil {
		return fmt.Errorf("DBus 未连接")
	}
	return dbusConn.Emit(
		"/com/ayaplayer/Control",
		"com.ayaplayer.Interface.Control",
		action,
		data,
	)
}

// ============================================
// WebSocket 处理
// ============================================
func handleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("升级失败:", err)
		return
	}
	defer conn.Close()

	clientsMu.Lock()
	clients[conn] = true
	total := len(clients)
	clientsMu.Unlock()
	log.Printf("🖥️  客户端连接 (%s)  总数: %d", r.RemoteAddr, total)

	// 推送当前状态
	stateMu.RLock()
	initial, _ := json.Marshal(state)
	stateMu.RUnlock()
	conn.WriteMessage(websocket.TextMessage, initial)

	// 读取客户端命令
	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			clientsMu.Lock()
			delete(clients, conn)
			total := len(clients)
			clientsMu.Unlock()
			log.Printf("🔌 客户端断开  总数: %d", total)
			break
		}

		var cmd struct {
			Action string `json:"action"`
			Data   string `json:"data"`
		}
		if err := json.Unmarshal(msg, &cmd); err != nil {
			continue
		}

		log.Printf("📥 控制: %s | %s", cmd.Action, cmd.Data)
		if err := sendControl(cmd.Action, cmd.Data); err != nil {
			log.Println("发送失败:", err)
		}
	}
}

// ============================================
// 封面代理
// ============================================
func handleCover(w http.ResponseWriter, r *http.Request) {
	stateMu.RLock()
	cover := state.Cover
	stateMu.RUnlock()

	if cover == "" {
		http.NotFound(w, r)
		return
	}

	// HTTP URL
	if strings.HasPrefix(cover, "http://") || strings.HasPrefix(cover, "https://") {
		client := &http.Client{Timeout: 5 * time.Second}
		req, err := http.NewRequest("GET", cover, nil)
		if err != nil {
			http.Error(w, err.Error(), 502)
			return
		}
		// B站防盗链
		req.Header.Set("Referer", "https://www.bilibili.com/")
		req.Header.Set("User-Agent", "Mozilla/5.0")

		resp, err := client.Do(req)
		if err != nil {
			http.Error(w, err.Error(), 502)
			return
		}
		defer resp.Body.Close()

		ct := resp.Header.Get("Content-Type")
		if ct == "" {
			ct = "image/jpeg"
		}
		w.Header().Set("Content-Type", ct)
		w.Header().Set("Cache-Control", "public, max-age=3600")
		io.Copy(w, resp.Body)
		return
	}

	// 本地文件
	if _, err := os.Stat(cover); err == nil {
		http.ServeFile(w, r, cover)
		return
	}

	http.NotFound(w, r)
}

// ============================================
// 静态文件
// ============================================
func handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}

	data, err := staticFS.ReadFile("static/index.html")
	if err != nil {
		http.Error(w, "not found", 404)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write(data)
}

// ============================================
// 主函数
// ============================================
func main() {
	initDBus()
	go broadcaster()

	http.HandleFunc("/", handleIndex)
	http.HandleFunc("/ws", handleWS)
	http.HandleFunc("/cover", handleCover)
	http.Handle("/static/", http.FileServer(http.FS(staticFS)))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8088"
	}

	hostname, _ := os.Hostname()
	log.Printf("🚀 启动: http://localhost:%s  (host: %s)", port, hostname)
	log.Printf("📁 工作目录: %s", mustAbs("."))

	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatal(err)
	}
}

func mustAbs(p string) string {
	abs, _ := filepath.Abs(p)
	return abs
}
