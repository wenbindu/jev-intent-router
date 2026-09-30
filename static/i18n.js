// UI translations only: conversation content and wire-format JSON stay untouched.
import { routeTranslations } from "./route-translations.js?v=20260930-2";
const translations = {
  "一段对话，多种可能。": "One conversation. Many possibilities.",
  "6 个 Agent 共享主对话，工具负责执行。观察路由、状态与调用成本。": "6 agents share one conversation. Tools handle actions. Explore routing, state and usage.",
  "检查配置中…": "Checking configuration…",
  "对话列表": "Conversation", "微信式对话 · 单一消息列表": "Chat interface · One message history",
  "清空": "Clear", "取消": "Cancel", "发送 ↵": "Send ↵", "输入消息": "Message", "输入一句话…": "Type a message…",
  "发送一句话，观察它的去向": "Send a message and follow its route",
  "角色扮演、练习英语、健身饮食、讲个故事，或随便聊聊。": "Roleplay, practice English, discuss fitness and nutrition, tell a story, or just chat.",
  "调用轨迹": "Call trace", "等待输入": "Ready", "发送后显示首 token、完整响应耗时与 token 用量。": "Send a message to see first-token latency, total response time and token usage.",
  "整轮耗时 —": "Turn duration —", "路由模块": "Routing", "意图路由": "Intent routing", "Agent 路由": "Agent routes", "Tools 路由": "Tool routes",
  "对话与生成": "Conversation & generation", "命令与执行": "Commands & actions",
  "持久任务占用设备；瞬时任务执行后保留当前任务背景。": "Persistent tasks occupy the device. Instant tasks preserve the current task context.",
  "Session 状态": "Session state", "当前持久任务": "Current persistent task", "用户轮次 / 消息": "User turns / Messages", "设备状态": "Device state", "持久任务变化": "Task changes",
  "同一份主对话 · 瞬时任务保留当前任务背景": "One shared conversation · Instant tasks preserve context",
  "仅本页内存保存，刷新或清空会重置。": "Stored in page memory. Reloading or clearing resets it.",
  "主消息列表": "Message history", "唯一的主对话记录。Jev 与 6 个 Agent 共享历史；_route 记录处理路径。": "One conversation history shared by Jev and all 6 agents. _route records the handling route.",
  "音量、关机与歌曲为虚拟命令下发 · 天气为固定 mock 样本 · API Key 只保存在服务端配置文件": "Volume, shutdown and music use simulated commands · Weather uses a fixed mock sample · API keys stay in server configuration",
  "持久任务": "Persistent", "瞬时任务": "Instant", "待命": "Standby", "阈值": "Threshold",
  "{name} 置信度阈值": "{name} confidence threshold", "查看 Prompt 与路由说明": "Prompt & routing details", "查看路由说明": "Routing details",
  "阈值必须是 0 到 1 之间的数字": "Threshold must be a number between 0 and 1",
  "保存失败：{error}": "Save failed: {error}", "未知错误": "Unknown error", "{count} 条消息": "{count} messages",
  "空闲": "Idle", "处理中": "Processing", "已结束 · 下轮新会话": "Ended · Next turn starts a new session",
  "初始任务：闲聊。持久任务变化后记录在这里。": "Initial task: Chat. Changes to persistent tasks appear here.",
  "第 {turn} 轮 · {task}": "Turn {turn} · {task}", "{from} → {to}": "{from} → {to}",
  "我": "Me", "路由中": "Routing", "系统": "System", "正在路由…": "Routing…", "{text}…": "{text}…",
  "↳ {name} · 工具响应": "↳ {name} · Tool response", "查看下发 JSON": "View command JSON",
  "已命中": "Selected", "未达阈值": "Below threshold", "JEV {confidence}% · 未过阈值": "JEV {confidence}% · Below threshold",
  "首 token": "First token", "首 token — 非流式": "First token — non-streaming", "首 token —": "First token —", "首字节": "First byte",
  "正在等待阶段结果…": "Waiting for stage results…", "新会话": "New session", "响应流为空": "Empty response stream", "响应意外结束": "Response ended unexpectedly",
  "完成 · {task}": "Done · {task}", "普通聊天": "Chat", "整轮 {ms} ms · 已报告 {input} in / {output} out tokens": "Turn {ms} ms · Reported {input} in / {output} out tokens",
  "已取消。": "Cancelled.", "请求失败：{error}": "Request failed: {error}", "本轮失败": "Turn failed", "已取消": "Cancelled", "失败": "Failed",
  "● 服务未连接": "● Service unavailable", "● 待配置：{names}": "● Setup required: {names}", "● 模型配置就绪": "● Models configured", "自然对话": "Conversation",
  "{model} · {label}": "{model} · {label}", "界面语言": "Interface language",
  "Jev 正在选择路径": "Jev is selecting a route", "Jev 路由": "Jev routing",
};
const names = {
  "音量设置": "Set volume", "音量调节": "Adjust volume", "关机": "Shutdown", "天气查询": "Weather", "歌曲播放": "Play music", "歌曲控制": "Music controls", "告别": "Goodbye",
  "扮演游戏": "Roleplay", "英语教师": "English teacher", "健身教练": "Fitness coach", "营养师": "Nutritionist", "讲故事": "Storyteller", "闲聊": "Chat",
};
Object.assign(translations, names, routeTranslations);
for (const [zh, en] of Object.entries(names)) {
  translations[`${zh} Agent`] = `${en} Agent`;
  translations[`${zh}工具`] = `${en} tool`;
}
// Server stage labels are UI metadata, not model responses.
const stages = {" 正在解析参数": " is parsing parameters", " 参数解析": " · Parameters", " 正在根据执行结果回答": " is responding to the result", " 工具后回答": " · Response", " 正在回答": " is responding", " 对话": " · Conversation"};
let locale = "zh-CN";
try { if (localStorage.getItem("intent-router.locale") === "en") locale = "en"; } catch { /* Storage can be disabled. */ }
export function t(source, params = {}) {
  let result = source;
  if (locale === "en") {
    result = Object.hasOwn(translations, source) ? translations[source] : undefined;
    if (result === undefined) {
      const suffix = Object.keys(stages).find((key) => source.endsWith(key));
      if (source.endsWith(" 置信度阈值")) result = t("{name} 置信度阈值", { name: source.slice(0, -6) });
      else if (source.startsWith("Qwen · ")) result = "Qwen · " + t(source.slice(7));
      else if (suffix) result = t(source.slice(0, -suffix.length)) + stages[suffix];
      else result = source.startsWith("执行 tool_") ? source.replace("执行 ", "Run ") : source;
    }
  }
  return result.replace(/\{(\w+)\}/g, (match, key) => key in params ? t(String(params[key])) : match);
}
export function bind(element, source, params = {}) {
  element.dataset.i18n = source;
  element.dataset.i18nParams = JSON.stringify(params);
  element.textContent = t(source, params);
}
export function unbind(element) {
  delete element.dataset.i18n;
  delete element.dataset.i18nParams;
}
export function translatePage(root = document) {
  document.documentElement.lang = locale;
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n, JSON.parse(el.dataset.i18nParams || "{}")); });
  for (const attr of ["placeholder", "aria-label"]) {
    root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => { el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))); });
  }
  document.querySelectorAll("[data-locale]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.locale === locale)));
}
export function initLanguageSwitch() {
  document.querySelectorAll("[data-locale]").forEach((button) => button.addEventListener("click", () => {
    locale = button.dataset.locale;
    try { localStorage.setItem("intent-router.locale", locale); } catch { /* Keep the choice for this page. */ }
    translatePage();
  }));
  translatePage();
}
