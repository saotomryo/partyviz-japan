const DEFAULT_API_BASE = "http://localhost:8000";

const apiBaseEl = document.getElementById("apiBase");
const apiKeyEl = document.getElementById("apiKey");
const saveConfigBtn = document.getElementById("saveConfig");
const searchProviderEl = document.getElementById("searchProvider");
const rubricProviderEl = document.getElementById("rubricProvider");

const topicListEl = document.getElementById("topicList");
const refreshTopicsBtn = document.getElementById("refreshTopics");
const upsertTopicBtn = document.getElementById("upsertTopic");
const topicIdInput = document.getElementById("topicId");
const topicNameInput = document.getElementById("topicName");
const topicDescInput = document.getElementById("topicDesc");

const selTopicIdEl = document.getElementById("selTopicId");
const selTopicTitleEl = document.getElementById("selTopicTitle");
const selTopicDescEl = document.getElementById("selTopicDesc");

const genTopicNameEl = document.getElementById("genTopicName");
const genStepsCountEl = document.getElementById("genStepsCount");
const axisAHintEl = document.getElementById("axisAHint");
const axisBHintEl = document.getElementById("axisBHint");
const genDescEl = document.getElementById("genDesc");
const generateRubricBtn = document.getElementById("generateRubric");
const refreshRubricsBtn = document.getElementById("refreshRubrics");
const rubricListEl = document.getElementById("rubricList");

const scoreMaxPartiesEl = document.getElementById("scoreMaxParties");
const scoreMaxEvidenceEl = document.getElementById("scoreMaxEvidence");
const runScoringBtn = document.getElementById("runScoring");
const loadLatestScoresBtn = document.getElementById("loadLatestScores");
const scoreResultEl = document.getElementById("scoreResult");

const openaiSearchModelEl = document.getElementById("openaiSearchModel");
const geminiSearchModelEl = document.getElementById("geminiSearchModel");
const openaiRubricModelEl = document.getElementById("openaiRubricModel");
const geminiRubricModelEl = document.getElementById("geminiRubricModel");
const saveLLMConfigBtn = document.getElementById("saveLLMConfig");

const partyNameJaEl = document.getElementById("partyNameJa");
const partyHomeUrlEl = document.getElementById("partyHomeUrl");
const partyDomainsEl = document.getElementById("partyDomains");
const partyConfidenceEl = document.getElementById("partyConfidence");
const partyStatusEl = document.getElementById("partyStatus");
const partyEvidenceEl = document.getElementById("partyEvidence");
const createPartyBtn = document.getElementById("createParty");
const updatePartyBtn = document.getElementById("updateParty");
const clearPartyFormBtn = document.getElementById("clearPartyForm");
const refreshPartiesBtn = document.getElementById("refreshParties");
const partyListEl = document.getElementById("partyList");
const selectedPartyIdEl = document.getElementById("selectedPartyId");
const partyDiscoverQueryEl = document.getElementById("partyDiscoverQuery");
const partyDiscoverLimitEl = document.getElementById("partyDiscoverLimit");
const discoverPartiesBtn = document.getElementById("discoverParties");
const purgePartiesBtn = document.getElementById("purgeParties");
const purgeTopicsBtn = document.getElementById("purgeTopics");
const purgeAllBtn = document.getElementById("purgeAll");

let selectedTopic = null;
let selectedParty = null;

function getApiBase() {
  return (localStorage.getItem("partyviz_admin_api_base") || DEFAULT_API_BASE).trim();
}

function getApiKey() {
  return (localStorage.getItem("partyviz_admin_api_key") || "").trim();
}

function getSearchProvider() {
  return (localStorage.getItem("partyviz_admin_search_provider") || "auto").trim();
}

function getRubricProvider() {
  return (localStorage.getItem("partyviz_admin_rubric_provider") || "auto").trim();
}

function getModel(key, fallback) {
  return (localStorage.getItem(key) || fallback || "").trim();
}

function setConfig(apiBase, apiKey) {
  localStorage.setItem("partyviz_admin_api_base", apiBase);
  localStorage.setItem("partyviz_admin_api_key", apiKey);
}

function setConfigAdvanced({ searchProvider, rubricProvider, openaiSearchModel, geminiSearchModel, openaiRubricModel, geminiRubricModel }) {
  localStorage.setItem("partyviz_admin_search_provider", searchProvider);
  localStorage.setItem("partyviz_admin_rubric_provider", rubricProvider);
  localStorage.setItem("partyviz_admin_openai_search_model", openaiSearchModel);
  localStorage.setItem("partyviz_admin_gemini_search_model", geminiSearchModel);
  localStorage.setItem("partyviz_admin_openai_rubric_model", openaiRubricModel);
  localStorage.setItem("partyviz_admin_gemini_rubric_model", geminiRubricModel);
}

async function request(path, { method = "GET", body } = {}) {
  const apiBase = getApiBase();
  const apiKey = getApiKey();
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;
  const res = await fetch(`${apiBase}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

function pillClass(status) {
  if (status === "active") return "pill active";
  if (status === "archived") return "pill archived";
  return "pill draft";
}

function renderTopics(topics) {
  topicListEl.innerHTML = "";
  topics.forEach((t) => {
    const li = document.createElement("li");
    li.className = "topic-item";
    li.innerHTML = `
      <p class="eyebrow">${t.topic_id}</p>
      <p class="title">${t.name}</p>
      <p class="muted">${t.description || ""}</p>
    `;
    li.addEventListener("click", () => selectTopic(t));
    topicListEl.appendChild(li);
  });
}

function selectTopic(topic) {
  selectedTopic = topic;
  document.querySelectorAll(".topic-item").forEach((el) => el.classList.remove("active"));
  const match = Array.from(topicListEl.children).find((li) =>
    li.querySelector(".eyebrow")?.textContent === topic.topic_id
  );
  if (match) match.classList.add("active");

  selTopicIdEl.textContent = topic.topic_id;
  selTopicTitleEl.textContent = topic.name;
  selTopicDescEl.textContent = topic.description || "";

  topicIdInput.value = topic.topic_id;
  topicNameInput.value = topic.name;
  topicDescInput.value = topic.description || "";

  genTopicNameEl.value = topic.name;
  genDescEl.value = topic.description || "";

  loadRubrics();
}

async function loadTopics() {
  try {
    const topics = await request("/admin/topics");
    renderTopics(topics);
    if (topics.length && !selectedTopic) selectTopic(topics[0]);
  } catch (e) {
    topicListEl.innerHTML = `<li class="muted">取得失敗: ${e.message}</li>`;
  }
}

async function upsertTopic() {
  const topic_id = topicIdInput.value.trim();
  const name = topicNameInput.value.trim();
  const description = topicDescInput.value.trim() || null;
  if (!topic_id || !name) {
    if (!name) {
      alert("name は必須です");
      return;
    }
  }
  try {
    const data = topic_id
      ? await request(`/admin/topics/${encodeURIComponent(topic_id)}`, {
          method: "PUT",
          body: { topic_id, name, description },
        })
      : await request(`/admin/topics`, {
          method: "POST",
          body: { name, description },
        });
    selectedTopic = data;
    await loadTopics();
    selectTopic(data);
  } catch (e) {
    alert(`保存失敗: ${e.message}`);
  }
}

function rubricToEditableHtml(r) {
  const stepsRows = (r.steps || [])
    .map(
      (s, idx) => `
      <tr>
        <td><input data-field="score" data-idx="${idx}" type="number" min="-100" max="100" value="${s.score}"/></td>
        <td><input data-field="label" data-idx="${idx}" value="${escapeHtml(s.label || "")}"/></td>
        <td><textarea data-field="criteria" data-idx="${idx}">${escapeHtml(s.criteria || "")}</textarea></td>
      </tr>`
    )
    .join("");

  return `
    <div class="rubric-item" data-rubric-id="${r.rubric_id}">
      <header>
        <div>
          <h3>v${r.version} <span class="${pillClass(r.status)}">${r.status}</span></h3>
          <div class="rubric-meta">axis: ${escapeHtml(r.axis_a_label)} ⇄ ${escapeHtml(r.axis_b_label)}</div>
        </div>
        <div>
          <button class="button-link" data-action="activate">Activate</button>
          <button class="button-link" data-action="save">保存（PATCH）</button>
        </div>
      </header>
      <div class="divider"></div>
      <div class="row">
        <label>axis_a_label<input data-field="axis_a_label" value="${escapeHtml(r.axis_a_label)}"/></label>
        <label>axis_b_label<input data-field="axis_b_label" value="${escapeHtml(r.axis_b_label)}"/></label>
      </div>
      <div class="row" style="margin-top:10px;">
        <label>status
          <select data-field="status">
            ${["draft", "active", "archived"]
              .map((s) => `<option value="${s}" ${s === r.status ? "selected" : ""}>${s}</option>`)
              .join("")}
          </select>
        </label>
      </div>
      <div class="divider"></div>
      <table>
        <thead><tr><th>score</th><th>label</th><th>criteria</th></tr></thead>
        <tbody>${stepsRows}</tbody>
      </table>
      <div class="rubric-meta">id: ${r.rubric_id}</div>
    </div>
  `;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadRubrics() {
  if (!selectedTopic) return;
  rubricListEl.innerHTML = `<p class="muted">読み込み中...</p>`;
  try {
    const rubrics = await request(`/admin/topics/${encodeURIComponent(selectedTopic.topic_id)}/rubrics`);
    if (!rubrics.length) {
      rubricListEl.innerHTML = `<p class="muted">ルーブリックがありません。</p>`;
      return;
    }
    rubricListEl.innerHTML = rubrics.map(rubricToEditableHtml).join("");
    wireRubricActions();
  } catch (e) {
    rubricListEl.innerHTML = `<p class="muted">取得失敗: ${e.message}</p>`;
  }
}

function collectRubricPayload(container) {
  const axis_a_label = container.querySelector('input[data-field="axis_a_label"]').value.trim();
  const axis_b_label = container.querySelector('input[data-field="axis_b_label"]').value.trim();
  const status = container.querySelector('select[data-field="status"]').value;

  const steps = [];
  const rows = container.querySelectorAll("tbody tr");
  rows.forEach((row) => {
    const score = Number(row.querySelector('input[data-field="score"]').value);
    const label = row.querySelector('input[data-field="label"]').value;
    const criteria = row.querySelector('textarea[data-field="criteria"]').value;
    steps.push({ score, label, criteria });
  });
  return { axis_a_label, axis_b_label, status, steps };
}

function wireRubricActions() {
  rubricListEl.querySelectorAll(".rubric-item").forEach((el) => {
    const rubricId = el.dataset.rubricId;
    el.querySelector('button[data-action="save"]').addEventListener("click", async () => {
      try {
        const payload = collectRubricPayload(el);
        await request(`/admin/rubrics/${encodeURIComponent(rubricId)}`, { method: "PATCH", body: payload });
        await loadRubrics();
      } catch (e) {
        alert(`保存失敗: ${e.message}`);
      }
    });
    el.querySelector('button[data-action="activate"]').addEventListener("click", async () => {
      try {
        await request(`/admin/rubrics/${encodeURIComponent(rubricId)}/activate`, { method: "POST" });
        await loadRubrics();
      } catch (e) {
        alert(`有効化失敗: ${e.message}`);
      }
    });
  });
}

async function generateRubric() {
  if (!selectedTopic) {
    alert("先にトピックを選択してください");
    return;
  }
  const body = {
    topic_name: genTopicNameEl.value.trim() || selectedTopic.name,
    description: genDescEl.value.trim() || selectedTopic.description || null,
    provider: (rubricProviderEl.value || "auto").trim(),
    openai_model: (openaiRubricModelEl.value || "").trim() || null,
    gemini_model: (geminiRubricModelEl.value || "").trim() || null,
    axis_a_hint: axisAHintEl.value.trim() || null,
    axis_b_hint: axisBHintEl.value.trim() || null,
    steps_count: Number(genStepsCountEl.value || 5),
  };
  try {
    await request(`/admin/topics/${encodeURIComponent(selectedTopic.topic_id)}/rubrics/generate`, {
      method: "POST",
      body,
    });
    await loadRubrics();
  } catch (e) {
    alert(`生成失敗: ${e.message}`);
  }
}

function renderParties(parties) {
  if (!parties.length) {
    partyListEl.innerHTML = `<p class="muted">政党がありません。</p>`;
    return;
  }
  partyListEl.innerHTML = parties
    .map(
      (p) => `
      <div class="rubric-item" data-party-id="${p.party_id}">
        <header>
          <div>
            <h3>${escapeHtml(p.name_ja)} <span class="pill">${escapeHtml(p.status)}</span></h3>
            <div class="rubric-meta">${escapeHtml(p.official_home_url || "")}</div>
          </div>
        </header>
        <div class="rubric-meta">party_id: ${escapeHtml(p.party_id)}</div>
        <div class="rubric-meta">domains: ${escapeHtml((p.allowed_domains || []).join(", "))}</div>
        <div class="rubric-meta">confidence: ${escapeHtml(p.confidence)}</div>
      </div>
    `
    )
    .join("");

  partyListEl.querySelectorAll(".rubric-item[data-party-id]").forEach((el) => {
    el.addEventListener("click", async () => {
      const id = el.dataset.partyId;
      try {
        const party = await request(`/admin/parties/${encodeURIComponent(id)}`);
        selectParty(party);
      } catch (e) {
        alert(`取得失敗: ${e.message}`);
      }
    });
  });
}

function selectParty(party) {
  selectedParty = party;
  if (selectedPartyIdEl) selectedPartyIdEl.textContent = party.party_id;
  partyNameJaEl.value = party.name_ja || "";
  partyHomeUrlEl.value = party.official_home_url || "";
  partyDomainsEl.value = (party.allowed_domains || []).join(",");
  partyConfidenceEl.value = party.confidence ?? 0;
  partyStatusEl.value = party.status || "candidate";
  partyEvidenceEl.value = JSON.stringify(party.evidence || {}, null, 2);
}

function clearPartyForm() {
  selectedParty = null;
  if (selectedPartyIdEl) selectedPartyIdEl.textContent = "(none)";
  partyNameJaEl.value = "";
  partyHomeUrlEl.value = "";
  partyDomainsEl.value = "";
  partyConfidenceEl.value = 0.5;
  partyStatusEl.value = "candidate";
  partyEvidenceEl.value = "";
}

function renderScores(run) {
  if (!run || !run.scores || !run.scores.length) {
    scoreResultEl.innerHTML = `<p class="muted">スコアがありません。スコアリング実行後も出ない場合は、(1) DBマイグレーションが未適用（\`alembic upgrade head\`）(2) 政党の \`official_home_url\` 未登録、の可能性があります。</p>`;
    return;
  }
  const items = [...run.scores].sort((a, b) => (b.stance_score || 0) - (a.stance_score || 0));
  scoreResultEl.innerHTML = `
    <div class="rubric-item">
      <div class="rubric-meta">run_id: ${run.run_id}</div>
      <div class="rubric-meta">search: ${escapeHtml(run.search_provider || "")} / ${escapeHtml(run.search_model || "")}</div>
      <div class="rubric-meta">score: ${escapeHtml(run.score_provider || "")} / ${escapeHtml(run.score_model || "")}</div>
      <div class="rubric-meta">created_at: ${escapeHtml(run.created_at || "")}</div>
    </div>
    ${items
      .map(
        (s) => `
      <div class="rubric-item">
        <header>
          <div>
            <h3>${escapeHtml(s.name_ja)} <span class="pill">${escapeHtml(s.stance_label)}</span></h3>
            <div class="rubric-meta">score: ${escapeHtml(s.stance_score)} / conf: ${escapeHtml(s.confidence)}</div>
          </div>
        </header>
        <div class="rubric-meta">${escapeHtml(s.rationale || "")}</div>
        ${s.evidence_url ? `<div class="rubric-meta">evidence: <a class="link" target="_blank" href="${escapeHtml(s.evidence_url)}">${escapeHtml(s.evidence_url)}</a></div>` : ""}
        ${s.evidence_quote ? `<div class="rubric-meta">quote: ${escapeHtml(s.evidence_quote)}</div>` : ""}
      </div>
    `
      )
      .join("")}
  `;
}

async function runScoring() {
  if (!selectedTopic) {
    alert("先にトピックを選択してください");
    return;
  }
  scoreResultEl.innerHTML = `<p class="muted">実行中...</p>`;
  try {
    const body = {
      topic_text: selectedTopic.name,
      search_provider: (searchProviderEl.value || "auto").trim(),
      score_provider: (rubricProviderEl.value || "auto").trim(),
      search_openai_model: (openaiSearchModelEl.value || "").trim() || null,
      search_gemini_model: (geminiSearchModelEl.value || "").trim() || null,
      score_openai_model: (openaiRubricModelEl.value || "").trim() || null,
      score_gemini_model: (geminiRubricModelEl.value || "").trim() || null,
      max_parties: Number(scoreMaxPartiesEl.value || 10),
      max_evidence_per_party: Number(scoreMaxEvidenceEl.value || 2),
    };
    const run = await request(`/admin/topics/${encodeURIComponent(selectedTopic.topic_id)}/scores/run`, {
      method: "POST",
      body,
    });
    renderScores(run);
  } catch (e) {
    scoreResultEl.innerHTML = `<p class="muted">失敗: ${e.message}</p>`;
  }
}

async function loadLatestScores() {
  if (!selectedTopic) return;
  scoreResultEl.innerHTML = `<p class="muted">読み込み中...</p>`;
  try {
    const run = await request(`/admin/topics/${encodeURIComponent(selectedTopic.topic_id)}/scores/latest`);
    renderScores(run);
  } catch (e) {
    scoreResultEl.innerHTML = `<p class="muted">取得失敗: ${e.message}</p>`;
  }
}

async function loadParties() {
  partyListEl.innerHTML = `<p class="muted">読み込み中...</p>`;
  try {
    const parties = await request("/admin/parties");
    renderParties(parties);
  } catch (e) {
    partyListEl.innerHTML = `<p class="muted">取得失敗: ${e.message}</p>`;
  }
}

async function updateParty() {
  if (!selectedParty) {
    alert("先に一覧から政党を選択してください");
    return;
  }
  const party_id = selectedParty.party_id;
  const name_ja = partyNameJaEl.value.trim() || null;
  const official_home_url = partyHomeUrlEl.value.trim() || null;
  const allowed_domains = (partyDomainsEl.value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const confidence = Number(partyConfidenceEl.value || 0);
  const status = partyStatusEl.value;

  let evidence = null;
  const evidenceText = (partyEvidenceEl.value || "").trim();
  if (evidenceText) {
    try {
      evidence = JSON.parse(evidenceText);
    } catch {
      alert("evidence は JSON 形式で入力してください");
      return;
    }
  } else {
    evidence = {};
  }

  try {
    const updated = await request(`/admin/parties/${encodeURIComponent(party_id)}`, {
      method: "PATCH",
      body: { name_ja, official_home_url, allowed_domains, confidence, status, evidence },
    });
    selectParty(updated);
    await loadParties();
  } catch (e) {
    alert(`更新失敗: ${e.message}`);
  }
}

async function createParty() {
  const name_ja = partyNameJaEl.value.trim();
  if (!name_ja) {
    alert("name_ja は必須です");
    return;
  }
  const official_home_url = partyHomeUrlEl.value.trim() || null;
  const allowed_domains = (partyDomainsEl.value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const confidence = Number(partyConfidenceEl.value || 0);
  const status = partyStatusEl.value;

  let evidence = {};
  const evidenceText = (partyEvidenceEl.value || "").trim();
  if (evidenceText) {
    try {
      evidence = JSON.parse(evidenceText);
    } catch {
      alert("evidence は JSON 形式で入力してください");
      return;
    }
  }

  try {
    await request("/admin/parties", {
      method: "POST",
      body: { name_ja, official_home_url, allowed_domains, confidence, status, evidence },
    });
    await loadParties();
  } catch (e) {
    alert(`登録失敗: ${e.message}`);
  }
}

async function discoverParties() {
  const query =
    (partyDiscoverQueryEl.value || "").trim() ||
    "日本の国政政党（国会に議席のある政党）と主要な新党・政治団体の公式サイト一覧 チームみらい";
  const limit = Number(partyDiscoverLimitEl.value || 50);
  try {
    const resp = await request("/admin/parties/discover", {
      method: "POST",
      body: {
        query,
        limit,
        provider: (searchProviderEl.value || "auto").trim(),
        openai_model: (openaiSearchModelEl.value || "").trim() || null,
        gemini_model: (geminiSearchModelEl.value || "").trim() || null,
        dry_run: false,
      },
    });
    await loadParties();
    alert(`自動取得: found=${resp.found} created=${resp.created} updated=${resp.updated} skipped=${resp.skipped}`);
  } catch (e) {
    alert(`自動取得失敗: ${e.message}`);
  }
}

async function purge(targets) {
  const confirmText = window.prompt("削除を実行するには DELETE と入力してください");
  if (confirmText !== "DELETE") {
    alert("キャンセルしました");
    return;
  }
  try {
    const resp = await request("/admin/dev/purge", {
      method: "POST",
      body: { targets, confirm: "DELETE" },
    });
    await loadTopics();
    await loadRubrics();
    await loadParties();
    alert(`削除しました: ${JSON.stringify(resp.deleted)}`);
  } catch (e) {
    alert(`削除失敗: ${e.message}`);
  }
}

saveConfigBtn.addEventListener("click", () => {
  const base = apiBaseEl.value.trim() || DEFAULT_API_BASE;
  const key = apiKeyEl.value.trim();
  setConfig(base, key);
  alert("API設定を保存しました");
});

saveLLMConfigBtn.addEventListener("click", () => {
  setConfigAdvanced({
    searchProvider: (searchProviderEl.value || "auto").trim(),
    rubricProvider: (rubricProviderEl.value || "auto").trim(),
    openaiSearchModel: (openaiSearchModelEl.value || "").trim(),
    geminiSearchModel: (geminiSearchModelEl.value || "").trim(),
    openaiRubricModel: (openaiRubricModelEl.value || "").trim(),
    geminiRubricModel: (geminiRubricModelEl.value || "").trim(),
  });
  alert("LLM設定を保存しました");
});

refreshTopicsBtn.addEventListener("click", loadTopics);
upsertTopicBtn.addEventListener("click", upsertTopic);
generateRubricBtn.addEventListener("click", generateRubric);
refreshRubricsBtn.addEventListener("click", loadRubrics);
refreshPartiesBtn.addEventListener("click", loadParties);
createPartyBtn.addEventListener("click", createParty);
updatePartyBtn.addEventListener("click", updateParty);
clearPartyFormBtn.addEventListener("click", clearPartyForm);
discoverPartiesBtn.addEventListener("click", discoverParties);
purgePartiesBtn.addEventListener("click", () => purge(["parties", "events"]));
purgeTopicsBtn.addEventListener("click", () => purge(["topics"]));
purgeAllBtn.addEventListener("click", () => purge(["all"]));
runScoringBtn.addEventListener("click", runScoring);
loadLatestScoresBtn.addEventListener("click", loadLatestScores);

// init
apiBaseEl.value = getApiBase();
apiKeyEl.value = getApiKey();
searchProviderEl.value = getSearchProvider();
rubricProviderEl.value = getRubricProvider();
openaiSearchModelEl.value = getModel("partyviz_admin_openai_search_model", "gpt-4o-mini-search-preview");
geminiSearchModelEl.value = getModel("partyviz_admin_gemini_search_model", "models/gemini-2.5-flash");
openaiRubricModelEl.value = getModel("partyviz_admin_openai_rubric_model", "gpt-5-mini");
geminiRubricModelEl.value = getModel("partyviz_admin_gemini_rubric_model", "models/gemini-2.5-flash");
clearPartyForm();
loadTopics();
loadParties();

partyDiscoverQueryEl.value =
  partyDiscoverQueryEl.value ||
  "日本の国政政党（国会に議席のある政党）と主要な新党・政治団体の公式サイト一覧 チームみらい";
