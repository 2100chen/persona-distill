---
name: persona-distill
description: |
  人物风格蒸馏与复刻。导入某人的聊天记录（微信/QQ/飞书导出的 txt，或“昵称: 内容”格式），
  自动分析并蒸馏其语言风格、口头禅、回复逻辑、行事偏好、语气情绪、标点与 emoji 习惯，
  生成标准化人物配置文件；之后 OpenClaw 可模仿该人物口吻进行对话、处理事务。
  支持多人物保存与快速切换激活人格。当用户说“蒸馏某人风格 / 复刻人物 / 模仿 XX 说话 /
  导入聊天记录生成人格 / 切换人格 / 当前用谁的声音 / persona distill”等时使用。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: 2.0.0
  author: 2100chen
---

# Persona-Distill：人物风格蒸馏复刻

把一个人的真实聊天记录，蒸馏成一份 OpenClaw 可直接装载的「人格配置」，让 agent 用这个人的口吻说话。**独立运行，不依赖任何其它 skill，也不调用任何模型 API——蒸馏由 OpenClaw agent（你）自己完成。**

## Outcome Contract

- **Outcome**：`data/personas/<人物>.md` —— 一份有证据支撑的标准化人格配置，可被 agent 读取并模仿。
- **Done when**：人物配置文件已生成、用户已看过摘要并确认、（可选）已切换为激活人格。
- **Evidence**：源聊天记录路径、`data/raw/<name>.json`（提取的结构化数据）、蒸馏出的样本原话、生成的配置文件路径。
- **Output**：先回报蒸馏摘要给用户确认，再写文件；不要默默覆盖已有配置。

## 核心工作流

1. **Pre-flight（先问清楚再动手）**
   - 聊天记录在哪？要用户给文件路径，或直接粘贴文本（保存到 `data/raw/<人物>.txt`）。
   - 目标人物在记录里叫什么（`--alias`）？如果记录里有多人，必须指明蒸馏谁。
   - 没有真实聊天记录 → **停下**，不要凭空编造人格。这是硬规则。

2. **提取数据（脚本做，不调模型）**：运行 `distill.py`，它只解析+统计，输出结构化数据
   ```bash
   python scripts/distill.py <聊天记录 txt/json> \
     --name <人物标识,英文短词如 zhangsan> --alias <记录里的昵称> [--budget 10000]
   ```
   - 输出 `data/raw/<name>.json`：含 alias、message_count、stats（平均长度/高频词/emoji/问句）、messages（抽样后的目标人物发言）。
   - `--name` 用作文件名；`--alias` 是记录里该人的实际称呼（不填则自动取最活跃者，脚本会打印 Top5 供核对）。
   - **此步不调用任何模型 API**，纯 Python 标准库，零依赖。

3. **蒸馏（agent 自己做，用你自带的模型）**：读取上一步的 JSON，按下方【蒸馏规范】提取人物画像
   - Read `data/raw/<name>.json`，以其中的 `messages`（目标人物真实发言）和 `stats`（高频词等佐证）为唯一依据。
   - 按【蒸馏规范】的 11 个维度逐项提炼，填入 `templates/persona.md` 的对应位置。
   - 写出 `data/personas/<name>.md`。已存在同名且用户未确认覆盖 → 停下问用户。

4. **确认**：把蒸馏出的「一句话画像 + 口头禅 + 风格锚点原话」回报给用户，问是否需要调整。
   - 用户若补充修正（“他其实更毒舌”），用 Edit 改配置对应小节，不必重跑。

5. **切换（可选）**：设为当前激活人格
   ```bash
   python scripts/switch_persona.py <name>     # 激活
   python scripts/switch_persona.py --status   # 看当前
   python scripts/switch_persona.py --clear    # 取消
   ```
   激活后 `data/personas/ACTIVE.md` 被更新，agent 后续回复采用此人格口吻。

6. **以人格对话**：激活人格后，**后续所有回复都要采用该人格的风格**（语气、口头禅、句式、emoji、行事逻辑），直到用户 `--clear`。回复前先 Read `data/personas/ACTIVE.md` 的「如何模仿」小节。
   - 人格只影响「风格与口吻」，不要伪造该人的私人事实（不知道就说不知道）。

## 蒸馏规范（给 agent，在第 3 步执行）

以 `data/raw/<name>.json` 的 `messages` 和 `stats` 为唯一依据，提炼以下内容（对应 `templates/persona.md` 的占位符）：

| 维度 | 说明 |
|---|---|
| summary | 一句话画像（≤40 字） |
| mimic_instruction | 给 agent 的直接指令：如何模仿此人说话（2-4 句具体可执行） |
| language_style | 语言风格：正式/随意、书面/口语、简洁/啰嗦 |
| catchphrases | 口头禅/高频词（**逐字原样**，≤8 个，优先用 stats.top_terms 里的真实高频词） |
| sentence_patterns | 句式习惯：疑问多不多、是否省略主语、反问等 |
| tone_emotion | 语气与情绪基调：温和/毒舌/急躁/沉稳 |
| reply_logic | 回复逻辑与处事偏好：先共情再建议？直接给结论？ |
| punctuation_emoji | 标点与 emoji 习惯 |
| openings / closings | 典型开场 / 收尾（**逐字**，各 ≤4） |
| values_attitude | 价值观 / 态度 / 雷区 |
| sample_lines | 风格锚点：最具代表性的原话（**逐字引用**，3-5 句，必须来自 messages） |
| dos / donts | 模仿时该做 / 不该做（各 3-6 条） |
| honest_boundary | 诚实边界/局限（3-5 条，如：仅反映聊天风格非完整本人；私人心境不可知；样本有限） |

**硬规则**：
- 口头禅、开场、收尾、锚点原话必须**逐字引用**自 messages，不得改写或编造。
- 证据不足的字段写「证据不足」，绝不臆测。
- stats.top_terms 是高频词佐证，可交叉核对模型结论，避免凭空编口头禅。

## 多人物管理

```bash
python scripts/list_personas.py   # 列出所有已蒸馏人格 + 当前激活
```
- 每个人物一个 `data/personas/<name>.md`，互不覆盖。
- 同时只有一个激活人格（`ACTIVE.md`）。

## Hard Rules

- **无记录不蒸馏**：没有真实聊天记录，绝不生成人格配置。证据不足的字段写「证据不足」，不要编。
- **原话锚点**：配置里的「风格锚点」必须是从记录里摘的真实原话，逐字引用，便于核对。
- **文件边界**：人格配置只写 `data/personas/`；提取的中间数据写 `data/raw/`。已存在同名配置且用户未确认 → 停下问。
- **隐私**：聊天记录含真实姓名/隐私，回显时只摘必要原话，不要整段倒出原始记录；`data/` 已 gitignored。
- **切换的影响范围**：激活人格会改变**之后所有回复**的口吻，切换前提醒用户。

## 文件结构

```
├── SKILL.md                 # 本文件（含蒸馏规范）
├── scripts/
│   ├── distill.py           # 解析 → 统计 → 输出 data/raw/<name>.json（不调模型）
│   ├── switch_persona.py    # 激活 / 状态 / 清除
│   ├── list_personas.py     # 列出人格
│   └── requirements.txt     # 无第三方依赖（纯标准库）
├── templates/
│   └── persona.md           # 标准化人物配置模板（agent 填充）
└── references/
    └── distillation-guide.md # 蒸馏维度说明 + 支持的记录格式 + 调优技巧
```

## Gotchas

| 发生过的问题 | 规则 |
|---|---|
| 没给聊天记录就编了一个人格 | 无记录不蒸馏；Pre-flight 先确认文件 |
| `--alias` 写错，蒸馏成了别人的风格 | 脚本会先打印识别到的说话人 Top5，对不上立刻停 |
| 中文 txt 是 GBK 编码读取乱码 | 脚本先 UTF-8 再回退 GBK |
| 配置里口头禅是编的、原记录里没有 | 只引用真实出现的词，锚点必须逐字原话；用 stats.top_terms 交叉核对 |
| 切了人格忘了切回来，之后所有回复都很怪 | 切换时明确告知用户「现在以 X 的口吻回复，--clear 恢复」 |

## 输出

蒸馏完，回报：人物标识、消息条数、一句话画像、3 条口头禅、3 条锚点原话、配置文件路径，
以及「是否切换为激活人格」的询问。不要默默做完全程。
