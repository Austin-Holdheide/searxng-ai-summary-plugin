/**
 * SearXNG AI Summary — Async Loader
 * ===================================
 * This script is injected into results pages automatically by the plugin's
 * after_request hook. No template changes needed.
 *
 * Flow:
 *   1. Page loads with search results (fast — no LLM wait)
 *   2. This script runs immediately after
 *   3. Creates a "Loading AI summary..." placeholder above results
 *   4. Reads result snippets already rendered on the page
 *   5. POSTs to /ai_summary endpoint (the plugin's Flask route)
 *   6. Replaces placeholder with the actual summary
 *   7. If anything fails, placeholder is silently removed
 */

(function () {
  "use strict";

  // ── Styles ────────────────────────────────────────────────────────────────
  const CSS = `
    #ai-summary-box {
      background: var(--color-answer-background, #e8f0fe);
      border: 1px solid var(--color-answer-border, #aecbfa);
      border-radius: 12px;
      padding: 16px 20px 12px;
      margin: 0 0 20px 0;
      max-width: 100%;
      font-family: inherit;
      animation: ai-fade-in 0.3s ease;
    }
    @keyframes ai-fade-in {
      from { opacity: 0; transform: translateY(-6px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    #ai-summary-box .ai-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
    }
    #ai-summary-box .ai-icon {
      color: #4285f4;
      font-size: 1rem;
    }
    #ai-summary-box .ai-label {
      font-weight: 600;
      font-size: 0.9rem;
      color: #1a73e8;
    }
    #ai-summary-box .ai-model {
      font-size: 0.72rem;
      color: #888;
      margin-left: auto;
      font-style: italic;
    }
    #ai-summary-box .ai-content {
      font-size: 0.95rem;
      line-height: 1.65;
      color: var(--color-text, #333);
    }
    #ai-summary-box .ai-footer {
      margin-top: 10px;
      font-size: 0.7rem;
      color: #999;
      border-top: 1px solid rgba(0,0,0,0.08);
      padding-top: 8px;
    }
    #ai-summary-box .ai-loading {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #888;
      font-size: 0.9rem;
    }
    #ai-summary-box .ai-spinner {
      width: 16px; height: 16px;
      border: 2px solid #cce0ff;
      border-top-color: #4285f4;
      border-radius: 50%;
      animation: ai-spin 0.7s linear infinite;
      flex-shrink: 0;
    }
    @keyframes ai-spin {
      to { transform: rotate(360deg); }
    }
    /* Dark theme */
    @media (prefers-color-scheme: dark) {
      #ai-summary-box {
        background: #1e2a3a;
        border-color: #2d4a7a;
      }
      #ai-summary-box .ai-label { color: #7baff5; }
      #ai-summary-box .ai-icon  { color: #7baff5; }
      #ai-summary-box .ai-content { color: #e0e0e0; }
    }
    [data-theme="dark"] #ai-summary-box,
    .dark #ai-summary-box {
      background: #1e2a3a;
      border-color: #2d4a7a;
    }
    [data-theme="dark"] #ai-summary-box .ai-label,
    [data-theme="dark"] #ai-summary-box .ai-icon { color: #7baff5; }
    [data-theme="dark"] #ai-summary-box .ai-content { color: #e0e0e0; }
  `;

  // ── Helpers ───────────────────────────────────────────────────────────────

  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function getQuery() {
    // Try the search input first, then the page title, then URL param
    const input = document.querySelector("#q");
    if (input && input.value.trim()) return input.value.trim();
    const params = new URLSearchParams(window.location.search);
    return params.get("q") || "";
  }

  function collectResults() {
    const results = [];
    // SearXNG simple theme result structure
    document.querySelectorAll(".result").forEach((el) => {
      const titleEl   = el.querySelector("h3 a") || el.querySelector("a");
      const contentEl = el.querySelector(".content") || el.querySelector("p");
      const title   = titleEl   ? titleEl.textContent.trim()   : "";
      const url     = titleEl   ? (titleEl.href || "")          : "";
      const content = contentEl ? contentEl.textContent.trim() : "";
      if (content) {
        results.push({ title, url, content: content.slice(0, 300) });
      }
    });
    return results;
  }

  function createPlaceholder() {
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
      </div>
    `;
    return box;
  }

  function fillBox(box, summary) {
    box.innerHTML = `
      <div class="ai-header">
        <span class="ai-icon">✦</span>
        <span class="ai-label">AI Summary</span>
      </div>
      <div class="ai-content">${escapeHtml(summary)}</div>
      <div class="ai-footer">AI-generated · May contain inaccuracies · Verify important information</div>
    `;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── Main ──────────────────────────────────────────────────────────────────

  async function run() {
    const resultsContainer = document.querySelector("#results");
    if (!resultsContainer) return; // not a results page

    const query = getQuery();
    if (!query) return;

    const results = collectResults();
    if (results.length === 0) return;

    injectStyles();

    // Insert placeholder above results
    const box = createPlaceholder();
    resultsContainer.parentNode.insertBefore(box, resultsContainer);

    try {
      const resp = await fetch("/ai_summary", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ query, results: results.slice(0, 5) }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data = await resp.json();
      if (data.summary && data.summary.trim()) {
        fillBox(box, data.summary.trim());
      } else {
        box.remove();
      }
    } catch (err) {
      console.warn("ai_summary: fetch failed:", err);
      box.remove();
    }
  }

  // Run after DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();