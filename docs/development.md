# Development guide

[← README](../README.md) · [简体中文](development.zh-CN.md)

## Architecture

```text
Browser: one shared messages list + task_state
  → Jev: use history and state to select one route with a confidence score
  → Check the route threshold
      → Agent: Qwen streaming conversation
      → Tool: DeepSeek arguments → execution → DeepSeek response
  → NDJSON: route, tool results, text, timings, and state
```

- All conversational agents share the message history. `_route` is display metadata and is removed before messages are sent to models.
- The state machine stores only `current_task`. Device state is reconstructed from successful tool results; failed actions do not overwrite prior state.
- Confidence must be **strictly greater than** the route threshold. Otherwise, the current conversational agent—or the chat agent—handles the fallback while preserving the current task.
- Tool state is committed as soon as execution succeeds, even if the subsequent response fails.
- Language switching translates the interface and explanatory text. User messages, model replies, and raw JSON retain their original content. The browser remembers the language choice.

See [Session and state transitions](session-binding-state-machine.md) for implementation details (in Chinese).

## Project structure

```text
intent_router/
  main.py             HTTP endpoints and static frontend
  service.py          Turn orchestration and streaming events
  providers.py        Jev / Chat Completions protocols
  state.py, device.py  Persistent tasks and device properties
  conversation.py     Shared history and tool-specific history views
  messages.py         Input validation
  agents/             Agent prompts, tool handlers, and registry
static/               Dashboard, animated paths, and UI translations
config.example.yaml   Server, model, and default threshold settings
tools.yaml            Routing criteria and persistent_task settings
tests/                Regression tests with simulated model responses
```

## Configuration and extension

- Jev requests append `/systemone` to its `base_url`. Qwen and DeepSeek use OpenAI-compatible base URLs with `/chat/completions` appended.
- Route thresholds default to `0.5`. Dashboard edits are saved atomically to `config.local.yaml`. Legacy route names are migrated automatically.
- To add a capability, update `routes.py`, `tools.yaml`, `agents/registry.py`, and the default thresholds. Conversational prompts live in `agents/prompts.py`.
- UI translations live in `static/i18n.js`; translated routing descriptions and prompts live in `static/route-translations.js`. Translations are matched against the original text. When that text changes, the original is displayed instead of an outdated translation.
- Pages and static assets require cache revalidation. Versioned resource URLs bypass older modules already cached before an upgrade.

## Development and verification

```sh
uv run pytest -q
```

Tests do not make live model calls. Interactive model testing requires configured credentials; Jev's routing accuracy needs separate evaluation with real model responses.

Logs are written to the terminal and `.logs/exchanges-YYYY-MM-DD.log`. A shared `trace_id` connects requests, routing decisions, and results. Logs exclude authentication headers but contain full conversation and tool data. Log files are created with private permissions.

## Current limitations

- Sessions live only in page memory. Reloading or clearing the page resets them; there is no server-side persistence or automatic summarization.
- Requests accept up to 80 messages, and agent responses are capped at 4,096 tokens. Long conversations are not automatically truncated or compressed.
- Each turn selects one route; compound actions are not implemented. State and confidence thresholds cannot guarantee correct interpretation of ambiguous follow-ups such as “another one.”
- Tool argument extraction requires calling the selected function. Evaluation of contextual ambiguity and mechanisms for declining execution still need further work.
