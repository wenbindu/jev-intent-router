// Connect the actual DOM nodes so lines follow resizing, details and list scrolling.
export function createFlowLines(layout, getState) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.classList.add("flow-lines");
  svg.setAttribute("aria-hidden", "true");
  layout.prepend(svg);
  const edges = new Map();
  let frame = null;

  function draw() {
    frame = null;
    const { busy, route, failed } = getState();
    svg.dataset.phase = failed ? "error" : busy ? (route ? "executing" : "routing") : route ? "complete" : "idle";
    const root = layout.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${root.width} ${root.height}`);
    const rect = (element) => {
      const r = element.getBoundingClientRect();
      return { left: r.left - root.left, right: r.right - root.left, top: r.top - root.top, bottom: r.bottom - root.top, width: r.width, height: r.height };
    };
    const seen = new Set();
    function edge(key, d, selected = false) {
      seen.add(key);
      let group = edges.get(key);
      if (!group) {
        group = document.createElementNS(ns, "g");
        group.dataset.edge = key;
        for (const name of ["flow-track", "flow-tail", "flow-pulse", "flow-core"]) {
          const path = document.createElementNS(ns, "path");
          path.classList.add(name);
          group.append(path);
        }
        svg.append(group);
        edges.set(key, group);
      }
      group.classList.toggle("selected", selected);
      for (const path of group.children) path.setAttribute("d", d);
    }
    const chat = rect(layout.querySelector(".conversation"));
    const input = rect(layout.querySelector(".flow-input"));
    const jev = rect(layout.querySelector("#jev-node"));
    const panel = rect(layout.querySelector(".route-panel"));
    const session = rect(layout.querySelector(".session-panel .panel-head"));
    const horizontal = panel.left >= chat.right;
    const inputY = input.top + input.height / 2;
    if (horizontal) {
      edge("chat-input", `M ${chat.right} ${inputY} H ${input.left}`, busy || Boolean(route));
    } else {
      // On mobile the trace panel sits below chat; use the outer gutter.
      const chatY = chat.top + 32;
      const gutter = Math.max(chat.left, panel.left) + 5;
      edge("chat-input", `M ${chat.left} ${chatY} H ${gutter - 12} V ${inputY} H ${input.left}`, busy || Boolean(route));
    }
    edge("input-jev", `M ${input.left + input.width / 2} ${input.bottom} V ${jev.top}`, busy || Boolean(route));
    const trunkX = panel.left + 11;
    const jevY = jev.top + jev.height / 2;
    let activeCard = null;
    for (const kind of ["agent", "tool"]) {
      const tree = layout.querySelector(`#${kind}-routes`);
      const group = tree.closest(".route-group");
      const heading = rect(group.querySelector(".group-title"));
      const treeBox = rect(tree);
      const headerY = heading.top + heading.height / 2;
      const branchX = heading.left + 12;
      const selectedGroup = Boolean(route?.startsWith(`${kind}_`));
      edge(`jev-${kind}`, `M ${jev.left} ${jevY} H ${trunkX} V ${headerY} H ${branchX}`, selectedGroup);
      for (const card of tree.querySelectorAll(".route-card")) {
        const box = rect(card);
        const y = box.top + Math.min(32, box.height / 2);
        // Do not draw over cards clipped by their scroll container.
        if (y < treeBox.top + 1 || y > treeBox.bottom - 1) continue;
        const selected = card.dataset.route === route;
        edge(card.dataset.route, `M ${branchX} ${headerY} V ${y} H ${box.left}`, selected);
        if (selected) activeCard = { box, y };
      }
    }
    if (activeCard && session.left >= panel.right) {
      const { box, y } = activeCard;
      const gutter = (panel.right + session.left) / 2;
      const endY = session.top + session.height / 2;
      edge("result-session", `M ${box.right} ${y} H ${gutter} V ${endY} H ${session.left}`, true);
    }
    for (const [key, element] of edges) {
      if (!seen.has(key)) {
        element.remove();
        edges.delete(key);
      }
    }
    // Keep the active branch above the shared, dim tree trunks.
    for (const element of edges.values()) {
      if (element.classList.contains("selected")) svg.append(element);
    }
  }
  function update() {
    if (frame === null) frame = requestAnimationFrame(draw);
  }
  const observer = new ResizeObserver(update);
  for (const element of [layout, ...layout.querySelectorAll(".panel, .route-card, .group-title")]) observer.observe(element);
  layout.addEventListener("scroll", update, true);
  layout.addEventListener("toggle", update, true);
  window.addEventListener("resize", update);
  update();
  return { update };
}
