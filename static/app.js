// Browser UI served by FastAPI; route labels and models come from /api/status.
import { createFlowLines } from "./flow-lines.js?v=20260930-2";
import { bind, unbind, t, translatePage } from "./i18n.js?v=20260930-2";
const statusData = await fetch("/api/status").then((response) => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).catch((error) => {
  bind(document.getElementById("connection"), "● 服务未连接");
  document.getElementById("connection").classList.add("bad");
  document.getElementById("send").disabled = true;
  throw error;
});
const routes = Object.keys(statusData.routes);
const routeConfig = statusData.routes;
const $ = (id) => document.getElementById(id);
const form = $("composer");
const input = $("input");
const send = $("send");
const cancel = $("cancel");
const messagesEl = $("messages");
const routesEl = $("routes");
const timingsEl = $("timings");
const history = [];
let taskState = { current_task: "agent_chat" };
let deviceState = { volume: 50, muted: false };
let sessionEnded = false;
let busy = false;
let controller = null;
let currentRoute = null;
let turnUsage = { input: 0, output: 0 };
let taskChanges = [];
let lastOutcome = "等待输入";
const symbols = { agent_chat: "◌", agent_story: "▤", agent_roleplay: "♜", agent_english: "Aa", agent_fitness: "↗", agent_nutrition: "♧", tool_volume_set: "◖", tool_volume_adjust: "◖", tool_shutdown: "⏻", tool_weather: "☁", tool_song_play: "♫", tool_song_control: "♫", tool_goodbye: "↗" };
const agentNames = Object.fromEntries(routes.map((route) => [route, routeConfig[route].agent.name]));
for (const route of routes) {
  const card = document.createElement("div");
  card.className = "route-card";
  card.dataset.route = route;
  card.title = route;
  const symbol = document.createElement("span");
  symbol.className = "route-symbol";
  symbol.textContent = symbols[route];
  const copy = document.createElement("div");
  copy.className = "route-copy";
  const title = document.createElement("strong");
  const name = document.createElement("span");
  bind(name, agentNames[route]);
  title.append(name);
  const taskKind = document.createElement("span");
  const persistent = routeConfig[route].agent.persistent_task;
  taskKind.className = `task-kind ${persistent ? "persistent" : "transient"}`;
  bind(taskKind, persistent ? "持久任务" : "瞬时任务");
  taskKind.title = `persistent_task: ${persistent}`;
  const sub = document.createElement("small");
  bind(sub, "{model} · {label}", { model: routeConfig[route].agent.model, label: routeConfig[route].label });
  title.append(taskKind);
  copy.append(title, sub);
  const state = document.createElement("span");
  state.className = "route-state";
  bind(state, "待命");
  const meta = document.createElement("div");
  meta.className = "route-meta";
  const thresholdLabel = document.createElement("label");
  thresholdLabel.className = "route-threshold-label";
  const thresholdText = document.createElement("span");
  bind(thresholdText, "阈值");
  thresholdLabel.append(thresholdText);
  const thresholdInput = document.createElement("input");
  thresholdInput.className = "route-threshold";
  thresholdInput.type = "number";
  thresholdInput.min = "0";
  thresholdInput.max = "1";
  thresholdInput.step = "any";
  thresholdInput.value = String(routeConfig[route].threshold);
  thresholdInput.dataset.i18nAriaLabel = `${agentNames[route]} 置信度阈值`;
  thresholdInput.setAttribute("aria-label", t("{name} 置信度阈值", { name: agentNames[route] }));
  thresholdInput.addEventListener("input", () => thresholdInput.setCustomValidity(""));
  thresholdInput.addEventListener("change", () => saveThreshold(route, thresholdInput));
  thresholdLabel.append(thresholdInput);
  meta.append(state, thresholdLabel);
  card.append(symbol, copy, meta);
  const details = document.createElement("details");
  details.className = "route-details";
  const summary = document.createElement("summary");
  bind(summary, routeConfig[route].prompt ? "查看 Prompt 与路由说明" : "查看路由说明");
  const description = document.createElement("p");
  bind(description, routeConfig[route].criteria);
  details.append(summary, description);
  if (routeConfig[route].prompt) {
    const prompt = document.createElement("p");
    prompt.className = "prompt-copy";
    bind(prompt, routeConfig[route].prompt);
    details.append(prompt);
  }
  copy.append(details);
  $(route.startsWith("agent_") ? "agent-routes" : "tool-routes").append(card);
}
const flowLines = createFlowLines(document.querySelector(".layout"), () => ({
  busy,
  route: currentRoute,
  failed: ["失败", "已取消"].includes(lastOutcome),
}));
function thresholdError(field, previous, message) {
  field.value = String(previous);
  field.setCustomValidity(message);
  field.reportValidity();
}
async function saveThreshold(route, field) {
  const previous = routeConfig[route].threshold;
  const raw = field.value.trim();
  const threshold = Number(raw);
  if (!raw || !Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    thresholdError(field, previous, t("阈值必须是 0 到 1 之间的数字"));
    return;
  }
  if (threshold === previous) return;
  field.disabled = true;
  let failure = null;
  try {
    const response = await fetch(`/api/routes/${route}/threshold`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    routeConfig[route].threshold = data.threshold;
    field.value = String(data.threshold);
  } catch (error) {
    failure = t("保存失败：{error}", { error: error instanceof Error ? error.message : "未知错误" });
  } finally {
    field.disabled = false;
  }
  if (failure) thresholdError(field, previous, failure);
}
function updateHistory() {
  bind($("history-count"), "{count} 条消息", { count: history.length });
  const list = $("history");
  list.textContent = JSON.stringify(history, null, 2);
  requestAnimationFrame(() => { list.scrollTop = list.scrollHeight; });
  updateSession();
}
function updateTaskState(value) {
  if (value.current_task !== taskState.current_task) {
    taskChanges.push({ from: taskState.current_task, to: value.current_task, route: currentRoute, turn: history.filter((message) => message.role === "user").length });
  }
  taskState = value;
  updateSession();
}
function updateSession() {
  const taskName = (route) => route ? routeConfig[route]?.label || route : "空闲";
  const lifecycle = busy ? "处理中" : sessionEnded ? "已结束 · 下轮新会话" : lastOutcome;
  bind($("session-lifecycle"), lifecycle);
  bind($("current-task"), taskName(taskState.current_task));
  $("current-task").dataset.agent = taskState.current_task || "";
  $("session-counts").textContent = `${history.filter((m) => m.role === "user").length} / ${history.length}`;
  $("device-state").textContent = JSON.stringify(deviceState, null, 2);
  const list = $("transitions");
  list.replaceChildren();
  if (!taskChanges.length) {
    const empty = document.createElement("p");
    empty.className = "placeholder";
    bind(empty, "初始任务：闲聊。持久任务变化后记录在这里。");
    list.append(empty);
  }
  for (const entry of [...taskChanges].reverse()) {
    const row = document.createElement("div");
    row.className = "transition-row";
    const title = document.createElement("strong");
    bind(title, "{from} → {to}", { from: taskName(entry.from), to: taskName(entry.to) });
    const detail = document.createElement("small");
    bind(detail, "第 {turn} 轮 · {task}", { turn: entry.turn, task: taskName(entry.route) });
    row.append(title, detail);
    list.append(row);
  }
}
function resetSession() {
  history.length = 0;
  taskChanges = [];
  taskState = { current_task: "agent_chat" };
  deviceState = { volume: 50, muted: false };
  sessionEnded = false;
  lastOutcome = "等待输入";
  updateHistory();
}
updateHistory();
function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
function bubble(role, text, pending = false) {
  const row = document.createElement("div");
  row.className = `message-row ${role}${pending ? " pending" : ""}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  bind(avatar, role === "user" ? "我" : "j");
  const main = document.createElement("div");
  main.className = "message-main";
  const label = document.createElement("div");
  label.className = "message-agent";
  const labelName = document.createElement("span");
  labelName.className = "message-agent-name";
  bind(labelName, role === "user" ? "我" : "路由中");
  label.append(labelName);
  const model = document.createElement("span");
  label.append(model);
  const body = document.createElement("div");
  body.className = "bubble";
  body.textContent = text;
  const time = document.createElement("span");
  time.className = "message-time";
  time.textContent = now();
  main.append(label, body, time);
  row.append(avatar, main);
  messagesEl.querySelector(".empty")?.remove();
  messagesEl.append(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return { root: row, body, label: labelName, model };
}
function setAgent(reply, agent) {
  bind(reply.label, agent.name);
  reply.model.textContent = agent.model;
  reply.root.dataset.agent = currentRoute || "agent_chat";
}
function toolReceipt(name, content) {
  const div = document.createElement("div");
  div.className = "tool-receipt";
  const title = document.createElement("span");
  bind(title, "↳ {name} · 工具响应", { name: routeConfig[name]?.label || name });
  const details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
  bind(summary, "查看下发 JSON");
  try {
    pre.textContent = JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    pre.textContent = content;
  }
  details.append(summary, pre);
  div.append(title, details);
  messagesEl.append(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
function setRoute(route, confidence, proposedRoute, threshold) {
  currentRoute = route;
  routesEl.classList.add("has-active");
  $("jev-node").classList.add("active");
  routesEl.querySelectorAll(".route-card").forEach((el) => {
    const active = el.dataset.route === route;
    const rejected = el.dataset.route === proposedRoute && route !== proposedRoute;
    el.classList.toggle("active", active);
    el.classList.toggle("below-threshold", rejected);
    const state = el.querySelector(".route-state");
    if (state)
      bind(state, active ? "已命中" : rejected ? "未达阈值" : "待命");
    if (active || rejected) {
      const group = el.parentElement;
      const bounds = el.getBoundingClientRect(), viewport = group.getBoundingClientRect();
      if (bounds.bottom > viewport.bottom) group.scrollTop += bounds.bottom - viewport.bottom;
      else if (bounds.top < viewport.top) group.scrollTop -= viewport.top - bounds.top;
    }
  });
  bind($("confidence"), confidence <= threshold ? "JEV {confidence}% · 未过阈值" : "JEV {confidence}%", { confidence: Math.round(confidence * 100) });
  flowLines.update();
}
function addTiming(t) {
  timingsEl.querySelector(".placeholder")?.remove();
  const row = document.createElement("div");
  row.className = "timing";
  const head = document.createElement("div");
  head.className = "timing-head";
  const name = document.createElement("span"), total = document.createElement("span");
  bind(name, t.name);
  total.textContent = `${t.total_ms} ms`;
  head.append(name, total);
  const values = document.createElement("div");
  values.className = "timing-values";
  const first = document.createElement("span");
  if (t.first_token_ms !== null)
    first.innerHTML = `<span data-i18n="首 token"></span> <b>${t.first_token_ms} ms</b>`;
  else
    bind(first, t.name.startsWith("Jev") ? "首 token — 非流式" : "首 token —");
  values.append(first);
  if (t.first_byte_ms != null) {
    const byte = document.createElement("span");
    byte.innerHTML = `<span data-i18n="首字节"></span> <b>${t.first_byte_ms} ms</b>`;
    values.append(byte);
  }
  const usage = document.createElement("span");
  if (t.usage) {
    usage.innerHTML = `tokens <b>${t.usage.input_tokens} in / ${t.usage.output_tokens} out</b>`;
    turnUsage.input += t.usage.input_tokens;
    turnUsage.output += t.usage.output_tokens;
  } else
    usage.textContent = "tokens —";
  values.append(usage);
  row.append(head, values);
  timingsEl.append(row);
  translatePage(row);
}
function resetTurn() {
  currentRoute = null;
  turnUsage = { input: 0, output: 0 };
  routesEl.classList.remove("has-active");
  $("jev-node").classList.remove("active");
  routesEl.querySelectorAll(".route-card").forEach((el) => {
    el.classList.remove("active");
    el.classList.remove("below-threshold");
    const state = el.querySelector(".route-state");
    if (state)
      bind(state, "待命");
  });
  bind($("confidence"), "JEV —");
  timingsEl.innerHTML = '<p class="placeholder" data-i18n="正在等待阶段结果…">正在等待阶段结果…</p>';
  bind($("total"), "整轮耗时 —");
  translatePage();
  flowLines.update();
}
function setBusy(value) {
  busy = value;
  send.disabled = value;
  cancel.hidden = !value;
  input.disabled = value;
  $("clear").disabled = value;
  if (!value) {
    controller = null;
    input.focus();
  }
  updateSession();
  flowLines.update();
}
async function run() {
  const text = input.value.trim();
  if (!text || busy)
    return;
  if (sessionEnded) {
    resetSession();
    const divider = document.createElement("div");
    divider.className = "tool-receipt";
    bind(divider, "新会话");
    messagesEl.append(divider);
  }
  resetTurn();
  lastOutcome = "等待输入";
  const userMessage = { role: "user", content: text, _route: null };
  history.push(userMessage);
  updateHistory();
  bubble("user", text);
  input.value = "";
  $("count").textContent = "0 / 4000";
  setBusy(true);
  controller = new AbortController();
  const reply = bubble("assistant", "", true);
  bind(reply.body, "正在路由…");
  let responseText = "", done = false;
  try {
    const response = await fetch("/api/turn", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history, task_state: taskState }), signal: controller.signal });
    if (!response.ok)
      throw new Error((await response.json()).error || `HTTP ${response.status}`);
    if (!response.body)
      throw new Error("响应流为空");
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = "";
    const consume = (line) => {
      if (!line.trim())
        return;
      const event = JSON.parse(line);
      if (event.device_state) deviceState = event.device_state;
      if (event.task_state) updateTaskState(event.task_state);
      if (event.ends_session) sessionEnded = true;
      if (event.type === "status") {
        bind($("status"), event.text);
        if (!responseText)
          bind(reply.body, "{text}…", { text: event.text });
      } else if (event.type === "route") {
        setRoute(event.route, event.confidence, event.proposed_route, event.threshold);
        setAgent(reply, event.agent);
        userMessage._route = event.route;
        updateHistory();
      } else if (event.type === "timing")
        addTiming(event.timing);
      else if (event.type === "tool") {
        history.push({ ...event.call, _route: currentRoute }, { ...event.result, _route: currentRoute });
        updateHistory();
        toolReceipt(event.result.name, event.result.content);
        messagesEl.append(reply.root);
      } else if (event.type === "delta") {
        responseText += event.text;
        unbind(reply.body);
        reply.body.textContent = responseText;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (event.type === "done") {
        done = true;
        setAgent(reply, event.agent);
        unbind(reply.body);
        reply.body.textContent = event.assistant.content;
        reply.root.classList.remove("pending");
        history.push(event.assistant);
        lastOutcome = "等待输入";
        sessionEnded = Boolean(event.ends_session);
        updateHistory();
        bind($("status"), "完成 · {task}", { task: currentRoute ? routeConfig[currentRoute].label : "普通聊天" });
        bind($("total"), "整轮 {ms} ms · 已报告 {input} in / {output} out tokens", { ms: event.total_ms, input: turnUsage.input, output: turnUsage.output });
        requestAnimationFrame(() => { messagesEl.scrollTop = messagesEl.scrollHeight; });
      } else if (event.type === "error") {
        throw new Error(event.message);
      }
    };
    while (true) {
      const { done: end, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !end });
      let pos;
      while ((pos = buffer.indexOf(`
`)) >= 0) {
        consume(buffer.slice(0, pos));
        buffer = buffer.slice(pos + 1);
      }
      if (end) {
        if (buffer.trim())
          consume(buffer);
        break;
      }
    }
    if (!done)
      throw new Error("响应意外结束");
  } catch (error) {
    bind(reply.body, error instanceof Error && error.name === "AbortError" ? "已取消。" : "请求失败：{error}", { error: error instanceof Error ? error.message : "未知错误" });
    reply.root.classList.remove("pending");
    if (!currentRoute)
      setAgent(reply, { name: "系统", model: "" });
    bind($("status"), "本轮失败");
    lastOutcome = error instanceof Error && error.name === "AbortError" ? "已取消" : "失败";
    history.push({ role: "assistant", content: reply.body.textContent, _route: currentRoute });
    updateHistory();
    requestAnimationFrame(() => { messagesEl.scrollTop = messagesEl.scrollHeight; });
  } finally {
    setBusy(false);
  }
}
form.addEventListener("submit", (event) => {
  event.preventDefault();
  run();
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    run();
  }
});
input.addEventListener("input", () => {
  $("count").textContent = `${input.value.length} / 4000`;
});
cancel.addEventListener("click", () => controller?.abort());
$("clear").addEventListener("click", () => {
  if (busy)
    return;
  resetSession();
  messagesEl.innerHTML = '<div class="empty"><div class="empty-mark">↗</div><strong data-i18n="发送一句话，观察它的去向">发送一句话，观察它的去向</strong><p data-i18n="角色扮演、练习英语、健身饮食、讲个故事，或随便聊聊。">角色扮演、练习英语、健身饮食、讲个故事，或随便聊聊。</p></div>';
  resetTurn();
  bind($("status"), "等待输入");
});
{
  const s = statusData;
  const missing = Object.entries(s.ready).filter(([, ready]) => !ready).map(([name]) => name);
  const el = $("connection");
  bind(el, missing.length ? "● 待配置：{names}" : "● 模型配置就绪", { names: missing.join(" / ") });
  el.classList.toggle("bad", missing.length > 0);
  routesEl.querySelectorAll(".route-card").forEach((card) => {
    const route = card.dataset.route;
    const model = s.routes[route].agent.model;
    const sub = card.querySelector("small");
    if (sub)
      bind(sub, "{model} · {label}", { model, label: route === "agent_chat" ? "自然对话" : routeConfig[route].label });
  });
}

translatePage();
