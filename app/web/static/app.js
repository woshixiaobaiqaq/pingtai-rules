const formError = document.querySelector("#form-error");
const contentInput = document.querySelector("#content-input");
const documentInput = document.querySelector("#document-input");
const documentButton = document.querySelector("#document-button");
const documentStatus = document.querySelector("#document-status");
const submitButton = document.querySelector("#submit-button");
const results = document.querySelector("#results");
const resultsStack = document.querySelector("#results-stack");
const platformLibrarySummary = document.querySelector("#platform-library-summary");
const ruleLibraryTotal = document.querySelector("#rule-library-total");
const platformCountNodes = [...document.querySelectorAll("[data-platform-count]")];

const platformLabels = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  video_channel: "视频号",
};

const supportedDocumentExtensions = new Set([
  "txt",
  "md",
  "markdown",
  "csv",
  "json",
  "log",
  "srt",
  "vtt",
]);
const maxDocumentBytes = 2 * 1024 * 1024;

const severityLabels = {
  none: "无命中",
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};
const inlineTextCollapseLength = 90;
const quotePreviewLength = 120;

void loadRuleLibrarySummary();

documentButton.addEventListener("click", () => {
  documentInput.click();
});

documentInput.addEventListener("change", async () => {
  const [file] = documentInput.files || [];
  if (!file) {
    return;
  }

  setDocumentLoading(true);
  renderError("");

  try {
    const text = await readTextDocument(file);
    contentInput.value = text.trim();
    contentInput.dispatchEvent(new Event("input", { bubbles: true }));
    results.hidden = true;
    resultsStack.innerHTML = "";
    renderDocumentStatus(`${file.name} · ${countTextUnits(contentInput.value)}字`);
    contentInput.focus();
  } catch (error) {
    renderDocumentStatus("");
    renderError(error.message || "文档读取失败。");
  } finally {
    setDocumentLoading(false);
    documentInput.value = "";
  }
});

submitButton.addEventListener("click", async () => {
  const content = contentInput.value.trim();
  const platforms = [...document.querySelectorAll(".platform-chip input:checked")].map(
    (node) => node.value,
  );

  if (!content) {
    renderError("请输入需要检测的内容。");
    return;
  }

  if (platforms.length === 0) {
    renderError("至少选择一个平台。");
    return;
  }

  setLoading(true);
  renderError("");

  try {
    const response = await fetch("/api/audit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content,
        platforms,
        persist: false,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : "检测失败。";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    renderPlatformResults(payload.report.platform_results);
    setTimeout(() => {
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  } catch (error) {
    renderError(error.message || "请求失败，请检查服务状态。");
    alert("出错了: " + error.message);
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "检测中..." : "开始检测";
}

function setDocumentLoading(isLoading) {
  documentButton.disabled = isLoading;
  documentButton.textContent = isLoading ? "读取中..." : "上传文档";
}

function renderError(message) {
  formError.hidden = !message;
  formError.textContent = message;
}

function renderDocumentStatus(message) {
  documentStatus.hidden = !message;
  documentStatus.textContent = message;
}

async function readTextDocument(file) {
  if (file.size > maxDocumentBytes) {
    throw new Error("文档不能超过 2MB。");
  }

  const extension = getFileExtension(file.name);
  const isSupportedType =
    file.type.startsWith("text/") || file.type === "application/json" || supportedDocumentExtensions.has(extension);
  if (!isSupportedType) {
    throw new Error("当前仅支持 txt、md、csv、json、log、srt、vtt 文本文档。");
  }

  const buffer = await file.arrayBuffer();
  const text = decodeTextBuffer(buffer);
  if (!text.trim()) {
    throw new Error("文档内容为空。");
  }
  return text.replace(/^\uFEFF/, "");
}

function decodeTextBuffer(buffer) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    try {
      return new TextDecoder("gb18030").decode(buffer);
    } catch {
      return new TextDecoder("utf-8").decode(buffer);
    }
  }
}

function getFileExtension(fileName) {
  const parts = fileName.toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function countTextUnits(value) {
  return value.replace(/\s/g, "").length;
}

async function loadRuleLibrarySummary() {
  const platforms = Object.keys(platformLabels);

  try {
    const entries = await Promise.all(
      platforms.map(async (platform) => {
        const params = new URLSearchParams({ platform, limit: "1", offset: "0" });
        const response = await fetch(`/api/rules?${params.toString()}`);
        if (!response.ok) {
          throw new Error(platform);
        }
        const payload = await response.json();
        return [platform, Number(payload.total || 0)];
      }),
    );

    const totals = Object.fromEntries(entries);
    const totalRules = platforms.reduce((sum, platform) => sum + (totals[platform] ?? 0), 0);

    platformCountNodes.forEach((node) => {
      const platform = node.dataset.platformCount;
      node.textContent = `${totals[platform] ?? 0}条`;
    });

    platformLibrarySummary.textContent = platforms
      .map((platform) => `${platformLabels[platform]} ${totals[platform] ?? 0}条`)
      .join(" / ");
    ruleLibraryTotal.textContent = `${totalRules} 条本地规则`;
  } catch {
    platformCountNodes.forEach((node) => {
      node.textContent = "--";
    });
    platformLibrarySummary.textContent = "抖音 / 小红书 / 视频号";
    ruleLibraryTotal.textContent = "规则数加载失败";
  }
}

function renderPlatformResults(platformResults) {
  results.hidden = false;
  resultsStack.innerHTML = "";
  resultsStack.appendChild(buildResultsTable(platformResults));
}

function buildResultsTable(platformResults) {
  const shell = document.createElement("div");
  shell.className = "results-table-shell";
  shell.innerHTML = `
    <table class="results-table">
      <thead>
        <tr>
          <th>平台</th>
          <th>风险</th>
          <th>命中关键词 / 命中内容</th>
          <th>命中规则</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  `;

  const body = shell.querySelector("tbody");
  platformResults.forEach((item, index) => {
    body.appendChild(buildPlatformRow(item, index));
  });

  return shell;
}

function buildPlatformRow(item, index) {
  const row = document.createElement("tr");
  row.style.animationDelay = `${index * 70}ms`;

  const rules = item.matched_rules || [];
  const terms = collectMatchedTerms(item);
  const contents = collectMatchedContents(item);
  const termsHtml =
    terms.length > 0
      ? terms.map((term) => `<span class="match-chip">${escapeHtml(term)}</span>`).join("")
      : `<span class="muted-text">无</span>`;
  const contentsText = contents.length > 0 ? contents.join("；") : "未发现明显命中内容";
  const contentHtml = buildFoldableInlineText(contentsText);

  row.innerHTML = `
    <td data-label="平台">
      <div class="platform-cell">
        <strong>${escapeHtml(platformLabels[item.platform] ?? item.platform)}</strong>
        <span>${rules.length} 条规则</span>
      </div>
    </td>
    <td data-label="风险">
      <span class="risk-pill ${severityClass(item.risk_level)}">${escapeHtml(
        severityLabels[item.risk_level] ?? item.risk_level,
      )}</span>
    </td>
    <td data-label="命中">
      <div class="hit-line">
        <span class="hit-line__label">关键词</span>
        <span class="hit-line__terms">${termsHtml}</span>
        <span class="hit-line__divider"></span>
        <span class="hit-line__label">内容</span>
        ${contentHtml}
      </div>
    </td>
    <td data-label="规则">
      ${buildCompactRulesHtml(rules)}
    </td>
  `;
  return row;
}

function buildCompactRulesHtml(rules) {
  if (rules.length === 0) {
    return `<span class="muted-text">未命中规则</span>`;
  }

  const visibleRules = rules.slice(0, 6);
  const extraCount = rules.length - visibleRules.length;
  return `
    <ul class="compact-rule-list">
      ${visibleRules.map((rule) => buildCompactRuleHtml(rule)).join("")}
    </ul>
    ${extraCount > 0 ? `<p class="compact-rule-more">另 ${extraCount} 条规则已折叠</p>` : ""}
  `;
}

function buildCompactRuleHtml(rule) {
  return `
    <li class="compact-rule">
      <div class="compact-rule__summary">
        <span class="compact-rule__id">${escapeHtml(rule.rule_id)}</span>
        <span class="risk-pill ${severityClass(rule.severity)}">${escapeHtml(
          severityLabels[rule.severity] ?? rule.severity,
        )}</span>
        <span class="compact-rule__title" title="${escapeHtml(rule.title)}">${escapeHtml(rule.title)}</span>
      </div>
      <details class="quote-details">
        <summary>查看摘录</summary>
        ${buildQuoteBodyHtml(rule.quote)}
      </details>
    </li>
  `;
}

function buildFoldableInlineText(value) {
  const text = String(value || "");
  if (text.length <= inlineTextCollapseLength) {
    return `<span class="hit-line__content" title="${escapeHtml(text)}">${escapeHtml(text)}</span>`;
  }

  return `
    <details class="hit-line__content text-details">
      <summary>
        <span class="text-details__preview">${escapeHtml(truncateText(text, inlineTextCollapseLength))}</span>
        <span class="text-details__toggle"></span>
      </summary>
      <p>${escapeHtml(text)}</p>
    </details>
  `;
}

function buildQuoteBodyHtml(value) {
  const text = String(value || "");
  if (text.length <= quotePreviewLength) {
    return `<p>${escapeHtml(text)}</p>`;
  }

  return `
    <p class="quote-preview">${escapeHtml(truncateText(text, quotePreviewLength))}</p>
    <details class="quote-full-details">
      <summary>展开全文</summary>
      <p>${escapeHtml(text)}</p>
    </details>
  `;
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trim()}...`;
}

function collectMatchedTerms(item) {
  const rules = item.matched_rules || [];
  const hits = item.hit_sentences || [];
  const tags = item.candidate_tags || [];
  return dedupeValues([
    ...rules.flatMap((rule) => rule.matched_keywords || []),
    ...hits.flatMap((hit) => (hit.highlights || []).map((highlight) => highlight.text)),
    ...tags.map((tag) => tag.matched_text),
  ])
    .filter((term) => term.length <= 28)
    .slice(0, 10);
}

function collectMatchedContents(item) {
  return dedupeValues((item.hit_sentences || []).map((hit) => hit.sentence)).slice(0, 2);
}

function dedupeValues(values) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
}

function severityClass(value) {
  if (value === "high") {
    return "risk-high";
  }
  if (value === "medium") {
    return "risk-medium";
  }
  if (value === "low") {
    return "risk-low";
  }
  return "risk-none";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
