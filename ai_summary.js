/**
 * SearXNG AI Summary — Streaming + Progressive JSON Rendering
 * =============================================================
 * Compact summary: types text token by token with blinking cursor.
 * More panel: renders each section AS it completes while streaming —
 *   overview appears first, then sections one by one, then follow-ups.
 */

(function () {
  "use strict";

  const CSS = `
    #ai-summary-box {
      background: var(--color-base-background, #1a1a1a);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      padding: 14px 18px 12px;
      margin: 0 0 16px 0;
      width: 100%;
      box-sizing: border-box;
      font-family: inherit;
      font-size: 0.9rem;
      line-height: 1.6;
      animation: ai-fade-in 0.25s ease;
    }
    @keyframes ai-fade-in {
      from { opacity:0; transform:translateY(-4px); }
      to   { opacity:1; transform:translateY(0); }
    }
    #ai-summary-box .ai-header {
      display:flex; align-items:center; gap:7px; margin-bottom:10px;
    }
    #ai-summary-box .ai-icon {
      font-size:1rem;
      background:linear-gradient(135deg,#4285f4,#a142f4);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }
    #ai-summary-box .ai-label {
      font-weight:600; font-size:0.82rem;
      background:linear-gradient(135deg,#4285f4,#a142f4);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }
    #ai-summary-box .ai-content {
      color:var(--color-text,#e0e0e0);
      font-size:0.88rem; line-height:1.65; margin:0 0 10px 0; min-height:1.4em;
    }
    #ai-summary-box .ai-cursor {
      display:inline-block; width:2px; height:1em;
      background:#4285f4; margin-left:2px; vertical-align:text-bottom;
      animation:ai-blink 0.8s step-end infinite;
    }
    @keyframes ai-blink { 0%,100%{opacity:1} 50%{opacity:0} }
    #ai-summary-box .ai-more-btn {
      display:inline-flex; align-items:center; gap:5px;
      background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.15);
      border-radius:20px; color:var(--color-text,#ccc);
      font-size:0.8rem; padding:4px 12px 4px 14px;
      cursor:pointer; transition:background 0.15s;
      font-family:inherit; margin-bottom:4px;
    }
    #ai-summary-box .ai-more-btn:hover { background:rgba(255,255,255,0.13); }
    #ai-summary-box .ai-more-btn .ai-chevron { font-size:0.7rem; transition:transform 0.2s; }
    #ai-summary-box .ai-more-btn.open .ai-chevron { transform:rotate(180deg); }
    #ai-summary-box .ai-expanded {
      border-top:1px solid rgba(255,255,255,0.08);
      margin-top:12px; padding-top:14px; display:none;
    }
    #ai-summary-box .ai-expanded.visible { display:block; }

    /* Progressive render: each block slides in */
    #ai-summary-box .ai-block {
      animation: ai-block-in 0.2s ease;
    }
    @keyframes ai-block-in {
      from { opacity:0; transform:translateY(6px); }
      to   { opacity:1; transform:translateY(0); }
    }

    #ai-summary-box .ai-overview {
      color:var(--color-text,#e0e0e0);
      font-size:0.88rem; line-height:1.65; margin:0 0 14px 0;
    }
    #ai-summary-box .ai-overview .ai-cursor { display:inline-block; }

    #ai-summary-box code {
      background:rgba(255,255,255,0.1); border-radius:4px; padding:1px 5px;
      font-family:'Consolas','Monaco','Courier New',monospace;
      font-size:0.85em; color:#f0c674;
    }
    #ai-summary-box .ai-section { margin-bottom:18px; }
    #ai-summary-box .ai-section-title {
      font-weight:700; font-size:0.9rem;
      color:var(--color-text,#fff); margin:0 0 10px 0;
    }
    #ai-summary-box .ai-item-text {
      display:flex; align-items:flex-start; gap:8px;
      color:var(--color-text,#ccc); font-size:0.85rem; line-height:1.6;
      margin-bottom:6px; padding-left:4px;
    }
    #ai-summary-box .ai-item-text::before { content:"•"; color:#4285f4; flex-shrink:0; margin-top:1px; }
    #ai-summary-box .ai-item-step { margin-bottom:14px; }
    #ai-summary-box .ai-item-step .ai-step-label {
      color:var(--color-text,#ccc); font-size:0.85rem;
      margin-bottom:6px; display:flex; align-items:center; gap:8px;
    }
    #ai-summary-box .ai-step-num {
      display:inline-flex; align-items:center; justify-content:center;
      width:20px; height:20px; border-radius:50%;
      background:rgba(66,133,244,0.25); color:#4285f4;
      font-size:0.75rem; font-weight:700; flex-shrink:0;
    }
    #ai-summary-box .ai-code-block {
      background:rgba(0,0,0,0.35); border:1px solid rgba(255,255,255,0.1);
      border-radius:8px; overflow:hidden; margin-bottom:4px;
    }
    #ai-summary-box .ai-code-header {
      display:flex; align-items:center; justify-content:space-between;
      padding:6px 12px; border-bottom:1px solid rgba(255,255,255,0.07);
    }
    #ai-summary-box .ai-code-lang {
      font-size:0.72rem; color:#888; display:flex; align-items:center; gap:5px;
    }
    #ai-summary-box .ai-code-lang::before { content:"</>"; font-size:0.78rem; opacity:0.6; }
    #ai-summary-box .ai-copy-btn {
      background:none; border:none; color:#888; font-size:0.75rem;
      cursor:pointer; display:flex; align-items:center; gap:4px;
      padding:2px 6px; border-radius:4px;
      transition:color 0.15s,background 0.15s; font-family:inherit;
    }
    #ai-summary-box .ai-copy-btn:hover { color:#fff; background:rgba(255,255,255,0.08); }
    #ai-summary-box .ai-copy-btn.copied { color:#4caf50; }
    #ai-summary-box .ai-code-block pre { margin:0; padding:10px 14px; overflow-x:auto; }
    #ai-summary-box .ai-code-block pre code {
      background:none; border-radius:0; padding:0; color:#e0e0e0;
      font-family:'Consolas','Monaco','Courier New',monospace;
      font-size:0.83rem; line-height:1.55; white-space:pre;
    }
    #ai-summary-box .ai-sources {
      display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 16px 0;
    }
    #ai-summary-box .ai-source-tag {
      display:inline-flex; align-items:center; gap:4px;
      background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1);
      border-radius:6px; font-size:0.75rem; padding:2px 8px;
      color:#aaa; text-decoration:none; transition:background 0.15s;
    }
    #ai-summary-box .ai-source-tag:hover { background:rgba(255,255,255,0.12); color:#fff; }
    #ai-summary-box .ai-followup-title {
      font-weight:700; font-size:0.85rem; color:var(--color-text,#fff);
      margin:16px 0 8px 0; padding-top:14px;
      border-top:1px solid rgba(255,255,255,0.08);
    }
    #ai-summary-box .ai-followup-item {
      display:flex; align-items:center; justify-content:space-between;
      padding:9px 0; border-bottom:1px solid rgba(255,255,255,0.06);
      cursor:pointer; color:var(--color-text,#ccc); font-size:0.85rem;
      transition:color 0.15s;
    }
    #ai-summary-box .ai-followup-item:hover { color:#fff; }
    #ai-summary-box .ai-followup-item::after { content:"▾"; font-size:0.75rem; opacity:0.4; }
    #ai-summary-box .ai-footer { margin-top:12px; font-size:0.68rem; color:#555; }
    #ai-summary-box .ai-loading {
      display:flex; align-items:center; gap:9px;
      color:#888; font-size:0.85rem; padding:4px 0;
    }
    #ai-summary-box .ai-spinner {
      width:14px; height:14px;
      border:2px solid rgba(255,255,255,0.1); border-top-color:#4285f4;
      border-radius:50%; animation:ai-spin 0.7s linear infinite; flex-shrink:0;
    }
    @keyframes ai-spin { to { transform:rotate(360deg); } }

    /* Sticky "generating" bar shown at bottom of More panel while streaming */
    #ai-summary-box .ai-generating {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 0 2px 0;
      font-size: 0.75rem;
      color: #666;
      border-top: 1px solid rgba(255,255,255,0.06);
      margin-top: 10px;
    }
    #ai-summary-box .ai-generating .ai-gen-spinner {
      width: 12px; height: 12px;
      border: 2px solid rgba(66,133,244,0.2);
      border-top-color: #4285f4;
      border-radius: 50%;
      animation: ai-spin 0.7s linear infinite;
      flex-shrink: 0;
    }
    #ai-summary-box .ai-generating .ai-gen-dots::after {
      content: '';
      animation: ai-dots 1.2s steps(4,end) infinite;
    }
    @keyframes ai-dots {
      0%  { content: '';    }
      25% { content: '.';   }
      50% { content: '..';  }
      75% { content: '...'; }
    }

    /* Light theme */
    @media (prefers-color-scheme: light) {
      #ai-summary-box { background:#fff; border-color:#e0e0e0; }
      #ai-summary-box .ai-content,
      #ai-summary-box .ai-overview,
      #ai-summary-box .ai-item-text,
      #ai-summary-box .ai-followup-item { color:#1f1f1f; }
      #ai-summary-box .ai-section-title,
      #ai-summary-box .ai-followup-title { color:#111; }
      #ai-summary-box code { background:rgba(0,0,0,0.06); color:#b05c00; }
      #ai-summary-box .ai-code-block { background:#f5f5f5; border-color:#ddd; }
      #ai-summary-box .ai-code-block .ai-code-header { border-bottom-color:#ddd; }
      #ai-summary-box .ai-code-block pre code { color:#333; }
      #ai-summary-box .ai-more-btn { background:rgba(0,0,0,0.04); border-color:rgba(0,0,0,0.12); color:#444; }
      #ai-summary-box .ai-source-tag { color:#555; border-color:rgba(0,0,0,0.1); }
      #ai-summary-box .ai-expanded { border-top-color:rgba(0,0,0,0.08); }
      #ai-summary-box .ai-followup-item { border-bottom-color:rgba(0,0,0,0.07); }
      #ai-summary-box .ai-spinner { border-color:#eee; border-top-color:#4285f4; }
      #ai-summary-box .ai-footer { color:#999; }
    }
    [data-theme="light"] #ai-summary-box { background:#fff; border-color:#e0e0e0; }
    [data-theme="light"] #ai-summary-box .ai-content,
    [data-theme="light"] #ai-summary-box .ai-overview { color:#1f1f1f; }
  `;

  // ── Utils ─────────────────────────────────────────────────────────────────

  function injectStyles() {
    if (document.getElementById("ai-summary-styles")) return;
    const s = document.createElement("style");
    s.id = "ai-summary-styles"; s.textContent = CSS;
    document.head.appendChild(s);
  }

  function getQuery() {
    const el = document.querySelector("#q");
    if (el && el.value.trim()) return el.value.trim();
    return new URLSearchParams(window.location.search).get("q") || "";
  }

  function collectResults() {
    const out = [];
    document.querySelectorAll(".result").forEach((el) => {
      const a = el.querySelector("h3 a") || el.querySelector("a");
      const s = el.querySelector(".content") || el.querySelector("p");
      const content = s ? s.textContent.trim() : "";
      if (content) out.push({
        title:   a ? a.textContent.trim() : "",
        url:     a ? (a.href || "") : "",
        content: content.slice(0, 300),
      });
    });
    return out;
  }

  function findInsertTarget() {
    for (const sel of ["#urls", "#main_results", "#results"]) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    const first = document.querySelector(".result");
    return first ? first.parentElement : null;
  }

  // Watch for our box being removed from the DOM by SearXNG's own JS
  // (SearXNG re-renders the results area after all engines respond,
  //  which can destroy elements we inserted)
  function watchBox(box, target) {
    const observer = new MutationObserver(() => {
      if (!document.body.contains(box)) {
        // Box was removed — re-insert it
        const newTarget = findInsertTarget();
        if (newTarget) {
          newTarget.insertAdjacentElement("beforebegin", box);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Stop watching after 30s (SearXNG should be stable by then)
    setTimeout(() => observer.disconnect(), 30000);
    return observer;
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function linkify(text) {
    return esc(text).replace(
      /(https?:\/\/[^\s<>"]+)/g,
      '<a href="$1" target="_blank" rel="noopener" ' +
      'style="color:inherit;text-decoration:underline;opacity:0.8;">$1</a>'
    );
  }

  function hostnameOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); }
    catch { return ""; }
  }

  // ── SSE stream reader ─────────────────────────────────────────────────────

  async function readStream(url, body, onChunk, onDone, onError) {
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith("data:")) continue;
          const raw = t.slice(5).trim();
          if (raw === "[DONE]") { onDone(); return; }
          try { const txt = JSON.parse(raw); if (txt) onChunk(txt); }
          catch (_) {}
        }
      }
      onDone();
    } catch (err) { onError(err); }
  }

  // ── Code block ────────────────────────────────────────────────────────────

  function renderCodeBlock(lang, code) {
    const id = "cb" + Math.random().toString(36).slice(2, 9);
    return `<div class="ai-code-block">
      <div class="ai-code-header">
        <span class="ai-code-lang">${esc(lang || "code")}</span>
        <button class="ai-copy-btn" onclick="(function(b){
          navigator.clipboard.writeText(document.getElementById('${id}').textContent).then(function(){
            b.classList.add('copied'); b.textContent='✓ Copied';
            setTimeout(function(){b.classList.remove('copied');b.innerHTML='📋 Copy Code';},2000);
          });
        })(this)">📋 Copy Code</button>
      </div>
      <pre><code id="${id}">${esc(code)}</code></pre>
    </div>`;
  }

  function renderItem(item, idx) {
    if (typeof item === "string") {
      const isCode = /^[$#>]|^(sudo|apt|npm|pip|git|docker|cd |ls |cat |echo |mkdir|chmod|curl|wget|python|node)\b/.test(item.trim());
      return isCode ? renderCodeBlock("bash", item.trim())
                    : `<div class="ai-item-text">${linkify(item)}</div>`;
    }
    if (item.type === "code") {
      return `<div class="ai-item-step">
        <div class="ai-step-label"><span class="ai-step-num">${idx+1}</span></div>
        ${renderCodeBlock(item.lang || "bash", item.value || "")}
      </div>`;
    }
    return `<div class="ai-item-text">${linkify(item.value || "")}</div>`;
  }

  function renderSection(sec) {
    const items = (sec.items || []).map(renderItem).join("");
    return `<div class="ai-section ai-block">
      <div class="ai-section-title">${esc(sec.title || "")}</div>
      ${items}
    </div>`;
  }

  function renderSources(results) {
    const seen = new Set(), tags = [];
    for (const r of results.slice(0, 4)) {
      const h = hostnameOf(r.url);
      if (!h || seen.has(h)) continue;
      seen.add(h);
      tags.push(`<a class="ai-source-tag" href="${esc(r.url)}" target="_blank" rel="noopener">
        <span style="opacity:0.5;font-size:0.8em">○</span> ${esc(h)}</a>`);
    }
    return tags.length ? `<div class="ai-sources ai-block">${tags.join("")}</div>` : "";
  }

  // ── Progressive JSON parser ───────────────────────────────────────────────
  //
  // As JSON streams in we track which top-level fields are complete and
  // append them to the panel immediately — overview first, then each
  // section as its closing `}` arrives, then follow-up questions.
  //
  // Strategy: use regex on the buffer to extract completed values.

  function makeProgressiveRenderer(panel, results) {
    let rendered = { overview: false, sources: false, sections: 0, followup: false };

    return function update(buffer) {
      // ── 1. Overview ───────────────────────────────────────────────────
      if (!rendered.overview) {
        // Match "overview":"...complete string..." — ends at unescaped "
        const m = buffer.match(/"overview"\s*:\s*"((?:[^"\\]|\\.)*)"/);
        if (m) {
          rendered.overview = true;
          const el = document.createElement("div");
          el.className = "ai-block";
          el.innerHTML = `<p class="ai-overview">${linkify(m[1])}</p>`;
          panel.appendChild(el);
        }
      }

      // ── 2. Source tags (once after overview) ─────────────────────────
      if (rendered.overview && !rendered.sources) {
        rendered.sources = true;
        const src = renderSources(results);
        if (src) {
          const el = document.createElement("div");
          el.innerHTML = src;
          panel.appendChild(el.firstElementChild);
        }
      }

      // ── 3. Sections — extract completed section objects ───────────────
      // Find the "sections" array content and extract complete {...} objects
      const secArrayMatch = buffer.match(/"sections"\s*:\s*\[([\s\S]*)/);
      if (secArrayMatch) {
        const arrContent = secArrayMatch[1];
        // Extract all complete {...} objects (balanced braces)
        let depth = 0, start = -1, count = 0;
        for (let i = 0; i < arrContent.length; i++) {
          const ch = arrContent[i];
          if (ch === "{") { if (depth === 0) start = i; depth++; }
          else if (ch === "}") {
            depth--;
            if (depth === 0 && start !== -1) {
              count++;
              if (count > rendered.sections) {
                // New complete section found — try to parse it
                try {
                  const sec = JSON.parse(arrContent.slice(start, i + 1));
                  rendered.sections = count;
                  const el = document.createElement("div");
                  el.innerHTML = renderSection(sec);
                  panel.appendChild(el.firstElementChild);
                } catch (_) {}
              }
              start = -1;
            }
          }
        }
      }

      // ── 4. Follow-up questions ────────────────────────────────────────
      if (!rendered.followup) {
        const fuMatch = buffer.match(/"follow_up"\s*:\s*(\[[^\]]*\])/);
        if (fuMatch) {
          try {
            const questions = JSON.parse(fuMatch[1]);
            if (Array.isArray(questions) && questions.length) {
              rendered.followup = true;
              const wrap = document.createElement("div");
              wrap.className = "ai-block";
              wrap.innerHTML = `<div class="ai-followup-title">Explore More</div>` +
                questions.map(q => `<div class="ai-followup-item">${esc(q)}</div>`).join("");
              panel.appendChild(wrap);
            }
          } catch (_) {}
        }
      }
    };
  }

  // ── Box builders ──────────────────────────────────────────────────────────

  function createBox() {
    const box = document.createElement("div");
    box.id = "ai-summary-box";
    box.innerHTML = `
      <div class="ai-header">
        <span class="ai-icon">✦</span>
        <span class="ai-label">AI Summary</span>
      </div>
      <div class="ai-content"><span class="ai-cursor"></span></div>`;
    return box;
  }

  function addMoreButton(box, results) {
    const contentEl = box.querySelector(".ai-content");
    const cursor = contentEl.querySelector(".ai-cursor");
    if (cursor) cursor.remove();

    const more = document.createElement("button");
    more.className = "ai-more-btn";
    more.id = "ai-more-btn";
    more.innerHTML = `More <span class="ai-chevron">▾</span>`;

    const panel = document.createElement("div");
    panel.className = "ai-expanded";
    panel.id = "ai-expanded";

    const footer = document.createElement("div");
    footer.className = "ai-footer";
    footer.textContent = "Auto-generated based on search results · May contain inaccuracies";

    contentEl.after(more, panel, footer);

    let loaded = false, isOpen = false;

    more.addEventListener("click", () => {
      isOpen = !isOpen;
      more.classList.toggle("open", isOpen);
      more.querySelector(".ai-chevron").textContent = isOpen ? "▴" : "▾";
      more.childNodes[0].textContent = isOpen ? "Less " : "More ";
      panel.classList.toggle("visible", isOpen);
      if (isOpen && !loaded) { loaded = true; streamMore(panel, results); }
    });
  }

  // ── Stream compact summary (smooth typewriter) ────────────────────────────
  //
  // Tokens from the LLM arrive at uneven intervals (a burst then a pause).
  // Instead of rendering each token directly we push every character into
  // a queue and drain it at a fixed 18ms/char interval — giving a smooth,
  // even typing speed no matter how fast or slow the model responds.

  function streamCompact(box, query, results) {
    const contentEl = box.querySelector(".ai-content");

    let fullText  = "";   // complete text received so far
    let displayed = "";   // text already typed onto screen
    let queue     = [];   // characters waiting to be typed
    let streamDone = false;
    let timerID   = null;

    function tick() {
      if (queue.length === 0) {
        if (streamDone) {
          // Safety check: if the box was removed from DOM by SearXNG's JS,
          // re-insert the wrapper before finalising
          const wrapper = document.getElementById("ai-summary-wrapper");
          if (wrapper && !document.body.contains(wrapper)) {
            const t = findInsertTarget();
            if (t) t.insertAdjacentElement("beforebegin", wrapper);
          }

          contentEl.innerHTML = linkify(displayed);
          if (displayed.trim()) addMoreButton(box, results);
          else {
            // Don't remove if box has content mid-stream (race condition guard)
            if (!displayed) box.closest("#ai-summary-wrapper")?.remove();
          }
          return;
        }
        // Queue empty but stream still going — wait briefly
        timerID = setTimeout(tick, 16);
        return;
      }

      // Drain chars at LLM speed:
      // If queue is building up (LLM is fast), drain more chars per tick
      // so the display keeps pace. If queue is small, drain just 1-2.
      const charsPerTick = queue.length > 60 ? 8
                         : queue.length > 30 ? 4
                         : queue.length > 10 ? 2
                         : 1;

      for (let i = 0; i < charsPerTick && queue.length; i++) {
        displayed += queue.shift();
      }

      contentEl.innerHTML = linkify(displayed) + '<span class="ai-cursor"></span>';
      timerID = setTimeout(tick, 16);
    }

    readStream(
      "/ai_summary",
      { query, results: results.slice(0, 5) },
      (chunk) => {
        // Push every character of the chunk into the queue
        for (const ch of chunk) queue.push(ch);
        fullText += chunk;
        // Start the ticker on first chunk
        if (!timerID) timerID = setTimeout(tick, 18);
      },
      () => {
        streamDone = true;
        if (!timerID) timerID = setTimeout(tick, 18);
      },
      (err) => { console.warn("ai_summary:", err); box.remove(); }
    );
  }

  // ── Stream More panel (progressive render) ────────────────────────────────

  function streamMore(panel, results) {
    // Initial full-panel spinner — shown before first content arrives
    const initSpinner = document.createElement("div");
    initSpinner.className = "ai-loading";
    initSpinner.innerHTML = `<div class="ai-spinner"></div> Loading detailed summary…`;
    panel.appendChild(initSpinner);

    // Sticky "Generating..." bar — appended to panel, stays at bottom
    // while streaming, removed when done
    const genBar = document.createElement("div");
    genBar.className = "ai-generating";
    genBar.innerHTML = `<div class="ai-gen-spinner"></div>
      <span>Generating<span class="ai-gen-dots"></span></span>`;

    let buffer = "";
    let firstChunk = true;
    const update = makeProgressiveRenderer(panel, results);

    readStream(
      "/ai_summary_more",
      { query: getQuery(), results: results.slice(0, 5) },
      (chunk) => {
        buffer += chunk;

        // On first chunk: swap init spinner for the sticky gen bar
        if (firstChunk) {
          firstChunk = false;
          if (initSpinner.parentNode) initSpinner.remove();
          panel.appendChild(genBar);
        }

        // Render new content, then re-append genBar so it stays at bottom
        update(buffer);
        panel.appendChild(genBar);
      },
      () => {
        // Stream finished — remove init spinner and gen bar
        if (initSpinner.parentNode) initSpinner.remove();
        if (genBar.parentNode) genBar.remove();

        // Final pass
        update(buffer);

        if (!panel.children.length) {
          panel.innerHTML = `<p class="ai-overview">${linkify(buffer)}</p>`;
        }
      },
      (err) => {
        console.warn("ai_summary_more:", err);
        if (initSpinner.parentNode) initSpinner.remove();
        if (genBar.parentNode) genBar.remove();
        panel.innerHTML = `<p style="color:#888;font-size:0.83rem;padding:8px 0">
          Could not load detailed summary. Please try again.</p>`;
      }
    );
  }

  // ── Main ──────────────────────────────────────────────────────────────────

  async function run() {
    const target = findInsertTarget();
    if (!target) return;
    const query = getQuery();
    if (!query) return;
    const results = collectResults();
    if (!results.length) return;

    injectStyles();

    // Wrap box in a stable container div so SearXNG re-renders
    // don't directly affect it
    const wrapper = document.createElement("div");
    wrapper.id = "ai-summary-wrapper";
    const box = createBox();
    wrapper.appendChild(box);
    target.insertAdjacentElement("beforebegin", wrapper);

    // Watch for wrapper being removed and re-insert if needed
    watchBox(wrapper, target);

    streamCompact(box, query, results);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();