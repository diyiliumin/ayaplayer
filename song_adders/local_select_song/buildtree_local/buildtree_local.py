#!/usr/bin/env python3
"""
buildtree_local - 本地音乐目录树构建器

从 path.txt 读取用户自己的音乐目录路径，扫描音频文件，
生成与其他 tree builder 完全一致的 4 层 JSON：
    group > title > tab > item

映射规则：
    group  = 第 1 层目录
    title  = 第 2 层及更深目录（不足时用同名补齐）
    tab    = 每个音频文件（一个文件一个 tab，展示名为文件名）
    item   = 音频文件元数据

如果真实目录层级不够深，用同名补齐（如 <root>/专辑/歌.mp3
会得到 group=专辑 title=专辑）。
"""

import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PATH_FILE = SCRIPT_DIR / "path.txt"
OUTPUT_FILE = SCRIPT_DIR / "tree.json"

SCHEME = "local"

AUDIO_EXTS = {
    ".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus",
    ".aac", ".wma", ".m4b", ".mp4",
}


def load_root():
    path = ""
    if PATH_FILE.exists():
        for line in PATH_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            path = line
            break

    if path:
        p = Path(path).expanduser()
        if p.is_dir():
            return p
        print(f"⚠️  path.txt 中的路径不是有效目录: {path}", file=sys.stderr)

    return None


def stable_cid(rel_path: str) -> int:
    """由相对路径生成稳定的 64 位无符号 cid（重建时保持稳定）"""
    return int.from_bytes(hashlib.md5(rel_path.encode("utf-8")).digest()[:8], "big")


def build_tree(root: Path):
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )

    # group_name -> { title_name -> [ (tab_name, abs_path, rel_path, size) ] }
    groups = {}
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue

        dirs = rel.parts[:-1]
        tab_name = rel.stem

        if len(dirs) >= 2:
            group_name = dirs[0]
            title_name = "/".join(dirs[1:])
        elif len(dirs) == 1:
            group_name = dirs[0]
            title_name = dirs[0]
        else:
            group_name = root.name or "Music"
            title_name = group_name

        groups.setdefault(group_name, {}).setdefault(title_name, []).append(
            (tab_name, str(f.resolve()), str(rel), f.stat().st_size)
        )

    tree = []
    for group_name in sorted(groups):
        titles = []
        for title_name in sorted(groups[group_name]):
            tabs = []
            for tab_name, abs_path, rel_path, size in sorted(groups[group_name][title_name]):
                tabs.append({
                    "name": tab_name,
                    "items": [{
                        "p": 1,
                        "title": tab_name,
                        "duration": 0,
                        "loaded_size": size,
                        "bvid": abs_path,
                        "cid": stable_cid(rel_path),
                        "group_title": group_name,
                        "tab_name": tab_name,
                        "scheme": SCHEME,
                    }],
                })
            titles.append({
                "name": title_name,
                "p": len(titles) + 1,
                "tabs": tabs,
            })
        tree.append({"name": group_name, "titles": titles})

    return tree


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "-s":
        print(PATH_FILE)
        return

    root = load_root()
    if root is None:
        print(f"❌ 请先在 {PATH_FILE} 里写入你的音乐目录路径", file=sys.stderr)
        sys.exit(1)

    print(f"📂 本地音乐目录: {root}")
    tree = build_tree(root)

    total = sum(
        len(tab["items"])
        for g in tree
        for t in g["titles"]
        for tab in t["tabs"]
    )

    OUTPUT_FILE.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"🎉 tree.json 已写入（{len(tree)} 个顶层 group / {total} 首曲目）")


if __name__ == "__main__":
    main()
