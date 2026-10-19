package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"  // ← 添加这行
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

// ========== 常量 ==========
const (
	TreeJSONPath = "./tree.json"
	GatewayPath  = "../../../../gateway/gateway.sh"
	EasyEditPath = "../../easy_edit.sh"
)

// 在文件开头加一个全局 logger
var debugFile *os.File

func init() {
	var err error
	debugFile, err = os.OpenFile("/tmp/bubble_debug.log",
		os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Fatal(err)
	}
}

func debugLog(format string, args ...interface{}) {
	timestamp := time.Now().Format("15:04:05.000")
	msg := fmt.Sprintf("[%s] %s\n", timestamp, fmt.Sprintf(format, args...))
	debugFile.WriteString(msg)
	debugFile.Sync()
}

type buildFinishedMsg struct{ err error }
type playFinishedMsg struct {
	count int
	total int
	err   error
}

// ========== 数据结构 ==========
type Item struct {
	Title  string `json:"title"`
	CID    uint64 `json:"cid"`
	BVID   string `json:"bvid"`
	Cover  string `json:"pic"`
	Scheme string `json:"scheme"`
	P      uint32 `json:"p"`
}

type TitleNode struct {
	Name  string `json:"name"`
	P     *uint32
	Items []Item
	Open  bool
}

// ===== 播放项结构 =====
type PlaylistItem struct {
	Title    string `json:"title"`
	Group    string `json:"group"`
	Category string `json:"category"`
	CID      uint64 `json:"cid"`
	BVID     string `json:"bvid"`
	Scheme   string `json:"scheme"`
	Cover    string `json:"pic"`
	P        uint32 `json:"p"`
}

type editorFinishedMsg struct {
	err error
}

type GroupNode struct {
	Name   string      `json:"name"`
	Titles []TitleNode `json:"titles"`
	Open   bool
}

type buildLineMsg string

type buildDoneMsg struct {
	output string
	err    error
}

type buildStreamMsg struct {
	ch <-chan tea.Msg
}

type NodeType int

const (
	NodeGroup NodeType = iota
	NodeTitle
	NodeItem
)

type TreeNode struct {
	Type     NodeType
	Depth    int
	Name     string
	CID      uint64
	BVID     string
	Scheme   string
	Cover    string
	P        uint32
	Expanded bool
	groupIdx int
	titleIdx int
	items    []Item
}

func (n TreeNode) Display() string {
	indent := strings.Repeat("  ", n.Depth)
	marker := " "
	if n.Type == NodeGroup || n.Type == NodeTitle {
		if n.Expanded {
			marker = "▼"
		} else {
			marker = "▶"
		}
	}
	return fmt.Sprintf("%s%s %s", indent, marker, n.Name)
}

// ========== 加载 tree.json ==========
func loadTree() []GroupNode {
	data, err := os.ReadFile(TreeJSONPath)
	if err != nil {
		log.Fatal("❌ 无法读取 tree.json")
	}

	var rawGroups []struct {
		Name   string `json:"name"`
		Titles []struct {
			Name string `json:"name"`
			P    *uint32
			Tabs []struct {
				Name  string `json:"name"`
				Items []struct {
					BVID   string `json:"bvid"`
					CID    uint64 `json:"cid"`
					Cover  string `json:"pic"`
					Scheme string `json:"scheme"`
					P      uint32 `json:"p"`
				} `json:"items"`
			} `json:"tabs"`
		} `json:"titles"`
	}
	if err := json.Unmarshal(data, &rawGroups); err != nil {
		log.Fatal("❌ 解析 tree.json 失败:", err)
	}

	var groups []GroupNode
	for _, rg := range rawGroups {
		var titles []TitleNode
		for _, rt := range rg.Titles {
			var items []Item
			for _, tab := range rt.Tabs {
				if len(tab.Items) > 0 {
					items = append(items, Item{
						Title:  tab.Name,
						CID:    tab.Items[0].CID,
						BVID:   tab.Items[0].BVID,
						Cover:  tab.Items[0].Cover,
						Scheme: tab.Items[0].Scheme,
						P:      tab.Items[0].P,
					})
				}
			}
			titles = append(titles, TitleNode{
				Name:  rt.Name,
				P:     rt.P,
				Items: items,
				Open:  false,
			})
		}
		groups = append(groups, GroupNode{
			Name:   rg.Name,
			Titles: titles,
			Open:   false,
		})
	}
	return groups
}

func (m model) Init() tea.Cmd {
	return nil
}

// ========== 核心函数：执行命令并流式输出 ==========

func readNextFromChannel(ch <-chan tea.Msg) tea.Cmd {
	return func() tea.Msg {
		msg, ok := <-ch
		if !ok {
			return buildDoneMsg{err: nil}
		}
		return msg
	}
}

func buildTreeCmd() tea.Cmd {
	return func() tea.Msg {
		cmd := exec.Command("stdbuf", "-oL", "-eL", "sh", "-c", "./build")

		stdout, err := cmd.StdoutPipe()
		if err != nil {
			return buildDoneMsg{err: err}
		}

		stderr, err := cmd.StderrPipe()
		if err != nil {
			return buildDoneMsg{err: err}
		}

		if err := cmd.Start(); err != nil {
			return buildDoneMsg{err: err}
		}

		ch := make(chan tea.Msg, 100)

		go func() {
			scanner := bufio.NewScanner(stdout)
			for scanner.Scan() {
				ch <- buildLineMsg(scanner.Text())
			}
		}()

		go func() {
			scanner := bufio.NewScanner(stderr)
			for scanner.Scan() {
				ch <- buildLineMsg("[ERR] " + scanner.Text())
			}
		}()

		go func() {
			err := cmd.Wait()
			ch <- buildDoneMsg{err: err}
			close(ch)
		}()

		return buildStreamMsg{ch: ch}
	}
}

// ========== 播放模式 ==========
type PlayMode int

const (
	PlayModeSequential PlayMode = iota
	PlayModeShuffle
)

func (p PlayMode) String() string {
	switch p {
	case PlayModeSequential:
		return "顺序"
	case PlayModeShuffle:
		return "随机"
	default:
		return "未知"
	}
}

// ========== 播放逻辑 ==========
func playCIDs(items []PlaylistItem, mode PlayMode, addmod AddMode) tea.Cmd {
	return func() tea.Msg {
		// 1. 复制列表
		list := make([]PlaylistItem, len(items))
		copy(list, items)

		// 2. 随机模式
		if mode == PlayModeShuffle {
			rand.Shuffle(len(list), func(i, j int) {
				list[i], list[j] = list[j], list[i]
			})
		}

		// 3. 序列化成多行 JSON
		var lines []string
		for _, item := range list {
			jsonBytes, err := json.Marshal(item)
			if err != nil {
				return playFinishedMsg{err: err}
			}
			lines = append(lines, string(jsonBytes))
		}

		// 4. 根据 addmod 选择 push 或 append
		content := strings.Join(lines, "\n")
		//
		// var gatewayCmd string
		// switch addmod {
		// case "i": // 插到顶部（push）
		// 	gatewayCmd = "push"
		// case "a": // 追加到末尾（append）
		// 	gatewayCmd = "append"
		// default:
		// 	gatewayCmd = "push" // 默认 push
		// }

		gatewayCmd := addmod.Command()
		cmd := exec.Command(GatewayPath, gatewayCmd, content)
		if output, err := cmd.CombinedOutput(); err != nil {
			return playFinishedMsg{
				err: fmt.Errorf("%s 失败: %v, 输出: %s", gatewayCmd, err, string(output)),
			}
		}

		// 5. 统计
		count := len(list)
		total := 0
		countCmd := exec.Command(GatewayPath, "count")
		if output, err := countCmd.Output(); err == nil {
			fmt.Sscanf(strings.TrimSpace(string(output)), "%d", &total)
		}

		return playFinishedMsg{
			count: count,
			total: total,
		}
	}
}

func expRandom(scale float64) int {
	digitCount := rand.Intn(6) + 1
	min := int(math.Pow10(digitCount - 1))
	max := int(math.Pow10(digitCount)) - 1
	if digitCount == 1 {
		min = 1
	}
	return rand.Intn(max-min+1) + min
}

func countTotalLines(filename string) int {
	file, err := os.Open(filename)
	if err != nil {
		return 0
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	count := 0
	for scanner.Scan() {
		count++
	}
	return count
}

// ========== 状态 ==========
type state int

const (
	StateBuildPrompt state = iota
	StateBuilding
	StateTUI
	StateSearchInput
)
// ========== 添加模式 ==========
type AddMode int

const (
	AddModeAppend AddMode = iota // 追加末尾
	AddModePush                  // 插入顶部
)

func (a AddMode) String() string {
	switch a {
	case AddModePush:
		return "顶部插入"
	case AddModeAppend:
		return "末尾追加"
	default:
		return "未知"
	}
}

func (a AddMode) Command() string {
	switch a {
	case AddModePush:
		return "push"
	case AddModeAppend:
		return "append"
	default:
		return "push"
	}
}

// ========== Model ==========
type model struct {
	state        state
	groups       []GroupNode
	visibleNodes []TreeNode
	allNodes     []TreeNode
	cursor       int
	viewport     viewport.Model
	playMode     PlayMode
	lastAddmod AddMode // ★ 新增：最近一次添加模式（push / append）
	buildError   error

	searchInput  textinput.Model
	lastSearch   string
	lastMatchIdx int

	buildLog   string
	isBuilding bool
	status     string

	buildOutput []string
	building    bool
	done        bool
	err         error

	// ★★★ 选中模式 ★★★
	selecting    bool  // 是否在选中模式
	selectStart  int   // 选中起点
	selectEnd    int   // 选中终点（光标位置）

	// ★★★ vim 风格按键 ★★★
	pendingG   bool   // 按了 g，等下一个 g
	pendingNum string // 累积数字（如 "10"）

	ch <-chan tea.Msg
}

func newModel() model {
	ti := textinput.New()
	ti.Placeholder = "输入关键词..."
	ti.Focus()

	m := model{
		playMode:     PlayModeSequential,
		lastMatchIdx: -1,
		searchInput:  ti,
	}
	if _, err := os.Stat(TreeJSONPath); err == nil {
		m.state = StateTUI
		m.groups = loadTree()
		m.rebuildAllNodes()
		m.rebuildVisible()
		m.initViewport()
	} else {
		m.state = StateBuildPrompt
	}
	return m
}

func (m *model) initViewport() {
	width, height, _ := getTerminalSize()
	v := viewport.New(width, height-3)
	m.viewport = v
}

func (m *model) rebuildAllNodes() {
	var nodes []TreeNode
	for gi, g := range m.groups {
		var groupItems []Item
		for _, t := range g.Titles {
			groupItems = append(groupItems, t.Items...)
		}
		nodes = append(nodes, TreeNode{
			Type:     NodeGroup,
			Depth:    0,
			Name:     g.Name,
			groupIdx: gi,
			items:    groupItems,
		})
		for ti, t := range g.Titles {
			nodes = append(nodes, TreeNode{
				Type:     NodeTitle,
				Depth:    1,
				Name:     t.Name,
				groupIdx: gi,
				titleIdx: ti,
				items:    t.Items,
			})
			for _, item := range t.Items {
				nodes = append(nodes, TreeNode{
					Type:     NodeItem,
					Depth:    2,
					Name:     item.Title,
					CID:      item.CID,
					BVID:     item.BVID,
					Scheme:   item.Scheme,
					Cover:    item.Cover,
					P:        item.P,
					groupIdx: gi,
					titleIdx: ti,
				})
			}
		}
	}
	m.allNodes = nodes
}

func (m *model) rebuildVisible() {
	var nodes []TreeNode
	for gi, g := range m.groups {
		var groupItems []Item
		for _, t := range g.Titles {
			groupItems = append(groupItems, t.Items...)
		}
		nodes = append(nodes, TreeNode{
			Type:     NodeGroup,
			Depth:    0,
			Name:     g.Name,
			Expanded: g.Open,
			groupIdx: gi,
			items:    groupItems,
		})
		if !g.Open {
			continue
		}
		for ti, t := range g.Titles {
			nodes = append(nodes, TreeNode{
				Type:     NodeTitle,
				Depth:    1,
				Name:     t.Name,
				Expanded: t.Open,
				groupIdx: gi,
				titleIdx: ti,
				items:    t.Items,
			})
			if !t.Open {
				continue
			}
			for _, item := range t.Items {
				nodes = append(nodes, TreeNode{
					Type:     NodeItem,
					Depth:    2,
					Name:     item.Title,
					CID:      item.CID,
					BVID:     item.BVID,
					Scheme:   item.Scheme,
					Cover:    item.Cover,
					P:        item.P,
					groupIdx: gi,
					titleIdx: ti,
				})
			}
		}
	}
	m.visibleNodes = nodes

	// ★★★ 修正 cursor，防止越界 ★★★
	if len(m.visibleNodes) == 0 {
		m.cursor = 0
	} else if m.cursor >= len(m.visibleNodes) {
		m.cursor = len(m.visibleNodes) - 1
	} else if m.cursor < 0 {
		m.cursor = 0
	}

	if m.state == StateTUI || m.state == StateSearchInput {
		m.refreshViewport()
	}
}

func (m *model) refreshViewport() {
	content := m.renderContent()
	m.viewport.SetContent(content)
	m.adjustViewport()
}
// allIndex 返回节点在 allNodes（全展开）中的下标，找不到返回 -1
func (m *model) allIndex(node TreeNode) int {
	for i, n := range m.allNodes {
		if n.Type == node.Type &&
			n.groupIdx == node.groupIdx &&
			n.titleIdx == node.titleIdx &&
			n.Name == node.Name {
			return i
		}
	}
	return -1
}

func (m *model) renderContent() string {
	if len(m.visibleNodes) == 0 {
		return "⚠️ 无数据"
	}

	// ★ 行号宽度按"全展开视图"的总行数算 ★
	total := len(m.allNodes)
	numWidth := len(fmt.Sprintf("%d", total))
	if numWidth < 2 {
		numWidth = 2
	}

	// ★ 光标所在行的绝对行号（1-based，基于 allNodes）★
	cursorAbs := 0
	if m.cursor >= 0 && m.cursor < len(m.visibleNodes) {
		if idx := m.allIndex(m.visibleNodes[m.cursor]); idx >= 0 {
			cursorAbs = idx + 1
		}
	}

	var lines []string
	for i, node := range m.visibleNodes {
		var numStr string
		if i == m.cursor {
			// ★ 当前行：绝对行号（基于全展开视图）★
			numStr = fmt.Sprintf("%*d", numWidth, cursorAbs)
		} else {
			// ★ 其他行：相对行号（按视觉顺序，即 visibleNodes 下标差）★
			diff := i - m.cursor
			if diff < 0 {
				diff = -diff
			}
			numStr = fmt.Sprintf("%*d", numWidth, diff)
		}

		line := node.Display()

		if i == m.cursor {
			line = fmt.Sprintf("\033[7m>%s %s \033[0m", numStr, line)
		} else if m.isSelected(i) {
			line = fmt.Sprintf("\033[7m %s %s \033[0m", numStr, line)
		} else {
			line = fmt.Sprintf(" %s %s", numStr, line)
		}

		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}

func (m *model) adjustViewport() {
	height := m.viewport.Height
	if height <= 0 || len(m.visibleNodes) == 0 {
		return
	}
	top := m.viewport.YOffset
	bottom := top + int(height) - 1
	if m.cursor < top {
		m.viewport.SetYOffset(m.cursor)
	} else if m.cursor > bottom {
		m.viewport.SetYOffset(m.cursor - int(height) + 1)
	}
}

// ★★★ 安全获取当前节点 ★★★
func (m *model) currentNode() (TreeNode, bool) {
	if len(m.visibleNodes) == 0 {
		return TreeNode{}, false
	}
	if m.cursor < 0 || m.cursor >= len(m.visibleNodes) {
		m.cursor = 0
	}
	return m.visibleNodes[m.cursor], true
}

func (m *model) jumpToAllNode(allIdx int) {
	if allIdx < 0 || allIdx >= len(m.allNodes) {
		return
	}
	node := m.allNodes[allIdx]

	m.groups[node.groupIdx].Open = true
	if node.Type == NodeItem || node.Type == NodeTitle {
		m.groups[node.groupIdx].Titles[node.titleIdx].Open = true
	}

	m.rebuildVisible()

	for j, vis := range m.visibleNodes {
		if vis.Type == node.Type &&
			vis.groupIdx == node.groupIdx &&
			vis.Name == node.Name &&
			(vis.Type != NodeItem || vis.titleIdx == node.titleIdx) {
			m.cursor = j
			m.refreshViewport()
			return
		}
	}
	m.cursor = 0
	m.refreshViewport()
}

func (m *model) searchAndJump(query string) {
	if query == "" {
		m.lastSearch = ""
		m.lastMatchIdx = -1
		return
	}

	lowerQuery := strings.ToLower(query)
	found := false
	for i, node := range m.allNodes {
		if strings.Contains(strings.ToLower(node.Name), lowerQuery) {
			m.lastSearch = query
			m.lastMatchIdx = i
			found = true
			m.jumpToAllNode(i)
			break
		}
	}

	if !found {
		m.lastSearch = ""
		m.lastMatchIdx = -1
	}
}

// currentAllIndex 返回当前光标节点在 allNodes 中的下标，找不到返回 -1
func (m *model) currentAllIndex() int {
	cur, ok := m.currentNode()
	if !ok {
		return -1
	}
	for i, n := range m.allNodes {
		if n.Type == cur.Type &&
			n.groupIdx == cur.groupIdx &&
			n.titleIdx == cur.titleIdx &&
			n.Name == cur.Name {
			return i
		}
	}
	return -1
}

// ★★★ 检查节点是否被选中 ★★★
func (m *model) isSelected(idx int) bool {
	if !m.selecting {
		return false
	}
	lo := m.selectStart
	hi := m.selectEnd
	if lo > hi {
		lo, hi = hi, lo
	}
	return idx >= lo && idx <= hi
}

// ★★★ 进入选中模式 ★★★
func (m *model) startSelect() {
	if len(m.visibleNodes) == 0 {
		return
	}
	m.selecting = true
	m.selectStart = m.cursor
	m.selectEnd = m.cursor
}

// ★★★ 退出选中模式 ★★★
func (m *model) cancelSelect() {
	m.selecting = false
	m.selectStart = 0
	m.selectEnd = 0
}

// ★★★ 获取选中的节点范围 ★★★
func (m *model) getSelectedNodes() (int, int) {
	lo := m.selectStart
	hi := m.selectEnd
	if lo > hi {
		lo, hi = hi, lo
	}
	return lo, hi
}

func (m model) helpView() string {
	modeStr := m.playMode.String()
	return fmt.Sprintf("\n[help] h=收起 l=展开 j/k=上下 Enter/a=追加播放列表 v=编辑播放列表 d=清空 m=切换模式(%s) q=退出 b=同步列表 /=搜索（n=next）", modeStr)
}

func (m model) LogView() string {
	lines := strings.Split(m.buildLog, "\n")
	lastLine := ""
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) != "" {
			lastLine = strings.TrimSpace(lines[i])
			break
		}
	}

	if lastLine == "" {
		lastLine = "就绪"
	}

	return fmt.Sprintf("\n\n[log] %s", lastLine)
}

func getTerminalSize() (int, int, error) {
	fd := int(os.Stdout.Fd())

	var sz struct {
		Row    uint16
		Col    uint16
		Xpixel uint16
		Ypixel uint16
	}

	_, _, err := syscall.Syscall(
		syscall.SYS_IOCTL,
		uintptr(fd),
		uintptr(syscall.TIOCGWINSZ),
		uintptr(unsafe.Pointer(&sz)),
	)

	if err != 0 {
		return 0, 0, fmt.Errorf("获取终端大小失败: %v", err)
	}

	return int(sz.Col), int(sz.Row), nil
}

func getBuildPath() (string, error) {
	cmd := exec.Command("./build", "-s")
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("执行 ./build -s 失败: %v", err)
	}

	path := strings.TrimSpace(string(output))
	if path == "" {
		return "", fmt.Errorf("provider 没有返回路径")
	}

	return path, nil
}

// ===== 打开编辑器命令 =====
// 打开编辑器命令 - 带参数
func openEditorCmd(filePath ...string) tea.Cmd {
    cmd_gateway := exec.Command("../../../../gateway/gateway.sh", "source")
    output, _ := cmd_gateway.Output()

    path := strings.TrimSpace(string(output))
    if len(filePath) > 0 && filePath[0] != "" {
        path = filePath[0]
    }

    editor := os.Getenv("EDITOR")
    if editor == "" {
        if _, err := exec.LookPath("nvim"); err == nil {
            editor = "nvim"
        } else if _, err := exec.LookPath("vim"); err == nil {
            editor = "vim"
        } else {
            return func() tea.Msg {
                return editorFinishedMsg{err: fmt.Errorf("未设置 $EDITOR，且找不到 nvim/vim")}
            }
        }
    } else {
        // 检查命令是否存在
        parts := strings.Fields(editor)
        if len(parts) > 0 {
            if _, err := exec.LookPath(parts[0]); err != nil {
                return func() tea.Msg {
                    return editorFinishedMsg{err: fmt.Errorf("$EDITOR 指向的命令不存在: %s", parts[0])}
                }
            }
        }
    }

    // 用 sh -c 执行，支持 $EDITOR 带参数
    cmd := exec.Command("sh", "-c", fmt.Sprintf("%s %q", editor, path))

    cmd.Stdin = os.Stdin
    cmd.Stdout = os.Stdout
    cmd.Stderr = os.Stderr

    return tea.ExecProcess(cmd, func(err error) tea.Msg {
        return editorFinishedMsg{err: err}
    })
}

// ===== 打开编辑器命令 =====
func easyedit(filePath ...string) tea.Cmd {
	easyeditPath := EasyEditPath

	// 如果传了参数，用参数
	if len(filePath) > 0 && filePath[0] != "" {
		easyeditPath = filePath[0]
	}

	// 解析为绝对路径
	abs, err := filepath.Abs(easyeditPath)
	if err != nil {
		abs = easyeditPath
	}

	if _, err := os.Stat(abs); err != nil {
		return func() tea.Msg {
			return editorFinishedMsg{err: fmt.Errorf("找不到 easyedit: %s", abs)}
		}
	}

	// 确保可执行
	os.Chmod(abs, 0755)

	cmd := exec.Command(abs)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return tea.ExecProcess(cmd, func(err error) tea.Msg {
		return editorFinishedMsg{err: err}
	})
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case buildStreamMsg:
		m.ch = msg.ch
		m.isBuilding = true
		return m, readNextFromChannel(msg.ch)

	case buildLineMsg:
		m.buildLog += string(msg) + "\n"

		if m.ch != nil {
			return m, tea.Sequence(
				func() tea.Msg { return nil },
				readNextFromChannel(m.ch),
			)
		}
		return m, nil

	case editorFinishedMsg:
		m.buildLog += "✅ exit editor\n"
		return m, nil

	case buildDoneMsg:
		m.isBuilding = false

		if msg.err != nil {
			m.status = "❌ 构建失败"
			m.buildLog += fmt.Sprintf("❌ 错误: %v\n", msg.err)
		} else {
			m.status = "✅ 构建成功"
		}

		if msg.output != "" {
			m.buildLog += msg.output
		}
		m.groups = loadTree()
		m.rebuildAllNodes()
		m.rebuildVisible()
		m.initViewport()
		m.state = StateTUI
		m.refreshViewport()
		return m, nil

	case playFinishedMsg:
		if msg.err != nil {
			m.status = fmt.Sprintf("❌ 写入播放列表失败: %v", msg.err)
			m.buildLog += fmt.Sprintf("❌ 写入播放列表失败: %v\n", msg.err)
		} else {
			m.status = fmt.Sprintf("✅ %s%s了 %d 个 CID（总数: %d）", m.playMode.String(),m.lastAddmod.String(), msg.count, msg.total)
			m.buildLog += fmt.Sprintf("📋 %s%s了 %d 个 CID 到播放列表（总数: %d）\n", m.playMode.String(), m.lastAddmod.String(), msg.count, msg.total)
		}
		return m, nil

	case buildFinishedMsg:
		if msg.err != nil {
			m.buildError = msg.err
			m.state = StateBuildPrompt
			return m, nil
		}
		_ = syscall.Exec(os.Args[0], os.Args, os.Environ())
		return m, nil

	case tea.KeyMsg:
		// ★★★ 重置 vim 状态（除非按的是 g/G/j/k/数字）★★★
		keyStr := msg.String()
		if keyStr != "g" && keyStr != "G" && keyStr != "j" && keyStr != "k" &&
		!(len(keyStr) == 1 && keyStr >= "0" && keyStr <= "9") {
			m.pendingG = false
			m.pendingNum = ""
		}

		switch m.state {
		case StateBuildPrompt:
			switch msg.String() {
			case "b", "B":
				m.state = StateTUI
				m.isBuilding = true
				m.status = "⏳ 构建中..."
				m.buildLog = "🚀 开始构建...\n"
				return m, buildTreeCmd()
			case "q", "ctrl+c":
				return m, tea.Quit
			}

		case StateSearchInput:
			var cmd tea.Cmd
			m.searchInput, cmd = m.searchInput.Update(msg)
			switch key := msg.String(); key {
			case "enter":
				query := m.searchInput.Value()
				m.searchAndJump(query)
				m.state = StateTUI
				m.searchInput.Blur()
				return m, nil
			case "esc":
				m.state = StateTUI
				m.searchInput.Blur()
				return m, nil
			}
			return m, cmd

		case StateTUI:
			// ★★★ 选中模式下，j/k 移动光标，V/Enter/Esc 退出 ★★★

			if m.selecting {
				switch msg.String() {
				case "j":
					if m.pendingNum != "" {
						n, err := strconv.Atoi(m.pendingNum)
						if err != nil || n <= 0 {
							n = 1
						}
						m.pendingNum = ""
						m.pendingG = false
						m.cursor += n
						if m.cursor >= len(m.visibleNodes) {
							m.cursor = len(m.visibleNodes) - 1
						}
						m.selectEnd = m.cursor
						m.refreshViewport()
						return m, nil
					}
					m.pendingG = false
					if m.cursor < len(m.visibleNodes)-1 {
						m.cursor++
						m.selectEnd = m.cursor
						m.refreshViewport()
					}

				case "k":
					if m.pendingNum != "" {
						n, err := strconv.Atoi(m.pendingNum)
						if err != nil || n <= 0 {
							n = 1
						}
						m.pendingNum = ""
						m.pendingG = false
						m.cursor -= n
						if m.cursor < 0 {
							m.cursor = 0
						}
						m.selectEnd = m.cursor
						m.refreshViewport()
						return m, nil
					}
					m.pendingG = false
					if m.cursor > 0 {
						m.cursor--
						m.selectEnd = m.cursor
						m.refreshViewport()
					}
				case "V":
					m.cancelSelect()
					m.refreshViewport()

				case "o":
					m.selectStart, m.selectEnd = m.selectEnd, m.selectStart
					m.cursor = m.selectEnd
					m.refreshViewport()

				case "esc":
					m.cancelSelect()
					m.refreshViewport()

				case "g":
					if m.pendingG {
						if m.pendingNum != "" {
							// Ngg：全展开第 N 行
							n, err := strconv.Atoi(m.pendingNum)
							if err != nil || n <= 0 {
								n = 1
							}
							m.pendingNum = ""
							m.pendingG = false
							target := n - 1
							if target >= len(m.allNodes) {
								target = len(m.allNodes) - 1
							}
							m.jumpToAllNode(target)
							m.selectEnd = m.cursor
							m.refreshViewport()
						} else {
							// gg：第一行
							m.pendingG = false
							m.jumpToAllNode(0)
							m.selectEnd = m.cursor
							m.refreshViewport()
						}
					} else {
						m.pendingG = true
					}

				case "G":
					if m.pendingNum != "" {
						// NG：全展开第 N 行
						n, err := strconv.Atoi(m.pendingNum)
						if err != nil || n <= 0 {
							n = 1
						}
						m.pendingNum = ""
						m.pendingG = false
						target := n - 1
						if target >= len(m.allNodes) {
							target = len(m.allNodes) - 1
						}
						m.jumpToAllNode(target)
						m.selectEnd = m.cursor
						m.refreshViewport()
						return m, nil
					}
					// 无数字：全展开最后一行
					m.pendingG = false
					m.jumpToAllNode(len(m.allNodes) - 1)
					m.selectEnd = m.cursor
					m.refreshViewport()

				case "1", "2", "3", "4", "5", "6", "7", "8", "9", "0":
					m.pendingNum += msg.String()
					m.pendingG = false
					return m, nil

				case "enter", "a", "i":
					lo, hi := m.getSelectedNodes()
					var items []PlaylistItem

					for i := lo; i <= hi; i++ {
						if i >= len(m.visibleNodes) {
							break
						}
						node := m.visibleNodes[i]

						if node.Type == NodeItem {
							items = append(items, PlaylistItem{
								CID:      node.CID,
								BVID:     node.BVID,
								Scheme:   node.Scheme,
								Cover:    node.Cover,
								P:        node.P,
								Title:    node.Name,
								Group:    m.groups[node.groupIdx].Name,
								Category: m.groups[node.groupIdx].Titles[node.titleIdx].Name,
							})
						} else if node.Type == NodeTitle {
							title := &m.groups[node.groupIdx].Titles[node.titleIdx]
							for _, item := range title.Items {
								items = append(items, PlaylistItem{
									CID:      item.CID,
									BVID:     item.BVID,
									Scheme:   item.Scheme,
									Cover:    item.Cover,
									P:        item.P,
									Title:    item.Title,
									Group:    m.groups[node.groupIdx].Name,
									Category: title.Name,
								})
							}
						} else if node.Type == NodeGroup {
							group := &m.groups[node.groupIdx]
							for _, title := range group.Titles {
								for _, item := range title.Items {
									items = append(items, PlaylistItem{
										CID:      item.CID,
										BVID:     item.BVID,
										Scheme:   item.Scheme,
										Cover:    item.Cover,
										Title:    item.Title,
										P:        item.P,
										Group:    group.Name,
										Category: title.Name,
									})
								}
							}
						}
					}

					m.cancelSelect()
					m.lastSearch = ""
					m.lastMatchIdx = -1
					if len(items) > 0 {
						addmod := AddModeAppend
						if  msg.String() == "i" {
							addmod = AddModePush
						}
						m.lastAddmod = addmod // ★ 记录
						return m, playCIDs(items, m.playMode, addmod)
					}
					m.cancelSelect()
					m.refreshViewport()
					return m, nil

				case "q", "ctrl+c":
					m.cancelSelect()
					m.refreshViewport()
				case "l":
					node, ok := m.currentNode()
					if !ok {
						break
					}
					if node.Type == NodeGroup {
						m.groups[node.groupIdx].Open = true
						m.rebuildVisible()
					} else if node.Type == NodeTitle {
						m.groups[node.groupIdx].Titles[node.titleIdx].Open = true
						m.rebuildVisible()
					}
				case "h":
					if len(m.visibleNodes) == 0 {
						break
					}
					curr := m.visibleNodes[m.cursor]

					var targetGroupIdx, targetTitleIdx *int
					var targetType NodeType
					foundTarget := false

					switch curr.Type {
					case NodeGroup:
						if m.groups[curr.groupIdx].Open {
							m.groups[curr.groupIdx].Open = false
							targetType = NodeGroup
							gi := curr.groupIdx
							targetGroupIdx = &gi
							foundTarget = true
						}
					case NodeTitle:
						if m.groups[curr.groupIdx].Titles[curr.titleIdx].Open {
							m.groups[curr.groupIdx].Titles[curr.titleIdx].Open = false
							targetType = NodeTitle
							gi, ti := curr.groupIdx, curr.titleIdx
							targetGroupIdx = &gi
							targetTitleIdx = &ti
							foundTarget = true
						} else {
							m.groups[curr.groupIdx].Open = false
							targetType = NodeGroup
							gi := curr.groupIdx
							targetGroupIdx = &gi
							foundTarget = true
						}
					case NodeItem:
						title := &m.groups[curr.groupIdx].Titles[curr.titleIdx]
						group := &m.groups[curr.groupIdx]
						if title.Open {
							title.Open = false
							targetType = NodeTitle
							gi, ti := curr.groupIdx, curr.titleIdx
							targetGroupIdx = &gi
							targetTitleIdx = &ti
							foundTarget = true
						} else if group.Open {
							group.Open = false
							targetType = NodeGroup
							gi := curr.groupIdx
							targetGroupIdx = &gi
							foundTarget = true
						}
					}

					if foundTarget {
						m.rebuildVisible()
						newCursor := -1
						for i, node := range m.visibleNodes {
							if node.Type == targetType && node.groupIdx == *targetGroupIdx {
								if targetType == NodeGroup {
									newCursor = i
									break
								} else if targetType == NodeTitle && node.titleIdx == *targetTitleIdx {
									newCursor = i
									break
								}
							}
						}
						if newCursor != -1 {
							m.cursor = newCursor
							m.refreshViewport()
						} else {
							m.cursor = 0
							m.refreshViewport()
						}
					}

				}
				return m, nil
			}
			switch key := msg.String(); key {
			case "b", "B":
				m.state = StateTUI
				m.isBuilding = true
				m.status = "⏳ 构建中..."
				m.buildLog = "🚀 开始构建...\n"
				return m, buildTreeCmd()
			case "V":
				// 进入选中模式
				m.startSelect()
				m.refreshViewport()
			case "g":
				if m.pendingG {
					if m.pendingNum != "" {
						// Ngg：全展开第 N 行
						n, err := strconv.Atoi(m.pendingNum)
						if err != nil || n <= 0 {
							n = 1
						}
						m.pendingNum = ""
						m.pendingG = false
						target := n - 1
						if target >= len(m.allNodes) {
							target = len(m.allNodes) - 1
						}
						m.jumpToAllNode(target)
					} else {
						// gg：第一行
						m.pendingG = false
						m.jumpToAllNode(0)
					}
				} else {
					m.pendingG = true
				}

			case "G":
				if m.pendingNum != "" {
					// NG：全展开第 N 行
					n, err := strconv.Atoi(m.pendingNum)
					if err != nil || n <= 0 {
						n = 1
					}
					m.pendingNum = ""
					m.pendingG = false
					target := n - 1
					if target >= len(m.allNodes) {
						target = len(m.allNodes) - 1
					}
					m.jumpToAllNode(target)
					return m, nil
				}
				// 无数字：全展开最后一行
				m.pendingG = false
				m.jumpToAllNode(len(m.allNodes) - 1)

			case "1", "2", "3", "4", "5", "6", "7", "8", "9", "0":
				m.pendingNum += key
				m.pendingG = false
				return m, nil

			case "q", "ctrl+c":
				return m, tea.Quit
			case "j":
				// ★ 带数字：按可见顺序向下 N 行 ★
				if m.pendingNum != "" {
					n, err := strconv.Atoi(m.pendingNum)
					if err != nil || n <= 0 {
						n = 1
					}
					m.pendingNum = ""
					m.pendingG = false
					m.cursor += n
					if m.cursor >= len(m.visibleNodes) {
						m.cursor = len(m.visibleNodes) - 1
					}
					m.refreshViewport()
					return m, nil
				}
				m.pendingG = false
				if m.cursor < len(m.visibleNodes)-1 {
					m.cursor++
					m.refreshViewport()
				}
			case "k":
				// ★ 带数字：按可见顺序向上 N 行 ★
				if m.pendingNum != "" {
					n, err := strconv.Atoi(m.pendingNum)
					if err != nil || n <= 0 {
						n = 1
					}
					m.pendingNum = ""
					m.pendingG = false
					m.cursor -= n
					if m.cursor < 0 {
						m.cursor = 0
					}
					m.refreshViewport()
					return m, nil
				}
				m.pendingG = false
				if m.cursor > 0 {
					m.cursor--
					m.refreshViewport()
				}
			case "l":
				node, ok := m.currentNode()
				if !ok {
					break
				}
				if node.Type == NodeGroup {
					m.groups[node.groupIdx].Open = true
					m.rebuildVisible()
				} else if node.Type == NodeTitle {
					m.groups[node.groupIdx].Titles[node.titleIdx].Open = true
					m.rebuildVisible()
				}
			case "h":
				if len(m.visibleNodes) == 0 {
					break
				}
				curr := m.visibleNodes[m.cursor]

				var targetGroupIdx, targetTitleIdx *int
				var targetType NodeType
				foundTarget := false

				switch curr.Type {
				case NodeGroup:
					if m.groups[curr.groupIdx].Open {
						m.groups[curr.groupIdx].Open = false
						targetType = NodeGroup
						gi := curr.groupIdx
						targetGroupIdx = &gi
						foundTarget = true
					}
				case NodeTitle:
					if m.groups[curr.groupIdx].Titles[curr.titleIdx].Open {
						m.groups[curr.groupIdx].Titles[curr.titleIdx].Open = false
						targetType = NodeTitle
						gi, ti := curr.groupIdx, curr.titleIdx
						targetGroupIdx = &gi
						targetTitleIdx = &ti
						foundTarget = true
					} else {
						m.groups[curr.groupIdx].Open = false
						targetType = NodeGroup
						gi := curr.groupIdx
						targetGroupIdx = &gi
						foundTarget = true
					}
				case NodeItem:
					title := &m.groups[curr.groupIdx].Titles[curr.titleIdx]
					group := &m.groups[curr.groupIdx]
					if title.Open {
						title.Open = false
						targetType = NodeTitle
						gi, ti := curr.groupIdx, curr.titleIdx
						targetGroupIdx = &gi
						targetTitleIdx = &ti
						foundTarget = true
					} else if group.Open {
						group.Open = false
						targetType = NodeGroup
						gi := curr.groupIdx
						targetGroupIdx = &gi
						foundTarget = true
					}
				}

				if foundTarget {
					m.rebuildVisible()
					newCursor := -1
					for i, node := range m.visibleNodes {
						if node.Type == targetType && node.groupIdx == *targetGroupIdx {
							if targetType == NodeGroup {
								newCursor = i
								break
							} else if targetType == NodeTitle && node.titleIdx == *targetTitleIdx {
								newCursor = i
								break
							}
						}
					}
					if newCursor != -1 {
						m.cursor = newCursor
						m.refreshViewport()
					} else {
						m.cursor = 0
						m.refreshViewport()
					}
				}

			case "enter", "a", "i":
				node, ok := m.currentNode()
				if !ok {
					break
				}
				var items []PlaylistItem

				if node.Type == NodeItem {
					items = []PlaylistItem{{
						CID:      node.CID,
						BVID:     node.BVID,
						Scheme:   node.Scheme,
						Cover:    node.Cover,
						P:        node.P,
						Title:    node.Name,
						Group:    m.groups[node.groupIdx].Name,
						Category: m.groups[node.groupIdx].Titles[node.titleIdx].Name,
					}}

				} else if node.Type == NodeTitle {
					title := &m.groups[node.groupIdx].Titles[node.titleIdx]
					for _, item := range title.Items {
						items = append(items, PlaylistItem{
							CID:      item.CID,
							BVID:     item.BVID,
							Scheme:   item.Scheme,
							Cover:    item.Cover,
							P:        item.P,
							Title:    item.Title,
							Group:    m.groups[node.groupIdx].Name,
							Category: title.Name,
						})
					}

				} else if node.Type == NodeGroup {
					group := &m.groups[node.groupIdx]
					for _, title := range group.Titles {
						for _, item := range title.Items {
							items = append(items, PlaylistItem{
								CID:      item.CID,
								BVID:     item.BVID,
								Scheme:   item.Scheme,
								Cover:    item.Cover,
								Title:    item.Title,
								P:        item.P,
								Group:    group.Name,
								Category: title.Name,
							})
						}
					}
				}
				m.lastSearch = ""
				m.lastMatchIdx = -1
				
				if len(items) > 0 {
					addmod := AddModeAppend
					if key == "i" {
						addmod = AddModePush
					}
					m.lastAddmod = addmod // ★ 记录
					return m, playCIDs(items, m.playMode, addmod)
				}
				return m, nil

			case "d":
				cmd := exec.Command(GatewayPath, "clear")
				cmd.Run()
				m.status = "✅ 播放列表已清空"
				m.buildLog += "📋 播放列表已清空\n"
				return m, nil

			case "v":
				m.status = "📝 正在编辑播放列表..."
				m.buildLog += "📝 打开 easyedit 编辑播放列表\n"
				return m, easyedit()

			case "s":
				path, err := getBuildPath()
				if err != nil {
					m.status = "❌ provider 不支持"
					m.buildLog += fmt.Sprintf("❌ %v\n", err)
					return m, nil
				}
				return m, openEditorCmd(path)

			case "r":
				m.buildLog += "🔀 正在打乱播放列表...\n"
				countCmd := exec.Command(GatewayPath, "count")
				output, _ := countCmd.Output()
				shuffleCmd := exec.Command(GatewayPath, "shuffle")
				luckyNum := expRandom(5000)
				if err := shuffleCmd.Run(); err != nil {
					m.status = "❌ 打乱失败: " + err.Error()
					m.buildLog += "❌ 打乱失败: " + err.Error() + "\n"
				} else {
					m.buildLog += fmt.Sprintf("✅ 播放列表已整体打乱(%s行)(lucky:%d)\n", strings.TrimSpace(string(output)), luckyNum)
				}
				return m, nil

			case "m":
				if m.playMode == PlayModeSequential {
					m.playMode = PlayModeShuffle
				} else {
					m.playMode = PlayModeSequential
				}
				m.refreshViewport()

			case "/":
				m.state = StateSearchInput
				m.searchInput.SetValue("")
				m.searchInput.Focus()
				return m, nil

			case "n":
				if m.lastSearch == "" || len(m.allNodes) == 0 {
					break
				}
				lowerQuery := strings.ToLower(m.lastSearch)
				start := m.lastMatchIdx + 1
				found := false
				for i := start; i < len(m.allNodes); i++ {
					if strings.Contains(strings.ToLower(m.allNodes[i].Name), lowerQuery) {
						m.lastMatchIdx = i
						found = true
						break
					}
				}
				if !found {
					for i := 0; i < start; i++ {
						if strings.Contains(strings.ToLower(m.allNodes[i].Name), lowerQuery) {
							m.lastMatchIdx = i
							found = true
							break
						}
					}
				}
				if found {
					m.jumpToAllNode(m.lastMatchIdx)
				}
			}
		}

	case error:
		if m.state == StateBuilding {
			m.buildError = msg
			m.state = StateBuildPrompt
		}
		return m, nil

	case tea.WindowSizeMsg:
		if m.state == StateTUI || m.state == StateSearchInput {
			helpHeight := 3
			m.viewport.Width = msg.Width
			m.viewport.Height = msg.Height - helpHeight
			m.refreshViewport()
		}
	}

	return m, nil
}

func (m model) View() string {
	switch m.state {
	case StateBuildPrompt:
		msg := "未检测到 buildtree/tree.json\n\n按 B 构建，Q 退出"
		if m.buildError != nil {
			msg += "\n\n❗ " + m.buildError.Error()
		}
		return msg
	case StateBuilding:
		return "正在同步列表...\n"
	case StateSearchInput:
		return "\n搜索: " + m.searchInput.View() + "\n\n（按 Enter 搜索，Esc 取消）"
	case StateTUI:
		return m.viewport.View() + m.LogView() + m.helpView()
	default:
		return "未知状态"
	}
}

func main() {
	p := tea.NewProgram(newModel(), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		log.Fatal(err)
	}
}
