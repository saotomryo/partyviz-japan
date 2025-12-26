const DEFAULT_API_BASE = "http://localhost:8000";
const DEFAULT_SNAPSHOT_URL = "./data/snapshot.json";

const topicIdEl = document.getElementById("rubricTopicId");
const topicNameEl = document.getElementById("rubricTopicName");
const topicDescEl = document.getElementById("rubricTopicDescription");
const rubricVersionEl = document.getElementById("rubricVersion");
const rubricBodyEl = document.getElementById("rubricBody");

let snapshotData = null;
let dataSource = "api";

function getQueryParam(key) {
  const url = new URL(window.location.href);
  return url.searchParams.get(key);
}

function getApiBase() {
  return (localStorage.getItem("partyviz_public_api_base") || DEFAULT_API_BASE).trim();
}

async function tryLoadSnapshot() {
  const source = (getQueryParam("source") || "").toLowerCase();
  if (source !== "snapshot") return;
  const snapshotUrl =
    getQueryParam("snapshot") ||
    (localStorage.getItem("partyviz_public_snapshot_url") || "").trim() ||
    DEFAULT_SNAPSHOT_URL;
  const res = await fetch(snapshotUrl, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`snapshot fetch failed: HTTP ${res.status}`);
  }
  const json = await res.json();
  if (!json || !Array.isArray(json.topics) || typeof json.rubrics !== "object") {
    throw new Error("snapshot format invalid");
  }
  snapshotData = json;
  dataSource = "snapshot";
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

async function getRubric(topicId) {
  if (dataSource === "snapshot") {
    return snapshotData?.rubrics?.[topicId] || null;
  }
  return fetchJSON(`${getApiBase()}/topics/${encodeURIComponent(topicId)}/rubric`);
}

async function getTopicMeta(topicId) {
  if (dataSource === "snapshot") {
    return (snapshotData?.topics || []).find((t) => t.topic_id === topicId) || null;
  }
  const data = await fetchJSON(`${getApiBase()}/topics`);
  return (data.topics || []).find((t) => t.topic_id === topicId) || null;
}

function renderRubric(rubric, topic) {
  if (!rubric) {
    rubricBodyEl.innerHTML = `<p class="muted">評価基準が見つかりません。</p>`;
    return;
  }
  const steps = Array.isArray(rubric.steps) ? rubric.steps.slice() : [];
  steps.sort((a, b) => (a.score || 0) - (b.score || 0));
  const axisLeft = rubric.axis_a_label || "";
  const axisRight = rubric.axis_b_label || "";
  rubricBodyEl.innerHTML = `
    <div class="rubric-view__axis">
      <div class="rubric-view__axis-label">-100: ${axisLeft}</div>
      <div class="rubric-view__axis-label rubric-view__axis-label--right">+100: ${axisRight}</div>
    </div>
    <div class="rubric-view__table-wrap">
      <table class="rubric-table">
        <colgroup>
          <col style="width: 90px;">
          <col style="width: 220px;">
          <col>
        </colgroup>
        <thead>
          <tr>
            <th>スコア</th>
            <th>ラベル</th>
            <th>基準</th>
          </tr>
        </thead>
        <tbody>
          ${steps
            .map(
              (s) => `
              <tr>
                <td class="rubric-table__score">${s.score}</td>
                <td class="rubric-table__label">${s.label}</td>
                <td class="rubric-table__criteria">${s.criteria}</td>
              </tr>
            `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;

  topicIdEl.textContent = topic?.topic_id || rubric.topic_id || "";
  topicNameEl.textContent = topic?.name || rubric.topic_id || "評価基準";
  topicDescEl.textContent = topic?.description || "";
  rubricVersionEl.textContent = `version: ${rubric.version ?? ""}`;
}

(async () => {
  try {
    await tryLoadSnapshot();
    const topicId = getQueryParam("topic");
    if (!topicId) throw new Error("topic is required");
    const [rubric, topic] = await Promise.all([getRubric(topicId), getTopicMeta(topicId)]);
    renderRubric(rubric, topic);
  } catch (err) {
    rubricBodyEl.innerHTML = `<p class="muted">読み込みに失敗しました: ${err.message}</p>`;
  }
})();
