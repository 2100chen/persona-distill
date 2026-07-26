#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona-distill · distill.py
解析聊天记录 -> 过滤目标人物 -> 统计特征 -> 输出结构化数据（供 OpenClaw agent 蒸馏）。

【本脚本不调用任何模型 API】。真正的蒸馏（提取 11 个维度、生成 persona.md）
由 OpenClaw 的 agent（它自带模型）读取本脚本输出的 JSON、按 SKILL.md 的蒸馏规范完成。

输入（二选一）：
  1) 微信导出「标准目录」(WeChatDataAnalysis 等导出的文件夹)：指向目录即可，
     自动发现 conversations/*/messages.json，单聊自动锁定对方(isSent=false)。
  2) 单个聊天记录文件（txt 或 json，多 schema 兼容）。

用法:
  # 目录（推荐，装完即用）
  python distill.py <导出目录> [--name <英文标识>] [--conv <序号|显示名|wxid>]
  # 单文件（向后兼容）
  python distill.py <聊天记录文件> --name <英文标识> [--alias <记录里的昵称>] [--budget 10000]

--name 不填时，按对方昵称自动派生文件名安全的短名。

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


# ---------------- 文本读取 ----------------
def read_text(path: pathlib.Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    sys.exit(f"无法解码文件（尝试了 utf-8/gbk）: {path}")


def read_json(path: pathlib.Path):
    return json.loads(read_text(path))


# ---------------- 单文件解析：txt ----------------
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


# ---------------- 单文件解析：json ----------------
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


# ---------------- 目录解析：WeChatDataAnalysis 标准导出 ----------------
# 标准目录结构：
#   <root>/manifest.json            # account(本人wxid) / stats
#   <root>/conversations/<会话>/
#       meta.json                   # username(对方wxid) / displayName / isGroup / messageCount
#       messages.json               # messages[]：isSent / senderUsername / senderDisplayName / content / renderType / type
# 单聊：对方消息 isSent==false；本人 isSent==true。蒸馏对方 → 取 isSent==false 的文本。
TEXT_RENDER = {"text"}
TEXT_TYPE = {1}  # 微信 type=1 即文本


def discover_conversations(root: pathlib.Path):
    """读 manifest.json(取 account) + conversations/*/meta.json → (account, [conv_info])。"""
    account = None
    manifest = root / "manifest.json"
    if manifest.exists():
        try:
            account = read_json(manifest).get("account")
        except (json.JSONDecodeError, OSError):
            pass
    conv_root = root / "conversations"
    convs = []
    if conv_root.is_dir():
        for meta_path in sorted(conv_root.glob("*/meta.json")):
            try:
                meta = read_json(meta_path)
            except (json.JSONDecodeError, OSError):
                continue
            convs.append({
                "dir": meta_path.parent,
                "displayName": (meta.get("displayName") or meta.get("username") or "").strip() or "(未命名)",
                "username": meta.get("username"),
                "isGroup": bool(meta.get("isGroup", False)),
                "messageCount": meta.get("messageCount"),
            })
    return account, convs


def select_conversation(convs, selector):
    """按 序号 / wxid 精确 / 显示名片段 选会话；未给且仅 1 个 → 自动选；歧义 → None。"""
    if not selector:
        return convs[0] if len(convs) == 1 else None
    if selector.isdigit():
        idx = int(selector) - 1
        if 0 <= idx < len(convs):
            return convs[idx]
    for c in convs:
        if selector == c["username"] or selector in (c["displayName"] or ""):
            return c
    return None


def load_conversation_pairs(conv, account):
    """读会话 messages.json → (pairs, is_group)。
    单聊：只取对方文本(isSent==false)，speaker 统一为会话显示名（避免 senderDisplayName 变体）。
    群聊：取所有文本，speaker = senderDisplayName。"""
    data = read_json(conv["dir"] / "messages.json")
    raw = data.get("messages", []) if isinstance(data, dict) else []
    is_group = conv["isGroup"]
    display = conv["displayName"]
    pairs = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        render = item.get("renderType")
        mtype = item.get("type")
        is_text = render in TEXT_RENDER or mtype in TEXT_TYPE or render is None
        if not is_text:
            continue
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if not is_group:
            if item.get("isSent"):       # 单聊跳过本人消息
                continue
            speaker = display            # 统一为对方显示名
        else:
            speaker = (item.get("senderDisplayName") or "").strip() or display
        pairs.append((speaker, content))
    return pairs, is_group


def parse_export_folder(root: pathlib.Path, conv_selector, alias_hint):
    """解析标准导出目录 → (pairs, alias_default, conv_info)。"""
    account, convs = discover_conversations(root)
    if not convs:
        sys.exit(
            f"目录里没找到 conversations/*/meta.json，不像微信标准导出：{root}\n"
            f"（若是单文件，请直接传文件路径而非目录。）"
        )
    print(f"导出目录: {root}")
    if account:
        print(f"  账号(本人): {account}")
    print(f"  发现 {len(convs)} 个会话：")
    for i, c in enumerate(convs, 1):
        flag = "群聊" if c["isGroup"] else "单聊"
        print(f"  [{i}] {c['displayName']}  ({flag}, {c['messageCount']} 条)  wxid={c['username']}")

    conv = select_conversation(convs, conv_selector)
    if conv is None:
        if conv_selector:
            sys.exit(f"\n--conv「{conv_selector}」未匹配到任何会话。可用：序号 / 显示名片段 / wxid（见上方清单）")
        sys.exit(
            "\n有多个会话，请用 --conv 指定：序号 / 显示名片段 / wxid\n"
            "例如 --conv 1   或   --conv 蛋仔   或   --conv wxid_xxx"
        )

    pairs, is_group = load_conversation_pairs(conv, account)
    conv_info = {
        "displayName": conv["displayName"],
        "username": conv["username"],
        "isGroup": is_group,
        "dir": str(conv["dir"]),
        "account": account,
    }
    if is_group:
        print(f"\n选中群聊「{conv['displayName']}」：请用 --alias 指定要蒸馏的发言者。")
        return pairs, None, conv_info
    print(f"\n选中单聊「{conv['displayName']}」：自动取对方消息（isSent=false）。")
    return pairs, conv["displayName"], conv_info


# ---------------- 文件名 slug ----------------
def slugify(text: str) -> str:
    """从显示名/昵称派生文件名安全的短 slug：取末尾空白分隔 token，去 emoji/标点，截断≤12。"""
    if not text:
        return "persona"
    parts = text.strip().split()
    token = parts[-1] if parts else text.strip()
    cleaned = re.sub(r"[^\w]+", "", token, flags=re.UNICODE).strip()
    return cleaned[:12] if cleaned else "persona"


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
    ap = argparse.ArgumentParser(
        description="解析聊天记录（微信导出目录 / txt / json）+ 统计，输出供 agent 蒸馏的结构化数据（不调模型）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  目录:  python distill.py \"E:\\\\蛋仔的聊天记录\" --name danzai\n"
               "  文件:  python distill.py 聊天.txt --name laowan --alias 老王",
    )
    ap.add_argument("chatlog", help="聊天记录：微信导出目录，或单个 txt/json 文件")
    ap.add_argument("--name", default=None, help="人物英文标识(文件名)；不填则按对方昵称自动命名")
    ap.add_argument("--alias", default=None, help="目标人物在记录里的昵称；群聊必填，单聊/单文件可省略")
    ap.add_argument("--conv", default=None, help="导出目录里选会话：序号 / 显示名片段 / wxid（多会话时用）")
    ap.add_argument("--budget", type=int, default=10000, help="输出给 agent 的消息字符上限,默认10000")
    args = ap.parse_args()

    chatlog = pathlib.Path(args.chatlog)
    if not chatlog.exists():
        sys.exit(f"路径不存在: {chatlog}")

    conv_info = None
    alias_default = None
    if chatlog.is_dir():
        pairs, alias_default, conv_info = parse_export_folder(chatlog, args.conv, args.alias)
    elif chatlog.suffix.lower() == ".json":
        try:
            pairs = parse_json_chat(read_json(chatlog))
        except json.JSONDecodeError as e:
            sys.exit(f"JSON 解析失败: {e}")
    else:
        pairs = parse_chat(read_text(chatlog))
    if not pairs:
        sys.exit("未解析到任何消息，请检查格式（参考 references/distillation-guide.md）")

    # 说话人统计
    speakers = Counter(s for s, _ in pairs)
    print("\n识别到的说话人 Top5：")
    for s, c in speakers.most_common(5):
        print(f"  {s}: {c} 条")

    alias = args.alias or alias_default or (speakers.most_common(1)[0][0] if speakers else None)
    if alias is None:
        sys.exit("无法确定目标人物，请用 --alias 指定。")
    if args.alias and alias not in speakers:
        sys.exit(f"--alias「{alias}」在记录中未找到。可用: {list(speakers)[:10]}")
    if not args.alias and not alias_default and speakers:
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

    name = args.name or slugify(alias)

    # 输出结构化数据（供 agent 蒸馏）
    if conv_info:
        export_format = "wechat-folder"
    elif chatlog.suffix.lower() == ".json":
        export_format = "json"
    else:
        export_format = "txt"
    payload = {
        "alias": alias,
        "name": name,
        "source": str(chatlog),
        "export_format": export_format,
        "message_count": len(msgs),
        "stats": stats,
        "messages": sampled,
    }
    if conv_info:
        payload["conversation"] = conv_info
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{name}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ 已输出结构化数据: {out}")
    print(f"  目标「{alias}」共 {len(msgs)} 条消息（抽样 {len(sampled)} 条给 agent）")
    print(f"  高频词(佐证): {', '.join(w for w, _ in stats['top_terms'][:15])}")
    print("\n下一步：OpenClaw agent 读取该 JSON，按 SKILL.md 蒸馏规范提取 11 维度，")
    print("        填 templates/persona.md → 写 data/personas/<name>.md。")


if __name__ == "__main__":
    main()
