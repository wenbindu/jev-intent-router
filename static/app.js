// Browser UI served by FastAPI; route labels and models come from /api/status.
const statusData = await fetch("/api/status").then((response) => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).catch((error) => {
  document.getElementById("connection").textContent = "● 服务未连接";
  document.getElementById("connection").classList.add("bad");
  document.getElementById("send").disabled = true;
  throw error;
});
const routes = Object.keys(statusData.routes);
const tools_default = statusData.routes;
var $ = (id) => document.getElementById(id);
var form = $("composer");
var input = $("input");
var send = $("send");
var cancel = $("cancel");
var messagesEl = $("messages");
var routesEl = $("routes");
var timingsEl = $("timings");
var history = [];
var sessionEnded = false;
var busy = false;
var controller = null;
var currentRoute = null;
var turnUsage = { input: 0, output: 0 };
var symbols = { chat: "◌", set_volume: "◖", adjust_volume: "◖", shutdown: "⏻", get_weather: "☁", play_song: "♫", song_control: "♫", handle_user_goodbye: "↗" };
var agentNames = Object.fromEntries(routes.map((route) => [route, tools_default[route].agent.name]));
for (const route of routes) {
  const card = document.createElement("div");
  card.className = "route-card";
  card.dataset.route = route;
  const symbol = document.createElement("span");
  symbol.className = "route-symbol";
  symbol.textContent = symbols[route];
  const copy = document.createElement("div");
  copy.className = "route-copy";
  const title = document.createElement("strong");
  title.textContent = agentNames[route];
  const sub = document.createElement("small");
  sub.textContent = route === "chat" ? "QWEN 3.7 FLASH · 自然对话" : `DEEPSEEK V4.1 FLASH · ${tools_default[route].label}`;
  copy.append(title, sub);
  const state = document.createElement("span");
  state.className = "route-state";
  state.textContent = "待命";
  card.append(symbol, copy, state);
  routesEl.append(card);
}
function updateHistory() {
  $("history-count").textContent = `${history.length} messages`;
  const list = $("history");
  list.textContent = JSON.stringify(history, null, 2);
  requestAnimationFrame(() => { list.scrollTop = list.scrollHeight; });
}
function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
function bubble(role, text, pending = false) {
  const row = document.createElement("div");
  row.className = `message-row ${role}${pending ? " pending" : ""}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "我" : "j";
  const main = document.createElement("div");
  main.className = "message-main";
  const label = document.createElement("div");
  label.className = "message-agent";
  label.textContent = role === "user" ? "我" : "路由中";
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
  return { root: row, body, label, model };
}
function setAgent(reply, agent) {
  reply.label.firstChild.textContent = agent.name;
  reply.model.textContent = agent.model;
}
function toolReceipt(name, content) {
  const div = document.createElement("div");
  div.className = "tool-receipt";
  const title = document.createElement("span");
  title.textContent = `↳ ${tools_default[name]?.label || name} · tool response`;
  const details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
  summary.textContent = "查看下发 JSON";
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
function setRoute(route, confidence) {
  currentRoute = route;
  routesEl.classList.add("has-active");
  $("jev-node").classList.add("active");
  routesEl.querySelectorAll(".route-card").forEach((el) => {
    const active = el.dataset.route === route;
    el.classList.toggle("active", active);
    const state = el.querySelector(".route-state");
    if (state)
      state.textContent = active ? "已命中" : "待命";
  });
  $("confidence").textContent = `JEV ${Math.round(confidence * 100)}%`;
}
function addTiming(t) {
  timingsEl.querySelector(".placeholder")?.remove();
  const row = document.createElement("div");
  row.className = "timing";
  const head = document.createElement("div");
  head.className = "timing-head";
  const name = document.createElement("span"), total = document.createElement("span");
  name.textContent = t.name;
  total.textContent = `${t.total_ms} ms`;
  head.append(name, total);
  const values = document.createElement("div");
  values.className = "timing-values";
  const first = document.createElement("span");
  if (t.first_token_ms !== null)
    first.innerHTML = `首 token <b>${t.first_token_ms} ms</b>`;
  else
    first.textContent = t.name.startsWith("Jev") ? "首 token — 非流式" : "首 token —";
  values.append(first);
  if (t.first_byte_ms != null) {
    const byte = document.createElement("span");
    byte.innerHTML = `首字节 <b>${t.first_byte_ms} ms</b>`;
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
}
function resetTurn() {
  currentRoute = null;
  turnUsage = { input: 0, output: 0 };
  routesEl.classList.remove("has-active");
  $("jev-node").classList.remove("active");
  routesEl.querySelectorAll(".route-card").forEach((el) => {
    el.classList.remove("active");
    const state = el.querySelector(".route-state");
    if (state)
      state.textContent = "待命";
  });
  $("confidence").textContent = "JEV —";
  timingsEl.innerHTML = '<p class="placeholder">正在等待阶段结果…</p>';
  $("total").textContent = "整轮耗时 —";
}
function setBusy(value) {
  busy = value;
  send.disabled = value;
  cancel.hidden = !value;
  input.disabled = value;
  if (!value) {
    controller = null;
    input.focus();
  }
}
async function run() {
  const text = input.value.trim();
  if (!text || busy)
    return;
  if (sessionEnded) {
    history.length = 0;
    sessionEnded = false;
    updateHistory();
    const divider = document.createElement("div");
    divider.className = "tool-receipt";
    divider.textContent = "新会话";
    messagesEl.append(divider);
  }
  resetTurn();
  history.push({ role: "user", content: text });
  updateHistory();
  bubble("user", text);
  input.value = "";
  $("count").textContent = "0 / 4000";
  setBusy(true);
  controller = new AbortController;
  const reply = bubble("assistant", "正在路由…", true);
  let responseText = "", done = false;
  try {
    const response = await fetch("/api/turn", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }), signal: controller.signal });
    if (!response.ok)
      throw new Error((await response.json()).error || `HTTP ${response.status}`);
    if (!response.body)
      throw new Error("响应流为空");
    const reader = response.body.getReader(), decoder = new TextDecoder;
    let buffer = "";
    const consume = (line) => {
      if (!line.trim())
        return;
      const event = JSON.parse(line);
      if (event.type === "status") {
        $("status").textContent = event.text;
        if (!responseText)
          reply.body.textContent = event.text + "…";
      } else if (event.type === "route") {
        setRoute(event.route, event.confidence);
        setAgent(reply, event.agent);
      } else if (event.type === "timing")
        addTiming(event.timing);
      else if (event.type === "tool") {
        history.push(event.call, event.result);
        updateHistory();
        toolReceipt(event.result.name, event.result.content);
        messagesEl.append(reply.root);
      } else if (event.type === "delta") {
        responseText += event.text;
        reply.body.textContent = responseText;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (event.type === "done") {
        done = true;
        setAgent(reply, event.agent);
        reply.body.textContent = event.assistant.content;
        reply.root.classList.remove("pending");
        history.push(event.assistant);
        sessionEnded = Boolean(event.ends_session);
        updateHistory();
        $("status").textContent = `完成 · ${currentRoute ? tools_default[currentRoute].label : "普通聊天"}`;
        $("total").textContent = `整轮 ${event.total_ms} ms · 已报告 ${turnUsage.input} in / ${turnUsage.output} out tokens`;
      } else if (event.type === "error")
        throw new Error(event.message);
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
    reply.body.textContent = error instanceof Error && error.name === "AbortError" ? "已取消。" : `请求失败：${error instanceof Error ? error.message : "未知错误"}`;
    reply.root.classList.remove("pending");
    if (!currentRoute)
      setAgent(reply, { name: "系统", model: "" });
    $("status").textContent = "本轮失败";
    history.push({ role: "assistant", content: reply.body.textContent });
    updateHistory();
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
  history.length = 0;
  sessionEnded = false;
  updateHistory();
  messagesEl.innerHTML = '<div class="empty"><div class="empty-mark">↗</div><strong>发送一句话，观察它的去向</strong><p>音量调到 35、关机、播放一首歌、北京天气如何，或随便聊聊。</p></div>';
  resetTurn();
  $("status").textContent = "等待输入";
});
{
  const s = statusData;
  const missing = Object.entries(s.ready).filter(([, ready]) => !ready).map(([name]) => name);
  const el = $("connection");
  el.textContent = missing.length ? `● 待配置：${missing.join(" / ")}` : "● 模型配置就绪";
  el.classList.toggle("bad", missing.length > 0);
  routesEl.querySelectorAll(".route-card").forEach((card) => {
    const route = card.dataset.route;
    const model = s.routes[route].agent.model;
    const sub = card.querySelector("small");
    if (sub)
      sub.textContent = `${model} · ${route === "chat" ? "自然对话" : tools_default[route].label}`;
  });
}
