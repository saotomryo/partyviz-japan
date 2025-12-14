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
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function stanceColorClass(label) {
  if (label === "oppose") return "chip stance danger";
  return "chip stance";
}

function scoreToPercent(score) {
  return ((score + 100) / 200) * 100;
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

function renderPositions(topic, mode, entity, scores) {
  modeBadgeEl.textContent = `mode: ${mode}`;
  if (!scores || scores.length === 0) {
    positionsEl.innerHTML = `<p class="muted">データがありません。</p>`;
    return;
  }
  const cards = scores.map(s => {
    const percent = scoreToPercent(s.stance_score);
    return `
      <div class="score-card">
        <div>
          <p class="score-card__title">${s.entity_id}</p>
          <p class="score-card__meta">${s.rationale}</p>
          <button class="button-link" data-entity="${s.entity_id}" data-topic="${topic.topic_id}" data-mode="${mode}">根拠を見る</button>
        </div>
        <div>
          <div class="axis">
            <div class="axis__marker" style="left:${percent}%;"></div>
          </div>
          <p class="score-card__meta">スコア: ${s.stance_score} / 信頼度: ${s.confidence}</p>
        </div>
        <div>
          <span class="${stanceColorClass(s.stance_label)}">${s.stance_label}</span>
        </div>
      </div>
    `;
  });
  positionsEl.innerHTML = cards.join("");

  positionsEl.querySelectorAll("button[data-entity]").forEach(btn => {
    btn.addEventListener("click", () => {
      const entityId = btn.dataset.entity;
      const topicId = btn.dataset.topic;
      const m = btn.dataset.mode;
      openDetail(entityId, topicId, m);
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

  detailContentEl.innerHTML = `
    <p class="eyebrow">${data.topic.topic_id}</p>
    <h3>${data.topic.name}</h3>
    <p class="muted">${data.topic.description || ""}</p>
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
    renderPositions(data.topic, mode, entity, data.scores);
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
