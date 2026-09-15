#!/bin/bash

# 获取真实路径（兼容软链接）
get_real_path() {
    local src="$1"
    while [ -L "$src" ]; do
        local dir
        dir="$(cd -P "$(dirname "$src")" && pwd)"
        src="$(readlink "$src")"
        [[ $src != /* ]] && src="$dir/$src"
    done
    cd -P "$(dirname "$src")" && pwd
}

SCRIPT_DIR="$(get_real_path "${BASH_SOURCE[0]}")"

# -s: 返回 path.txt 路径（供 TUI 编辑音乐目录）
if [ "$1" = "-s" ]; then
    echo "$SCRIPT_DIR/path.txt"
    exit 0
fi

cd "$SCRIPT_DIR"
./buildtree_local.py
