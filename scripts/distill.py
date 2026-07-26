#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona-distill · distill.py
解析聊天记录 -> 过滤目标人物 -> 统计特征 -> 输出结构化数据（供 OpenClaw agent 蒸馏）。

【本脚本不调用任何模型 API】。真正的蒸馏（提取 11 个维度、生成 persona.md）
由 OpenClaw 的 agent（它自带模型）读取本脚本输出的 JSON、按 SKILL.md 的蒸馏规范完成。

用法:
  python distill.py <聊天记录文件> --name <英文标识> [--alias <记录里的昵称>] [--budget 10000]

输出: data/raw/<name>.json   （含 alias / source / 统计 / messages，供 agent 读取蒸馏）
零第三方依赖，纯 Python 标准库。
"""
import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter

# Windows 控制台默认 GBK，强制 UTF-8 输出，避免 emoji/中文报 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ---------------- 数据目录（可移植）----------------
def _data_dir(subdir, env_key):
    """环境变量 > 本地/项目 data/ > ~/.openclaw"""
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
RAW_DIR = PERSONAS_DIR.parent / "raw"   # 与 personas 同根

STOP_CHARS = set("的了是你您他她它就都也还不没在有这个们吧吗呢啊呀哦嗯啦嘛啥和与去来说看想知道把给对从被让".replace(" ", ""))


# ---------------- 解析聊天记录 ----------------
def read_text(path: pathlib.Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    sys.exit(f"无法解码文件（尝试了 utf-8/gbk）: {path}")


# 时间戳行: 2024-03-01 10:23:45 [昵称(可选)]
TS_RE = re.compile(
    r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}[\s,T]+\d{1,2}:\d{2}(?::\d{2})?\s*(.*)$"
)
TAIL_ID_RE = re.compile(r"[（(<【\[][^)）>】\]]+[)）>】\]]\s*$")
INLINE_RE = re.compile(r"^\s*(.{1,24}?)\s*[:：]\s*(.+)$")


def clean_speaker(s: str) -> str:
    s = TAIL_ID_RE.sub("", s).strip()
    return s.strip("\"'“”‘’ ")


def parse_chat(text: str):
    """返回 [(speaker, message), ...]。先判定整文件格式，再单一模式解析，
    避免时间戳模式下把消息正文里的 'X: Y' 误判成说话人。"""
    lines = text.splitlines()
    uses_ts = any(TS_RE.match(l) for l in lines)
    pairs = []

    if uses_ts:
        cur, buf = None, []

        def flush():
            nonlocal buf
            if cur and buf:
                msg = " ".join(b.strip() for b in buf if b.strip())
                if msg:
                    pairs.append((cur, msg))
            buf = []

        for line in lines:
            m = TS_RE.match(line)
            if m:
                flush()
                cur = clean_speaker(m.group(1))
            elif cur is not None:
                buf.append(line)
        flush()
    else:
        for line in lines:
            mi = INLINE_RE.match(line)
            if mi:
                sp = clean_speaker(mi.group(1))
                content = mi.group(2).strip()
                if content and not re.match(r"^\d", sp) and sp.lower() not in ("http", "https"):
                    pairs.append((sp, content))
    return pairs


def _first_str(d, keys):
    """按 keys 优先级取第一个非空字符串值；支持 WeChatMsg 嵌套 {sender:{nickname:...}}。"""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for sub in ("nickname", "displayName", "display_name", "name"):
                sv = v.get(sub)
                if isinstance(sv, str) and sv.strip():
                    return sv.strip()
    return ""


def parse_json_chat(data):
    """解析 JSON 聊天导出（微信/QQ 多 schema 兼容）→ [(speaker, message), ...]。"""
    if isinstance(data, dict):
        for key in ("messages", "data", "list", "rows"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    sender_keys = ("senderDisplayName", "displayName", "display_name", "nickname",
                   "sender", "talker", "senderUsername", "name", "from")
    content_keys = ("text", "content", "body", "message", "msg")
    pairs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        speaker = _first_str(item, sender_keys)
        text = _first_str(item, content_keys)
        if speaker and text:
            pairs.append((speaker, text))
    return pairs


# ---------------- 统计特征（作为蒸馏佐证）----------------
CJK_RE = re.compile(r"[一-鿿]+")
WORD_RE = re.compile(r"[A-Za-z0-9]+")
EMOJI_RE = re.compile(
    "[" "\U0001F300-\U0001FAFF" "☀-➿" "]+", flags=re.UNICODE
)


def top_terms(msgs, k=30):
    cnt = Counter()
    for m in msgs:
        for w in WORD_RE.findall(m):
            if len(w) > 1:
                cnt[w.lower()] += 1
        for run in CJK_RE.findall(m):
            for i in range(len(run) - 1):
                g = run[i:i + 2]
                if g[0] not in STOP_CHARS and g[1] not in STOP_CHARS:
                    cnt[g] += 1
    return cnt.most_common(k)


def sample_messages(msgs, budget):
    """超 budget 时确定性等距抽样（不随机，保证可复现）。"""
    if not msgs:
        return []
    total = sum(len(m) for m in msgs)
    if total <= budget:
        return list(msgs)
    out, acc = [], 0
    step = max(1, int(len(msgs) / max(1, budget / (total / len(msgs)))))
    for i in range(0, len(msgs), step):
        if acc + len(msgs[i]) > budget:
            break
        out.append(msgs[i])
        acc += len(msgs[i])
    return out


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="解析聊天记录+统计，输出供 agent 蒸馏的结构化数据（不调模型）")
    ap.add_argument("chatlog", help="聊天记录文件路径（txt 或 json）")
    ap.add_argument("--name", required=True, help="人物英文标识(用作文件名,如 zhangsan)")
    ap.add_argument("--alias", default=None, help="记录里该人的昵称；不填则取出现最多的人")
    ap.add_argument("--budget", type=int, default=10000, help="输出给 agent 的消息字符上限,默认10000")
    args = ap.parse_args()

    chatlog = pathlib.Path(args.chatlog)
    if not chatlog.exists():
        sys.exit(f"聊天记录不存在: {chatlog}")

    if chatlog.suffix.lower() == ".json":
        try:
            pairs = parse_json_chat(json.loads(read_text(chatlog)))
        except json.JSONDecodeError as e:
            sys.exit(f"JSON 解析失败: {e}")
    else:
        pairs = parse_chat(read_text(chatlog))
    if not pairs:
        sys.exit("未解析到任何消息，请检查格式（参考 references/distillation-guide.md）")

    # 说话人统计
    speakers = Counter(s for s, _ in pairs)
    print("识别到的说话人 Top5：")
    for s, c in speakers.most_common(5):
        print(f"  {s}: {c} 条")

    alias = args.alias or speakers.most_common(1)[0][0]
    if args.alias and alias not in speakers:
        sys.exit(f"--alias「{alias}」在记录中未找到。可用: {list(speakers)[:10]}")
    if not args.alias:
        print(f"\n未指定 --alias，自动选择出现最多的说话人：「{alias}」")

    msgs = [m for s, m in pairs if s == alias]
    if len(msgs) < 10:
        print(f"\n[!] 样本偏少（{len(msgs)} 条），蒸馏结果可能不稳定。")

    # 统计
    total_len = sum(len(m) for m in msgs)
    stats = {
        "count": len(msgs),
        "avg_length": round((total_len / len(msgs)) if msgs else 0, 1),
        "emoji": sum(len(EMOJI_RE.findall(m)) for m in msgs),
        "questions": sum(1 for m in msgs if re.search(r"[?？]", m)),
        "top_terms": top_terms(msgs),
    }
    sampled = sample_messages(msgs, args.budget)

    # 输出结构化数据（供 agent 蒸馏）
    payload = {
        "alias": alias,
        "name": args.name,
        "source": str(chatlog),
        "message_count": len(msgs),
        "stats": stats,
        "messages": sampled,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{args.name}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ 已输出结构化数据: {out}")
    print(f"  目标「{alias}」共 {len(msgs)} 条消息（抽样 {len(sampled)} 条给 agent）")
    print(f"  高频词(佐证): {', '.join(w for w,_ in stats['top_terms'][:15])}")
    print("\n下一步：OpenClaw agent 读取该 JSON，按 SKILL.md 蒸馏规范提取 11 维度，")
    print("        填 templates/persona.md → 写 data/personas/<name>.md。")


if __name__ == "__main__":
    main()
