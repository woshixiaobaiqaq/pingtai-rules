const formError = document.querySelector("#form-error");
const contentInput = document.querySelector("#content-input");
const submitButton = document.querySelector("#submit-button");
const results = document.querySelector("#results");
const resultsStack = document.querySelector("#results-stack");
const resultTemplate = document.querySelector("#platform-result-template");
const platformLibrarySummary = document.querySelector("#platform-library-summary");
const ruleLibraryTotal = document.querySelector("#rule-library-total");
const platformCountNodes = [...document.querySelectorAll("[data-platform-count]")];

const platformLabels = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  video_channel: "视频号",
};

const severityLabels = {
  none: "无命中",
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

void loadRuleLibrarySummary();

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
      const detail = payload?.detail ?? "检测失败。";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    renderPlatformResults(payload.report.platform_results);
  } catch (error) {
    renderError(error.message || "请求失败，请检查服务状态。");
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "检测中..." : "开始检测";
}

function renderError(message) {
  formError.hidden = !message;
  formError.textContent = message;
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

  platformResults.forEach((item, index) => {
    resultsStack.appendChild(buildPlatformCard(item, index));
  });
}

function buildPlatformCard(item, index) {
  const fragment = resultTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".platform-card");
  const rules = item.matched_rules || [];
  card.style.animationDelay = `${index * 70}ms`;

  fragment.querySelector(".platform-card__name").textContent = platformLabels[item.platform] ?? item.platform;
  fragment.querySelector(".platform-card__title").textContent =
    rules.length > 0 ? "命中规则" : "未命中规则";
  fragment.querySelector(".platform-card__count").textContent = `${rules.length} 条`;

  const ruleList = fragment.querySelector(".rule-list");
  if (rules.length === 0) {
    ruleList.appendChild(buildEmptyState("当前平台未命中规则。"));
    return fragment;
  }

  rules.forEach((rule) => {
    ruleList.appendChild(buildRuleCard(rule));
  });

  return fragment;
}

function buildRuleCard(rule) {
  const element = document.createElement("article");
  element.className = "rule-card";
  element.innerHTML = `
    <div class="rule-card__meta">
      <span class="rule-card__id">${escapeHtml(rule.rule_id)}</span>
      <span class="rule-card__severity ${severityClass(rule.severity)}">${escapeHtml(
        severityLabels[rule.severity] ?? rule.severity,
      )}</span>
    </div>
    <h4>${escapeHtml(rule.title)}</h4>
    <p>${escapeHtml(rule.reason)}</p>
    <p>${escapeHtml(rule.quote)}</p>
  `;
  return element;
}

function buildEmptyState(message) {
  const element = document.createElement("div");
  element.className = "empty-state";
  element.textContent = message;
  return element;
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
