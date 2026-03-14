/**
 * SearXNG AI Summary — Async Loader
 * Styled to match Google's AI Overview look
 */

(function () {
  "use strict";

  const CSS = `
    #ai-summary-box {
      background: var(--color-base-background, #fff);
      border: 1px solid var(--color-answer-border, #dde1e7);
      border-radius: 12px;
      padding: 14px 18px 10px;
      margin: 0 0 16px 0;
      width: 100%;
      box-sizing: border-box;
      font-family: inherit;
      font-size: 0.9rem;
      line-height: 1.6;
      animation: ai-fade-in 0.25s ease;
    }
    @keyframes ai-fade-in {
      from { opacity: 0; transform: translateY(-4px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    #ai-summary-box .ai-header {
      display: flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 8px;
    }
    #ai-summary-box .ai-icon {
      background: linear-gradient(135deg, #4285f4, #a142f4);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      font-size: 1rem;
      line-height: 1;
    }
    #ai-summary-box .ai-label {
      font-weight: 600;
      font-size: 0.82rem;
      background: linear-gradient(135deg, #4285f4, #a142f4);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 0.01em;
    }
    #ai-summary-box .ai-content {
      color: var(--color-text, #1f1f1f);
      font-size: 0.88rem;
      line-height: 1.65;
      margin: 0;
    }
    #ai-summary-box .ai-footer {
      margin-top: 8px;
      font-size: 0.68rem;
      color: #999;
    }
    #ai-summary-box .ai-loading {
      display: flex;
      align-items: center;
      gap: 9px;
      color: #999;
      font-size: 0.85rem;
      padding: 2px 0;
    }
    #ai-summary-box .ai-spinner {
      width: 14px; height: 14px;
      border: 2px solid #e0e0e0;
      border-top-color: #4285f4;
      border-radius: 50%;
      animation: ai-spin 0.7s linear infinite;
      flex-shrink: 0;
    }
    @keyframes ai-spin { to { transform: rotate(360deg); } }

    /* Dark theme */
    [data-theme="dark"] #ai-summary-box,
    .dark #ai-summary-box {
      background: #1e1f20;
      border-color: #3c4043;
    }
    [data-theme="dark"] #ai-summary-box .ai-content,
    .dark #ai-summary-box .ai-content { color: #e3e3e3; }
    @media (prefers-color-scheme: dark) {
      #ai-summary-box { background: #1e1f20; border-color: #3c4043; }
      #ai-summary-box .ai-content { color: #e3e3e3; }
    }
  `;

  function injectStyles() {
    const s = document.createElement("style");
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function getQuery() {
    const input = document.querySelector("#q");
    if (input && input.value.trim()) return input.value.trim();
    return new URLSearchParams(window.location.search).get("q") || "";
  }

  function collectResults() {
    const out = [];
    document.querySelectorAll(".result").forEach((el) => {
      const a       = el.querySelector("h3 a") || el.querySelector("a");
      const snippet = el.querySelector(".content") || el.querySelector("p");
      const content = snippet ? snippet.textContent.trim() : "";
      if (content) {
        out.push({
          title:   a ? a.textContent.trim() : "",
          url:     a ? (a.href || "") : "",
          content: content.slice(0, 300),
        });
      }
    });
    return out;
  }

  function findInsertTarget() {
    // SearXNG simple theme nests results like:
    //   #main > #main_results > #urls > .result
    // We want to insert BEFORE #urls (the list of results)
    // so the box sits above the first result inside the same column.

    const candidates = [
      "#urls",               // SearXNG main results list
      "#main_results",       // outer results wrapper
      "#results",            // fallback
    ];

    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el) return el;
    }

    // Last resort: parent of first result
    const first = document.querySelector(".result");
    return first ? first.parentElement : null;
  }

  function escapeHtml(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function linkify(text) {
    // Escape HTML first, then convert URLs to clickable links
    const escaped = escapeHtml(text);
    return escaped.replace(
      /(https?:\/\/[^\s<>"]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:underline;text-underline-offset:2px;opacity:0.85;">$1</a>'
    );
  }

  function placeholder() {
    const box = document.createElement("div");
    box.id = "ai-summary-box";
    box.innerHTML = `
      <div class="ai-header">
        <span class="ai-icon">✦</span>
        <span class="ai-label">AI Summary</span>
      </div>
      <div class="ai-loading">
        <div class="ai-spinner"></div>
        Generating summary…
      </div>`;
    return box;
  }

  function fill(box, text) {
    box.innerHTML = `
      <div class="ai-header">
        <span class="ai-icon">✦</span>
        <span class="ai-label">AI Summary</span>
      </div>
      <p class="ai-content">${linkify(text)}</p>
      <div class="ai-footer">AI-generated · May contain inaccuracies · Verify important information</div>`;
  }

  async function run() {
    const target = findInsertTarget();
    if (!target) return;

    const query = getQuery();
    if (!query) return;

    const results = collectResults();
    if (!results.length) return;

    injectStyles();

    const box = placeholder();
    // Insert the box as the first child of the results container
    // so it sits directly above the first result
    target.insertAdjacentElement("beforebegin", box);

    try {
      const resp = await fetch("/ai_summary", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ query, results: results.slice(0, 5) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.summary && data.summary.trim()) {
        fill(box, data.summary.trim());
      } else {
        box.remove();
      }
    } catch (e) {
      console.warn("ai_summary:", e);
      box.remove();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();