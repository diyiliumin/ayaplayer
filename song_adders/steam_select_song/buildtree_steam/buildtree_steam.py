#!/usr/bin/env python3
"""
buildtree_steam - Steam 音乐目录树构建器

读取 config.json 中的 Steam 音乐根目录，扫描音频文件，
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
CONFIG_FILE = SCRIPT_DIR / "config.json"
OUTPUT_FILE = SCRIPT_DIR / "tree.json"

SCHEME = "steam"

AUDIO_EXTS = {
    ".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus",
    ".aac", ".wma", ".m4b", ".mp4",
}

DEFAULT_ROOTS = [
    Path("~/.steam/steam/steamapps/music"),
    Path("~/.local/share/Steam/steamapps/music"),
    Path("~/.steam/steamapps/music"),
]


def load_root():
    root = ""
    if CONFIG_FILE.exists():
        try:
            root = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("root", "")
        except Exception as e:
            print(f"⚠️  读取 config.json 失败: {e}", file=sys.stderr)

    if root:
        p = Path(root).expanduser()
        if p.is_dir():
            return p
        print(f"⚠️  config.json 中的 root 不是有效目录: {root}", file=sys.stderr)

    for cand in DEFAULT_ROOTS:
        if cand.expanduser().is_dir():
            return cand.expanduser()

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
            group_name = root.name or "Steam Music"
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
        print(CONFIG_FILE)
        return

    root = load_root()
    if root is None:
        print(f"❌ 找不到 Steam 音乐目录，请编辑 {CONFIG_FILE} 设置 root", file=sys.stderr)
        sys.exit(1)

    print(f"📂 Steam 音乐根目录: {root}")
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
