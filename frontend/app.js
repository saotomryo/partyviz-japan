const DEFAULT_API_BASE = "http://localhost:8000";
const DEFAULT_SNAPSHOT_URL = "./data/snapshot.json";

const topicListEl = document.getElementById("topicList");
const topicSelectEl = document.getElementById("topicSelect");
const topicSelectXEl = document.getElementById("topicSelectX");
const topicSelectYEl = document.getElementById("topicSelectY");
const axisTopicSelectorsEl = document.getElementById("axisTopicSelectors");
const positionsEl = document.getElementById("positions");
const modeSelect = document.getElementById("modeSelect");
const entitySelect = document.getElementById("entitySelect");
const viewModeSelectEl = document.getElementById("viewModeSelect");
const themeSelectEl = document.getElementById("themeSelect");
const topicIdEl = document.getElementById("selectedTopicId");
const topicNameEl = document.getElementById("selectedTopicName");
const topicDescEl = document.getElementById("selectedTopicDescription");
const modeBadgeEl = document.getElementById("modeBadge");
const rubricLinkEl = document.getElementById("rubricLink");
const overlayEl = document.getElementById("detailOverlay");
const overlayCloseBtn = document.getElementById("overlayClose");
const detailContentEl = document.getElementById("detailContent");
const adminLinkEl = document.getElementById("adminLink");

let selectedTopicId = null;
let snapshotData = null;
let dataSource = "api";
let snapshotUrlUsed = DEFAULT_SNAPSHOT_URL;
let topicsCache = [];
let themeName = "midnight";

function getQueryParam(key) {
  const url = new URL(window.location.href);
  return url.searchParams.get(key);
}

function getApiBase() {
  return (localStorage.getItem("partyviz_public_api_base") || DEFAULT_API_BASE).trim();
}

async function tryLoadSnapshot() {
  const source = (getQueryParam("source") || "").toLowerCase();
  if (source === "api") return;

  const snapshotUrl =
    getQueryParam("snapshot") ||
    (localStorage.getItem("partyviz_public_snapshot_url") || "").trim() ||
    DEFAULT_SNAPSHOT_URL;
  snapshotUrlUsed = snapshotUrl;

  try {
    const res = await fetch(snapshotUrl, { cache: "no-cache" });
    if (!res.ok) {
      if (source === "snapshot") throw new Error(`snapshot fetch failed: HTTP ${res.status}`);
      return;
    }
    const json = await res.json();
    if (!json || !Array.isArray(json.topics) || typeof json.positions !== "object") {
      if (source === "snapshot") throw new Error("snapshot format invalid");
      return;
    }
    snapshotData = json;
    dataSource = "snapshot";
  } catch (e) {
    if (source === "snapshot") throw e;
  }
}

function applyUiForDataSource() {
  if (dataSource === "snapshot" && adminLinkEl) {
    adminLinkEl.remove();
  }
  if (rubricLinkEl) {
    rubricLinkEl.classList.add("hidden");
  }
}

function applyTheme(theme) {
  const themeValue = (theme || "midnight").toLowerCase();
  document.body.classList.remove("theme-dawn", "theme-sunny");
  if (themeValue === "dawn") document.body.classList.add("theme-dawn");
  if (themeValue === "sunny") document.body.classList.add("theme-sunny");
  themeName = themeValue;
  if (themeSelectEl) themeSelectEl.value = themeValue;
  localStorage.setItem("partyviz_public_theme", themeValue);
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

async function getTopics() {
  if (dataSource === "snapshot") {
    return { topics: snapshotData.topics };
  }
  return fetchJSON(`${getApiBase()}/topics`);
}

async function getPositionsForScope(topicId, mode, entity, scope, fallback = 1) {
  if (dataSource === "snapshot") {
    const mixed = scope === "mixed" ? snapshotData.positions_mixed?.[topicId] : null;
    const p = mixed || (fallback ? snapshotData.positions?.[topicId] : null);
    if (!p) throw new Error("snapshot: positions not found for topic");
    return p;
  }
  return fetchJSON(
    `${getApiBase()}/topics/${topicId}/positions?mode=${mode}&entity=${encodeURIComponent(entity)}&scope=${encodeURIComponent(scope)}&fallback=${fallback}`
  );
}

async function getDetail(entityId, topicId, mode, scope) {
  if (dataSource === "snapshot") {
    const p =
      (scope === "mixed" ? snapshotData.positions_mixed?.[topicId] : null) ||
      snapshotData.positions?.[topicId];
    const s = p?.scores?.find((x) => x.entity_id === entityId);
    if (!p || !s) throw new Error("snapshot: score not found");
    return {
      topic: p.topic,
      mode: p.mode || mode,
      entity_id: entityId,
      rubric_version: p.rubric_version ?? null,
      axis_a_label: p.axis_a_label ?? null,
      axis_b_label: p.axis_b_label ?? null,
      score: s,
    };
  }
  return fetchJSON(
    `${getApiBase()}/entities/${entityId}/topics/${topicId}/detail?mode=${mode}&scope=${encodeURIComponent(scope)}&fallback=1`
  );
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
  topicsCache = topics || [];
  if (topicListEl) topicListEl.innerHTML = "";
  const fillSelect = (el, items) => {
    if (!el) return;
    el.innerHTML = "";
    items.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.topic_id;
      opt.textContent = `${t.name}`;
      el.appendChild(opt);
    });
  };
  fillSelect(topicSelectEl, topicsCache);
  fillSelect(topicSelectXEl, topicsCache);
  fillSelect(topicSelectYEl, topicsCache);
  if (topicsCache.length) {
    selectedTopicId = topicsCache[0].topic_id;
    if (topicSelectEl) topicSelectEl.value = selectedTopicId;
    if (topicSelectXEl) topicSelectXEl.value = topicsCache[0].topic_id;
    if (topicSelectYEl) topicSelectYEl.value = topicsCache[1]?.topic_id || topicsCache[0].topic_id;
    updateSelectedTopicMeta(selectedTopicId);
    loadPositions();
  }
}

function updateSelectedTopicMeta(topicId) {
  const topic = topicsCache.find((t) => t.topic_id === topicId);
  topicIdEl.textContent = topic?.topic_id || "topic";
  topicNameEl.textContent = topic?.name || "トピックを選択してください";
  topicDescEl.textContent = topic?.description || "";
}

function buildRubricLink(topicId) {
  if (!topicId) return null;
  const params = new URLSearchParams({ topic: topicId });
  if (dataSource === "snapshot") {
    params.set("source", "snapshot");
    if (snapshotUrlUsed) params.set("snapshot", snapshotUrlUsed);
  }
  return `rubric.html?${params.toString()}`;
}

function updateRubricLink(positions) {
  if (!rubricLinkEl) return;
  const topicId = positions?.topic?.topic_id || selectedTopicId;
  const version = positions?.rubric_version ?? null;
  const url = buildRubricLink(topicId);
  if (!url || version === null) {
    rubricLinkEl.classList.add("hidden");
    return;
  }
  rubricLinkEl.classList.remove("hidden");
  rubricLinkEl.href = url;
  rubricLinkEl.textContent = `評価基準を見る（v${version}）`;
}

function renderPositionsBlock(data, scopeLabel, scopeValue) {
  const { topic, mode, scores, axis_a_label, axis_b_label } = data;
  if (!scores || scores.length === 0) {
    return `
      <div class="rubric-item">
        <header><h3>${scopeLabel}</h3></header>
        <p class="muted">データがありません。</p>
      </div>
    `;
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

      return `<button class="plot-axis__dot" style="left:${percent}%; top:calc(50% + ${offset}px); background:${color};" title="${escapeAttr(fullTitle)}" data-name="${escapeAttr(title)}" data-entity="${s.entity_id}" data-topic="${topic.topic_id}" data-mode="${mode}" data-scope="${scopeValue}"></button>`;
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
              <button class="plot-dot" style="left:${percent}%; background:${color};" title="${escapeAttr(title)} (${s.stance_score})" data-entity="${s.entity_id}" data-topic="${topic.topic_id}" data-mode="${mode}" data-scope="${scopeValue}"></button>
            </div>
          </div>
          <div class="plot-row__score">${s.stance_score}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="plot" style="margin-bottom: 18px;">
      <div class="plot__header">
        <div>
          <div class="rubric-meta">${scopeLabel}</div>
          <div class="plot__axis-head">
            <div class="plot__axis-label plot__axis-label--left">-100: ${leftLabel}</div>
            <div class="plot__axis-label plot__axis-label--right">+100: ${rightLabel}</div>
          </div>
        </div>
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
}

function renderDetail(data) {
  const alt = data._alt || null;
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

  const altSummary =
    alt && alt.score
      ? `<div class="rubric-item" style="margin: 10px 0;">
          <div class="rubric-meta">公式のみ（比較）</div>
          <div style="margin-top:6px;">
            <span class="${stanceColorClass(alt.score.stance_label)}">${alt.score.stance_label}</span>
            <span class="chip confidence">conf: ${alt.score.confidence}</span>
            <span class="chip">score: ${alt.score.stance_score}</span>
          </div>
        </div>`
      : "";

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
    ${altSummary}
    <p>${s.rationale}</p>
    <h4>根拠</h4>
    <ul class="evidence-list">${evidence}</ul>
    <p class="muted">topic_version: ${s.meta.topic_version} / calc_version: ${s.meta.calc_version}</p>
  `;
}

function renderAxisComparison(xData, yData) {
  const xTopic = xData.topic;
  const yTopic = yData.topic;
  const xMap = new Map(xData.scores.map((s) => [s.entity_id, s]));
  const yMap = new Map(yData.scores.map((s) => [s.entity_id, s]));
  const scores = [];
  xMap.forEach((xScore, id) => {
    const yScore = yMap.get(id);
    if (!yScore) return;
    scores.push({ id, x: xScore, y: yScore });
  });
  const colorMap = buildPartyColorMap(xData.scores);
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const jitterByKey = new Map();
  const dots = scores
    .map((item) => {
      const percentX = scoreToPercent(item.x.stance_score);
      const percentY = scoreToPercent(item.y.stance_score);
      const key = `${Math.round(percentX)}:${Math.round(percentY)}`;
      const bucket = jitterByKey.get(key) || [];
      bucket.push(item.id);
      jitterByKey.set(key, bucket);
      const idx = bucket.length - 1;
      const angle = (idx * 137.5) * (Math.PI / 180);
      const radius = 10 + Math.floor(idx / 6) * 6;
      const dx = Math.cos(angle) * radius;
      const dy = Math.sin(angle) * radius;
      const clampedX = clamp(percentX, 3, 97);
      const clampedY = clamp(percentY, 3, 97);
      const color = colorMap.get(item.id) || "#7ad5ff";
      const name = item.x.entity_name || item.id;
      const title = `${name} (${item.x.stance_score}, ${item.y.stance_score})`;
      return `<button class="axis-plot__dot" style="left:${clampedX}%; bottom:${clampedY}%; background:${color}; --dx:${dx.toFixed(1)}px; --dy:${dy.toFixed(1)}px;" title="${escapeAttr(title)}" data-name="${escapeAttr(name)}" data-entity="${item.id}"></button>`;
    })
    .join("");

  const legend = scores
    .slice()
    .sort((a, b) => (a.x.entity_name || a.id).localeCompare(b.x.entity_name || b.id, "ja"))
    .map((item) => {
      const name = item.x.entity_name || item.id;
      const color = colorMap.get(item.id) || "#7ad5ff";
      return `<span class="plot-legend__item"><span class="plot-legend__swatch" style="background:${color};"></span>${escapeAttr(name)}</span>`;
    })
    .join("");

  return `
    <div class="axis-plot">
      <div class="rubric-meta">2軸比較</div>
      <div class="axis-plot__grid">
        <div class="axis-plot__zero-x"></div>
        <div class="axis-plot__zero-y"></div>
        <div class="axis-plot__axis-label axis-plot__axis-label--x">
          ${escapeAttr(xTopic.name)}（X）
        </div>
        <div class="axis-plot__axis-label axis-plot__axis-label--y">
          ${escapeAttr(yTopic.name)}（Y）
        </div>
        <div class="axis-plot__axis-end axis-plot__axis-end--x-left">
          -100: ${escapeAttr(xData.axis_a_label || "")}
        </div>
        <div class="axis-plot__axis-end axis-plot__axis-end--x-right">
          +100: ${escapeAttr(xData.axis_b_label || "")}
        </div>
        <div class="axis-plot__axis-end axis-plot__axis-end--y-top">
          +100: ${escapeAttr(yData.axis_b_label || "")}
        </div>
        <div class="axis-plot__axis-end axis-plot__axis-end--y-bottom">
          -100: ${escapeAttr(yData.axis_a_label || "")}
        </div>
        ${dots}
      </div>
      <div class="plot-legend">${legend}</div>
    </div>
  `;
}

async function openDetail(entityId, topicId, mode, scope) {
  try {
    overlayEl.classList.remove("hidden");
    detailContentEl.innerHTML = `<p class="muted">読み込み中...</p>`;
    const scopeNorm = (scope || "official").toLowerCase();
    const data = await getDetail(entityId, topicId, mode, scopeNorm);
    if (scopeNorm === "mixed") {
      try {
        const official = await getDetail(entityId, topicId, mode, "official");
        data._alt = official;
      } catch {
        // ignore
      }
    }
    renderDetail(data);
  } catch (err) {
    detailContentEl.innerHTML = `<p class="muted">取得に失敗しました: ${err.message}</p>`;
  }
}

async function loadTopics() {
  try {
    const data = await getTopics();
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
    modeBadgeEl.textContent = `mode: ${mode}`;
    if (viewModeSelectEl && viewModeSelectEl.value === "axis2") {
      const topicX = topicSelectXEl?.value;
      const topicY = topicSelectYEl?.value;
      if (!topicX || !topicY) {
        positionsEl.innerHTML = `<p class="muted">2軸のトピックを選択してください。</p>`;
        return;
      }
      const [xData, yData] = await Promise.all([
        getPositionsForScope(topicX, mode, entity, "official", 1),
        getPositionsForScope(topicY, mode, entity, "official", 1),
      ]);
      topicIdEl.textContent = `${topicX} × ${topicY}`;
      topicNameEl.textContent = "2軸比較";
      topicDescEl.textContent = `${xData.topic.name} と ${yData.topic.name} を比較表示します。`;
      positionsEl.innerHTML = renderAxisComparison(xData, yData);
      updateRubricLink(null);
      positionsEl.querySelectorAll("button.axis-plot__dot").forEach((btn) => {
        btn.addEventListener("click", () => {
          openAxisDetail(btn.dataset.entity, xData, yData);
        });
      });
      return;
    }

    const officialData = await getPositionsForScope(selectedTopicId, mode, entity, "official", 1);
    let mixedData = null;
    try {
      mixedData = await getPositionsForScope(selectedTopicId, mode, entity, "mixed", 0);
    } catch {
      mixedData = null;
    }
    const blocks = [];
    blocks.push(renderPositionsBlock(officialData, "公式のみ", "official"));
    if (mixedData && mixedData.scores && mixedData.scores.length) {
      const officialAt = officialData.run_created_at ? new Date(officialData.run_created_at).getTime() : 0;
      const mixedAt = mixedData.run_created_at ? new Date(mixedData.run_created_at).getTime() : 0;
      if (!officialAt || !mixedAt || mixedAt >= officialAt) {
        blocks.push(renderPositionsBlock(mixedData, "公式＋外部（mixed）", "mixed"));
      }
    }
    positionsEl.innerHTML = blocks.join("");
    updateRubricLink(officialData);
    positionsEl.querySelectorAll("button.plot-dot, button.plot-axis__dot").forEach((btn) => {
      btn.addEventListener("click", () => {
        openDetail(btn.dataset.entity, btn.dataset.topic, btn.dataset.mode, btn.dataset.scope);
      });
    });
  } catch (err) {
    positionsEl.innerHTML = `<p class="muted">取得に失敗しました: ${err.message}</p>`;
  }
}

function openAxisDetail(entityId, xData, yData) {
  const xScore = (xData.scores || []).find((s) => s.entity_id === entityId);
  const yScore = (yData.scores || []).find((s) => s.entity_id === entityId);
  if (!xScore || !yScore) return;
  const xUrl = primaryEvidenceUrl(xScore);
  const yUrl = primaryEvidenceUrl(yScore);
  const xQuote = xScore?.evidence?.[0]?.quote || "";
  const yQuote = yScore?.evidence?.[0]?.quote || "";
  detailContentEl.innerHTML = `
    <p class="eyebrow">2軸比較</p>
    <h3>${xScore.entity_name || entityId}</h3>
    <div class="rubric-item" style="margin: 10px 0;">
      <div class="rubric-meta">${escapeAttr(xData.topic.name)}（X）</div>
      <div style="margin-top:6px;">
        <span class="${stanceColorClass(xScore.stance_label)}">${xScore.stance_label}</span>
        <span class="chip confidence">conf: ${xScore.confidence}</span>
        <span class="chip">score: ${xScore.stance_score}</span>
      </div>
      ${xScore.rationale ? `<div class="rubric-meta" style="margin-top:6px;">${escapeAttr(xScore.rationale)}</div>` : ""}
      ${xQuote ? `<div class="rubric-meta" style="margin-top:6px;"><code>${escapeAttr(xQuote)}</code></div>` : ""}
      ${xUrl ? `<div class="rubric-meta"><a class="link" target="_blank" rel="noreferrer" href="${escapeAttr(xUrl)}">${escapeAttr(xUrl)}</a></div>` : ""}
    </div>
    <div class="rubric-item" style="margin: 10px 0;">
      <div class="rubric-meta">${escapeAttr(yData.topic.name)}（Y）</div>
      <div style="margin-top:6px;">
        <span class="${stanceColorClass(yScore.stance_label)}">${yScore.stance_label}</span>
        <span class="chip confidence">conf: ${yScore.confidence}</span>
        <span class="chip">score: ${yScore.stance_score}</span>
      </div>
      ${yScore.rationale ? `<div class="rubric-meta" style="margin-top:6px;">${escapeAttr(yScore.rationale)}</div>` : ""}
      ${yQuote ? `<div class="rubric-meta" style="margin-top:6px;"><code>${escapeAttr(yQuote)}</code></div>` : ""}
      ${yUrl ? `<div class="rubric-meta"><a class="link" target="_blank" rel="noreferrer" href="${escapeAttr(yUrl)}">${escapeAttr(yUrl)}</a></div>` : ""}
    </div>
  `;
  overlayEl.classList.remove("hidden");
}

modeSelect.addEventListener("change", loadPositions);
entitySelect.addEventListener("change", loadPositions);
if (themeSelectEl) {
  themeSelectEl.addEventListener("change", () => {
    applyTheme(themeSelectEl.value);
  });
}
if (viewModeSelectEl) {
  viewModeSelectEl.addEventListener("change", () => {
    const isAxis = viewModeSelectEl.value === "axis2";
    if (axisTopicSelectorsEl) axisTopicSelectorsEl.classList.toggle("hidden", !isAxis);
    if (topicSelectEl) topicSelectEl.classList.toggle("hidden", isAxis);
    updateSelectedTopicMeta(selectedTopicId);
    loadPositions();
  });
}
if (topicSelectEl) {
  topicSelectEl.addEventListener("change", () => {
    selectedTopicId = topicSelectEl.value;
    updateSelectedTopicMeta(selectedTopicId);
    loadPositions();
  });
}
if (topicSelectXEl) topicSelectXEl.addEventListener("change", loadPositions);
if (topicSelectYEl) topicSelectYEl.addEventListener("change", loadPositions);
overlayCloseBtn.addEventListener("click", () => overlayEl.classList.add("hidden"));
overlayEl.addEventListener("click", (e) => {
  if (e.target === overlayEl) overlayEl.classList.add("hidden");
});

(async () => {
  try {
    await tryLoadSnapshot();
    applyUiForDataSource();
    const savedTheme = localStorage.getItem("partyviz_public_theme");
    applyTheme(savedTheme || "midnight");
  } catch (e) {
    positionsEl.innerHTML = `<p class="muted">スナップショット読み込みに失敗しました: ${e.message}</p>`;
  }
  loadTopics();
})();
