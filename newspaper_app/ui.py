# -*- coding: utf-8 -*-
"""Single-page interface. Text comes from text.UI as JSON."""

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #e6d9c4;
    --paper: #f7f1e6;
    --ink: #241c14;
    --muted: #6f6256;
    --line: #d9c7ae;
    --red: #8d2c2c;
    --red-d: #6e1f1f;
    --chip: #efe4d2;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body {
    font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    color: var(--ink);
    background:
      radial-gradient(1200px 500px at 10% -10%, #f3e7d4, transparent 50%),
      var(--bg);
  }
  header {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; border-bottom: 1px solid var(--line);
    background: rgba(247, 241, 230, 0.92); position: sticky; top: 0; z-index: 2;
  }
  header h1 { font-size: 18px; margin: 0; letter-spacing: 0.04em; font-weight: 650; }
  header h1 span { color: var(--red); }
  .spacer { flex: 1; }
  button, .file {
    font: inherit; color: var(--ink); background: var(--paper);
    border: 1px solid var(--line); border-radius: 8px; padding: 7px 12px; cursor: pointer;
  }
  button.primary { background: var(--red); color: #fffaf4; border-color: var(--red-d); }
  button.primary:hover { background: var(--red-d); }
  button:disabled { opacity: 0.55; cursor: default; }
  .layout { display: grid; grid-template-columns: 260px 1fr 380px; height: calc(100% - 57px); }
  .col { min-height: 0; overflow: auto; padding: 12px; }
  .col + .col { border-left: 1px solid var(--line); }
  .hint { color: var(--muted); font-size: 13px; line-height: 1.55; margin: 0 0 10px; }
  #library { display: flex; flex-direction: column; gap: 6px; }
  .file { text-align: left; width: 100%; background: transparent; }
  .file.on { border-color: var(--red); background: #fff; box-shadow: inset 3px 0 0 var(--red); }
  .file small { display: block; color: var(--muted); font-size: 12px; }
  .stage-wrap { background: #d9cbb6; border-radius: 12px; padding: 10px; min-height: 240px; }
  .stage { position: relative; }
  .stage img { width: 100%; height: auto; display: block; background: white; }
  .stage svg { position: absolute; left: 0; top: 0; width: 100%; height: 100%; }
  .hit { fill: rgba(141, 44, 44, 0.08); stroke: #8d2c2c; stroke-width: 2; cursor: pointer; }
  .hit.on { fill: rgba(141, 44, 44, 0.18); stroke-width: 4; }
  .pager { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
  #alist { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
  .card {
    text-align: left; width: 100%; background: var(--paper); border: 1px solid var(--line);
    border-radius: 8px; padding: 8px 10px; cursor: pointer;
  }
  .card.on { border-color: var(--red); }
  .card b { display: block; font-size: 14px; }
  .card em { font-style: normal; color: var(--muted); font-size: 12px; }
  .badge { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 99px; background: var(--chip); margin-left: 4px; }
  .badge.hot { background: #f0d2d2; color: var(--red-d); }
  label { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 4px; }
  input[type=text], textarea {
    width: 100%; font: inherit; color: var(--ink); background: white;
    border: 1px solid var(--line); border-radius: 8px; padding: 8px;
  }
  textarea { min-height: 280px; resize: vertical; line-height: 1.65; font-family: "SimSun", "Songti SC", serif; }
  .row { display: flex; gap: 8px; margin-top: 8px; }
  #status { font-size: 13px; color: var(--muted); min-height: 1.2em; }
  .empty { color: var(--muted); padding: 24px 8px; }
  @media (max-width: 1100px) {
    .layout { grid-template-columns: 1fr; height: auto; }
    .col + .col { border-left: 0; border-top: 1px solid var(--line); }
  }
</style>
</head>
<body>
<header>
  <h1><span>__TITLE__</span></h1>
  <div class="spacer"></div>
  <button id="btnAll"></button>
  <button id="btnGo" class="primary"></button>
  <button id="btnTxt"></button>
  <button id="btnMd"></button>
  <button id="btnJson"></button>
</header>
<div class="layout">
  <aside class="col">
    <p class="hint" id="hint"></p>
    <div class="row" style="margin-top:0">
      <button id="btnRefresh"></button>
      <label class="primary" style="display:inline-block;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer">
        <span id="uploadLabel"></span>
        <input id="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp" hidden>
      </label>
    </div>
    <p class="hint" id="inbox"></p>
    <div id="library"></div>
  </aside>
  <section class="col">
    <div id="status"></div>
    <div class="pager">
      <button id="btnPrev"></button>
      <span id="pageLabel"></span>
      <button id="btnNext"></button>
    </div>
    <div class="stage-wrap" id="stageWrap">
      <p class="empty" id="empty"></p>
    </div>
  </section>
  <aside class="col">
    <div id="alist"></div>
    <div id="editor"></div>
  </aside>
</div>
<script>
const UI = __I18N__;
let library = [];
let currentRel = "";
let current = null;
let pageIndex = 0;
let selectedId = null;
let saveTimer = null;
let pollTimer = null;

const $ = (id) => document.getElementById(id);
function setText() {
  document.title = UI.app_name;
  $("btnAll").textContent = UI.recognize_all;
  $("btnGo").textContent = UI.recognize;
  $("btnTxt").textContent = UI.export_txt;
  $("btnMd").textContent = UI.export_md;
  $("btnJson").textContent = UI.export_json;
  $("btnRefresh").textContent = UI.refresh;
  $("btnPrev").textContent = UI.prev_page;
  $("btnNext").textContent = UI.next_page;
  $("hint").textContent = UI.hint;
  $("inbox").textContent = UI.inbox_note;
  $("uploadLabel").textContent = UI.upload;
  $("empty").textContent = UI.empty;
}
function kindLabel(kind) {
  if (kind === "ad") return UI.kind_ad;
  if (kind === "notice") return UI.kind_notice;
  return UI.kind_article;
}
async function refresh() {
  const res = await fetch("/api/library");
  library = await res.json();
  const box = $("library");
  box.innerHTML = "";
  library.forEach((item) => {
    const btn = document.createElement("button");
    btn.className = "file" + (item.rel === currentRel ? " on" : "");
    btn.textContent = item.name;
    if (item.done) {
      const s = document.createElement("small");
      s.textContent = UI.done;
      btn.appendChild(s);
    }
    btn.onclick = () => selectFile(item.rel);
    box.appendChild(btn);
  });
}
async function selectFile(rel) {
  currentRel = rel;
  await refresh();
  const res = await fetch("/api/result?rel=" + encodeURIComponent(rel));
  if (res.ok) {
    current = await res.json();
    pageIndex = 0;
    selectedId = (current.articles[0] || {}).id || null;
    render();
  } else {
    current = null;
    pageIndex = 0;
    selectedId = null;
    $("stageWrap").innerHTML = '<p class="empty" id="empty"></p>';
    $("empty").textContent = UI.empty;
    $("alist").innerHTML = "";
    $("editor").innerHTML = "";
    $("pageLabel").textContent = "";
    $("status").textContent = "";
  }
}
function pages() { return (current && current.pages) || []; }
function articlesOnPage() {
  if (!current) return [];
  const p = pages()[pageIndex];
  if (!p) return [];
  return current.articles.filter((a) => a.page === p.page);
}
function render() {
  const ps = pages();
  const p = ps[pageIndex];
  $("pageLabel").textContent = p ? (UI.page + " " + p.page + " / " + ps.length + (p.layout_label ? " \u00b7 " + p.layout_label : "")) : "";
  $("btnPrev").disabled = pageIndex <= 0;
  $("btnNext").disabled = !p || pageIndex >= ps.length - 1;
  const wrap = $("stageWrap");
  wrap.innerHTML = "";
  if (!p) {
    wrap.innerHTML = '<p class="empty"></p>';
    wrap.querySelector(".empty").textContent = UI.empty;
  } else {
    const stage = document.createElement("div");
    stage.className = "stage";
    const img = document.createElement("img");
    img.src = "/api/page?rel=" + encodeURIComponent(currentRel) + "&page=" + p.page + "&t=" + Date.now();
    img.alt = "";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + p.width + " " + p.height);
    articlesOnPage().forEach((a) => {
      const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      const [x0, y0, x1, y1] = a.bbox || [0, 0, 0, 0];
      r.setAttribute("x", x0);
      r.setAttribute("y", y0);
      r.setAttribute("width", Math.max(1, x1 - x0));
      r.setAttribute("height", Math.max(1, y1 - y0));
      r.setAttribute("class", "hit" + (a.id === selectedId ? " on" : ""));
      r.onclick = () => { selectedId = a.id; render(); };
      svg.appendChild(r);
    });
    stage.appendChild(img);
    stage.appendChild(svg);
    wrap.appendChild(stage);
    if (p.masthead) {
      const m = document.createElement("p");
      m.className = "hint";
      m.textContent = UI.masthead + "\uff1a" + p.masthead;
      wrap.appendChild(m);
    }
  }
  const list = $("alist");
  list.innerHTML = "";
  const arts = current ? current.articles : [];
  arts.forEach((a) => {
    const btn = document.createElement("button");
    btn.className = "card" + (a.id === selectedId ? " on" : "");
    const b = document.createElement("b");
    b.textContent = a.title || UI.untitled;
    btn.appendChild(b);
    const em = document.createElement("em");
    const bits = [UI.page + a.page, kindLabel(a.kind)];
    if (a.author) bits.push(a.author);
    if (a.featured) bits.push(UI.featured);
    em.textContent = bits.join(" \u00b7 ");
    btn.appendChild(em);
    btn.onclick = () => {
      selectedId = a.id;
      const idx = ps.findIndex((pg) => pg.page === a.page);
      if (idx >= 0) pageIndex = idx;
      render();
    };
    list.appendChild(btn);
  });
  renderEditor();
}
function selected() {
  if (!current) return null;
  return current.articles.find((a) => a.id === selectedId) || null;
}
function renderEditor() {
  const box = $("editor");
  box.innerHTML = "";
  const a = selected();
  if (!a) return;
  const lt = document.createElement("label");
  lt.textContent = UI.title;
  const it = document.createElement("input");
  it.type = "text";
  it.value = a.title || "";
  it.oninput = () => { a.title = it.value; scheduleSave(); };
  const la = document.createElement("label");
  la.textContent = UI.author;
  const ia = document.createElement("input");
  ia.type = "text";
  ia.placeholder = UI.author_ph;
  ia.value = a.author || "";
  ia.oninput = () => { a.author = ia.value; scheduleSave(); };
  const lb = document.createElement("label");
  lb.textContent = UI.body;
  const tb = document.createElement("textarea");
  tb.value = a.body || "";
  tb.oninput = () => { a.body = tb.value; scheduleSave(); };
  const row = document.createElement("div");
  row.className = "row";
  const merge = document.createElement("button");
  merge.textContent = UI.merge_prev;
  merge.onclick = () => mergePrev(a.id);
  const del = document.createElement("button");
  del.textContent = UI.delete;
  del.onclick = () => removeArt(a.id);
  row.appendChild(merge);
  row.appendChild(del);
  [lt, it, la, ia, lb, tb, row].forEach((n) => box.appendChild(n));
}
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveArticle, 350);
}
async function saveArticle() {
  const a = selected();
  if (!a || !currentRel) return;
  await fetch("/api/article", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({rel: currentRel, id: a.id, title: a.title, author: a.author, body: a.body})
  });
  $("status").textContent = UI.saved;
}
async function mergePrev(id) {
  await fetch("/api/merge", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({rel: currentRel, id: id})
  });
  await selectFile(currentRel);
}
async function removeArt(id) {
  await fetch("/api/delete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({rel: currentRel, id: id})
  });
  await selectFile(currentRel);
}
async function recognize(all) {
  if (!all && !currentRel) { $("status").textContent = UI.empty; return; }
  $("btnGo").disabled = true;
  $("btnAll").disabled = true;
  const res = await fetch("/api/process", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(all ? {all: true} : {rel: currentRel})
  });
  const data = await res.json();
  if (!res.ok) {
    $("status").textContent = data.error || UI.failed;
    $("btnGo").disabled = false;
    $("btnAll").disabled = false;
    return;
  }
  watch(data.job);
}
function watch(job) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const res = await fetch("/api/job?id=" + encodeURIComponent(job));
    const data = await res.json();
    $("status").textContent = data.message || UI.working;
    if (data.status === "done" || data.status === "error") {
      clearInterval(pollTimer);
      $("btnGo").disabled = false;
      $("btnAll").disabled = false;
      if (data.status === "done") {
        if (!currentRel && data.rel) currentRel = data.rel;
        await refresh();
        if (currentRel) await selectFile(currentRel);
      }
    }
  }, 800);
}
function exportAs(fmt) {
  if (!currentRel) return;
  clearTimeout(saveTimer);
  saveArticle().then(() => {
    window.location = "/api/export?rel=" + encodeURIComponent(currentRel) + "&fmt=" + fmt;
  });
}
$("btnRefresh").onclick = refresh;
$("btnGo").onclick = () => recognize(false);
$("btnAll").onclick = () => recognize(true);
$("btnTxt").onclick = () => exportAs("txt");
$("btnMd").onclick = () => exportAs("md");
$("btnJson").onclick = () => exportAs("json");
$("btnPrev").onclick = () => { if (pageIndex > 0) { pageIndex -= 1; render(); } };
$("btnNext").onclick = () => { if (current && pageIndex < pages().length - 1) { pageIndex += 1; render(); } };
$("file").onchange = async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/upload", {method: "POST", body: body});
  const data = await res.json();
  if (data.rel) await selectFile(data.rel);
  ev.target.value = "";
};
setText();
refresh();
</script>
</body>
</html>
"""


def render_page(ui):
    import json

    html = PAGE.replace("__TITLE__", ui["app_name"])
    html = html.replace("__I18N__", json.dumps(ui, ensure_ascii=True))
    return html
