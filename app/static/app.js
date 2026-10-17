"use strict";
// ThreatLens front end: plain JS, no external requests. All text is inserted as text nodes.

const state = {
  health: null, samples: [], analysis: null, text: "", tab: "paste", editing: true,
  decisions: [], selected: 0, explains: {}, picker: null, savedId: null,
  analyst: load("tl.analyst", "Analyst"),
};
const PAGES = { analyze: "Analyze report", queue: "Review queue", exports: "Reviewed exports", evaluation: "Model evaluation" };
const view = document.getElementById("view");

function load(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }
function store(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } }

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}
const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
function toast(msg) {
  const t = h("div", { class: "toast" }, msg);
  document.body.append(t); setTimeout(() => t.remove(), 3200);
}

// Highlight evidence terms (per suggestion rank) and masked values in a passage.
function highlight(text, groups) {
  const ranges = [];
  groups.forEach(({ terms, cls }) => terms.forEach((term) => {
    const words = term.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const re = new RegExp(`\\b${words.join("\\W+")}\\w*`, "gi");
    for (const m of text.matchAll(re)) ranges.push([m.index, m.index + m[0].length, cls]);
  }));
  for (const m of text.matchAll(/\[(IP|URL|EMAIL|DOMAIN|HASH|USER)\]/g)) ranges.push([m.index, m.index + m[0].length, "redacted"]);
  ranges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const frag = document.createDocumentFragment();
  let pos = 0;
  for (const [s, e, cls] of ranges) {
    if (s < pos) continue;
    frag.append(text.slice(pos, s));
    frag.append(cls === "redacted" ? h("span", { class: "redacted", title: "masked before analysis" }, text.slice(s + 1, e - 1)) : h("mark", { class: cls }, text.slice(s, e)));
    pos = e;
  }
  frag.append(text.slice(pos));
  return frag;
}
const rankGroups = () => (state.analysis?.suggestions || []).map((s, i) => ({ terms: s.evidence_terms || [], cls: `r${i + 1}` }));

// ---------- Shared decision helpers ----------
function decide(i, decision, extra = {}) {
  state.decisions[i] = { ...state.decisions[i], decision, ...extra };
  state.picker = null; state.savedId = null;
  render();
}
const pending = () => state.decisions.filter((d) => d.decision === "pending").length;
const DECISION_TEXT = { accepted: "✓ Accepted", corrected: "✎ Corrected", rejected: "✕ Rejected", pending: "! Needs review" };

function picker(i) {
  const s = state.analysis.suggestions[i];
  const list = h("ul");
  const fill = (items) => {
    list.replaceChildren(...items.filter((t) => t.technique_id !== s.technique_id).map((t) => h("li", {},
      h("button", { onclick: () => decide(i, "corrected", { corrected_to: t.technique_id, corrected_name: t.name }) },
        h("b", {}, t.technique_id), " · ", t.name, t.score != null ? h("small", {}, `  model score ${t.score.toFixed(2)}`) : ""))));
  };
  fill(state.analysis.alternatives);
  let timer;
  const input = h("input", { placeholder: "Search all techniques by ID or name…", oninput: (e) => {
    clearTimeout(timer);
    const q = e.target.value.trim();
    timer = setTimeout(async () => fill(q ? await api(`/api/techniques?q=${encodeURIComponent(q)}`) : state.analysis.alternatives), 200);
  } });
  setTimeout(() => input.focus(), 0);
  return h("div", { class: "picker" }, h("div", { class: "label", style: "margin-top:0" }, "Choose the correct technique (next-best model suggestions first)"), input, list);
}

async function explain(i, btn) {
  const s = state.analysis.suggestions[i];
  btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner dark" }), "Granite is writing on LinuxONE…");
  try {
    state.explains[i] = await api("/api/explain", { technique_id: s.technique_id, evidence: s.evidence, evidence_terms: s.evidence_terms });
  } catch (e) { state.explains[i] = { error: e.message }; }
  render();
}
function whyBlock(i) {
  const x = state.explains[i];
  if (!x) return null;
  if (x.error) return h("div", { class: "why" }, x.error);
  const granite = x.kind !== "evidence";
  return h("div", { class: "why" },
    h("div", { class: "why-h" }, granite ? "AI explanation · IBM Granite, generated on LinuxONE" : "Evidence-based explanation"),
    x.text || "(no explanation generated)",
    h("small", {}, granite
      ? `Focused on: “${x.focus}” · ${x.model} · ${x.seconds}s. Generated text: check it against the evidence above.`
      : `Granite only repeated the passage, so ThreatLens shows the matching clause and the ATT&CK definition instead.`));
}

// ---------- Analyze page ----------
async function analyze(btn) {
  const text = state.text.trim();
  if (!text) return toast("Paste a sentence or short passage first.");
  if (btn) { btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Analysing on LinuxONE…"); }
  try {
    state.analysis = await api("/api/analyze", { text });
    state.decisions = state.analysis.suggestions.map((s) => ({ decision: "pending", note: "", technique_id: s.technique_id }));
    state.explains = {}; state.picker = null; state.selected = 0; state.editing = false; state.savedId = null;
  } catch (e) { toast(e.message); }
  render();
}

function renderAnalyze() {
  const a = state.analysis;
  const input = state.editing || !a
    ? h("textarea", { placeholder: "Paste a sentence or short passage from a threat report…", oninput: (e) => (state.text = e.target.value) }, state.text)
    : h("div", { class: "passage-view" }, highlight(a.passage_redacted, rankGroups()));
  const samples = h("div", { class: "samples" }, state.samples.map((s) => h("button", { class: "sample", onclick: () => { state.text = s.text; state.tab = "paste"; state.editing = true; render(); } },
    h("b", {}, s.title), h("span", {}, s.text.length > 150 ? s.text.slice(0, 150) + "…" : s.text))));
  const left = h("div", {},
    h("div", { class: "card" },
      h("h2", {}, "Report passage"),
      h("div", { class: "tabs" },
        h("button", { class: state.tab === "paste" ? "on" : "", onclick: () => { state.tab = "paste"; render(); } }, "Paste text"),
        h("button", { class: state.tab === "sample" ? "on" : "", onclick: () => { state.tab = "sample"; render(); } }, "Sample passage")),
      state.tab === "sample" ? samples : input,
      h("div", { class: "hint" }, h("span", {}, "Use a sentence or short passage. IPs, domains, emails, hashes and user names are masked before analysis."),
        a && !state.editing ? h("button", { class: "linkbtn", onclick: () => { state.editing = true; render(); } }, "Edit passage") : null),
      h("button", { class: "primary", onclick: (e) => analyze(e.currentTarget) }, "Suggest techniques", h("span", {}, "→")),
      a && Object.keys(a.redactions).length ? h("div", { class: "notice" },
        "Masked before analysis: ", Object.entries(a.redactions).map(([k, v]) => `${v} ${k}`).join(", "), ". Only the masked text is stored or exported.") : null,
      a ? h("details", { class: "masked" }, h("summary", {}, "View masked input"),
        h("p", { class: "desc" }, Object.keys(a.redactions).length
          ? "The model, the AI explanation and any saved review only ever see this masked version:"
          : "Nothing sensitive was detected, so the text was analysed as entered:"),
        h("pre", {}, a.passage_redacted)) : null),
    h("div", { class: "card private" },
      h("div", { class: "ico" }, lockIcon()),
      h("div", {}, h("h3", {}, "Private by design"),
        h("p", {}, a ? `Analysed on IBM LinuxONE (${a.platform}) in ${a.latency_ms} ms. Analysis and storage stay on your LinuxONE server.`
                     : "Analysis and storage stay on your LinuxONE server. No report text is sent to an external AI service."))));

  let right;
  if (!a) {
    right = h("div", {}, h("div", { class: "sugg-head" }, h("h2", {}, "Suggested techniques")),
      h("p", { class: "sub" }, "Ranked suggestions · Confirm against the evidence"),
      h("div", { class: "empty" }, "Paste a passage or pick a sample, then choose ", h("b", {}, "Suggest techniques"), ". You will get the three most likely MITRE ATT&CK techniques, the sentence that supports each one, and the words that drove the score."));
  } else {
    right = h("div", {},
      h("div", { class: "sugg-head" }, h("h2", {}, "Suggested techniques"), h("span", { class: "badge" }, `${pending()} to review`)),
      h("p", { class: "sub" }, "Ranked suggestions · Confirm against the evidence"),
      a.suggestions.map((s, i) => suggestionCard(s, i)),
      h("div", { class: "footnote" }, h("span", {}, "Model suggestions · Human review required"),
        h("a", { class: "btn ghost", href: "#/queue" }, listIcon(), "Review summary")));
  }
  view.replaceChildren(
    h("div", { class: "hero" }, h("div", {}, h("h1", {}, "Turn reports into clear evidence."), h("p", { class: "lede" }, "Paste a passage. Review three suggestions. Keep control.")),
      h("span", { class: "tag" }, "Runs on IBM LinuxONE")),
    h("div", { class: "grid2" }, left, right));
}

function suggestionCard(s, i) {
  const d = state.decisions[i];
  const stateLabel = d.decision === "corrected" ? `✎ Corrected to ${d.corrected_to} · ${d.corrected_name}` : DECISION_TEXT[d.decision];
  const decided = d.decision !== "pending";
  const undo = () => decide(i, "pending", { corrected_to: "", corrected_name: "" });
  return h("div", { class: `card sugg${decided ? ` done-${d.decision}` : ""}` },
    h("div", { class: "rank" }, String(i + 1).padStart(2, "0")),
    h("div", {},
      h("div", { class: "tid" }, s.technique_id),
      h("h3", {}, s.name),
      h("div", { class: "chips" }, s.tactics.map((t) => h("span", { class: "chip" }, t))),
      h("p", { class: "desc" }, s.summary),
      h("div", { class: "quote" }, h("span", { class: "quote-h" }, "Evidence from the passage"), "“", highlight(s.evidence, [{ terms: s.evidence_terms, cls: `r${i + 1}` }]), "”"),
      h("div", { class: "actions" },
        h("span", { class: `state ${d.decision}` }, stateLabel),
        h("button", { class: "btn", onclick: (e) => explain(i, e.currentTarget), disabled: !state.health?.granite?.available, title: "Ask IBM Granite (runs on LinuxONE) to explain this match" }, "AI explanation"),
        decided
          ? h("button", { class: "btn", onclick: undo, title: "Back to undecided" }, "Undo")
          : [h("button", { class: "btn", onclick: () => decide(i, "rejected", { corrected_to: "", corrected_name: "" }) }, "✕ Reject"),
             h("button", { class: "btn", onclick: () => { state.picker = state.picker === i ? null : i; render(); } }, "✎ Correct"),
             h("button", { class: "btn go", onclick: () => decide(i, "accepted", { corrected_to: "", corrected_name: "" }) }, "✓ Accept")]),
      state.picker === i ? picker(i) : null,
      whyBlock(i)));
}

// ---------- Review queue ----------
async function saveReview(btn) {
  btn.disabled = true;
  try {
    const a = state.analysis;
    const r = await api("/api/reviews", {
      analyst: state.analyst, passage: a.passage_redacted,
      decisions: a.suggestions.map((s, i) => ({ ...state.decisions[i], technique_id: s.technique_id, score: s.score, rank: s.rank, evidence: s.evidence })),
    });
    state.savedId = r.review_id;
    toast(`Review ${r.review_id} saved on LinuxONE (masked text only).`);
  } catch (e) { toast(e.message); }
  render();
}

function renderQueue() {
  const a = state.analysis;
  const hero = h("div", { class: "hero" }, h("div", {}, h("h1", {}, "Your judgement. Clearly documented."),
    h("p", { class: "lede" }, "Check the evidence, confirm the mapping, and export your review.")), h("span", { class: "tag" }, "Human in the loop"));
  if (!a) return view.replaceChildren(hero, h("div", { class: "empty" }, "No passage under review yet. ", h("a", { href: "#/analyze" }, "Analyze a report"), " first."));
  const accepted = state.decisions.filter((d) => d.decision === "accepted" || d.decision === "corrected").length;
  const i = Math.min(state.selected, a.suggestions.length - 1);
  const s = a.suggestions[i], d = state.decisions[i];
  const rows = a.suggestions.map((x, j) => {
    const dj = state.decisions[j];
    return h("tr", { class: j === i ? "sel" : "", onclick: () => { state.selected = j; state.picker = null; render(); } },
      h("td", {}, h("b", {}, x.technique_id), " · ", x.name, dj.decision === "corrected" ? h("div", { class: "chip", style: "margin-top:6px;display:inline-block" }, `→ ${dj.corrected_to} · ${dj.corrected_name}`) : null),
      h("td", {}, (x.evidence_terms || []).join(", ") || x.evidence.slice(0, 80)),
      h("td", {}, h("span", { class: `state ${dj.decision}` }, DECISION_TEXT[dj.decision])));
  });
  const panel = h("div", { class: "card panel" },
    h("h2", {}, "Review suggestion"),
    h("span", { class: "idchip" }, s.technique_id),
    h("h3", {}, s.name),
    h("p", { class: "desc" }, s.summary),
    h("div", { class: "label" }, "Evidence from report"),
    h("div", { class: "quote" }, "“", highlight(s.evidence, [{ terms: s.evidence_terms, cls: `r${i + 1}` }]), "”"),
    whyBlock(i) || h("button", { class: "btn", onclick: (e) => explain(i, e.currentTarget), disabled: !state.health?.granite?.available }, "AI explanation (IBM Granite)"),
    h("div", { class: "label" }, "Analyst note"),
    h("textarea", { placeholder: "Why you accepted or changed this mapping…", oninput: (e) => { state.decisions[i].note = e.target.value; state.savedId = null; } }, d.note || ""),
    d.decision !== "pending" ? h("div", { class: `decided ${d.decision}` },
      d.decision === "corrected" ? `✎ Corrected to ${d.corrected_to} · ${d.corrected_name}` : DECISION_TEXT[d.decision],
      h("button", { class: "linkbtn", onclick: () => decide(i, "pending", { corrected_to: "", corrected_name: "" }) }, "Undo")) : null,
    h("div", { class: "btnrow" },
      h("button", { class: "btn go", disabled: d.decision === "accepted", onclick: () => decide(i, "accepted", { corrected_to: "", corrected_name: "" }) },
        d.decision === "accepted" ? "Accepted ✓" : "Accept suggestion"),
      h("button", { class: "btn ghost", onclick: () => { state.picker = state.picker === i ? null : i; render(); } },
        d.decision === "corrected" ? "Change again" : "Change technique"),
      h("button", { class: "btn", disabled: d.decision === "rejected", onclick: () => decide(i, "rejected", { corrected_to: "", corrected_name: "" }) },
        d.decision === "rejected" ? "Rejected ✕" : "Reject")),
    state.picker === i ? picker(i) : null);
  const fmt = h("select", {}, h("option", { value: "csv" }, "CSV"), h("option", { value: "json" }, "JSON"));
  const left = pending();
  view.replaceChildren(hero,
    h("div", { class: "kpis" },
      kpi(docIcon(), a.suggestions.length, "suggestions"), kpi(checkIcon(), accepted, "accepted"), kpi(warnIcon(), left, "needs review", true)),
    h("div", { class: "queue" },
      h("div", { class: "card" },
        h("h2", {}, "Source passage"),
        h("div", { style: "font-size:17px;line-height:1.8;white-space:pre-wrap" }, highlight(a.passage_redacted, rankGroups())),
        h("h2", { style: "margin-top:24px" }, "Review decisions"),
        h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Technique"), h("th", {}, "Evidence"), h("th", {}, "Decision"))), h("tbody", {}, rows))),
      panel),
    h("div", { class: "card exportbar" },
      h("div", { class: "ico" }, docIcon()),
      h("div", { class: "grow" }, h("h3", {}, "Export reviewed results"),
        h("p", {}, left ? `${left} suggestion${left > 1 ? "s" : ""} still need${left > 1 ? "" : "s"} a decision.` : state.savedId ? `Saved as review ${state.savedId}.` : "All suggestions reviewed. Save, then export.")),
      h("span", {}, "Format"), fmt,
      h("button", { class: "btn ghost", disabled: left > 0 || !!state.savedId, onclick: (e) => saveReview(e.currentTarget) }, state.savedId ? "Saved" : "Save review"),
      h("button", { class: "btn go", disabled: !state.savedId, onclick: () => (location.href = `/api/export?format=${fmt.value}`) }, "Export results")));
}
const kpi = (icon, n, label, warn) => h("div", { class: "card kpi" }, h("div", { class: `ico${warn ? " warn" : ""}` }, icon), h("div", {}, h("b", {}, n), h("span", {}, label)));

// ---------- Reviewed exports ----------
async function renderExports() {
  view.replaceChildren(h("div", { class: "empty" }, "Loading saved reviews…"));
  const reviews = await api("/api/reviews").catch(() => []);
  const count = (r, k) => r.decisions.filter((d) => d.decision === k).length;
  const dl = (fmt, cls) => reviews.length
    ? h("a", { class: `btn ${cls}`, href: `/api/export?format=${fmt}` }, `Download ${fmt.toUpperCase()}`)
    : h("button", { class: `btn ${cls}`, disabled: true, title: "Save a review first" }, `Download ${fmt.toUpperCase()}`);
  view.replaceChildren(
    h("div", { class: "hero" }, h("div", {}, h("h1", {}, "Reviewed exports."), h("p", { class: "lede" }, "Every saved review, stored on LinuxONE with sensitive values masked.")),
      h("div", { class: "btnrow", style: "margin:0" }, dl("csv", "go"), dl("json", ""))),
    reviews.length ? h("div", { class: "card" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Saved (UTC)", "Analyst", "Accepted", "Corrected", "Rejected", "Passage (masked)"].map((t) => h("th", {}, t)))),
      h("tbody", {}, reviews.map((r) => h("tr", {}, h("td", {}, r.saved_utc), h("td", {}, r.analyst), h("td", {}, count(r, "accepted")),
        h("td", {}, count(r, "corrected")), h("td", {}, count(r, "rejected")),
        h("td", {}, r.passage_redacted.length > 140 ? r.passage_redacted.slice(0, 140) + "…" : r.passage_redacted))))))
      : h("div", { class: "empty" }, h("p", { style: "margin:0 0 16px" }, "No reviews saved yet. Analyse a passage, decide on each suggestion in the Review queue, then choose ", h("b", {}, "Save review"), "."),
          h("a", { class: "btn go", href: "#/analyze" }, "Analyze a passage")));
}

// ---------- Model evaluation ----------
async function renderEvaluation() {
  view.replaceChildren(h("div", { class: "empty" }, "Loading evaluation…"));
  const ev = await api("/api/evaluation").catch(() => null);
  const m = ev?.metrics, hl = state.health;
  if (!m?.results) return view.replaceChildren(h("div", { class: "empty" }, "No evaluation results found on the server."));
  const R = m.results;
  const metricRows = [];
  for (const split of ["test", "external_test", "val"]) for (const subset of ["all", "clean"]) for (const level of ["technique", "parent"]) {
    const x = R[split][subset][level];
    metricRows.push(h("tr", {}, h("td", {}, split === "external_test" ? "CISA (external)" : split), h("td", {}, subset), h("td", {}, level), h("td", {}, x.rows),
      h("td", {}, pct(x["hit@1"])), h("td", {}, h("b", {}, pct(x["hit@3"])), h("div", { class: "bar" }, h("i", { style: `width:${x["hit@3"] * 100}%` }))),
      h("td", {}, pct(x["hit@5"])), h("td", {}, x.micro_f1.toFixed(3)), h("td", {}, x.macro_f1.toFixed(3))));
  }
  const corpus = ev.corpus || {};
  const T = R.test.all.technique, X = R.external_test.all.technique;
  view.replaceChildren(
    h("div", { class: "hero" }, h("div", {}, h("h1", {}, "Measured, not promised."),
      h("p", { class: "lede" }, "Trained and tested on IBM LinuxONE. Tuned on validation only; test and CISA scored once.")), h("span", { class: "tag" }, `Evaluated ${m.built_utc} UTC`)),
    h("div", { class: "tiles" },
      tile(pct(T["hit@3"]), "Top-3 hit rate (test)", `${pct(R.test.clean.technique["hit@3"])} on near-duplicate-free rows`),
      tile(T.micro_f1.toFixed(2), "Micro-F1 (test)", `threshold ${m.threshold}, tuned on validation`),
      tile(pct(X["hit@3"]), "Top-3 on CISA advisories", `never trained on · ${pct(R.external_test.all.parent["hit@3"])} at parent level`),
      tile(`${m.latency_ms_per_sentence} ms`, "Model latency per sentence", "TF-IDF + scoring on LinuxONE CPU; excludes network and browser")),
    h("div", { class: "stack" },
      h("div", { class: "card" }, h("h2", {}, "Model card"),
        kv(
          "Model", `${m.model} (C=${m.C})`,
          "Evaluated model", `${m.labels_in_model} techniques learned from train only (techniques with ≥ ${m.min_support} examples)`,
          "Served model", hl?.model_meta?.trained_on ? `${hl.labels} techniques, retrained on ${hl.model_meta.trained_on} (${hl.model_meta.rows.toLocaleString()} rows) with the same settings` : "–",
          "Label catalogue", hl ? `MITRE ATT&CK Enterprise STIX bundle (updated ${hl.attack_updated}), ${hl.catalogue} active techniques` : "–",
          "Generative step", hl?.granite?.available ? `IBM Granite ${hl.granite.file} via llama.cpp ${hl.libraries.llama_cpp_python}: optional explanation, not used for scoring` : "not available",
          "Platform", hl ? `IBM LinuxONE ${hl.platform}, ${hl.cpus} CPUs; NNPA on-chip AI ${hl.nnpa ? "available on this server (the classifier itself runs on CPU)" : "not listed"}` : m.platform,
          "Corpus", corpus.unique_rows ? `${corpus.unique_rows.toLocaleString()} sentences; ${corpus.distinct_techniques_per_split?.train} techniques in train` : "–")),
      h("details", { class: "card more" }, h("summary", {}, "View detailed evaluation"),
        h("p", { class: "desc" }, "Hit@k: a correct technique appears in the top k suggestions. Clean: held-out rows sharing under half their 8-word phrases with training text. Parent: sub-techniques counted at their parent technique."),
        h("table", {}, h("thead", {}, h("tr", {}, ["Split", "Subset", "Level", "Rows", "Hit@1", "Hit@3", "Hit@5", "Micro-F1", "Macro-F1"].map((t) => h("th", {}, t)))), h("tbody", {}, metricRows)),
        h("h2", { style: "margin-top:24px" }, "Test split by source"),
        h("table", {}, h("thead", {}, h("tr", {}, ["Source", "Rows", "Hit@3", "Hit@3 parent"].map((t) => h("th", {}, t)))),
          h("tbody", {}, Object.entries(R.test_by_source).filter(([, b]) => b.technique.rows >= 20).map(([src, b]) =>
            h("tr", {}, h("td", {}, src), h("td", {}, b.technique.rows), h("td", {}, pct(b.technique["hit@3"])), h("td", {}, pct(b.parent["hit@3"]))))))),
      h("div", { class: "card" }, h("h2", {}, "Examples from CISA advisories (never seen in training)"),
        ev.examples.map((x) => h("div", { class: "ex" }, h("span", { class: x.hit ? "ok" : "no" }, x.hit ? "✓ correct in top 3 " : "✕ missed "), x.text,
          h("div", { class: "desc", style: "margin:4px 0 0" }, `Reference: ${x.gold} (${x.gold_names}) · Model top 3: ${x.top3.map((t, k) => `${t} ${x.names[k]}`).join(" | ")}`))))));
}
const kv = (...pairs) => h("div", { class: "kv" }, pairs.map((x) => h("div", {}, x)));
const tile = (big, label, small) => h("div", { class: "card tile" }, h("b", {}, big), h("span", {}, label), h("small", {}, small));

// ---------- Icons (inline SVG, no external assets) ----------
function svg(paths, color = "#0E6E4E") {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  el.setAttribute("viewBox", "0 0 24 24"); el.setAttribute("width", "24"); el.setAttribute("height", "24");
  el.setAttribute("fill", "none"); el.setAttribute("stroke", color); el.setAttribute("stroke-width", "1.8");
  el.setAttribute("stroke-linecap", "round"); el.setAttribute("stroke-linejoin", "round");
  paths.forEach((d) => { const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", d); el.append(p); });
  return el;
}
const lockIcon = () => svg(["M6 11h12v10H6z", "M8 11V8a4 4 0 0 1 8 0v3", "M12 15v2"]);
const docIcon = () => svg(["M6 3h8l4 4v14H6z", "M14 3v4h4", "M9 12h6M9 16h6"]);
const checkIcon = () => svg(["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M8 12l3 3 5-6"]);
const warnIcon = () => svg(["M12 3l9 16H3z", "M12 10v4", "M12 17h.01"], "#8A5A12");
const listIcon = () => svg(["M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"], "#0B2D26");

// ---------- Router & boot ----------
function render() {
  const page = (location.hash.replace("#/", "") || "analyze").split("?")[0];
  const key = PAGES[page] ? page : "analyze";
  document.getElementById("crumb").textContent = PAGES[key];
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === key));
  ({ analyze: renderAnalyze, queue: renderQueue, exports: renderExports, evaluation: renderEvaluation })[key]();
}
function setAnalyst(name) {
  state.analyst = name; store("tl.analyst", name);
  document.getElementById("analyst-name").textContent = name;
  document.getElementById("avatar").textContent = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}
document.getElementById("analyst-btn").addEventListener("click", () => {
  const name = prompt("Analyst name (stored with saved reviews)", state.analyst);
  if (name && name.trim()) setAnalyst(name.trim().slice(0, 40));
});
window.addEventListener("hashchange", () => { state.picker = null; render(); });

(async function boot() {
  setAnalyst(state.analyst);
  render();
  try {
    state.health = await api("/api/health");
    document.getElementById("status-dot").classList.add("ok");
    document.getElementById("status-text").textContent = `LinuxONE · ${state.health.platform} · Local`;
    document.getElementById("foot-platform").textContent = `IBM LinuxONE · ${state.health.platform}`;
    document.getElementById("foot-model").textContent =
      `Model covers ${state.health.labels} of ${state.health.catalogue} ATT&CK techniques${state.health.nnpa ? " · NNPA available" : ""}`;
    state.samples = await api("/api/samples");
  } catch {
    document.getElementById("status-dot").classList.remove("ok");
    document.getElementById("status-text").textContent = "Server not reachable";
  }
  render();
  // Deep link for demos: #/analyze?sample=1 (or #/queue?sample=1) fills and analyses that sample.
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const n = Number(params.get("sample"));
  if (n && state.samples[n - 1]) {
    state.text = state.samples[n - 1].text;
    await analyze(document.querySelector(".primary"));
    // &explain=1 also asks Granite about the first suggestion (for demos and screenshots).
    if (params.get("explain") && state.analysis) {
      const btn = [...document.querySelectorAll(".btn")].find((b) => b.textContent.startsWith("AI explanation"));
      if (btn) await explain(0, btn);
    }
  }
})();
