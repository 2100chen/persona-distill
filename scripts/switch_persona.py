#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona-distill · switch_persona.py
切换 / 查看 / 清除当前激活的人格。

激活人格会被写入 data/personas/ACTIVE.md，agent 在回复前读取它并采用此口吻。

用法:
  python switch_persona.py <name>     # 激活指定人格
  python switch_persona.py --status   # 查看当前激活
  python switch_persona.py --clear    # 取消激活
"""
import argparse
import datetime
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
ACTIVE = PERSONAS_DIR / "ACTIVE.md"
REGISTRY = PERSONAS_DIR / "active.json"


def available():
    return sorted(p.stem for p in PERSONAS_DIR.glob("*.md") if p.name != "ACTIVE.md")


def activate(name: str):
    src = PERSONAS_DIR / f"{name}.md"
    if not src.exists():
        sys.exit(f"未找到人格「{name}」。可用: {available() or '（空，请先蒸馏）'}")
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    REGISTRY.write_text(json.dumps({
        "active": name,
        "switched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": str(src),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 已激活人格「{name}」(→ data/personas/ACTIVE.md)")
    print("  之后 agent 的回复会采用此人格口吻，直到 --clear。")
    print(f"  取消激活: python {pathlib.Path(__file__).name} --clear")


def status():
    if REGISTRY.exists():
        info = json.loads(REGISTRY.read_text(encoding="utf-8"))
        print(f"当前激活人格: {info['active']}（{info['switched_at']} 切换）")
    else:
        print("当前无激活人格（agent 使用默认口吻）。")


def clear():
    for p in (ACTIVE, REGISTRY):
        if p.exists():
            p.unlink()
    print("✓ 已清除激活人格，agent 恢复默认口吻。")


def main():
    ap = argparse.ArgumentParser(description="切换/查看/清除激活人格")
    ap.add_argument("name", nargs="?", help="要激活的人格标识")
    ap.add_argument("--status", action="store_true", help="查看当前激活")
    ap.add_argument("--clear", action="store_true", help="清除激活")
    args = ap.parse_args()
    if args.status:
        status()
    elif args.clear:
        clear()
    elif args.name:
        activate(args.name)
    else:
        ap.print_help()
        print("\n可用人格:", available() or "（空）")


if __name__ == "__main__":
    main()
