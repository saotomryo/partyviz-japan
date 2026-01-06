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
const summaryCache = new Map();

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

function categorizeTopicForRadar(topicId, topicName) {
  const tid = (topicId || "").trim().toLowerCase();
  const name = (topicName || "").trim().toLowerCase();
  const text = `${tid} ${name}`;
  if (["財政", "税", "消費税", "賃金", "物価", "成長", "産業", "経済", "金融", "最低賃金"].some((k) => text.includes(k))) {
    return { key: "economy", label: "経済・財政" };
  }
  if (["社会保障", "年金", "医療", "介護", "子育て", "教育", "奨学", "保育"].some((k) => text.includes(k))) {
    return { key: "welfare", label: "社会保障・子育て" };
  }
  if (["安全保障", "防衛", "外交", "自衛隊", "反撃", "日米", "中国", "北朝鮮"].some((k) => text.includes(k))) {
    return { key: "security", label: "外交・安全保障" };
  }
  if (["人権", "ジェンダー", "夫婦別姓", "lgbt", "同性", "移民", "難民", "入管", "表現"].some((k) => text.includes(k))) {
    return { key: "rights", label: "人権・多様性" };
  }
  if (["デジタル", "行政", "規制改革", "ai", "人工知能", "dx", "マイナン"].some((k) => text.includes(k))) {
    return { key: "digital", label: "デジタル・行政改革" };
  }
  return { key: "other", label: "その他" };
}

function isMissingScoreItemForRadar(scoreItem) {
  if (!scoreItem) return true;
  if (scoreItem.stance_label !== "not_mentioned") return false;
  if (Number(scoreItem.stance_score || 0) !== 0) return false;
  if (Number(scoreItem.confidence || 0) !== 0) return false;
  const rationale = String(scoreItem.rationale || "");
  if (rationale.includes("スコア未作成") || rationale.includes("スコアがありません") || rationale.includes("未評価")) {
    return true;
  }
  const hasEvidence = Array.isArray(scoreItem.evidence) && scoreItem.evidence.some((ev) => ev?.url);
  return !hasEvidence;
}

function medianOfSorted(numbers) {
  if (!numbers.length) return null;
  const mid = Math.floor(numbers.length / 2);
  if (numbers.length % 2 === 1) return numbers[mid];
  return (numbers[mid - 1] + numbers[mid]) / 2;
}

async function getRadar(entityId, scope) {
  const scopeNorm = (scope || "official").toLowerCase();
  if (dataSource !== "snapshot") {
    return fetchJSON(`${getApiBase()}/entities/${entityId}/radar?scope=${encodeURIComponent(scopeNorm)}`);
  }

  const categoryOrder = [
    { key: "economy", label: "経済・財政" },
    { key: "welfare", label: "社会保障・子育て" },
    { key: "security", label: "外交・安全保障" },
    { key: "rights", label: "人権・多様性" },
    { key: "digital", label: "デジタル・行政改革" },
    { key: "other", label: "その他" },
  ];

  const pointsByCat = new Map(categoryOrder.map((c) => [c.key, []]));
  const topics = (snapshotData?.topics || []).filter((t) => t?.is_active !== false);
  let included = 0;

  topics.forEach((t) => {
    const p = snapshotData.positions?.[t.topic_id];
    const score = p?.scores?.find((x) => x.entity_id === entityId);
    if (!p || !score) return;
    if (isMissingScoreItemForRadar(score)) return;
    const cat = categorizeTopicForRadar(t.topic_id, t.name);
    const bucket = pointsByCat.get(cat.key) || [];
    bucket.push({
      topic_id: t.topic_id,
      topic_name: t.name,
      stance_score: Number(score.stance_score || 0),
      stance_label: score.stance_label,
      confidence: Number(score.confidence || 0),
    });
    pointsByCat.set(cat.key, bucket);
    included += 1;
  });

  const categories = categoryOrder.map((cat) => {
    const pts = pointsByCat.get(cat.key) || [];
    const scores = pts.map((x) => x.stance_score).sort((a, b) => a - b);
    return {
      key: cat.key,
      label: cat.label,
      count: scores.length,
      median: medianOfSorted(scores),
      min: scores.length ? scores[0] : null,
      max: scores.length ? scores[scores.length - 1] : null,
      topics: pts.slice().sort((a, b) => String(a.topic_id).localeCompare(String(b.topic_id))),
    };
  });

  return {
    entity_type: "party",
    entity_id: entityId,
    entity_name: null,
    scope: scopeNorm,
    topic_total: topics.length,
    topic_included: included,
    categories,
  };
}

async function getAllPartiesRadar(scope) {
  const scopeNorm = (scope || "official").toLowerCase();
  if (dataSource !== "snapshot") {
    return fetchJSON(`${getApiBase()}/radar/parties?scope=${encodeURIComponent(scopeNorm)}&include_topics=0`);
  }

  const categoryOrder = [
    { key: "economy", label: "経済・財政" },
    { key: "welfare", label: "社会保障・子育て" },
    { key: "security", label: "外交・安全保障" },
    { key: "rights", label: "人権・多様性" },
    { key: "digital", label: "デジタル・行政改革" },
    { key: "other", label: "その他" },
  ];

  const topics = (snapshotData?.topics || []).filter((t) => t?.is_active !== false);
  const topicNameById = new Map(topics.map((t) => [t.topic_id, t.name]));

  const partyById = new Map();
  topics.some((t) => {
    const p = snapshotData.positions?.[t.topic_id];
    if (p?.scores?.length) {
      p.scores.forEach((s) => {
        partyById.set(s.entity_id, { entity_id: s.entity_id, entity_name: s.entity_name || s.entity_id });
      });
      return true;
    }
    return false;
  });

  const partyCategoryScores = new Map(); // partyId -> catKey -> scores[]
  const partyIncludedTopics = new Map(); // partyId -> Set(topic_id)

  const ensureBucket = (partyId, catKey) => {
    if (!partyCategoryScores.has(partyId)) partyCategoryScores.set(partyId, new Map());
    const map = partyCategoryScores.get(partyId);
    if (!map.has(catKey)) map.set(catKey, []);
    return map.get(catKey);
  };

  const ensureTopicSet = (partyId) => {
    if (!partyIncludedTopics.has(partyId)) partyIncludedTopics.set(partyId, new Set());
    return partyIncludedTopics.get(partyId);
  };

  topics.forEach((t) => {
    const p = snapshotData.positions?.[t.topic_id];
    if (!p?.scores?.length) return;
    const topicName = topicNameById.get(t.topic_id) || t.name || t.topic_id;
    const cat = categorizeTopicForRadar(t.topic_id, topicName);
    p.scores.forEach((s) => {
      if (isMissingScoreItemForRadar(s)) return;
      const scores = ensureBucket(s.entity_id, cat.key);
      scores.push(Number(s.stance_score || 0));
      ensureTopicSet(s.entity_id).add(t.topic_id);
      if (!partyById.has(s.entity_id)) {
        partyById.set(s.entity_id, { entity_id: s.entity_id, entity_name: s.entity_name || s.entity_id });
      }
    });
  });

  const parties = Array.from(partyById.values()).sort((a, b) => String(a.entity_name).localeCompare(String(b.entity_name), "ja"));

  return parties.map((party) => {
    const catMap = partyCategoryScores.get(party.entity_id) || new Map();
    const included = partyIncludedTopics.get(party.entity_id) || new Set();
    const categories = categoryOrder.map((cat) => {
      const scores = (catMap.get(cat.key) || []).slice().sort((a, b) => a - b);
      return {
        key: cat.key,
        label: cat.label,
        count: scores.length,
        median: medianOfSorted(scores),
        min: scores.length ? scores[0] : null,
        max: scores.length ? scores[scores.length - 1] : null,
        topics: [],
      };
    });
    return {
      entity_type: "party",
      entity_id: party.entity_id,
      entity_name: party.entity_name,
      scope: scopeNorm,
      topic_total: topics.length,
      topic_included: included.size,
      categories,
    };
  });
}

function buildSummaryText({
  posTopics,
  negTopics,
  nearParty,
  farParty,
  quote,
  topicCount,
  fiscalNote,
}) {
  const posPart = posTopics.slice(0, 2).join("・");
  const negPart = negTopics.slice(0, 1).join("・");
  const phrases = [];
  if (posPart) phrases.push(`${posPart}に積極的`);
  if (negPart) phrases.push(`${negPart}は慎重`);
  const lead = phrases.length ? `平均より${phrases.join("、")}。` : "平均との差が小さい。";
  let comp = "";
  if (nearParty && farParty) comp = `${nearParty}に近く、${farParty}とは差が大きい。`;
  else if (nearParty) comp = `${nearParty}に近い傾向。`;
  const extra = topicCount ? `対象${topicCount}件の相対評価。` : "";
  const note = fiscalNote ? fiscalNote : "";
  const q = quote ? `根拠:「${quote}」` : "";
  let text = `${lead}${comp}${extra}${note}${q}`;
  return text;
}

function cleanQuote(text) {
  const t = String(text || "").replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim();
  return t;
}

async function getPartySummaries(scope) {
  const scopeNorm = (scope || "official").toLowerCase();
  const cacheKey = `summaries:${scopeNorm}`;
  if (summaryCache.has(cacheKey)) return summaryCache.get(cacheKey);

  if (dataSource !== "snapshot") {
    const data = await fetchJSON(`${getApiBase()}/summaries/parties?scope=${encodeURIComponent(scopeNorm)}`);
    summaryCache.set(cacheKey, data);
    return data;
  }

  const topics = (snapshotData?.topics || []).filter((t) => t?.is_active !== false);
  const topicById = new Map(topics.map((t) => [t.topic_id, t]));

  const partyById = new Map();
  topics.forEach((t) => {
    const p = snapshotData.positions?.[t.topic_id];
    p?.scores?.forEach((s) => {
      if (!partyById.has(s.entity_id)) {
        partyById.set(s.entity_id, { entity_id: s.entity_id, entity_name: s.entity_name || s.entity_id });
      }
    });
  });

  const topicScores = new Map();
  const partyScores = new Map();
  const partyQuotes = new Map();

  topics.forEach((t) => {
    const p = snapshotData.positions?.[t.topic_id];
    if (!p?.scores?.length) return;
    p.scores.forEach((s) => {
      if (isMissingScoreItemForRadar(s)) return;
      if (!partyScores.has(s.entity_id)) partyScores.set(s.entity_id, new Map());
      partyScores.get(s.entity_id).set(t.topic_id, Number(s.stance_score || 0));
      if (!topicScores.has(t.topic_id)) topicScores.set(t.topic_id, []);
      topicScores.get(t.topic_id).push(Number(s.stance_score || 0));
      const quote = s?.evidence?.[0]?.quote ? cleanQuote(s.evidence[0].quote) : "";
      if (quote) {
        if (!partyQuotes.has(s.entity_id)) partyQuotes.set(s.entity_id, new Map());
        partyQuotes.get(s.entity_id).set(t.topic_id, quote);
      }
    });
  });

  const topicStats = new Map();
  topicScores.forEach((vals, tid) => {
    if (!vals.length) return;
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, vals.length);
    const std = Math.sqrt(variance);
    topicStats.set(tid, { mean, std });
  });

  const partyZ = new Map();
  partyScores.forEach((scores, pid) => {
    const zmap = new Map();
    scores.forEach((val, tid) => {
      const stat = topicStats.get(tid);
      if (!stat) return;
      const z = stat.std === 0 ? 0 : (val - stat.mean) / stat.std;
      zmap.set(tid, z);
    });
    partyZ.set(pid, zmap);
  });

  const distance = (a, b) => {
    const keys = Array.from(a.keys()).filter((k) => b.has(k));
    if (keys.length < 2) return null;
    const vals = keys.map((k) => (a.get(k) - b.get(k)) ** 2);
    return vals.reduce((x, y) => x + y, 0) / vals.length;
  };

  const summaries = Array.from(partyById.values()).map((party) => {
    const zmap = partyZ.get(party.entity_id) || new Map();
    const zItems = Array.from(zmap.entries()).sort((a, b) => b[1] - a[1]);
    const posIds = zItems.slice(0, 3).map((x) => x[0]);
    const negIds = Array.from(zmap.entries()).sort((a, b) => a[1] - b[1]).slice(0, 2).map((x) => x[0]);
    const posTopics = posIds.map((tid) => topicById.get(tid)?.name).filter(Boolean);
    const negTopics = negIds.map((tid) => topicById.get(tid)?.name).filter(Boolean);

    let fiscalNote = null;
    const fiscalTid = posIds.concat(negIds).find((tid) => {
      const name = topicById.get(tid)?.name || "";
      return ["財政", "財政規律", "財政再建", "積極財政"].some((k) => name.includes(k));
    });
    if (fiscalTid) {
      const z = zmap.get(fiscalTid);
      if (typeof z === "number") {
        if (z < 0) fiscalNote = "※財政はマイナス側=積極財政寄り。";
        else if (z > 0) fiscalNote = "※財政はプラス側=規律重視寄り。";
      }
    }

    const dists = [];
    partyZ.forEach((other, pid) => {
      if (pid === party.entity_id) return;
      const d = distance(zmap, other);
      if (d === null) return;
      dists.push([d, pid]);
    });
    dists.sort((a, b) => a[0] - b[0]);
    const nearParty = dists.length ? partyById.get(dists[0][1])?.entity_name : null;
    const farParty = dists.length ? partyById.get(dists[dists.length - 1][1])?.entity_name : null;

    let quote = "";
    for (const tid of posIds.concat(negIds)) {
      const q = partyQuotes.get(party.entity_id)?.get(tid);
      if (q) {
        quote = q;
        break;
      }
    }

    const topicCount = partyScores.get(party.entity_id)?.size || 0;
    const summaryText = buildSummaryText({
      posTopics,
      negTopics,
      nearParty,
      farParty,
      quote,
      topicCount,
      fiscalNote,
    });

    return {
      entity_id: party.entity_id,
      entity_name: party.entity_name,
      scope: scopeNorm,
      summary_text: summaryText,
      positive_topics: posTopics,
      negative_topics: negTopics,
      near_party: nearParty,
      far_party: farParty,
      evidence_quote: quote || null,
    };
  });

  summaryCache.set(cacheKey, summaries);
  return summaries;
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

const RADAR_MIN_COLOR = "#ff7f6b";
const RADAR_MAX_COLOR = "#57d1a3";

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

function renderRadarSummary(radar) {
  const categories = Array.isArray(radar?.categories) ? radar.categories : [];
  const rows = categories
    .filter((c) => c && typeof c.key === "string")
    .map((c) => {
      const has = typeof c.median === "number" && typeof c.min === "number" && typeof c.max === "number";
      const min = has ? c.min : null;
      const max = has ? c.max : null;
      const med = has ? c.median : null;
      const left = has ? scoreToPercent(min) : 0;
      const right = has ? scoreToPercent(max) : 0;
      const dot = has ? scoreToPercent(med) : 0;
      const width = has ? Math.max(2, right - left) : 0;
      return `
        <div class="radar-row">
          <div class="radar-row__label">
            <div class="radar-row__title">${escapeAttr(c.label || c.key)}</div>
            <div class="radar-row__meta muted">対象: ${Number(c.count || 0)}件</div>
          </div>
          <div class="radar-row__track">
            <div class="radar-track">
              <div class="radar-track__zero"></div>
              ${has ? `<div class="radar-track__range" style="left:${left}%; width:${width}%;"></div>` : ""}
              ${has ? `<div class="radar-track__dot" style="left:${dot}%;"></div>` : ""}
              <div class="radar-track__tick radar-track__tick--left">-100</div>
              <div class="radar-track__tick radar-track__tick--right">+100</div>
            </div>
          </div>
          <div class="radar-row__values">
            ${has ? `<div class="radar-row__value">中央値: ${med}</div><div class="muted">範囲: ${min}〜${max}</div>` : `<div class="muted">データなし</div>`}
          </div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="radar-summary__head">
      <h4>大項目サマリ（中央値＋ブレ幅）</h4>
      <div class="muted">対象: ${Number(radar?.topic_included || 0)}/${Number(radar?.topic_total || 0)} トピック</div>
    </div>
    <div class="radar-rows">${rows}</div>
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
    <div id="partySummary" class="summary-card">
      <div class="summary-card__head">政党要旨（相対評価）</div>
      <div class="muted">要旨を読み込み中...</div>
    </div>
    ${axisInfo}
    <div style="margin: 10px 0;">
      <span class="${stanceColorClass(s.stance_label)}">${s.stance_label}</span>
      <span class="chip confidence">conf: ${s.confidence}</span>
      <span class="chip">score: ${s.stance_score}</span>
    </div>
    ${altSummary}
    <p>${s.rationale}</p>
    <div id="radarSummary" class="radar-summary">
      <div class="radar-summary__head">
        <h4>大項目サマリ（中央値＋ブレ幅）</h4>
        <div class="muted">スコアなしは除外</div>
      </div>
      <div class="muted">読み込み中...</div>
    </div>
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

function radarScoreToRadius(score, maxRadius) {
  const s = typeof score === "number" ? score : 0;
  return maxRadius * ((s + 100) / 200);
}

function renderRadarSvg(radar, color, opts = {}) {
  const categories = Array.isArray(radar?.categories) ? radar.categories : [];
  const n = categories.length || 1;
  const size = Number(opts.size || 200);
  const cx = size / 2;
  const cy = size / 2;
  const maxR = Math.max(48, Math.floor(size * 0.36));
  const showAxisLabels = Boolean(opts.showAxisLabels);
  const showScaleLabels = Boolean(opts.showScaleLabels);
  const showRangeBand = opts.showRangeBand !== false;
  const fontSize = Math.max(10, Math.min(12, Math.floor(size / 30)));

  const splitLabel = (text) => {
    const t = String(text || "").trim();
    if (!t) return [];
    if (t.includes("・") && t.length >= 8) {
      const parts = t.split("・").filter(Boolean);
      if (parts.length >= 2) return [parts[0], parts.slice(1).join("・")];
    }
    if (t.length >= 12) {
      const mid = Math.ceil(t.length / 2);
      return [t.slice(0, mid), t.slice(mid)];
    }
    return [t];
  };

  const angleFor = (i) => (-90 + (360 / n) * i) * (Math.PI / 180);
  const pointFor = (i, score) => {
    const a = angleFor(i);
    const r = radarScoreToRadius(score, maxR);
    return { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r };
  };

  const polygonPath = (pts) => {
    if (!pts.length) return "";
    const head = pts[0];
    const rest = pts.slice(1);
    return `M ${head.x.toFixed(1)} ${head.y.toFixed(1)} ${rest
      .map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ")} Z`;
  };

  const rings = [0.25, 0.5, 0.75, 1.0]
    .map((p) => `<circle cx="${cx}" cy="${cy}" r="${(maxR * p).toFixed(1)}" class="radar-svg__ring" />`)
    .join("");
  const zeroRing = `<circle cx="${cx}" cy="${cy}" r="${(maxR * 0.5).toFixed(1)}" class="radar-svg__zero-ring" />`;
  const axes = categories
    .map((_, i) => {
      const a = angleFor(i);
      const x2 = cx + Math.cos(a) * maxR;
      const y2 = cy + Math.sin(a) * maxR;
      return `<line x1="${cx}" y1="${cy}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" class="radar-svg__axis" />`;
    })
    .join("");

  const axisLabels = showAxisLabels
    ? categories
        .map((c, i) => {
          const a = angleFor(i);
          const labelR = maxR + Math.max(18, Math.floor(size * 0.08));
          let x = cx + Math.cos(a) * labelR;
          let y = cy + Math.sin(a) * labelR;
          const text = String(c?.label || c?.key || "");
          const dx = x - cx;
          const dy = y - cy;
          const anchor = Math.abs(dx) < 6 ? "middle" : dx > 0 ? "start" : "end";
          const baseline = "middle";
          const pad = Math.max(10, Math.floor(size * 0.04));
          if (anchor === "start") x = Math.min(x, size - pad);
          if (anchor === "end") x = Math.max(x, pad);
          y = Math.min(size - pad, Math.max(pad, y));

          const lines = splitLabel(text);
          const baseY = lines.length > 1 ? y - fontSize * 0.55 : y;
          const tspans = lines
            .map((line, idx) => {
              const dy = idx === 0 ? 0 : fontSize * 1.05;
              return `<tspan x="${x.toFixed(1)}" dy="${dy.toFixed(1)}">${escapeAttr(line)}</tspan>`;
            })
            .join("");
          return `<text x="${x.toFixed(1)}" y="${baseY.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="${baseline}" class="radar-svg__label" style="font-size:${fontSize}px;">${tspans}</text>`;
        })
        .join("")
    : "";

  const scaleLabels = showScaleLabels
    ? `
      <text x="${cx.toFixed(1)}" y="${(cy + 10).toFixed(1)}" text-anchor="middle" class="radar-svg__scale">-100</text>
      <text x="${cx.toFixed(1)}" y="${(cy - maxR - 10).toFixed(1)}" text-anchor="middle" class="radar-svg__scale">+100</text>
    `
    : "";

  const points = categories.map((c, i) => pointFor(i, typeof c.median === "number" ? c.median : 0));
  const polygonPoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  const minPoints = categories.map((c, i) => pointFor(i, typeof c.min === "number" ? c.min : 0));
  const maxPoints = categories.map((c, i) => pointFor(i, typeof c.max === "number" ? c.max : 0));
  const minPath = polygonPath(minPoints);
  const maxPath = polygonPath(maxPoints);
  const rangeBand = showRangeBand
    ? `<path d="${maxPath} ${minPath}" fill="${color}" fill-opacity="0.10" fill-rule="evenodd" class="radar-svg__band" />`
    : "";

  const maxStroke = showRangeBand
    ? `<path d="${maxPath}" fill="none" stroke="${RADAR_MAX_COLOR}" stroke-opacity="0.75" stroke-width="2.2" class="radar-svg__max" />`
    : "";
  const minStroke = showRangeBand
    ? `<path d="${minPath}" fill="none" stroke="${RADAR_MIN_COLOR}" stroke-opacity="0.75" stroke-width="2.2" class="radar-svg__min" />`
    : "";

  const rangeTicks = showRangeBand
    ? categories
        .map((c, i) => {
          const min = typeof c.min === "number" ? c.min : 0;
          const max = typeof c.max === "number" ? c.max : 0;
          const a = angleFor(i);
          const r1 = radarScoreToRadius(min, maxR);
          const r2 = radarScoreToRadius(max, maxR);
          const x1 = cx + Math.cos(a) * r1;
          const y1 = cy + Math.sin(a) * r1;
          const x2 = cx + Math.cos(a) * r2;
          const y2 = cy + Math.sin(a) * r2;
          return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" class="radar-svg__range-line" />`;
        })
        .join("")
    : "";

  const dots = categories
    .map((c, i) => {
      const p = points[i];
      const med = typeof c.median === "number" ? c.median : null;
      const min = typeof c.min === "number" ? c.min : null;
      const max = typeof c.max === "number" ? c.max : null;
      const title = `${c.label || c.key}: ${
        med === null ? "データなし" : `中央値 ${med} / 範囲 ${min}〜${max} / ${Number(c.count || 0)}件`
      }`;
      return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.4" class="radar-svg__dot" style="fill:${color};"><title>${escapeAttr(title)}</title></circle>`;
    })
    .join("");

  return `
    <svg class="radar-svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="radar" style="overflow: visible;">
      ${rings}
      ${zeroRing}
      ${axes}
      ${axisLabels}
      ${scaleLabels}
      ${rangeBand}
      ${maxStroke}
      ${minStroke}
      ${rangeTicks}
      <polygon points="${polygonPoints}" fill="${color}" fill-opacity="0.16" stroke="${color}" stroke-width="2.2" />
      ${dots}
      <circle cx="${cx}" cy="${cy}" r="2.2" class="radar-svg__center" />
    </svg>
  `;
}

function renderRadarLegend(partyColor) {
  return `
    <div class="radar-legend" role="note" aria-label="凡例">
      <div class="radar-legend__item"><span class="radar-legend__swatch" style="background:${escapeAttr(partyColor)};"></span>中央値（多角形）</div>
      <div class="radar-legend__item"><span class="radar-legend__line radar-legend__line--max"></span>最大（線）</div>
      <div class="radar-legend__item"><span class="radar-legend__line radar-legend__line--min"></span>最小（線）</div>
      <div class="radar-legend__item"><span class="radar-legend__band" style="background:${escapeAttr(partyColor)};"></span>範囲（塗り）</div>
    </div>
  `;
}

function renderRadarGallery(radars) {
  const items = Array.isArray(radars) ? radars : [];
  if (!items.length) return `<p class="muted">レーダーデータがありません。</p>`;

  const getActiveTopicsForMapping = () => {
    if (dataSource === "snapshot") {
      return (snapshotData?.topics || []).filter((t) => t?.is_active !== false);
    }
    return (topicsCache || []).filter((t) => t?.is_active !== false);
  };

  const partyList = items
    .map((r) => ({ id: r.entity_id, name: r.entity_name || r.entity_id }))
    .sort((a, b) => String(a.name).localeCompare(String(b.name), "ja"));
  const colorMap = new Map();
  partyList.forEach((p, idx) => colorMap.set(p.id, PARTY_COLORS[idx % PARTY_COLORS.length]));

  const categoryOrder = [
    { key: "economy", label: "経済・財政" },
    { key: "welfare", label: "社会保障・子育て" },
    { key: "security", label: "外交・安全保障" },
    { key: "rights", label: "人権・多様性" },
    { key: "digital", label: "デジタル・行政改革" },
    { key: "other", label: "その他" },
  ];

  const topicsForMapping = getActiveTopicsForMapping();
  const topicsByCategory = new Map(categoryOrder.map((c) => [c.key, []]));
  topicsForMapping.forEach((t) => {
    const cat = categorizeTopicForRadar(t.topic_id, t.name);
    const list = topicsByCategory.get(cat.key) || [];
    list.push({ topic_id: t.topic_id, name: t.name || t.topic_id });
    topicsByCategory.set(cat.key, list);
  });
  categoryOrder.forEach((c) => {
    const list = topicsByCategory.get(c.key) || [];
    list.sort((a, b) => String(a.name).localeCompare(String(b.name), "ja"));
    topicsByCategory.set(c.key, list);
  });

  const initialPartyId = partyList[0]?.id || "";
  const initialRadar = items.find((x) => x.entity_id === initialPartyId) || items[0];
  const initialColor = colorMap.get(initialRadar?.entity_id) || "#57d1a3";

  const main = `
    <div class="radar-main">
      <div class="radar-main__head">
        <div>
          <div class="rubric-meta">選択した政党のレーダー</div>
          <div class="muted">中心:-100（抑制/消極） / 外側:+100（推進/積極）</div>
        </div>
        <label class="radar-main__select">
          政党
          <select id="radarMainPartySelect">
            ${partyList
              .map(
                (p) =>
                  `<option value="${escapeAttr(p.id)}" ${
                    p.id === initialPartyId ? "selected" : ""
                  }>${escapeAttr(p.name)}</option>`
              )
              .join("")}
          </select>
        </label>
      </div>
      <div class="radar-main__chart" id="radarMainChart">
        ${renderRadarSvg(initialRadar, initialColor, { size: 420, showAxisLabels: true, showScaleLabels: true })}
      </div>
      <div class="radar-main__summary" id="radarMainSummary">
        <div class="muted">要旨を読み込み中...</div>
      </div>
      <div id="radarMainLegend">${renderRadarLegend(initialColor)}</div>
    </div>
  `;

  const intro = `
      <div class="radar-card radar-card--intro">
        <div class="radar-card__head">
          <div class="radar-card__title">レーダーチャートの見方</div>
          <div class="radar-card__meta muted">多角形＝各大項目の中央値</div>
        </div>
      <div class="radar-intro">
        <div class="radar-intro__text">
          <div class="muted">中心が「-100（より抑制/消極）」、外側が「+100（より推進/積極）」です。数値の詳細は各カードの「詳細」から確認できます。</div>
          <div class="radar-intro__axes">
            <div class="radar-intro__axes-title muted">大項目（軸）</div>
            <div class="radar-intro__axes-list">${
              categoryOrder
                .map((c) => {
                  const topics = topicsByCategory.get(c.key) || [];
                  const full = topics.map((t) => `${t.name} (${t.topic_id})`).join("\\n");
                  const previewItems = topics.slice(0, 6).map((t) => t.name);
                  const preview =
                    topics.length <= 6
                      ? previewItems.join(" / ")
                      : `${previewItems.join(" / ")} / …他${topics.length - 6}件`;
                  const tooltip = topics.length ? preview : "該当トピックなし";
                  return `<span class="chip radar-axis-chip" data-tooltip="${escapeAttr(tooltip)}" title="${escapeAttr(full || tooltip)}">${escapeAttr(c.label)}</span>`;
                })
                .join("")
            }</div>
          </div>
        </div>
      </div>
    </div>
  `;

  const cards = partyList
    .map((p) => {
      const radar = items.find((x) => x.entity_id === p.id);
      if (!radar) return "";
      const color = colorMap.get(p.id) || "#57d1a3";
      return `
        <div class="radar-card" data-entity="${escapeAttr(p.id)}">
          <div class="radar-card__head">
            <div class="radar-card__title">${escapeAttr(p.name)}</div>
            <div class="radar-card__meta muted">${Number(radar.topic_included || 0)}/${Number(radar.topic_total || 0)}</div>
          </div>
          <div class="radar-card__chart">
            ${renderRadarSvg(radar, color, { size: 200 })}
          </div>
          <div class="radar-card__actions">
            <button class="button-link radar-card__button" data-entity="${escapeAttr(p.id)}">詳細</button>
          </div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="radar-gallery">
      ${main}
      ${intro}
      ${cards}
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
    try {
      const summaries = await getPartySummaries(scopeNorm);
      const summary = summaries.find((s) => s.entity_id === entityId);
      const summaryEl = document.getElementById("partySummary");
      if (summaryEl) {
        summaryEl.innerHTML = summary
          ? `<div class="summary-card__head">政党要旨（相対評価）</div><div class="summary-card__text">${escapeAttr(summary.summary_text)}</div>`
          : `<div class="summary-card__head">政党要旨（相対評価）</div><div class="muted">要旨がありません。</div>`;
      }
    } catch {
      const summaryEl = document.getElementById("partySummary");
      if (summaryEl) {
        summaryEl.innerHTML = `<div class="summary-card__head">政党要旨（相対評価）</div><div class="muted">要旨の取得に失敗しました。</div>`;
      }
    }
    try {
      const radar = await getRadar(entityId, scopeNorm);
      const radarEl = document.getElementById("radarSummary");
      if (radarEl) radarEl.innerHTML = renderRadarSummary(radar);
    } catch (e) {
      const radarEl = document.getElementById("radarSummary");
      if (radarEl) radarEl.innerHTML = `<div class="muted">大項目サマリの取得に失敗しました: ${escapeAttr(e.message || String(e))}</div>`;
    }
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
    if (viewModeSelectEl && viewModeSelectEl.value === "radar") {
      topicIdEl.textContent = "radar";
      topicNameEl.textContent = "レーダーチャート";
      topicDescEl.textContent = "各政党の大項目サマリ（中央値）を多角形で表示します。";
      const radars = await getAllPartiesRadar("official");
      positionsEl.innerHTML = renderRadarGallery(radars);
      updateRubricLink(null);

      const updateRadarMain = (entityId) => {
        const radar = radars.find((r) => r.entity_id === entityId);
        if (!radar) return;
        const partyList = radars
          .map((r) => ({ id: r.entity_id, name: r.entity_name || r.entity_id }))
          .sort((a, b) => String(a.name).localeCompare(String(b.name), "ja"));
        const idx = partyList.findIndex((p) => p.id === entityId);
        const color = PARTY_COLORS[(idx >= 0 ? idx : 0) % PARTY_COLORS.length];
        const chartEl = document.getElementById("radarMainChart");
        if (chartEl) {
          chartEl.innerHTML = renderRadarSvg(radar, color, { size: 420, showAxisLabels: true, showScaleLabels: true });
        }
        const legendEl = document.getElementById("radarMainLegend");
        if (legendEl) legendEl.innerHTML = renderRadarLegend(color);
        const summaryEl = document.getElementById("radarMainSummary");
        if (summaryEl) {
          getPartySummaries("official")
            .then((summaries) => {
              const s = summaries.find((x) => x.entity_id === entityId);
              summaryEl.innerHTML = s
                ? `<div class="summary-card__text">${escapeAttr(s.summary_text)}</div>`
                : `<div class="muted">要旨がありません。</div>`;
            })
            .catch(() => {
              summaryEl.innerHTML = `<div class="muted">要旨の取得に失敗しました。</div>`;
            });
        }
      };

      const selectEl = document.getElementById("radarMainPartySelect");
      if (selectEl) {
        selectEl.addEventListener("change", () => {
          updateRadarMain(selectEl.value);
        });
        updateRadarMain(selectEl.value);
      }

      positionsEl.querySelectorAll(".radar-card[data-entity]").forEach((card) => {
        card.addEventListener("click", (e) => {
          const btn = e.target?.closest?.("button");
          if (btn) return;
          const id = card.dataset.entity;
          if (!id) return;
          if (selectEl) selectEl.value = id;
          updateRadarMain(id);
        });
      });

      positionsEl.querySelectorAll("button.radar-card__button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const entityId = btn.dataset.entity;
          const radar = radars.find((r) => r.entity_id === entityId);
          if (!radar) return;
          const partyList = radars
            .map((r) => ({ id: r.entity_id, name: r.entity_name || r.entity_id }))
            .sort((a, b) => String(a.name).localeCompare(String(b.name), "ja"));
          const idx = partyList.findIndex((p) => p.id === entityId);
          const color = PARTY_COLORS[(idx >= 0 ? idx : 0) % PARTY_COLORS.length];
          detailContentEl.innerHTML = `
            <p class="eyebrow">レーダーチャート</p>
            <h3>${escapeAttr(radar.entity_name || radar.entity_id)}</h3>
            <p class="muted">中心:-100（抑制/消極） / 外側:+100（推進/積極）</p>
            <div class="radar-detail__chart">
              ${renderRadarSvg(radar, color, { size: 320, showAxisLabels: true, showScaleLabels: true })}
            </div>
            ${renderRadarLegend(color)}
            ${renderRadarSummary(radar)}
          `;
          overlayEl.classList.remove("hidden");
        });
      });
      return;
    }
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
    <div id="radarSummary" class="radar-summary">
      <div class="radar-summary__head">
        <h4>大項目サマリ（中央値＋ブレ幅）</h4>
        <div class="muted">スコアなしは除外</div>
      </div>
      <div class="muted">読み込み中...</div>
    </div>
  `;
  overlayEl.classList.remove("hidden");
  getRadar(entityId, "official")
    .then((radar) => {
      const radarEl = document.getElementById("radarSummary");
      if (radarEl) radarEl.innerHTML = renderRadarSummary(radar);
    })
    .catch((e) => {
      const radarEl = document.getElementById("radarSummary");
      if (radarEl) radarEl.innerHTML = `<div class="muted">大項目サマリの取得に失敗しました: ${escapeAttr(e.message || String(e))}</div>`;
    });
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
    const mode = viewModeSelectEl.value;
    const isAxis = mode === "axis2";
    const isRadar = mode === "radar";
    if (axisTopicSelectorsEl) axisTopicSelectorsEl.classList.toggle("hidden", !isAxis);
    if (topicSelectEl) topicSelectEl.classList.toggle("hidden", isAxis || isRadar);
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
