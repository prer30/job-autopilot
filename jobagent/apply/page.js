// Injected into every frame of an application page. Exposes window.__ja with:
//   collect(onlyNew)  -> list of form questions (and tags each element with data-ja)
//   mark(statuses)    -> colors fields: green filled, yellow AI draft, orange needs you
//   banner(summary)   -> top-of-page status bar + highlights the Submit button
//   confirmation()    -> true if the page looks like "application submitted"
// Nothing here ever clicks or submits anything.
(() => {
  if (window.__ja) return;
  let counter = 0;
  const prefix = Math.random().toString(36).slice(2, 6);
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const SKIP_TYPES = new Set(["hidden", "submit", "button", "image", "reset", "password", "search"]);
  const SUBMIT_RX = /^(submit|submit application|apply|apply now|send application|send|finish|complete application)$/i;

  const visible = (el) => {
    if (el.type === "file") return true; // file inputs are usually hidden behind a styled button
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden") return false;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return true;
    // visually-hidden radios/checkboxes styled via their label
    return (el.type === "radio" || el.type === "checkbox") && !!el.closest("label, fieldset, [role=radiogroup], [role=group]");
  };

  const textOf = (n) => clean(n ? (n.innerText || n.textContent) : "");

  function ownLabel(el) {
    const parts = [];
    const al = el.getAttribute("aria-label");
    if (al) parts.push(al);
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(textOf(n)); });
    if (el.id) {
      try { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) parts.push(textOf(l)); } catch (e) {}
    }
    const wrap = el.closest("label");
    if (wrap) parts.push(textOf(wrap));
    return clean([...new Set(parts)].join(" | "));
  }

  function nearbyQuestion(el, exclude) {
    // Walk up a few levels looking for a label/legend-ish element that isn't the input itself.
    let n = el.parentElement;
    for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
      const lab = n.querySelector("legend, label, [class*='label' i], [class*='question' i], h3, h4, p");
      if (lab && !lab.contains(el) && !(exclude || []).some((x) => lab.contains(x))) {
        const t = textOf(lab);
        if (t && t.length < 400) return t;
      }
    }
    return "";
  }

  function groupQuestion(inputs) {
    const fs = inputs[0].closest("fieldset");
    if (fs) { const lg = fs.querySelector("legend"); if (lg) return textOf(lg); }
    const rg = inputs[0].closest("[role=radiogroup], [role=group]");
    if (rg) {
      const id = rg.getAttribute("aria-labelledby");
      if (id && document.getElementById(id)) return textOf(document.getElementById(id));
      if (rg.getAttribute("aria-label")) return rg.getAttribute("aria-label");
    }
    // lowest ancestor containing every option; its text minus the option labels is the question
    let anc = inputs[0].parentElement;
    while (anc && !inputs.every((i) => anc.contains(i))) anc = anc.parentElement;
    for (let up = 0; anc && up < 3; up++, anc = anc.parentElement) {
      let t = textOf(anc);
      inputs.forEach((i) => { const ol = ownLabel(i); if (ol) t = t.replace(ol, " "); });
      t = clean(t);
      if (t) return t.slice(0, 300);
    }
    return "";
  }

  function isRequired(el, label) {
    return !!(el.required || el.getAttribute("aria-required") === "true" || /\*\s*$|\*\s*\||\(required\)/i.test(label));
  }

  function tag(el) {
    if (!el.dataset.ja) el.dataset.ja = `${prefix}-${counter++}`;
    return el.dataset.ja;
  }

  function collect(onlyNew) {
    const out = [];
    const seenGroups = new Set();
    const els = document.querySelectorAll("input, select, textarea");
    for (const el of els) {
      const type = (el.type || "").toLowerCase();
      if (SKIP_TYPES.has(type) || el.disabled || el.readOnly && type !== "file") continue;
      if (!visible(el)) continue;
      if (onlyNew && el.dataset.jaDone) continue;

      if (type === "radio" || type === "checkbox") {
        const name = el.name;
        const group = name ? [...document.querySelectorAll(`input[type="${type}"][name="${CSS.escape(name)}"]`)] : [el];
        if (group.length > 1) {
          const key = type + ":" + name;
          if (seenGroups.has(key)) continue;
          seenGroups.add(key);
          const q = groupQuestion(group);
          out.push({
            kind: type === "radio" ? "radio" : "checkboxes", label: q,
            required: group.some((g) => isRequired(g, q)),
            answered: group.some((g) => g.checked),
            options: group.map((g) => ({ ref: tag(g), text: ownLabel(g) || g.value })),
            ref: tag(group[0]),
          });
          continue;
        }
        const lab = ownLabel(el) || nearbyQuestion(el);
        out.push({ kind: "checkbox", ref: tag(el), label: lab, required: isRequired(el, lab), answered: el.checked });
        continue;
      }

      const label = ownLabel(el) || nearbyQuestion(el) || el.placeholder || el.name || el.id || "";
      const f = {
        ref: tag(el), label: clean(label + (el.placeholder && !label.includes(el.placeholder) ? " | " + el.placeholder : "")),
        required: isRequired(el, label), type, value: el.value || "", name: el.name || el.id || "",
        accept: el.getAttribute("accept") || "",
      };
      if (el.tagName === "SELECT") {
        f.kind = "select";
        f.options = [...el.options].map((o) => clean(o.text));
        f.value = el.selectedIndex > 0 ? clean(el.options[el.selectedIndex].text) : "";
      } else if (type === "file") {
        f.kind = "file";
        f.value = el.files && el.files.length ? el.files[0].name : "";
      } else if (el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list") {
        f.kind = "combobox";
        // react-select shows the chosen value in a sibling, not in input.value
        const ctl = el.closest("[class*='control' i], [class*='select' i]");
        const shown = ctl ? ctl.querySelector("[class*='single-value' i], [class*='singleValue' i]") : null;
        f.value = shown ? textOf(shown) : el.value;
      } else {
        f.kind = el.tagName === "TEXTAREA" ? "textarea" : "text";
      }
      out.push(f);
    }
    return out;
  }

  const COLORS = { filled: "#16a34a", learned: "#16a34a", ai: "#eab308", you: "#f97316", consent: "#f97316" };

  function mark(statuses) {
    for (const [ref, status] of Object.entries(statuses)) {
      const el = document.querySelector(`[data-ja="${ref}"]`);
      if (!el) continue;
      el.dataset.jaDone = "1";
      if (el.name) document.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`).forEach((g) => (g.dataset.jaDone = "1"));
      const color = COLORS[status];
      if (!color) continue;
      const target = el.type === "radio" || el.type === "checkbox" || el.type === "file"
        ? (el.closest("fieldset, [role=radiogroup], label, div") || el) : el;
      target.style.outline = `2px solid ${color}`;
      target.style.outlineOffset = "2px";
      target.title = { filled: "Filled by Job Autopilot", learned: "Filled from an answer you gave before",
        ai: "AI draft - please review", you: "Needs your answer", consent: "Read and tick this yourself" }[status] || "";
    }
  }

  function findSubmit() {
    const cands = [...document.querySelectorAll("button, input[type=submit], [role=button], a")];
    return cands.filter((b) => {
      const t = clean(b.innerText || b.value || b.getAttribute("aria-label"));
      return (b.type === "submit" && t) || SUBMIT_RX.test(t);
    }).filter(visible);
  }

  function banner(s) {
    findSubmit().forEach((b) => {
      b.style.outline = "4px dashed #dc2626";
      b.style.outlineOffset = "4px";
      b.title = "Job Autopilot never clicks this - review the form, then click it yourself";
    });
    if (window.top !== window) return;
    let bar = document.getElementById("__ja_bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "__ja_bar";
      bar.style.cssText = "position:fixed;z-index:2147483647;left:12px;right:12px;bottom:12px;padding:10px 14px;" +
        "border-radius:10px;background:#111827;color:#f9fafb;font:13px/1.45 system-ui,sans-serif;" +
        "box-shadow:0 6px 24px rgba(0,0,0,.35);display:flex;gap:12px;align-items:center;flex-wrap:wrap";
      document.documentElement.appendChild(bar);
    }
    const dot = (c) => `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${c};margin-right:4px"></span>`;
    bar.innerHTML = `<b>🤖 Job Autopilot</b><span>${s.job}</span>` +
      `<span>${dot("#16a34a")}${s.filled} filled</span>` +
      (s.ai ? `<span>${dot("#eab308")}${s.ai} AI drafts to review</span>` : "") +
      `<span>${dot("#f97316")}${s.you} need you</span>` +
      `<span style="margin-left:auto">Review, then click <b style="color:#fca5a5">Submit</b> yourself ·
        <a href="#" style="color:#93c5fd" onclick="this.closest('#__ja_bar').remove();return false">hide</a></span>`;
  }

  function confirmation() {
    const t = (document.body ? document.body.innerText : "").slice(0, 6000).toLowerCase();
    return /thank(s| you) for (applying|submitting|your application)|application (has been |was )?(submitted|received)|we('ve| have) received your application|successfully (submitted|applied)/.test(t);
  }

  window.__ja = { collect, mark, banner, confirmation };
})();
