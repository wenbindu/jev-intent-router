# Jev Intent Router

使用 Jev `choice` 路由用户输入，再交给对应 Agent。页面左侧是对话列表，中间显示命中的 Agent 与调用延迟、耗时和 token 用量，最右侧常驻展示主消息列表，并自动滚动到最新内容。

## 运行

项目使用 FastAPI 和 `uv`。前端静态页面与 API 由同一个端口提供，无需单独启动前端服务。

```sh
uv sync
cp config.example.yaml config.local.yaml
# 在 config.local.yaml 填写 jev、qwen、deepseek 的 api_key
uv run python -m intent_router
```

打开 `http://127.0.0.1:3000/route`。端口在 `config.local.yaml` 的 `server.port` 中配置，也可临时覆盖：

```sh
PORT=3107 uv run python -m intent_router
```

本地配置统一使用忽略版本控制的 `config.local.yaml`。`config.example.yaml` 和 `tools.yaml` 是不含密钥的配置模板及路由标准。

Qwen 的 `base_url` 填 OpenAI 兼容协议基础地址，例如 `.../compatible-mode/v1`；程序追加 `/chat/completions`。DeepSeek 同样使用 OpenAI 兼容的流式 Chat Completions。Jev 的 `base_url` 追加 `/systemone`。

## 架构

```text
浏览器主消息列表 → Jev choice → Agent 注册表
                               ├─ chat → Qwen 流式回答
                               ├─ set_volume → DeepSeek 提参 → 设置虚拟音量 → DeepSeek 回答
                               ├─ adjust_volume → DeepSeek 提参 → 相对调节虚拟音量 → DeepSeek 回答
                               ├─ shutdown → DeepSeek 提参 → 虚拟关机命令 → DeepSeek 回答
                               ├─ play_song → DeepSeek 提参 → 虚拟播放命令 → DeepSeek 回答
                               ├─ song_control → DeepSeek 提参 → 下一首/重播/停止/退出 → DeepSeek 回答
                               ├─ handle_user_goodbye → DeepSeek 提参 → 告别并结束会话
                               └─ get_weather → DeepSeek 提参 → 固定天气样本 → DeepSeek 回答
```

Jev 只决定 Agent，不解析参数。`intent_router/agents/registry.py` 注册路由与 Agent 实例；每个 Agent 文件负责自己的上下文范围、参数约束、工具 schema 和执行逻辑。公共 `ToolAgent` 只负责“解析 → 执行 → 回答”的流式流程。新增 Agent 时增加 `tools.yaml` 的 Jev 标准、Agent 类和注册项即可。每个 Agent 可独立指定模型服务；当前普通聊天用 Qwen 3.7 Flash，其余用 DeepSeek V4.1 Flash。

浏览器仍保留完整的单一消息列表。服务端按用户轮次读取它：Jev 得到最近六轮的用户输入、命中的 Agent 和实际工具结果摘要；工具 Agent 只取相关路径的完整 `user → assistant.tool_calls → tool → assistant` 轮次，并把当前 query 放在最后。两个音量 Agent 共享最近三轮音量操作和最新的虚拟设备状态，所以“设为 35 → 再大点”得到 35 → 45。歌曲播放与歌曲控制共享播放器历史。天气、关机、告别各自控制历史范围；聊天 Agent 使用自然语言 `user/assistant` 历史。

对照所给的工具配置：具体音量与相对调节已拆开；增加了歌曲控制和告别 Agent；播放歌曲允许只提供歌手、情绪、语言或角色，不强制指定歌名；天气支持可选地点与语言，仍只返回 mock 样本。关机与普通聊天沿用项目原有要求。`set_volume` 接受用户原始整数并在执行器中压缩到 0–100，例如 160 → 100。相对调节额外保留 `unmute`。告别 Agent 的最终事件携带 `ends_session: true`，下一条消息开始新会话。

工具解析请求只提供选中 Agent 的一个函数，并设置 `tool_choice: "required"`。执行结果作为 `assistant.tool_calls` 与 `tool` 消息写回主列表。最终回答调用设置 `tool_choice: "none"`，避免再次调用工具。如果最终回答仍设置 `required`，模型会被强制继续调用函数，无法直接结束回答；如果省略 `tool_choice`，模型可能自行决定再次调用函数，所以这里显式禁止。DeepSeek 请求关闭思考模式。

所给告别工具的 `strict: true` 没有直接复制到默认 DeepSeek 地址：DeepSeek 的严格工具模式需要 `/beta` 地址，且对象的所有字段都必须列入 `required`；歌曲的可选字段也不满足这一限制。当前由执行器校验参数，`tool_choice: "required"` 仍会强制调用选中的函数。

音量、关机和播放仅向虚拟设备下发，不改变电脑状态。天气 Agent 返回固定样本（27°C、湿度 50%），回答需说明不是实时数据。浏览器消息列表包含 `user`、`assistant`、`assistant.tool_calls` 和 `tool`，刷新后清空。

## 日志与验证

Loguru 向标准输出打印每次 Jev/LLM 调用：发出前显示 `REQUEST` 和完整 `request body`，返回后显示 `RESPONSE`、HTTP 状态、耗时和 `response body`。流式响应在终端显示最终拼接的正文、工具调用、用量和结束原因；逐块 SSE 原文仍保存在 `.logs/exchanges-YYYY-MM-DD.jsonl` 的 `response_body` 中，拼接结果保存在 `response_assembled` 中。终端还打印 Jev 选中的路由上下文、Agent 实际纳入的消息以及工具调用与结果。相同一轮的日志共用 `trace_id`，可用 `jq` 筛选。日志不包含 API Key 或 Authorization 头，但包含用户文本；文件以私有权限创建。

```sh
uv run pytest -q
```
