#!/bin/bash

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
# 检查第一个参数
if [ "$1" = "-s" ]; then
    # 如果参数是 -v，返回 urls.txt 的内容
    echo "$SCRIPT_DIR/urls.txt"
    exit 0
fi

# 否则正常运行
cd "$SCRIPT_DIR"
./buildtree_web_walker.py
