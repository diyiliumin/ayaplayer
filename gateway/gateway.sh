#!/bin/bash

# ============================================
# gateway - 数据源网关（支持本地 + 远程 HTTP）
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_LIST="$SCRIPT_DIR/source_list.txt"
DAEMON_PORT="${GATEWAY_PORT:-10721}"
DAEMON_PID_FILE="/tmp/gateway_daemon.pid"

# ============================================
# 获取数据源 URI（可能是 file:// 或 http://）
# ============================================
get_source_uri() {
    if [[ ! -f "$SOURCE_LIST" ]]; then
        echo "❌ 找不到 source_list.txt" >&2
        return 1
    fi
    
    local line=$(head -n 1 "$SOURCE_LIST")
    if [[ -z "$line" ]]; then
        echo "❌ source_list.txt 为空" >&2
        return 1
    fi
    
    echo "$line"
}

# ============================================
# URI → 本地路径（如果是 file://）
# ============================================
uri_to_path() {
    local uri="$1"
    if [[ "$uri" == file://* ]]; then
        local path="${uri#file://}"
        if [[ "$path" != /* ]]; then
            path="$SCRIPT_DIR/$path"
        fi
        path=$(realpath -m "$path" 2>/dev/null || echo "$path")
        echo "$path"
    else
        echo ""
    fi
}

# ============================================
# 判断是否远程
# ============================================
is_remote() {
    local uri="$1"
    [[ "$uri" == http://* ]] || [[ "$uri" == https://* ]]
}

# ============================================
# 远程 API 调用
# ============================================
remote_call() {
    local uri="$1"
    local endpoint="$2"
    shift 2
    local args=("$@")
    
    # 构造 JSON body
    local body=""
    if [[ ${#args[@]} -gt 0 ]]; then
        body=$(printf '%s\n' "${args[@]}" | jq -R . | jq -s .)
    fi
    
    local url="${uri%/}/$endpoint"
    
    if [[ -z "$body" ]] || [[ "$body" == "[]" ]]; then
        curl -s -X GET "$url" 2>/dev/null
    else
        curl -s -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$body" 2>/dev/null
    fi
}

# ============================================
# Checkout / Commit - 本地编辑远程数据源
# ============================================

CHECKOUT_DIR="${CHECKOUT_DIR:-/tmp/gateway_checkout}"
CHECKOUT_FILE="$CHECKOUT_DIR/playlist"
CHECKOUT_META="$CHECKOUT_DIR/meta"

# ============================================
# 命令: checkout - 下载当前数据源到本地
# ============================================
cmd_checkout() {
    local uri=$(get_source_uri) || return 1
    
    # 创建目录
    mkdir -p "$CHECKOUT_DIR"
    
    # 下载
    if is_remote "$uri"; then
        echo "📥 下载远程数据源: $uri" >&2
        curl -s "$uri/read" > "$CHECKOUT_FILE"
        if [ $? -ne 0 ]; then
            echo "❌ 下载失败" >&2
            return 1
        fi
    else
        local path=$(uri_to_path "$uri")
        if [[ ! -f "$path" ]]; then
            echo "❌ 文件不存在: $path" >&2
            return 1
        fi
        echo "📋 复制本地数据源: $path" >&2
        cp "$path" "$CHECKOUT_FILE"
    fi
    
    # 保存元信息
    cat > "$CHECKOUT_META" <<EOF
URI=$uri
TIME=$(date +%Y-%m-%d\ %H:%M:%S)
LINES=$(wc -l < "$CHECKOUT_FILE")
EOF
    
    echo "✅ 已下载到: $CHECKOUT_FILE" >&2
    echo "   行数: $(wc -l < "$CHECKOUT_FILE")" >&2
    echo "   编辑: nvim $CHECKOUT_FILE" >&2
    echo "   上传: gateway commit" >&2
}

# ============================================
# 命令: commit - 上传本地修改到数据源
# ============================================
# ============================================
# 命令: commit - 上传本地修改到数据源（用 write）
# ============================================
cmd_commit() {
    if [[ ! -f "$CHECKOUT_FILE" ]]; then
        echo "❌ 没有 checkout 的文件，先运行: gateway checkout" >&2
        return 1
    fi
    
    local uri=$(get_source_uri) || return 1
    
    # 显示修改
    echo "📊 提交到: $uri" >&2
    echo "   行数: $(wc -l < "$CHECKOUT_FILE")" >&2
    
    # 读取内容
    local content=$(cat "$CHECKOUT_FILE")
    
    # 上传
    if is_remote "$uri"; then
        # ★★★ 用 write 一次性上传 ★★★
        local body=$(printf '%s' "$content" | jq -Rs .)
        local result=$(curl -s -X POST "$uri/write" \
            -H "Content-Type: application/json" \
            -d "[$body]" 2>/dev/null)
        
        if [[ "$result" == *"ok"* ]]; then
            echo "✅ 已上传（bulk write）" >&2
        else
            # ★★★ 回退：clear + append ★★★
            echo "⚠️ write 失败，回退到 clear+append" >&2
            remote_call "$uri" "clear" > /dev/null
            local count=0
            while IFS= read -r line; do
                [[ -z "$line" ]] && continue
                remote_call "$uri" "append" "$line" > /dev/null
                count=$((count + 1))
            done < "$CHECKOUT_FILE"
            echo "✅ 已上传 $count 行（append）" >&2
        fi
    else
        # ★★★ 本地：直接复制 ★★★
        local path=$(uri_to_path "$uri")
        
        # 备份
        # if [[ -f "$path" ]]; then
        #     cp "$path" "${path}.bak.$(date +%s)"
        # fi
        
        cp "$CHECKOUT_FILE" "$path"
        echo "✅ 已写入: $path" >&2
    fi
    
    # 清理
    rm -f "$CHECKOUT_FILE" "$CHECKOUT_META"
    echo "✅ 提交完成" >&2
}

# ============================================
# 统一写入操作: write（覆盖全部）
# ============================================
op_write() {
    local content
    if [ $# -gt 0 ]; then
        content="$1"
    else
        content=$(cat)
    fi
    
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        local body=$(printf '%s' "$content" | jq -Rs .)
        local result=$(curl -s -X POST "$uri/write" \
            -H "Content-Type: application/json" \
            -d "[$body]" 2>/dev/null)
        
        if [[ "$result" == *"ok"* ]] || [[ -z "$result" ]]; then
            echo "✅ 已写入" >&2
            return 0
        else
            echo "❌ 写入失败: $result" >&2
            return 1
        fi
    else
        local path=$(uri_to_path "$uri")
        if [[ -f "$path" ]]; then
            cp "$path" "${path}.bak.$(date +%s)"
        fi
        printf '%s' "$content" > "$path"
        echo "✅ 已写入: $path" >&2
        return 0
    fi
}

# ============================================
# 命令: diff - 显示本地和远程的差异
# ============================================
cmd_diff() {
    if [[ ! -f "$CHECKOUT_FILE" ]]; then
        echo "❌ 没有 checkout 的文件" >&2
        return 1
    fi
    
    local uri=$(get_source_uri) || return 1
    local remote_content
    
    if is_remote "$uri"; then
        remote_content=$(curl -s "$uri/read")
    else
        local path=$(uri_to_path "$uri")
        remote_content=$(cat "$path")
    fi
    
    echo "📊 差异 (本地 vs 远程):" >&2
    echo "--- 远程"
    echo "+++ 本地"
    diff <(echo "$remote_content") "$CHECKOUT_FILE"
}

# ============================================
# 命令: status - 显示 checkout 状态
# ============================================
cmd_status() {
    if [[ ! -f "$CHECKOUT_FILE" ]]; then
        echo "❌ 没有 checkout" >&2
        return 1
    fi
    
    echo "📁 Checkout 状态:" >&2
    cat "$CHECKOUT_META" >&2
    echo "" >&2
    echo "本地文件: $CHECKOUT_FILE" >&2
    echo "当前行数: $(wc -l < "$CHECKOUT_FILE")" >&2
}

# ============================================
# 统一读取操作
# ============================================
op_read() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "read"
    else
        local path=$(uri_to_path "$uri")
        [[ -f "$path" ]] && cat "$path"
    fi
}

op_first() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "first"
    else
        local path=$(uri_to_path "$uri")
        [[ -f "$path" ]] && head -n 1 "$path"
    fi
}

op_count() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "count"
    else
        local path=$(uri_to_path "$uri")
        if [[ -f "$path" ]]; then
            wc -l < "$path" | tr -d ' '
        else
            echo "0"
        fi
    fi
}

# ============================================
# 统一写入操作
# ============================================
# op_append() {
#     local line="$1"
#     local uri=$(get_source_uri) || return 1
#     
#     if is_remote "$uri"; then
#         remote_call "$uri" "append" "$line"
#     else
#         local path=$(uri_to_path "$uri")
#         echo "$line" >> "$path"
#     fi
# }

# ============================================
# 统一写入操作: append（支持多行，一次提交）
# ============================================
op_append() {
    local uri=$(get_source_uri) || return 1
    local path=$(uri_to_path "$uri")
    
    # ★★★ 收集内容（参数或 stdin）★★★
    local content=""
    if [ $# -gt 0 ]; then
        content="$*"
    else
        content=$(cat)
    fi
    
    if [ -z "$content" ]; then
        echo "❌ 没有内容" >&2
        return 1
    fi
    
    if is_remote "$uri"; then
        # ★★★ 远程：一次 read + 一次 write ★★★
        local existing=$(remote_call "$uri" "read")
        local new_content
        if [ -n "$existing" ]; then
            new_content="${existing}
${content}"
        else
            new_content="$content"
        fi
        op_write "$new_content"
    else
        # ★★★ 本地：直接追加 ★★★
        printf '%s\n' "$content" >> "$path"
        echo "✅ 已追加" >&2
    fi
}

# op_push() {
#     local line="$1"
#     local uri=$(get_source_uri) || return 1
#     
#     if is_remote "$uri"; then
#         remote_call "$uri" "push" "$line"
#     else
#         local path=$(uri_to_path "$uri")
#         [[ ! -f "$path" ]] && touch "$path"
#         echo "$line" | cat - "$path" > "$path.tmp" && mv "$path.tmp" "$path"
#     fi
# }

# ============================================
# 统一写入操作: push（支持多行，一次提交）
# ============================================
op_push() {
    local uri=$(get_source_uri) || return 1
    local path=$(uri_to_path "$uri")
    
    # ★★★ 收集内容（参数或 stdin）★★★
    local content=""
    if [ $# -gt 0 ]; then
        content="$*"
    else
        content=$(cat)
    fi
    
    if [ -z "$content" ]; then
        echo "❌ 没有内容" >&2
        return 1
    fi
    
    if is_remote "$uri"; then
        # ★★★ 远程：一次 read + 一次 write ★★★
        local existing=$(remote_call "$uri" "read")
        local new_content
        if [ -n "$existing" ]; then
            new_content="${content}
${existing}"
        else
            new_content="$content"
        fi
        op_write "$new_content"
    else
        # ★★★ 本地：插到顶部 ★★★
        if [[ ! -f "$path" ]]; then
            touch "$path"
        fi
        printf '%s\n' "$content" | cat - "$path" > "$path.tmp" && mv "$path.tmp" "$path"
        echo "✅ 已推入" >&2
    fi
}

op_pop() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "pop"
    else
        local path=$(uri_to_path "$uri")
        if [[ -f "$path" ]] && [[ -s "$path" ]]; then
            local first=$(head -n 1 "$path")
            tail -n +2 "$path" > "$path.tmp" && mv "$path.tmp" "$path"
            echo "$first"
        fi
    fi
}

# op_finish() {
#     local json="$1"
#     local uri=$(get_source_uri) || return 1
#     
#     if is_remote "$uri"; then
#         remote_call "$uri" "finish" "$json"
#     else
#         local path=$(uri_to_path "$uri")
#         [[ ! -f "$path" ]] || [[ ! -s "$path" ]] && return 1
#         
#         local first=$(head -n 1 "$path")
#         local first_norm=$(echo "$first" | jq -S -c '.' 2>/dev/null)
#         local json_norm=$(echo "$json" | jq -S -c '.' 2>/dev/null)
#         
#         if [[ "$first_norm" == "$json_norm" ]]; then
#             tail -n +2 "$path" > "$path.tmp" && mv "$path.tmp" "$path"
#             echo "✅ 已删除顶部" >&2
#             return 0
#         else
#             echo "⚠️ 顶部不匹配，跳过" >&2
#             return 1
#         fi
#     fi
# }

op_finish() {
    local json="$1"
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "finish" "$json"
    else
        local path=$(uri_to_path "$uri")
        [[ ! -f "$path" ]] || [[ ! -s "$path" ]] && return 1
        
        local first=$(head -n 1 "$path")
        local first_norm=$(echo "$first" | jq -S -c '.' 2>/dev/null)
        local json_norm=$(echo "$json" | jq -S -c '.' 2>/dev/null)
        
        if [[ "$first_norm" == "$json_norm" ]]; then
            # ★★★ 删除顶部 ★★★
            tail -n +2 "$path" > "$path.tmp" && mv "$path.tmp" "$path"
            echo "✅ 已删除顶部" >&2
            
            # ★★★ 检查是否在 loop_list 目录里 ★★★
            local loop_dir="$SCRIPT_DIR/../to_be_played/loop_list"
            local abs_path=$(realpath "$path" 2>/dev/null || echo "$path")
            local abs_loop=$(realpath "$loop_dir" 2>/dev/null || echo "$loop_dir")
            
            if [[ "$abs_path" == "$abs_loop"/* ]]; then
                # ★★★ 在 loop_list 里：追加到末尾 ★★★
                echo "$first" >> "$path"
                echo "🔁 循环模式：已追加到末尾" >&2
            fi
            
            return 0
        else
            echo "⚠️ 顶部不匹配，跳过" >&2
            return 1
        fi
    fi
}

op_clear() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "clear"
    else
        local path=$(uri_to_path "$uri")
        > "$path"
        echo "✅ 已清空" >&2
    fi
}

op_shuffle() {
    local uri=$(get_source_uri) || return 1
    
    if is_remote "$uri"; then
        remote_call "$uri" "shuffle"
    else
        local path=$(uri_to_path "$uri")
        shuf "$path" > "$path.tmp" && mv "$path.tmp" "$path"
        echo "✅ 已打乱" >&2
    fi
}

# ============================================
# 命令: sources / set / switch
# ============================================
cmd_source() {
    get_source_uri
}

cmd_sources() {
    if [[ -f "$SOURCE_LIST" ]]; then
        cat -n "$SOURCE_LIST"
    fi
}

cmd_set() {
    local new_source="$1"
    if [[ -z "$new_source" ]]; then
        echo "用法: gateway set <uri>" >&2
        return 1
    fi
    if [[ ! -f "$SOURCE_LIST" ]]; then
        touch "$SOURCE_LIST"
    fi
    echo "$new_source" | cat - "$SOURCE_LIST" > "$SOURCE_LIST.tmp" && mv "$SOURCE_LIST.tmp" "$SOURCE_LIST"
    echo "✅ 数据源已切换" >&2
}

cmd_switch() {
    if [[ ! -f "$SOURCE_LIST" ]] || [[ ! -s "$SOURCE_LIST" ]]; then
        echo "❌ source_list.txt 为空" >&2
        return 1
    fi
    local count=$(wc -l < "$SOURCE_LIST")
    if [[ $count -lt 2 ]]; then
        echo "⚠️ 只有 1 个数据源，无法切换" >&2
        return 1
    fi
    local first=$(head -n 1 "$SOURCE_LIST")
    tail -n +2 "$SOURCE_LIST" > "$SOURCE_LIST.tmp"
    echo "$first" >> "$SOURCE_LIST.tmp"
    mv "$SOURCE_LIST.tmp" "$SOURCE_LIST"
    echo "✅ 已切换到: $(get_source_uri)" >&2
}

# ============================================
# 命令: count / length
# ============================================
cmd_count() {
    op_count
}

# ============================================
# ============================================
# DAEMON 模式 - 在服务端运行
# ============================================
# ============================================

# 判断请求路径，调用本地操作
handle_request() {
    local method="$1"
    local path="$2"
    local body="$3"
    
    case "$path" in
        /read)
            op_read
            ;;
        /first)
            op_first
            ;;
        /count)
            op_count
            ;;
        /pop)
            op_pop
            ;;
        /append)
            local line=$(echo "$body" | jq -r '.[0]' 2>/dev/null)
            op_append "$line"
            echo "✅ OK" >&2
            ;;
        /push)
            local line=$(echo "$body" | jq -r '.[0]' 2>/dev/null)
            op_push "$line"
            echo "✅ OK" >&2
            ;;
        /finish)
            local line=$(echo "$body" | jq -r '.[0]' 2>/dev/null)
            op_finish "$line"
            ;;
        /clear)
            op_clear
            ;;
        /shuffle)
            op_shuffle
            ;;
        /source)
            cmd_source
            ;;
        /sources)
            cmd_sources
            ;;
        /health)
            echo '{"status":"ok"}'
            ;;
        *)
            echo "❌ 未知路径: $path" >&2
            return 1
            ;;
    esac
}

start_daemon() {
    echo "🚀 启动 gateway daemon 在端口 $DAEMON_PORT" >&2
    
    # 用 socat 或 ncat 监听
    if command -v socat &>/dev/null; then
        # 用 socat 实现简单的 HTTP 服务
        socat TCP-LISTEN:$DAEMON_PORT,reuseaddr,fork EXEC:"$SCRIPT_DIR/gateway_daemon_handler.sh" &
        echo $! > "$DAEMON_PID_FILE"
        echo "✅ Daemon PID: $(cat $DAEMON_PID_FILE)" >&2
    elif command -v ncat &>/dev/null; then
        ncat -l $DAEMON_PORT --keep-open --exec "$SCRIPT_DIR/gateway_daemon_handler.sh" &
        echo $! > "$DAEMON_PID_FILE"
        echo "✅ Daemon PID: $(cat $DAEMON_PID_FILE)" >&2
    else
        echo "❌ 需要 socat 或 ncat" >&2
        return 1
    fi
}

stop_daemon() {
    if [[ -f "$DAEMON_PID_FILE" ]]; then
        local pid=$(cat "$DAEMON_PID_FILE")
        kill "$pid" 2>/dev/null
        rm -f "$DAEMON_PID_FILE"
        echo "✅ Daemon 已停止" >&2
    else
        echo "⚠️ Daemon 未运行" >&2
    fi
}

# ============================================
# 简单的 Python HTTP 服务器（更可靠）
# ============================================
start_python_daemon() {
    echo "🚀 启动 Python HTTP daemon 在端口 $DAEMON_PORT" >&2
    
    python3 "$SCRIPT_DIR/gateway_daemon.py" "$DAEMON_PORT" &
    echo $! > "$DAEMON_PID_FILE"
    echo "✅ Daemon PID: $(cat $DAEMON_PID_FILE)" >&2
}

# ============================================
# 主入口
# ============================================
cmd_help() {
    cat <<EOF
gateway - 数据源网关（支持本地 + 远程）

用法: gateway <命令> [参数]

【基础操作】
  pop / shift              弹出并返回第一行
  push <line>              推送到顶部
  append <line>            追加到末尾
  finish <json>            匹配顶部则删除（避免重复）
  read                     读取全部内容
  count                    统计行数
  clear                    清空

【读取操作】
  first                    第一行
  last                     最后一行

【数据源管理】
  source                   显示当前数据源
  sources                  列出所有数据源
  set <uri>                切换数据源
  switch                   切换到下一个

【Checkout/Commit】（本地编辑远程）
  checkout                 下载数据源到 /tmp/gateway_checkout/playlist
  commit                   上传本地修改到数据源
  diff                     显示差异
  status                   显示 checkout 状态

【DAEMON 模式】
  --daemon start           启动 HTTP 服务
  --daemon stop            停止 HTTP 服务
  --daemon status          查看状态

支持的数据源:
  file://../playlist.json           本地文件
  http://localhost:8787             远程 gateway
  https://example.com/playlist.json 远程 HTTP

示例:
  gateway pop
  gateway push '{"title":"xxx"}'
  gateway finish '{"title":"xxx"}'
  gateway set 'http://localhost:8787'
  gateway --daemon start
EOF
}

main() {
    local cmd="$1"
    shift
    
    case "$cmd" in
        # 基础
        pop|shift)           op_pop ;;
        push|unshift)        op_push "$@" ;;
        append|push_back)    op_append "$@" ;;
        finish)              op_finish "$@" ;;
        read|readlines)      op_read ;;
        count|length)        op_count ;;
        clear|truncate)      op_clear ;;
        shuffle)             op_shuffle ;;
        
        # 读取
        first|getnext)       op_first ;;
        last)                # TODO
                             local uri=$(get_source_uri)
                             if is_remote "$uri"; then
                                 remote_call "$uri" "last"
                             else
                                 local path=$(uri_to_path "$uri")
                                 [[ -f "$path" ]] && tail -n 1 "$path"
                             fi
                             ;;
        
        # 数据源
        source)              cmd_source ;;
        sources)             cmd_sources ;;
        set)                 cmd_set "$@" ;;
        switch)              cmd_switch ;;
        write)               op_write "$@" ;;

	# Checkout/Commit
	checkout)          cmd_checkout ;;
 	commit)            cmd_commit ;;
 	diff)              cmd_diff ;;
 	status)            cmd_status ;;

        
        # Daemon
        --daemon)
            case "$1" in
                start)   start_python_daemon ;;
                stop)    stop_daemon ;;
                status)  
                    if [[ -f "$DAEMON_PID_FILE" ]]; then
                        local pid=$(cat "$DAEMON_PID_FILE")
                        if kill -0 "$pid" 2>/dev/null; then
                            echo "✅ Daemon 运行中 (PID: $pid)" >&2
                        else
                            echo "⚠️ Daemon 已死" >&2
                        fi
                    else
                        echo "⚠️ Daemon 未运行" >&2
                    fi
                    ;;
                *)       echo "用法: gateway --daemon {start|stop|status}" >&2 ;;
            esac
            ;;
        
        # 帮助
        help|"")             cmd_help ;;
        *)
            echo "❌ 未知命令: $cmd" >&2
            echo "运行 'gateway help' 查看帮助" >&2
            exit 1
            ;;
    esac
}

main "$@"

