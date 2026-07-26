#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona-distill · list_personas.py
列出所有已蒸馏的人格配置 + 当前激活项。

用法: python list_personas.py
"""
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def _data_dir(subdir, env_key):
    env = os.getenv(env_key)
    if env:
        return pathlib.Path(env).expanduser()
    cur = pathlib.Path(__file__).resolve().parent
    for _ in range(8):
        if (cur / "data").is_dir():
            return cur / "data" / subdir
        if (cur / ".git").exists() or cur.parent == cur:
            break
        cur = cur.parent
    return pathlib.Path(os.getenv("OPENCLAW_HOME", str(pathlib.Path.home() / ".openclaw"))) / "data" / subdir


PERSONAS_DIR = _data_dir("personas", "PERSONA_DISTILL_DIR")
REGISTRY = PERSONAS_DIR / "active.json"


def extract(path: pathlib.Path):
    """读 frontmatter 的 alias + 正文里的一句话画像。"""
    text = path.read_text(encoding="utf-8")
    alias = path.stem
    for line in text.splitlines():
        if line.startswith("alias:"):
            alias = line.split(":", 1)[1].strip()
    summary = "（无画像）"
    for line in text.splitlines():
        if "一句话画像" in line:
            summary = line.split("：", 1)[-1].strip()
            break
    return alias, summary


def main():
    active = ""
    if REGISTRY.exists():
        active = json.loads(REGISTRY.read_text(encoding="utf-8")).get("active", "")

    files = sorted(p for p in PERSONAS_DIR.glob("*.md") if p.name != "ACTIVE.md")
    if not files:
        print("（暂无人格配置，请先用 distill.py 蒸馏）")
        return
    print(f"已蒸馏人格（共 {len(files)} 个）：")
    for p in files:
        alias, summary = extract(p)
        mark = " ← 当前激活" if p.stem == active else ""
        print(f"  • {p.stem}  ({alias}){mark}")
        print(f"      {summary}")
    if active:
        print(f"\n激活项: {active}")
    else:
        print("\n（当前无激活人格）")


if __name__ == "__main__":
    main()
