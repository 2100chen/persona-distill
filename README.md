# persona-distill

> OpenClaw / Agent Skill · 人物风格蒸馏复刻

导入某人的**真实聊天记录**（txt 或 JSON），蒸馏其语言风格、口头禅、回复逻辑、语气、行事偏好，生成一份标准化「人格配置」，让 agent 用此人的口吻对话。支持多人物保存与一键切换。

**不调用任何模型 API，零第三方依赖。** 脚本只做解析+统计；蒸馏由 OpenClaw agent（自带模型）按 SKILL.md 完成。

---

## 它怎么工作

```
聊天记录 (txt/json)
    │  distill.py（纯标准库，不调模型）
    ▼
data/raw/<name>.json  （目标人物消息 + 高频词/emoji/问句统计）
    │  OpenClaw agent 读取，按 SKILL.md 的 11 维蒸馏规范（agent 自带模型）
    ▼
data/personas/<name>.md  （标准化人格配置）→ switch_persona 激活 → agent 采用此口吻
```

- **distill.py**：解析聊天记录（txt 时间戳/行内 + JSON 多 schema），过滤目标人物，统计特征，输出结构化 JSON。**纯 Python 标准库，不调任何 API。**
- **agent 蒸馏**：OpenClaw agent 读取 JSON，用自己的模型按 SKILL.md 里的 11 维规范提炼人格画像，填模板生成 persona.md。

## 与同类项目对比

| 项目 | 怎么拿到人物素材 | 谁做蒸馏 | 亮点 | 短板 |
|---|---|---|---|---|
| colleague / dot-skill | 飞书/钉钉/Slack 自动抓取 + 文件 + 字幕 | 宿主 agent | 采集最全 | 配置繁琐；微信没真做 |
| nuwa-skill | 只搜公开网络，不碰私聊 | 宿主 agent | 公众人物、有质量校验 | 只适合名人；成本高 |
| ex-skill | 微信/QQ 导出文件 + 截图 + 照片 | 宿主 agent | 情感关系、安全细 | 微信需第三方工具解密 |
| boss-skills | 微信/飞书/邮件 + 公开学术资料 | 宿主 agent | 决策结构化、可打分 | 解析粗糙、偏学术英文 |
| chat2work | 桌面应用直读微信数据库 | 宿主 agent | 免导出、可溯源 | 仅微信、依赖桌面应用 |
| **persona-distill（本项目）** | **用户给聊天记录（txt/json）** | **OpenClaw agent** | **最简单、零依赖、不调 API** | 不做自动采集 |

## 功能特性

- **多格式聊天记录**：txt（时间戳 / `昵称: 内容`）+ JSON（WeChatMsg/留痕/QQ exporter 多 schema 自动识别）；UTF-8/GBK 自动识别
- **11 维度人格画像**：语言风格、口头禅、句式、语气情绪、回复逻辑、标点 emoji、开场收尾、价值观/雷区、风格锚点（逐字原话）、Do/Don't、诚实边界
- **有据可查**：口头禅与锚点逐字引用自真实记录，不编造；高频词统计交叉佐证
- **零依赖**：distill.py 纯 Python 标准库，无需 pip 装任何包，无需 API key
- **多人物 + 一键切换**：每个人物一份配置；`ACTIVE.md` 标记当前激活
- **标准 Skill 格式**：SKILL.md + 脚本，OpenClaw / 任意 Agent Skills 运行时可加载

## 安装

```bash
npm install github:2100chen/persona-distill
# 或
git clone https://github.com/2100chen/persona-distill.git
```

## 前置要求

- **Python 3.10+**（跑 distill.py，纯标准库，无需 pip 安装任何依赖）
- **OpenClaw**（agent 用其自带的模型做蒸馏）

> 不需要任何模型 API key——蒸馏由 OpenClaw agent 完成，不是脚本调 API。

## 用法

### 在 OpenClaw 里（推荐）

对 agent 说「蒸馏老王的聊天风格」→ agent 自动：
1. 跑 `distill.py` 解析记录、输出 `data/raw/<name>.json`
2. 读取 JSON，按 SKILL.md 蒸馏 11 维度，生成 `data/personas/<name>.md`
3. 回报画像给你确认，可选激活

### 命令行（独立使用）

```bash
# 1. 提取数据（不调模型）
python scripts/distill.py <聊天记录文件> --name <英文标识> --alias <记录里的昵称>

# 2. 把 data/raw/<name>.json 喂给你自己的 LLM，按 SKILL.md 的蒸馏规范生成 persona.md
```

### 切换 / 列出人格

```bash
python scripts/switch_persona.py <name>     # 激活：之后 agent 回复采用此口吻
python scripts/switch_persona.py --status   # 查看当前
python scripts/switch_persona.py --clear    # 取消
python scripts/list_personas.py             # 列出所有
```

## License

MIT License
