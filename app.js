"use strict";

const PYODIDE_VERSION = "0.26.4";
const $ = (id) => document.getElementById(id);
const ALL = [...PROJECTS, SANDBOX];

/* ---------- Speicher (Fortschritt + eigener Code) ---------- */
const store = (() => {
  const KEY = "python-werkstatt-v1";
  let data = { done: {}, code: {} };
  try { data = { ...data, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch (_) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (_) {} };
  return {
    isDone: (p, s) => !!(data.done[p] && data.done[p].includes(s)),
    doneCount: (p) => (data.done[p] || []).length,
    toggleDone(p, s) {
      const l = (data.done[p] = data.done[p] || []);
      const i = l.indexOf(s);
      i >= 0 ? l.splice(i, 1) : l.push(s);
      save();
    },
    getCode: (p, s) => data.code[`${p}:${s}`],
    setCode(p, s, c) { data.code[`${p}:${s}`] = c; save(); },
    clearCode(p, s) { delete data.code[`${p}:${s}`]; save(); },
  };
})();

/* ---------- Python (Pyodide) ---------- */
let pyodide = null;
let running = false;

function setStatus(t) { $("status").textContent = t; }

function loadPython() {
  const s = document.createElement("script");
  s.src = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.js`;
  s.onerror = () => setStatus("⚠ Python konnte nicht geladen werden (Internet?)");
  s.onload = async () => {
    try {
      pyodide = await loadPyodide();
      pyodide.setStdout({ batched: (t) => print(t + "\n") });
      pyodide.setStderr({ batched: (t) => print(t + "\n", "err") });
      pyodide.registerJsModule("werkstatt", {
        input(prompt) {
          const answer = window.prompt(prompt || "Eingabe:");
          print(prompt, "");
          print((answer ?? "") + "\n", "inp");
          return answer;
        },
      });
      pyodide.runPython(`
import builtins, werkstatt
def _input(prompt=""):
    r = werkstatt.input(str(prompt))
    if r is None:
        raise KeyboardInterrupt("Eingabe abgebrochen")
    return r
builtins.input = _input
`);
      setStatus("Python bereit ✓");
      $("run").disabled = false;
    } catch (e) {
      setStatus("⚠ Fehler beim Start von Python");
      console.error(e);
    }
  };
  document.head.appendChild(s);
}

function print(text, cls = "") {
  const out = $("output");
  if (cls) {
    const span = document.createElement("span");
    span.className = cls;
    span.textContent = text;
    out.appendChild(span);
  } else {
    out.appendChild(document.createTextNode(text));
  }
  out.scrollTop = out.scrollHeight;
}

function friendlyError(msg) {
  // Interne Pyodide-Zeilen weglassen, nur den eigenen Code im Traceback zeigen.
  const i = msg.indexOf('File "<exec>"');
  if (i < 0) return msg.trim() + "\n";
  return ("Traceback (most recent call last):\n  " + msg.slice(i)).trim() + "\n";
}

async function runCode() {
  if (!pyodide || running) return;
  running = true;
  $("run").disabled = true;
  $("output").textContent = "";
  try {
    const globals = pyodide.globals.get("dict")();
    await pyodide.runPythonAsync($("code").value, { globals });
    globals.destroy();
  } catch (e) {
    print(friendlyError(String(e.message || e)), "err");
  } finally {
    running = false;
    $("run").disabled = false;
  }
}

/* ---------- Ansichten ---------- */
let cur = { project: null, step: 0 };

function showView(name) {
  $("home").classList.toggle("hidden", name !== "home");
  $("workshop").classList.toggle("hidden", name !== "workshop");
}

function renderHome() {
  const total = PROJECTS.reduce((n, p) => n + p.steps.length, 0);
  const done = PROJECTS.reduce((n, p) => n + store.doneCount(p.id), 0);
  $("overall").textContent = `${done} von ${total} Schritten geschafft`;
  $("cards").innerHTML = "";
  for (const p of PROJECTS) {
    const d = store.doneCount(p.id);
    const el = document.createElement("button");
    el.className = "card";
    el.innerHTML = `
      <span class="icon">${p.icon}</span>
      <h3></h3><p></p>
      <div class="tags"></div>
      <div class="bar"><i style="width:${(d / p.steps.length) * 100}%"></i></div>`;
    el.querySelector("h3").textContent = p.title;
    el.querySelector("p").textContent = p.summary;
    const tags = el.querySelector(".tags");
    for (const t of [p.level, ...p.concepts]) {
      const s = document.createElement("span");
      s.className = "tag";
      s.textContent = t;
      tags.appendChild(s);
    }
    el.onclick = () => (location.hash = `#/${p.id}/0`);
    $("cards").appendChild(el);
  }
}

function openProject(id, step = 0) {
  const p = ALL.find((x) => x.id === id);
  if (!p) return (location.hash = "");
  cur = { project: p, step: Math.min(Math.max(step, 0), p.steps.length - 1) };
  showView("workshop");
  $("p-title").textContent = `${p.icon} ${p.title}`;
  $("p-summary").textContent = p.summary;
  $("ideas").innerHTML = "";
  p.ideas.forEach((i) => {
    const li = document.createElement("li");
    li.textContent = i;
    $("ideas").appendChild(li);
  });
  $("ideas-box").classList.toggle("hidden", !p.ideas.length);
  renderStep();
}

function renderStep() {
  const { project: p, step } = cur;
  const s = p.steps[step];
  const sandbox = p === SANDBOX;

  $("steps").classList.toggle("hidden", sandbox);
  $("done").classList.toggle("hidden", sandbox);
  $("hint").classList.toggle("hidden", sandbox);
  $("steps").innerHTML = "";
  p.steps.forEach((_, i) => {
    const b = document.createElement("button");
    b.textContent = i + 1;
    b.title = p.steps[i].title;
    b.className = (i === step ? "active " : "") + (store.isDone(p.id, i) ? "done" : "");
    b.onclick = () => (location.hash = `#/${p.id}/${i}`);
    $("steps").appendChild(b);
  });

  $("step-body").innerHTML = `<h3>${sandbox ? "Sandkiste" : `Schritt ${step + 1}: ${s.title}`}</h3>${s.text}`;
  $("code").value = store.getCode(p.id, step) ?? s.code;
  $("output").textContent = "";
  $("hint-box").classList.add("hidden");
  updateDoneButton();
}

function updateDoneButton() {
  const d = store.isDone(cur.project.id, cur.step);
  $("done").classList.toggle("is-done", d);
  $("done").textContent = d ? "✓ Geschafft!" : "✓ Schritt geschafft";
}

function route() {
  const m = location.hash.match(/^#\/([\w-]+)(?:\/(\d+))?/);
  if (m) return openProject(m[1], Number(m[2] || 0));
  showView("home");
  renderHome();
}

/* ---------- Editor-Komfort ---------- */
function setupEditor() {
  const ta = $("code");
  ta.addEventListener("input", () => store.setCode(cur.project.id, cur.step, ta.value));
  ta.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); return runCode(); }
    const { selectionStart: a, selectionEnd: b, value: v } = ta;
    const insert = (txt) => {
      ta.setRangeText(txt, a, b, "end");
      ta.dispatchEvent(new Event("input"));
    };
    if (e.key === "Tab") { e.preventDefault(); insert("    "); }
    if (e.key === "Enter") {
      // Automatisch einrücken, nach ":" eine Stufe tiefer
      const line = v.slice(v.lastIndexOf("\n", a - 1) + 1, a);
      const indent = line.match(/^ */)[0] + (/:\s*$/.test(line) ? "    " : "");
      e.preventDefault();
      insert("\n" + indent);
    }
  });
}

/* ---------- Start ---------- */
$("run").onclick = runCode;
$("clear").onclick = () => ($("output").textContent = "");
$("open-sandbox").onclick = () => (location.hash = "#/sandbox/0");
$("back").onclick = () => (location.hash = "");
$("logo").onclick = (e) => { e.preventDefault(); location.hash = ""; route(); };
$("hint").onclick = () => {
  const box = $("hint-box");
  box.textContent = "💡 " + cur.project.steps[cur.step].hint;
  box.classList.toggle("hidden");
};
$("reset").onclick = () => {
  if (!confirm("Code auf den Anfang zurücksetzen? Deine Änderungen gehen verloren.")) return;
  store.clearCode(cur.project.id, cur.step);
  renderStep();
};
$("done").onclick = () => {
  store.toggleDone(cur.project.id, cur.step);
  renderStep();
};

setupEditor();
window.addEventListener("hashchange", route);
route();
loadPython();
