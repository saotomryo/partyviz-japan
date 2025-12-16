const API_BASE = "http://localhost:8000";

const topicListEl = document.getElementById("topicList");
const positionsEl = document.getElementById("positions");
const modeSelect = document.getElementById("modeSelect");
const entitySelect = document.getElementById("entitySelect");
const topicIdEl = document.getElementById("selectedTopicId");
const topicNameEl = document.getElementById("selectedTopicName");
const topicDescEl = document.getElementById("selectedTopicDescription");
const modeBadgeEl = document.getElementById("modeBadge");
const overlayEl = document.getElementById("detailOverlay");
const overlayCloseBtn = document.getElementById("overlayClose");
const detailContentEl = document.getElementById("detailContent");

let selectedTopicId = null;

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

function stanceColorClass(label) {
  if (label === "oppose") return "chip stance danger";
  return "chip stance";
}

function scoreToPercent(score) {
  return ((score + 100) / 200) * 100;
}

function primaryEvidenceUrl(scoreItem) {
  if (scoreItem?.evidence?.length && scoreItem.evidence[0]?.url) return scoreItem.evidence[0].url;
  return null;
}

const PARTY_COLORS = [
  "#7ad5ff",
  "#57d1a3",
  "#ff8a7a",
  "#ffd27a",
  "#c58bff",
  "#5df2d6",
  "#ff6bd6",
  "#7aff7a",
  "#ffb86b",
  "#6b8cff",
  "#f06bff",
  "#6bf0ff",
];

function buildPartyColorMap(scores) {
  const items = scores
    .map((s) => ({ id: s.entity_id, name: s.entity_name || s.entity_id }))
    .sort((a, b) => a.name.localeCompare(b.name, "ja"));
  const map = new Map();
  items.forEach((p, idx) => {
    map.set(p.id, PARTY_COLORS[idx % PARTY_COLORS.length]);
  });
  return map;
}

function escapeAttr(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderTopics(topics) {
  topicListEl.innerHTML = "";
  topics.forEach((t, idx) => {
    const li = document.createElement("li");
    li.className = "topic-item";
    li.innerHTML = `
      <p class="eyebrow">${t.topic_id}</p>
      <p class="title">${t.name}</p>
      <p class="muted">${t.description || ""}</p>
    `;
    li.addEventListener("click", () => {
      selectedTopicId = t.topic_id;
      document.querySelectorAll(".topic-item").forEach(el => el.classList.remove("active"));
      li.classList.add("active");
      topicIdEl.textContent = t.topic_id;
      topicNameEl.textContent = t.name;
      topicDescEl.textContent = t.description || "";
      loadPositions();
    });
    topicListEl.appendChild(li);
    if (idx === 0) {
      li.click();
    }
  });
}

function renderPositions(data) {
  const { topic, mode, entity, scores, axis_a_label, axis_b_label } = data;
  modeBadgeEl.textContent = `mode: ${mode}`;
  if (!scores || scores.length === 0) {
    positionsEl.innerHTML = `<p class="muted">データがありません。</p>`;
    return;
  }

  const leftLabel = axis_a_label || "Axis (-100)";
  const rightLabel = axis_b_label || "Axis (+100)";

  const colorMap = buildPartyColorMap(scores);

  const bucketKey = (score) => String(Math.round(Number(score || 0)));
  const buckets = new Map();
  scores.forEach((s) => {
    const k = bucketKey(s.stance_score);
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(s);
  });
  const maxBucketSize = Math.max(...Array.from(buckets.values()).map((arr) => arr.length), 1);
  const axisHeight = 34 + maxBucketSize * 14;

  const axisDots = scores
    .slice()
    .sort((a, b) => (b.stance_score || 0) - (a.stance_score || 0))
    .map((s) => {
      const percent = scoreToPercent(s.stance_score);
      const title = s.entity_name || s.entity_id;
      const evidenceUrl = primaryEvidenceUrl(s);
      const fullTitle = `${title} (${s.stance_score})${evidenceUrl ? `\\n${evidenceUrl}` : ""}`;

      const key = bucketKey(s.stance_score);
      const group = buckets.get(key) || [s];
      const idx = group.findIndex((x) => x.entity_id === s.entity_id);
      const step = 14;
      const offset = (idx - (group.length - 1) / 2) * step;
      const color = colorMap.get(s.entity_id) || "#7ad5ff";

      return `<button class="plot-axis__dot" style="left:${percent}%; top:calc(50% + ${offset}px); background:${color};" title="${escapeAttr(fullTitle)}" data-entity="${s.entity_id}" data-topic="${topic.topic_id}" data-mode="${mode}"></button>`;
    })
    .join("");

  const legend = scores
    .slice()
    .sort((a, b) => (a.entity_name || a.entity_id).localeCompare(b.entity_name || b.entity_id, "ja"))
    .map((s) => {
      const name = s.entity_name || s.entity_id;
      const color = colorMap.get(s.entity_id) || "#7ad5ff";
      return `<span class="plot-legend__item"><span class="plot-legend__swatch" style="background:${color};"></span>${escapeAttr(name)}</span>`;
    })
    .join("");

  const rows = scores
    .slice()
    .sort((a, b) => (b.stance_score || 0) - (a.stance_score || 0))
    .map((s) => {
      const percent = scoreToPercent(s.stance_score);
      const title = s.entity_name || s.entity_id;
      const evidenceUrl = primaryEvidenceUrl(s);
      const color = colorMap.get(s.entity_id) || "#7ad5ff";
      return `
        <div class="plot-row">
          <div class="plot-row__name">
            <div class="plot-row__title">${title}</div>
            <div class="plot-row__meta">
              <span class="${stanceColorClass(s.stance_label)}">${s.stance_label}</span>
              <span class="chip confidence">conf: ${s.confidence}</span>
              <span class="chip">score: ${s.stance_score}</span>
            </div>
            ${evidenceUrl ? `<div class="plot-row__url"><a href="${evidenceUrl}" target="_blank" rel="noreferrer">${evidenceUrl}</a></div>` : `<div class="plot-row__url muted">根拠URLなし</div>`}
          </div>
          <div class="plot-row__track">
            <div class="plot-track">
              <div class="plot-track__zero"></div>
              <button class="plot-dot" style="left:${percent}%; background:${color};" title="${escapeAttr(title)} (${s.stance_score})" data-entity="${s.entity_id}" data-topic="${topic.topic_id}" data-mode="${mode}"></button>
            </div>
          </div>
          <div class="plot-row__score">${s.stance_score}</div>
        </div>
      `;
    })
    .join("");

  positionsEl.innerHTML = `
    <div class="plot">
      <div class="plot__header">
        <div class="plot__axis-label plot__axis-label--left">-100: ${leftLabel}</div>
        <div class="plot__axis-label plot__axis-label--right">+100: ${rightLabel}</div>
      </div>
      <div class="plot-legend">${legend}</div>
      <div class="plot__axis">
        <div class="plot-axis" style="height:${axisHeight}px;">
          <div class="plot-axis__band"></div>
          <div class="plot-axis__zero"></div>
          ${axisDots}
          <div class="plot-axis__tick plot-axis__tick--left">-100</div>
          <div class="plot-axis__tick plot-axis__tick--center">0</div>
          <div class="plot-axis__tick plot-axis__tick--right">+100</div>
        </div>
      </div>
      <div class="plot__rows">
        ${rows}
      </div>
    </div>
  `;

  positionsEl.querySelectorAll("button.plot-dot, button.plot-axis__dot").forEach((btn) => {
    btn.addEventListener("click", () => {
      openDetail(btn.dataset.entity, btn.dataset.topic, btn.dataset.mode);
    });
  });
}

function renderDetail(data) {
  const s = data.score;
  const evidence = s.evidence
    .map(
      ev => `
      <li class="evidence-item">
        <div><strong>URL:</strong> <a href="${ev.url}" target="_blank" rel="noreferrer">${ev.url}</a></div>
        <div class="muted">取得: ${new Date(ev.fetched_at).toLocaleString()}</div>
        <div><code>${ev.quote}</code></div>
        <div class="muted">範囲: ${ev.quote_start} - ${ev.quote_end}</div>
      </li>`
    )
    .join("");

  const axisInfo =
    data.axis_a_label && data.axis_b_label
      ? `<p class="muted">-100: ${data.axis_a_label} / +100: ${data.axis_b_label}</p>`
      : "";

  detailContentEl.innerHTML = `
    <p class="eyebrow">${data.topic.topic_id}</p>
    <h3>${data.topic.name}</h3>
    <p class="muted">${s.entity_name || s.entity_id}</p>
    <p class="muted">${data.topic.description || ""}</p>
    ${axisInfo}
    <div style="margin: 10px 0;">
      <span class="${stanceColorClass(s.stance_label)}">${s.stance_label}</span>
      <span class="chip confidence">conf: ${s.confidence}</span>
      <span class="chip">score: ${s.stance_score}</span>
    </div>
    <p>${s.rationale}</p>
    <h4>根拠</h4>
    <ul class="evidence-list">${evidence}</ul>
    <p class="muted">topic_version: ${s.meta.topic_version} / calc_version: ${s.meta.calc_version}</p>
  `;
}

async function openDetail(entityId, topicId, mode) {
  try {
    overlayEl.classList.remove("hidden");
    detailContentEl.innerHTML = `<p class="muted">読み込み中...</p>`;
    const data = await fetchJSON(`${API_BASE}/entities/${entityId}/topics/${topicId}/detail?mode=${mode}`);
    renderDetail(data);
  } catch (err) {
    detailContentEl.innerHTML = `<p class="muted">取得に失敗しました: ${err.message}</p>`;
  }
}

async function loadTopics() {
  try {
    const data = await fetchJSON(`${API_BASE}/topics`);
    renderTopics(data.topics);
  } catch (err) {
    topicListEl.innerHTML = `<li class="muted">トピック取得に失敗しました: ${err.message}</li>`;
  }
}

async function loadPositions() {
  if (!selectedTopicId) return;
  const mode = modeSelect.value;
  const entity = entitySelect.value;
  try {
    const data = await fetchJSON(`${API_BASE}/topics/${selectedTopicId}/positions?mode=${mode}&entity=${encodeURIComponent(entity)}`);
    renderPositions(data);
  } catch (err) {
    positionsEl.innerHTML = `<p class="muted">取得に失敗しました: ${err.message}</p>`;
  }
}

modeSelect.addEventListener("change", loadPositions);
entitySelect.addEventListener("change", loadPositions);
overlayCloseBtn.addEventListener("click", () => overlayEl.classList.add("hidden"));
overlayEl.addEventListener("click", (e) => {
  if (e.target === overlayEl) overlayEl.classList.add("hidden");
});

loadTopics();
