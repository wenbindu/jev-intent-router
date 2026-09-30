# Jev Intent Router

[English](README.md) | **简体中文**

一个可观察的对话路由实验项目：Jev 选择路径，Qwen 驱动 6 个对话 Agent，DeepSeek 提取工具参数并生成执行结果回复。

`/route` 提供单页工作台：聊天及调用轨迹、Agent / Tools 路由、Session 状态及主消息列表。支持中文 / EN 界面、路由阈值编辑和金色流动路径。

## 演示

[▶ 观看演示视频](demo.mp4)

## 快速开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。前端与 API 由同一个 FastAPI 服务提供，无需 Node.js 或前端构建。

```sh
uv sync --locked
cp config.example.yaml config.local.yaml
# 在 config.local.yaml 中填写 jev / qwen / deepseek 的 api_key
uv run python -m intent_router
```

默认打开 <http://127.0.0.1:3000/route>。端口可在 `server.port` 配置，或临时覆盖：

```sh
PORT=3107 uv run python -m intent_router
```

`config.local.yaml`、环境文件、日志和浏览器测试产物均由 `.gitignore` 排除。提交配置只修改无密钥的 `config.example.yaml`。

## 能力

| 类型 | 路由 |
| --- | --- |
| 对话 Agent | `agent_roleplay`、`agent_english`、`agent_fitness`、`agent_nutrition`、`agent_story`、`agent_chat` |
| 工具 | `tool_volume_set`、`tool_volume_adjust`、`tool_shutdown`、`tool_weather`、`tool_song_play`、`tool_song_control`、`tool_goodbye` |

六个 Agent 和歌曲播放属于**持久任务**；其余为**瞬时任务**。瞬时任务执行后保留原任务背景。设备音量与静音属性独立于当前任务。

音量、关机与音乐仅模拟命令，不操作宿主机；天气返回固定 mock 样本。告别成功后，下一轮开始新会话。

## 架构

```text
浏览器：唯一的 messages + task_state
  → Jev：结合历史及状态，返回单条路由与置信度
  → 阈值判断
      → Agent：Qwen 流式对话
      → Tool：DeepSeek 提参 → 执行 → DeepSeek 回复
  → NDJSON：路由、工具结果、文本、耗时与状态
```

- 主消息列表由所有 Agent 共享；`_route` 仅用于展示，调用模型前过滤。
- 状态机只保存 `current_task`。设备 JSON 从成功工具结果重建，失败操作不会覆盖先前状态。
- 置信度须**严格大于**路由阈值。否则由当前 Agent 或闲聊 Agent 澄清，并保持原任务。
- 工具执行成功即提交状态，即使后续回复失败也保留执行结果。
- 语言切换只改变界面与说明文本，用户消息、模型回复和原始 JSON 保留原文。选择保存在浏览器中。

详见 [Session 与状态转移](docs/session-binding-state-machine.md)。

## 目录

```text
intent_router/
  main.py             HTTP 接口与前端静态资源
  service.py          单轮编排与流式事件
  providers.py        Jev / Chat Completions 协议
  state.py, device.py  持久任务及设备属性
  conversation.py     主消息列表与工具历史视图
  messages.py         输入校验
  agents/             Agent prompt、工具执行器及注册表
static/               页面、流动连线和中英文文案
config.example.yaml   服务、模型及默认阈值
tools.yaml            路由标准与 persistent_task 配置
tests/                使用模拟模型响应的回归测试
```

## 配置与扩展

- Jev `base_url` 追加 `/systemone`；Qwen / DeepSeek 使用 OpenAI 兼容基础地址，追加 `/chat/completions`。
- 阈值默认 `0.5`。页面编辑后原子保存到 `config.local.yaml`，旧路由名称自动迁移。
- 新增能力时同步修改 `routes.py`、`tools.yaml`、`agents/registry.py` 和默认阈值；对话提示词在 `agents/prompts.py`。
- 界面翻译在 `static/i18n.js`，路由说明译文在 `static/route-translations.js`。译文按原文匹配，原文改变时展示原文，避免显示过期翻译。
- 页面及静态资源强制缓存校验；资源版本号用于避开升级前已经缓存的旧模块。

## 开发与验证

```sh
uv run pytest -q
```

测试无需真实模型调用。浏览器联调需要配置模型；真实 Jev 的语义准确率需单独评测。

日志写入终端与 `.logs/exchanges-YYYY-MM-DD.log`，按 `trace_id` 关联请求、路由判断和结果。日志不记录认证头，但含完整对话及工具数据；日志文件以私有权限创建。

## 当前限制

- Session 仅存在本页内存中；刷新或清空会重置，无服务端持久化和自动摘要。
- 每次请求最多 80 条消息，Agent 回答上限 4096 tokens；尚未自动截断或压缩长对话。
- 每轮只处理一条路由，未实现复合动作。状态和阈值无法保证消除“换一个”等跨场景误判。
- 工具提参强制调用选中的函数，仍需完善上下文歧义评测与拒绝执行机制。
