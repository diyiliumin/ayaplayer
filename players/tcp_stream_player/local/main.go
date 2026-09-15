package main

import (
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	_ "embed"
)

//go:embed web/index.html
var indexHTML []byte

const (
	chunkSize   = 32 * 1024
	gracePeriod = 300 * time.Millisecond
)

type broadcaster struct {
	mu      sync.Mutex
	clients map[chan []byte]struct{}
	closed  bool
}

func newBroadcaster() *broadcaster {
	return &broadcaster{clients: make(map[chan []byte]struct{})}
}

func (b *broadcaster) push(data []byte) {
	if len(data) == 0 {
		return
	}
	b.mu.Lock()
	for ch := range b.clients {
		select {
		case ch <- data:
		default:
			// 慢客户端：丢弃而不是阻塞源
		}
	}
	b.mu.Unlock()
}

func (b *broadcaster) closeStream() {
	b.mu.Lock()
	if !b.closed {
		b.closed = true
		for ch := range b.clients {
			close(ch)
		}
		b.clients = make(map[chan []byte]struct{})
	}
	b.mu.Unlock()
}

func (b *broadcaster) streamHandler(contentType string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming unsupported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", contentType)
		w.Header().Set("Cache-Control", "no-cache, no-store")
		w.Header().Set("Access-Control-Allow-Origin", "*")

		b.mu.Lock()
		closed := b.closed
		ch := make(chan []byte, 256)
		if !closed {
			b.clients[ch] = struct{}{}
		}
		b.mu.Unlock()

		defer func() {
			b.mu.Lock()
			delete(b.clients, ch)
			b.mu.Unlock()
		}()

		if closed {
			return
		}

		for data := range ch {
			if _, err := w.Write(data); err != nil {
				return
			}
			flusher.Flush()
		}
	}
}

func serveIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" && r.URL.Path != "/index.html" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write(indexHTML)
}

func listenURL(listen string) string {
	if strings.HasPrefix(listen, ":") {
		return "http://127.0.0.1" + listen
	}
	if strings.HasPrefix(listen, "http://") || strings.HasPrefix(listen, "https://") {
		return listen
	}
	return "http://" + listen
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	if _, err := exec.LookPath("xdg-open"); err == nil {
		cmd = exec.Command("xdg-open", url)
	} else if _, err := exec.LookPath("firefox"); err == nil {
		cmd = exec.Command("firefox", url)
	}
	_ = cmd.Start()
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	listen := flag.String("listen", envOr("TCP_STREAM_LISTEN", ":8080"), "listen address")
	contentType := flag.String("type", envOr("TCP_STREAM_TYPE", "video/mp2t"), "Content-Type of the stream")
	open := flag.Bool("open", false, "open the page in a browser on start")
	flag.Parse()

	b := newBroadcaster()

	mux := http.NewServeMux()
	mux.HandleFunc("/", serveIndex)
	mux.HandleFunc("/stream", b.streamHandler(*contentType))

	server := &http.Server{Handler: mux}
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatalf("listen %s: %v", *listen, err)
	}
	url := listenURL(*listen)

	// 从 stdin 读，广播
	go func() {
		buf := make([]byte, chunkSize)
		for {
			n, err := os.Stdin.Read(buf)
			if n > 0 {
				data := make([]byte, n)
				copy(data, buf[:n])
				b.push(data)
			}
			if err != nil {
				break
			}
		}
		b.closeStream()
		time.Sleep(gracePeriod)
		_ = server.Close()
	}()

	// 信号处理
	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig
		b.closeStream()
		_ = server.Close()
	}()

	log.Printf("ayaplayer tcp_stream_player listening on %s", url)
	log.Printf("stream: %s/stream", url)

	if *open {
		go openBrowser(url)
	}

	if err := server.Serve(ln); err != nil && err != http.ErrServerClosed {
		log.Fatalf("serve: %v", err)
	}
}
