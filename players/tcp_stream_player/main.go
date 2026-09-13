package main

import (
	"flag"
	"io"
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

// broadcaster fans the incoming audio bytes out to every connected client,
// spooling to disk so a late-joining client still receives the bytes it missed
// (e.g. the container header a decoder needs).
type broadcaster struct {
	mu        sync.Mutex
	clients   map[chan []byte]struct{}
	spool     *os.File
	spoolSize int64
	closed    bool
}

func newBroadcaster() (*broadcaster, error) {
	f, err := os.CreateTemp("", "tcp_stream_player_*.spool")
	if err != nil {
		return nil, err
	}
	return &broadcaster{clients: make(map[chan []byte]struct{}), spool: f}, nil
}

func (b *broadcaster) push(data []byte) {
	if len(data) == 0 {
		return
	}
	b.mu.Lock()
	if _, err := b.spool.Write(data); err == nil {
		b.spoolSize += int64(len(data))
	}
	for ch := range b.clients {
		select {
		case ch <- data:
		default:
			// slow client: drop the chunk rather than block the source
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

func (b *broadcaster) cleanup() {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.spool != nil {
		name := b.spool.Name()
		_ = b.spool.Close()
		_ = os.Remove(name)
		b.spool = nil
	}
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

		// Atomically snapshot the spool and register for live chunks so a
		// late joiner still gets the header bytes without duplicating chunks.
		b.mu.Lock()
		size := b.spoolSize
		spoolName := b.spool.Name()
		closed := b.closed
		ch := make(chan []byte, 256)
		b.clients[ch] = struct{}{}
		b.mu.Unlock()
		defer func() {
			b.mu.Lock()
			delete(b.clients, ch)
			b.mu.Unlock()
		}()

		if size > 0 {
			if f, err := os.Open(spoolName); err == nil {
				_, _ = io.CopyN(w, f, size)
				_ = f.Close()
				flusher.Flush()
			}
		}

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
	} else {
		return
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
	contentType := flag.String("type", envOr("TCP_STREAM_TYPE", "audio/mpeg"), "Content-Type of the stream")
	open := flag.Bool("open", false, "open the page in a browser on start")
	flag.Parse()

	b, err := newBroadcaster()
	if err != nil {
		log.Fatal(err)
	}
	defer b.cleanup()

	mux := http.NewServeMux()
	mux.HandleFunc("/", serveIndex)
	mux.HandleFunc("/stream", b.streamHandler(*contentType))

	server := &http.Server{Handler: mux}
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatalf("listen %s: %v", *listen, err)
	}
	url := listenURL(*listen)

	// Receive bytes from stdin and fan them out to connected clients.
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

	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig
		b.closeStream()
		_ = server.Close()
	}()

	log.Printf("ayaplayer tcp_stream_player listening on %s", url)
	log.Printf("audio stream: %s/stream", url)

	if *open {
		go openBrowser(url)
	}

	if err := server.Serve(ln); err != nil && err != http.ErrServerClosed {
		log.Fatalf("serve: %v", err)
	}
}
