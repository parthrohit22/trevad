const VERDICTS = {
  affordable_now: { label: "Affordable now", tone: "good" },
  affordable_with_plan: { label: "Affordable with a plan", tone: "plan" },
  affordable_later: { label: "Affordable later", tone: "later" },
  not_affordable: { label: "Not affordable", tone: "bad" },
};

const METHODS = {
  full_payment: "Pay in full",
  partial_payment: "Pay part now",
  installments: "Installments",
  wait: "Wait",
  not_recommended: "Do not proceed",
};

const state = { requests: [], filter: "all", query: "", selected: null };

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function money(value, currency) {
  if (value === null || value === undefined) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));
  } catch {
    return `${currency} ${value}`;
  }
}

function shortMoney(value, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(value);
  } catch {
    return String(Math.round(value));
  }
}

function day(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function badge(verdict) {
  const info = VERDICTS[verdict];
  return el("span", { class: `badge tone-${info.tone}`, text: info.label });
}

function visible() {
  const query = state.query.trim().toLowerCase();
  return state.requests.filter((item) => {
    if (state.filter !== "all" && item.verdict !== state.filter) return false;
    if (!query) return true;
    return [item.request_id, item.request.title, item.request.user_name].join(" ").toLowerCase().includes(query);
  });
}

function renderSummary() {
  const counts = {};
  for (const item of state.requests) counts[item.verdict] = (counts[item.verdict] || 0) + 1;
  const root = document.getElementById("summary");
  root.replaceChildren(
    el("span", { class: "stat" }, [el("b", { text: state.requests.length }), "requests"]),
    ...Object.entries(VERDICTS).map(([key, info]) => el("span", { class: "stat" }, [el("b", { text: counts[key] || 0 }), info.label.toLowerCase()])),
  );
}

function renderFilters() {
  const root = document.getElementById("filters");
  const options = [["all", "All"], ...Object.entries(VERDICTS).map(([key, info]) => [key, info.label])];
  root.replaceChildren(
    ...options.map(([key, label]) =>
      el("button", {
        type: "button",
        "aria-pressed": String(state.filter === key),
        text: label,
        onclick: () => { state.filter = key; renderFilters(); renderList(); },
      }),
    ),
  );
}

function renderList() {
  const root = document.getElementById("request-list");
  const items = visible();
  if (!items.length) {
    root.replaceChildren(el("li", { class: "muted", text: "No matching requests." }));
    return;
  }
  root.replaceChildren(
    ...items.map((item) =>
      el("li", {}, el("button", {
        type: "button",
        "aria-current": String(item.request_id === state.selected),
        onclick: () => select(item.request_id),
      }, [
        el("div", { class: "row" }, [el("span", { class: "title", text: item.request.title }), badge(item.verdict)]),
        el("div", { class: "row meta" }, [
          el("span", { text: item.request.user_name }),
          el("span", { text: money(item.requested_amount, item.currency) }),
        ]),
      ])),
    ),
  );
}

function kpi(label, value) {
  return el("div", { class: "kpi" }, [el("span", { text: label }), el("strong", { text: value })]);
}

function chart(data) {
  const width = 860;
  const height = 280;
  const pad = { left: 70, right: 16, top: 16, bottom: 30 };
  const points = data.forecast.map((row) => ({ date: row.date, base: Number(row.baseline), plan: Number(row.with_plan) }));
  const floor = Number(data.minimum_balance);
  const values = points.flatMap((p) => [p.base, p.plan]).concat(floor);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const span = max - min || 1;
  min -= span * 0.08;
  max += span * 0.08;
  const x = (index) => pad.left + (index / Math.max(points.length - 1, 1)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - (value - min) / (max - min)) * (height - pad.top - pad.bottom);
  const line = (key) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");

  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img", "aria-label": "90-day balance forecast" });
  for (let i = 0; i <= 4; i += 1) {
    const value = min + ((max - min) * i) / 4;
    root.append(svg("line", { x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value), class: "grid" }));
    const label = svg("text", { x: pad.left - 8, y: y(value) + 4, "text-anchor": "end" });
    label.textContent = shortMoney(value, data.currency);
    root.append(label);
  }
  [0, Math.floor((points.length - 1) / 2), points.length - 1].forEach((index, n) => {
    const label = svg("text", { x: x(index), y: height - 8, "text-anchor": n === 0 ? "start" : n === 2 ? "end" : "middle" });
    label.textContent = day(points[index].date);
    root.append(label);
  });
  root.append(svg("line", { x1: pad.left, x2: width - pad.right, y1: y(floor), y2: y(floor), class: "floor" }));
  root.append(svg("path", { d: line("base"), class: "baseline" }));
  root.append(svg("path", { d: line("plan"), class: "plan" }));

  const index = new Map(points.map((p, i) => [p.date, i]));
  for (const payment of data.schedule) {
    const i = index.get(payment.date);
    if (i !== undefined) root.append(svg("circle", { cx: x(i), cy: y(points[i].plan), r: 5, class: "payment" }));
  }

  const guide = svg("line", { y1: pad.top, y2: height - pad.bottom, class: "guide", visibility: "hidden" });
  const tip = svg("g", { class: "tip", visibility: "hidden" });
  const tipBox = svg("rect", { width: 190, height: 52, rx: 6 });
  const tipLines = [0, 1, 2].map((n) => svg("text", { x: 10, y: 17 + n * 14 }));
  tip.append(tipBox, ...tipLines);
  root.append(guide, tip);

  const overlay = svg("rect", { x: pad.left, y: pad.top, width: width - pad.left - pad.right, height: height - pad.top - pad.bottom, fill: "transparent" });
  overlay.addEventListener("mousemove", (event) => {
    const box = root.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * width;
    const i = Math.round(((px - pad.left) / (width - pad.left - pad.right)) * (points.length - 1));
    const p = points[Math.max(0, Math.min(points.length - 1, i))];
    const gx = x(points.indexOf(p));
    guide.setAttribute("x1", gx);
    guide.setAttribute("x2", gx);
    guide.setAttribute("visibility", "visible");
    tipLines[0].textContent = day(p.date);
    tipLines[1].textContent = `With plan: ${money(p.plan, data.currency)}`;
    tipLines[2].textContent = `No purchase: ${money(p.base, data.currency)}`;
    const tx = gx + 200 > width ? gx - 200 : gx + 10;
    tip.setAttribute("transform", `translate(${tx},${pad.top + 4})`);
    tip.setAttribute("visibility", "visible");
  });
  overlay.addEventListener("mouseleave", () => {
    guide.setAttribute("visibility", "hidden");
    tip.setAttribute("visibility", "hidden");
  });
  root.append(overlay);
  return root;
}

function table(headers, rows, numeric = []) {
  return el("div", { class: "table-wrap" }, el("table", {}, [
    el("thead", {}, el("tr", {}, headers.map((h, i) => el("th", { class: numeric.includes(i) ? "num" : "", text: h })))),
    el("tbody", {}, rows.map((row) => el("tr", { class: row.className || "" }, row.cells.map((cell, i) => el("td", { class: numeric.includes(i) ? "num" : "" }, cell))))),
  ]));
}

function renderDetail(data) {
  const currency = data.currency;
  const req = data.request;
  const lowest = Math.min(...data.forecast.map((row) => Number(row.with_plan)));
  const selected = data.candidates.find((c) => c.safe && c.method === data.method && (c.option_id || null) === (data.option_id || null) && c.changes.length === data.spending_changes.length);

  const hero = el("section", { class: "card hero" }, [
    el("div", { class: "heading" }, [
      el("div", {}, [
        el("h1", { text: req.title }),
        el("div", { class: "sub", text: `${req.user_name} · ${money(data.requested_amount, currency)} · decide by ${day(req.deadline)}` }),
      ]),
      badge(data.verdict),
    ]),
    el("p", { class: "explanation", text: data.explanation }),
  ]);

  const kpis = el("section", { class: "kpis" }, [
    kpi("Recommendation", METHODS[data.method]),
    kpi("Safe to pay today", money(data.safe_to_pay_today, currency)),
    kpi("Earliest full payment", data.earliest_full_payment_date ? day(data.earliest_full_payment_date) : "Not within 90 days"),
    kpi("Lowest balance ahead", money(lowest, currency)),
    kpi("Minimum to keep", money(data.minimum_balance, currency)),
  ]);

  const forecast = el("section", { class: "card" }, [
    el("h2", { text: "90-day balance forecast" }),
    chart(data),
    el("div", { class: "legend" }, [
      el("span", {}, [el("i", { style: "border-color: var(--accent)" }), "With the recommendation"]),
      el("span", {}, [el("i", { style: "border-color: var(--baseline); border-top-style: dashed" }), "Without the purchase"]),
      el("span", {}, [el("i", { style: "border-color: var(--bad); border-top-style: dashed" }), "Minimum balance"]),
    ]),
  ]);

  const schedule = el("section", { class: "card" }, [
    el("h2", { text: "Payment plan" }),
    data.schedule.length
      ? table(["Date", "Amount"], data.schedule.map((p) => ({ cells: [day(p.date), money(p.amount, currency)] })), [1])
      : el("p", { class: "muted", text: "No payment is recommended." }),
    data.spending_changes.length
      ? el("div", {}, [
          el("h2", { text: "Spending changes required", style: "margin-top: 16px" }),
          el("ul", { class: "list" }, data.spending_changes.map((c) =>
            el("li", { text: c.action === "stop" ? `Stop ${c.label} (${money(c.current_amount, currency)} each time)` : `Reduce ${c.label} from ${money(c.current_amount, currency)} to ${money(c.new_amount, currency)}` }))),
        ])
      : null,
  ]);

  const evidence = el("section", { class: "card" }, [
    el("h2", { text: "Evidence from messages" }),
    data.evidence.length
      ? el("ul", { class: "list" }, data.evidence.map((f) => el("li", {}, [f.summary, el("span", { class: "muted", text: ` · ${f.message_id}` })])))
      : el("p", { class: "muted", text: "No messages changed this forecast." }),
  ]);

  const plans = el("section", { class: "card" }, [
    el("h2", { text: "Plans considered" }),
    table(
      ["Plan", "Payments", "Total", "Lowest balance", "Result"],
      data.candidates.map((c) => ({
        className: c === selected ? "selected" : "",
        cells: [
          METHODS[c.method] + (c.option_id ? ` (${c.option_id.split("-").pop()})` : "") + (c.changes.length ? " + changes" : ""),
          c.payments.length === 1 ? day(c.payments[0].date) : `${c.payments.length} from ${day(c.payments[0].date)}`,
          money(c.total, currency),
          c.lowest_balance ? money(c.lowest_balance, currency) : "—",
          c === selected ? "Selected" : c.safe ? "Safe, ranked lower" : c.rejection,
        ],
      })),
      [2, 3],
    ),
  ]);

  const flows = el("section", { class: "card" }, el("details", {}, [
    el("summary", { text: `Forecast cash flows (${data.cash_flows.length})` }),
    table(
      ["Date", "Description", "Source", "Amount"],
      data.cash_flows.map((f) => ({ cells: [day(f.date), f.label, f.source, `${f.direction === "in" ? "+" : "−"}${money(f.amount, currency)}`] })),
      [3],
    ),
  ]));

  document.getElementById("detail").replaceChildren(hero, kpis, forecast, el("div", { class: "grid-two" }, [schedule, evidence]), plans, flows);
}

async function select(requestId) {
  state.selected = requestId;
  renderList();
  const response = await fetch(`/api/v1/requests/${encodeURIComponent(requestId)}`);
  if (!response.ok) {
    document.getElementById("detail").replaceChildren(el("p", { class: "empty", text: "Could not load this decision." }));
    return;
  }
  renderDetail(await response.json());
}

async function start() {
  document.getElementById("search").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderList();
  });
  const response = await fetch("/api/v1/requests");
  state.requests = await response.json();
  renderSummary();
  renderFilters();
  renderList();
  if (state.requests.length) select(state.requests[0].request_id);
  else document.getElementById("detail").replaceChildren(el("p", { class: "empty", text: "No requests in this portfolio." }));
}

start();
