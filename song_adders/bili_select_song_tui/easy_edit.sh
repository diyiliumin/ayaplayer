#!/bin/bash

# ============================================
# easyedit - 可视化编辑 playlist（带 delta 提交）
# 用法: ./easyedit.sh [--dry-run]
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY="$SCRIPT_DIR/../../gateway/gateway.sh"

TMP_DIR="/tmp/easyedit_$$"
FULL_FILE="$TMP_DIR/full.jsonl"
INDEX_FILE="$TMP_DIR/index.tsv"
EASY_FILE="$TMP_DIR/easy.txt"
NEW_FILE="$TMP_DIR/new.jsonl"

# 参数
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
    esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT
mkdir -p "$TMP_DIR"

# ============================================
# 1. 下载
# ============================================
echo -e "${CYAN}📥 下载 playlist...${NC}"
"$GATEWAY" read > "$FULL_FILE"

if [ ! -s "$FULL_FILE" ]; then
    echo -e "${RED}❌ playlist 为空${NC}" >&2
    exit 1
fi

TOTAL=$(wc -l < "$FULL_FILE")
echo -e "${GREEN}✅ $TOTAL 首${NC}"

# ============================================
# 2. 建索引（title → JSON）
# ============================================
echo -e "${CYAN}🔨 建索引...${NC}"

jq -r -s '
    .[] | 
    [(.title // ""), (tojson)] | 
    @tsv
' "$FULL_FILE" > "$INDEX_FILE"

# ============================================
# 3. 生成简化视图（只有 title）
# ============================================
echo -e "${CYAN}📝 生成视图...${NC}"

awk -F'\t' '{
    if ($1 == "") print $2
    else print $1
}' "$INDEX_FILE" > "$EASY_FILE"

# ============================================
# 4. 编辑
# ============================================
echo -e "${CYAN}✏️  打开编辑器...${NC}"
echo -e "${YELLOW}   文件: $EASY_FILE${NC}"
echo -e "${YELLOW}   提示: 每行是一个 title，删除=删歌，移动=调序${NC}"
echo ""

EDITOR="${EDITOR:-nvim}"
command -v "$EDITOR" &>/dev/null || EDITOR="vim"
command -v "$EDITOR" &>/dev/null || EDITOR="nano"

"$EDITOR" "$EASY_FILE"

echo ""
echo -e "${CYAN}🔍 分析修改...${NC}"

if [ ! -f "$EASY_FILE" ]; then
    echo -e "${RED}❌ 文件被删除${NC}" >&2
    exit 1
fi

# ============================================
# 5. 匹配（awk 哈希表，O(n)）
# ============================================
echo -e "${CYAN}🔄 匹配...${NC}"

awk -F'\t' '
    NR == FNR {
        if ($1 != "") map[$1] = $2
        next
    }
    $0 == "" || /^#/ { next }
    {
        if ($0 in map) {
            print map[$0]
            matched++
        } else {
            unmatched++
            print "⚠️ 未匹配: " $0 > "/dev/stderr"
        }
    }
    END {
        print "📊 匹配: " matched " 首" > "/dev/stderr"
        print "📊 未匹配: " unmatched " 首（已丢弃）" > "/dev/stderr"
    }
' "$INDEX_FILE" "$EASY_FILE" > "$NEW_FILE"

# ============================================
# 6. 统计
# ============================================
NEW_COUNT=$(wc -l < "$NEW_FILE")

echo ""
echo -e "${CYAN}📊 统计:${NC}"
echo -e "   原始:     $TOTAL 首"
echo -e "   编辑后:   $NEW_COUNT 首"

# ============================================
# 7. 检查差异
# ============================================
if diff -q "$FULL_FILE" "$NEW_FILE" >/dev/null 2>&1; then
    echo ""
    echo -e "${GREEN}✅ 没有变化${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}📊 差异预览:${NC}"
diff "$FULL_FILE" "$NEW_FILE" | head -30

# ============================================
# 8. Dry run 退出
# ============================================
if [ "$DRY_RUN" = true ]; then
    echo ""
    echo -e "${YELLOW}🔍 --dry-run: 不提交${NC}"
    echo "   新内容: $NEW_FILE"
    cp "$NEW_FILE" /tmp/easyedit_result.jsonl
    echo "   副本: /tmp/easyedit_result.jsonl"
    exit 0
fi

# ============================================
# 9. 提交（用 write 一次性上传）
# ============================================
echo ""
echo -e "${CYAN}📤 提交...${NC}"

CONTENT=$(cat "$NEW_FILE")

# ★★★ 用 write 一次性提交 ★★★
if "$GATEWAY" write "$CONTENT" 2>/dev/null; then
    echo -e "${GREEN}✅ 已提交 $NEW_COUNT 首（bulk write）${NC}"
else
    # ★★★ 回退：clear + append ★★★
    echo -e "${YELLOW}   → write 失败，回退到 clear+append${NC}"
    "$GATEWAY" clear
    
    COMMIT_COUNT=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        "$GATEWAY" append "$line" >/dev/null
        COMMIT_COUNT=$((COMMIT_COUNT + 1))
    done < "$NEW_FILE"
    
    echo -e "${GREEN}✅ 已提交 $COMMIT_COUNT 首${NC}"
fi

echo -e "${GREEN}✅ 完成${NC}"
