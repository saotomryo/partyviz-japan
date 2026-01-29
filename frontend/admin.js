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
const topicSubkeywordsInput = document.getElementById("topicSubkeywords");
const topicActiveEl = document.getElementById("topicActive");

const selTopicIdEl = document.getElementById("selTopicId");
const selTopicTitleEl = document.getElementById("selTopicTitle");
const selTopicDescEl = document.getElementById("selTopicDesc");

const genTopicNameEl = document.getElementById("genTopicName");
const genStepsCountEl = document.getElementById("genStepsCount");
const axisAHintEl = document.getElementById("axisAHint");
const axisBHintEl = document.getElementById("axisBHint");
const genDescEl = document.getElementById("genDesc");
const genReverseAxisEl = document.getElementById("genReverseAxis");
const generateRubricBtn = document.getElementById("generateRubric");
const refreshRubricsBtn = document.getElementById("refreshRubrics");
const rubricListEl = document.getElementById("rubricList");

const scoreMaxEvidenceEl = document.getElementById("scoreMaxEvidence");
const scoreIncludeExternalEl = document.getElementById("scoreIncludeExternal");
const scoreIndexOnlyEl = document.getElementById("scoreIndexOnly");
const runScoringBtn = document.getElementById("runScoring");
const loadLatestScoresBtn = document.getElementById("loadLatestScores");
const scoreResultEl = document.getElementById("scoreResult");
const scorePartyCountEl = document.getElementById("scorePartyCount");
const downloadSnapshotBtn = document.getElementById("downloadSnapshot");
const summaryScopeEl = document.getElementById("summaryScope");
const runSummaryBtn = document.getElementById("runSummary");
const summaryResultEl = document.getElementById("summaryResult");

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
const partyPolicyUrlsEl = document.getElementById("partyPolicyUrls");
const partyEvidenceEl = document.getElementById("partyEvidence");
const createPartyBtn = document.getElementById("createParty");
const updatePartyBtn = document.getElementById("updateParty");
const clearPartyFormBtn = document.getElementById("clearPartyForm");
const refreshPartiesBtn = document.getElementById("refreshParties");
const crawlPolicySourcesBtn = document.getElementById("crawlPolicySources");
const savePolicySourcesBtn = document.getElementById("savePolicySources");
const partyListEl = document.getElementById("partyList");
const selectedPartyIdEl = document.getElementById("selectedPartyId");
const partyDiscoverQueryEl = document.getElementById("partyDiscoverQuery");
const partyDiscoverLimitEl = document.getElementById("partyDiscoverLimit");
const discoverPartiesBtn = document.getElementById("discoverParties");
const purgePartiesBtn = document.getElementById("purgeParties");
const purgeTopicsBtn = document.getElementById("purgeTopics");
const purgePolicyScoresBtn = document.getElementById("purgePolicyScores");
const purgeAllBtn = document.getElementById("purgeAll");

// Deep Research prompt generator (policy page)
const drMaxItemsPerTopicEl = document.getElementById("drMaxItemsPerTopic");
const generateDeepResearchPromptBtn = document.getElementById("generateDeepResearchPrompt");
const copyDeepResearchPromptBtn = document.getElementById("copyDeepResearchPrompt");
const deepResearchPromptOutputEl = document.getElementById("deepResearchPromptOutput");
const researchPackInputEl = document.getElementById("researchPackInput");
const importResearchPackBtn = document.getElementById("importResearchPack");
const importResearchPackResultEl = document.getElementById("importResearchPackResult");

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

function _normalizeMultilineUrls(text) {
  return (text || "")
    .split("\n")
    .map((s) => String(s || "").trim())
    .filter(Boolean)
    .map((s) => s.replace(/^["']|["']$/g, "")); // strip copy/paste quotes
}

function _buildDeepResearchPromptAllTopics({ party, topics, allowedDomains, policyBaseUrls, officialHomeUrl, maxItemsPerTopic }) {
  const partyName = party?.name_ja || "";
  const partyId = party?.party_id || "";
  const domainsCsv = (allowedDomains || []).join(", ");
  const baseUrlsText = (policyBaseUrls || []).map((u) => `- ${u}`).join("\n");
  const nowIso = new Date().toISOString();
  const topicLines = (topics || [])
    .map((t) => {
      const id = t?.topic_id || "";
      const name = t?.name || "";
      const desc = t?.description || "";
      return `- ${id}: ${name}${desc ? ` / ${desc}` : ""}`.trim();
    })
    .filter(Boolean)
    .join("\n");
  const maxPerTopic = Math.max(1, Math.min(5, Math.trunc(Number(maxItemsPerTopic || 2))));

  return `あなたは日本の政党の公式一次情報から、指定トピックに関する記述を抽出するリサーチャーです。
目的: 「公式ページおよび policy_base_urls 配下」だけを使って、全トピック（active）について関連する根拠箇所（引用）を収集し、指定のJSON（リサーチパック）で出力してください。

対象政党:
- party_name_ja: ${partyName}
- party_id: ${partyId}
- official_home_url: ${officialHomeUrl || ""}
- allowed_domains: ${domainsCsv}

使用してよいソース（厳守）:
- official_home_url のドメイン（allowed_domains内）にあるページ
- 次の policy_base_urls（配下を含む）
${baseUrlsText || "- （未設定）"}

禁止:
- 上記以外の外部サイト、SNS、まとめ、ニュース記事の参照
- 推測で埋めること（見つからない場合は見つからないと明示）

トピック一覧（active）:
${topicLines || "- （トピックがありません）"}

作業指示:
1) policy_base_urls から開始し、各トピックに関連する箇所（本文またはPDFの該当箇所）を探してください。
2) 根拠は必ず URL とセットで、短い引用（quote: 1〜3文程度）を抜き出してください。
3) quote が意味する主張を1文で claim にまとめてください。
4) 古い選挙の公約など「現時点の最新ではない」と判断できる場合は deprecated=true とし、deprecated_reason を付けてください。
5) 各トピックあたり最大 ${maxPerTopic} 件（重要順）に絞ってください。該当が無いトピックは無理に作らず、notes に topic_id を列挙してください。

出力（重要: JSONのみ、余計な説明なし）:
次のスキーマの JSON を出力してください（リサーチパック）。
{
  "format": "partyviz_research_pack",
  "version": 1,
  "generated_at": "${nowIso}",
  "generator": "chatgpt_deep_research",
  "notes": "見つからなかった topic_id: ...",
  "parties": [
    {
      "party_id": "${partyId}",
      "party_name_ja": "${partyName}",
      "items": [
        {
          "source_url": "https://...",
          "source_title": "任意",
          "fetched_at": "${nowIso}",
          "source_type": "official_html",
          "topic_ids": ["<topic_id>"],
          "quote": "…",
          "claim": "…",
          "deprecated": false,
          "deprecated_reason": "任意"
        }
      ]
    }
  ]
}

備考:
- items は「topic_ids ごと」に最大 ${maxPerTopic} 件程度に絞ってください。
- URL は実在するものだけを出してください。
- fetched_at はあなたが確認した時刻（${nowIso} 付近）でOKです。`;
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

async function downloadSnapshot() {
  const apiBase = getApiBase();
  const apiKey = getApiKey();
  const headers = {};
  if (apiKey) headers["X-API-Key"] = apiKey;

  const res = await fetch(`${apiBase}/admin/snapshot`, { headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "snapshot.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function runPartySummaries() {
  if (!summaryResultEl) return;
  const scope = (summaryScopeEl?.value || "official").trim();
  summaryResultEl.innerHTML = `<p class="muted">要旨を生成中...</p>`;
  try {
    const data = await request(`/summaries/parties?scope=${encodeURIComponent(scope)}`);
    if (!Array.isArray(data) || data.length === 0) {
      summaryResultEl.innerHTML = `<p class="muted">要旨データがありません。</p>`;
      return;
    }
    const rows = data
      .map(
        (item) => `
        <div class="score-card">
          <div>
            <h4 class="score-card__title">${escapeHtml(item.entity_name || item.entity_id)}</h4>
            <p class="muted">${escapeHtml(item.summary_text || "")}</p>
          </div>
          <div class="score-card__meta">scope: ${escapeHtml(item.scope || "")}</div>
        </div>
      `
      )
      .join("");
    summaryResultEl.innerHTML = rows;
  } catch (e) {
    summaryResultEl.innerHTML = `<p class="muted">要旨生成に失敗: ${e.message}</p>`;
  }
}

function pillClass(status) {
  if (status === "active") return "pill active";
  if (status === "archived") return "pill archived";
  return "pill draft";
}

function renderTopics(topics) {
  if (!topicListEl) return;
  topicListEl.innerHTML = "";
  topics.forEach((t) => {
    const li = document.createElement("li");
    li.className = "topic-item";
    li.innerHTML = `
      <p class="eyebrow">${t.topic_id}</p>
      <p class="title">${t.name} ${t.is_active === false ? '<span class="pill">inactive</span>' : ""}</p>
      <p class="muted">${t.description || ""}</p>
    `;
    li.addEventListener("click", () => selectTopic(t));
    topicListEl.appendChild(li);
  });
}

function selectTopic(topic) {
  selectedTopic = topic;
  if (topicListEl) {
    document.querySelectorAll(".topic-item").forEach((el) => el.classList.remove("active"));
    const match = Array.from(topicListEl.children).find((li) =>
      li.querySelector(".eyebrow")?.textContent === topic.topic_id
    );
    if (match) match.classList.add("active");
  }

  if (selTopicIdEl) selTopicIdEl.textContent = topic.topic_id;
  if (selTopicTitleEl) selTopicTitleEl.textContent = topic.name;
  if (selTopicDescEl) selTopicDescEl.textContent = topic.description || "";

  if (topicIdInput) topicIdInput.value = topic.topic_id;
  if (topicNameInput) topicNameInput.value = topic.name;
  if (topicDescInput) topicDescInput.value = topic.description || "";
  const kws = topic.search_subkeywords || [];
  if (topicSubkeywordsInput) topicSubkeywordsInput.value = kws.length ? kws.join(", ") : "（生成結果が空です）";
  if (topicActiveEl) topicActiveEl.value = String(topic.is_active !== false);

  if (genTopicNameEl) genTopicNameEl.value = topic.name;
  if (genDescEl) genDescEl.value = topic.description || "";

  loadRubrics();
}

async function loadTopics() {
  if (!topicListEl) return;
  try {
    const topics = await request("/admin/topics");
    renderTopics(topics);
    if (topics.length && !selectedTopic) selectTopic(topics[0]);
  } catch (e) {
    topicListEl.innerHTML = `<li class="muted">取得失敗: ${e.message}</li>`;
  }
}

async function upsertTopic() {
  if (!topicIdInput || !topicNameInput || !topicDescInput) return;
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
          body: { topic_id, name, description, is_active: topicActiveEl ? topicActiveEl.value === "true" : true },
        })
      : await request(`/admin/topics`, {
          method: "POST",
          body: { name, description, is_active: topicActiveEl ? topicActiveEl.value === "true" : true },
        });
    selectedTopic = data;
    await loadTopics();
    selectTopic(data);
  } catch (e) {
    alert(`保存失敗: ${e.message}`);
  }
}

function flipRubricPayload(payload) {
  const axis_a_label = String(payload.axis_b_label || "").trim();
  const axis_b_label = String(payload.axis_a_label || "").trim();
  const status = payload.status;
  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  const flippedSteps = steps
    .map((s) => ({
      score: -Number(s.score),
      label: s.label,
      criteria: s.criteria,
    }))
    .sort((a, b) => a.score - b.score);
  return { axis_a_label, axis_b_label, status, steps: flippedSteps };
}

function stepsToRowsHtml(steps) {
  return (steps || [])
    .map(
      (s, idx) => `
      <tr>
        <td><input data-field="score" data-idx="${idx}" type="number" min="-100" max="100" value="${escapeHtml(s.score)}"/></td>
        <td><input data-field="label" data-idx="${idx}" value="${escapeHtml(s.label || "")}"/></td>
        <td><textarea data-field="criteria" data-idx="${idx}">${escapeHtml(s.criteria || "")}</textarea></td>
      </tr>`
    )
    .join("");
}

function rubricToEditableHtml(r) {
  const stepsRows = stepsToRowsHtml(r.steps || []);

  return `
    <div class="rubric-item" data-rubric-id="${r.rubric_id}">
      <header>
        <div>
          <h3>v${r.version} <span class="${pillClass(r.status)}">${r.status}</span></h3>
          <div class="rubric-meta">axis: ${escapeHtml(r.axis_a_label)} ⇄ ${escapeHtml(r.axis_b_label)}</div>
        </div>
        <div>
          <button class="button-link" data-action="flipSave">軸反転して保存</button>
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
  if (!rubricListEl) return;
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
  if (!rubricListEl) return;
  rubricListEl.querySelectorAll(".rubric-item").forEach((el) => {
    const rubricId = el.dataset.rubricId;
    el.querySelector('button[data-action="flipSave"]')?.addEventListener("click", async () => {
      if (!confirm("軸を反転して保存します（-100⇄+100）。よろしいですか？")) return;
      try {
        const payload = collectRubricPayload(el);
        const flipped = flipRubricPayload(payload);
        await request(`/admin/rubrics/${encodeURIComponent(rubricId)}`, { method: "PATCH", body: flipped });
        await loadRubrics();
      } catch (e) {
        alert(`反転保存失敗: ${e.message}`);
      }
    });
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
  if (!genTopicNameEl || !genStepsCountEl || !genDescEl) return;
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
    const res = await request(`/admin/topics/${encodeURIComponent(selectedTopic.topic_id)}/rubrics/generate`, {
      method: "POST",
      body,
    });
    if (genReverseAxisEl?.checked && res?.rubric?.rubric_id) {
      const flipped = flipRubricPayload({
        axis_a_label: res.rubric.axis_a_label,
        axis_b_label: res.rubric.axis_b_label,
        status: res.rubric.status,
        steps: res.rubric.steps,
      });
      await request(`/admin/rubrics/${encodeURIComponent(res.rubric.rubric_id)}`, { method: "PATCH", body: flipped });
    }
    await loadRubrics();
  } catch (e) {
    alert(`生成失敗: ${e.message}`);
  }
}

function renderParties(parties) {
  if (!partyListEl) return;
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
  if (partyNameJaEl) partyNameJaEl.value = party.name_ja || "";
  if (partyHomeUrlEl) partyHomeUrlEl.value = party.official_home_url || "";
  if (partyDomainsEl) partyDomainsEl.value = (party.allowed_domains || []).join(",");
  if (partyConfidenceEl) partyConfidenceEl.value = party.confidence ?? 0;
  if (partyStatusEl) partyStatusEl.value = party.status || "candidate";
  if (partyEvidenceEl) partyEvidenceEl.value = JSON.stringify(party.evidence || {}, null, 2);
  if (partyPolicyUrlsEl) partyPolicyUrlsEl.value = "";
  if (party && party.party_id) {
    request(`/admin/parties/${encodeURIComponent(party.party_id)}/policy-sources`)
      .then((res) => {
        const urls = (res.sources || []).map((s) => s.base_url).filter(Boolean);
        if (partyPolicyUrlsEl) partyPolicyUrlsEl.value = urls.join("\n");
      })
      .catch(() => {
        if (partyPolicyUrlsEl) partyPolicyUrlsEl.value = "";
      });
  }
}

function clearPartyForm() {
  selectedParty = null;
  if (selectedPartyIdEl) selectedPartyIdEl.textContent = "(none)";
  if (partyNameJaEl) partyNameJaEl.value = "";
  if (partyHomeUrlEl) partyHomeUrlEl.value = "";
  if (partyDomainsEl) partyDomainsEl.value = "";
  if (partyConfidenceEl) partyConfidenceEl.value = 0.5;
  if (partyStatusEl) partyStatusEl.value = "candidate";
  if (partyEvidenceEl) partyEvidenceEl.value = "";
  if (partyPolicyUrlsEl) partyPolicyUrlsEl.value = "";
}

function renderScores(run) {
  if (!scoreResultEl) return;
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
  if (!scoreResultEl) return;
  if (!scoreMaxEvidenceEl) return;
  if (!selectedTopic) {
    alert("先にトピックを選択してください");
    return;
  }
  scoreResultEl.innerHTML = `<p class="muted">実行中...</p>`;
  try {
    const MAX_EVIDENCE_PER_PARTY = 5;
    let maxEvidence = Number(scoreMaxEvidenceEl.value || 2);
    if (!Number.isFinite(maxEvidence)) maxEvidence = 2;
    const clampedEvidence = Math.max(1, Math.min(MAX_EVIDENCE_PER_PARTY, Math.trunc(maxEvidence)));
    if (clampedEvidence !== maxEvidence) {
      scoreMaxEvidenceEl.value = String(clampedEvidence);
      alert(`max_evidence_per_party は 1〜${MAX_EVIDENCE_PER_PARTY} の範囲です（${clampedEvidence} に丸めました）`);
    }
    const body = {
      topic_text: selectedTopic.name,
      search_provider: (searchProviderEl?.value || "auto").trim(),
      score_provider: (rubricProviderEl?.value || "auto").trim(),
      search_openai_model: (openaiSearchModelEl?.value || "").trim() || null,
      search_gemini_model: (geminiSearchModelEl?.value || "").trim() || null,
      score_openai_model: (openaiRubricModelEl?.value || "").trim() || null,
      score_gemini_model: (geminiRubricModelEl?.value || "").trim() || null,
      max_evidence_per_party: clampedEvidence,
      include_external: Boolean(scoreIncludeExternalEl && scoreIncludeExternalEl.checked),
      index_only: Boolean(scoreIndexOnlyEl && scoreIndexOnlyEl.checked),
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
  if (!scoreResultEl) return;
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
  if (!partyListEl) return;
  partyListEl.innerHTML = `<p class="muted">読み込み中...</p>`;
  try {
    const parties = await request("/admin/parties");
    renderParties(parties);
    if (scorePartyCountEl) {
      const activeCount = (parties || []).filter((p) => (p.status || "") !== "rejected").length;
      scorePartyCountEl.textContent = String(activeCount);
    }
  } catch (e) {
    partyListEl.innerHTML = `<p class="muted">取得失敗: ${e.message}</p>`;
    if (scorePartyCountEl) {
      scorePartyCountEl.textContent = "-";
    }
  }
}

async function updateParty() {
  if (!partyNameJaEl || !partyHomeUrlEl || !partyDomainsEl || !partyConfidenceEl || !partyStatusEl || !partyEvidenceEl)
    return;
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
    if (partyPolicyUrlsEl) {
      const base_urls = (partyPolicyUrlsEl.value || "")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      await request(`/admin/parties/${encodeURIComponent(party_id)}/policy-sources`, {
        method: "PUT",
        body: { base_urls },
      });
    }
    selectParty(updated);
    await loadParties();
  } catch (e) {
    alert(`更新失敗: ${e.message}`);
  }
}

async function createParty() {
  if (!partyNameJaEl || !partyHomeUrlEl || !partyDomainsEl || !partyConfidenceEl || !partyStatusEl || !partyEvidenceEl)
    return;
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
    const created = await request("/admin/parties", {
      method: "POST",
      body: { name_ja, official_home_url, allowed_domains, confidence, status, evidence },
    });
    if (partyPolicyUrlsEl) {
      const base_urls = (partyPolicyUrlsEl.value || "")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      if (base_urls.length) {
        await request(`/admin/parties/${encodeURIComponent(created.party_id)}/policy-sources`, {
          method: "PUT",
          body: { base_urls },
        });
      }
    }
    selectParty(created);
    await loadParties();
  } catch (e) {
    alert(`登録失敗: ${e.message}`);
  }
}

async function discoverParties() {
  if (!partyDiscoverQueryEl || !partyDiscoverLimitEl) return;
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
        provider: (searchProviderEl?.value || "auto").trim(),
        openai_model: (openaiSearchModelEl?.value || "").trim() || null,
        gemini_model: (geminiSearchModelEl?.value || "").trim() || null,
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

saveConfigBtn?.addEventListener("click", () => {
  const base = apiBaseEl.value.trim() || DEFAULT_API_BASE;
  const key = apiKeyEl.value.trim();
  setConfig(base, key);
  alert("API設定を保存しました");
});

saveLLMConfigBtn?.addEventListener("click", () => {
  setConfigAdvanced({
    searchProvider: (searchProviderEl?.value || "auto").trim(),
    rubricProvider: (rubricProviderEl?.value || "auto").trim(),
    openaiSearchModel: (openaiSearchModelEl?.value || "").trim(),
    geminiSearchModel: (geminiSearchModelEl?.value || "").trim(),
    openaiRubricModel: (openaiRubricModelEl?.value || "").trim(),
    geminiRubricModel: (geminiRubricModelEl?.value || "").trim(),
  });
  alert("LLM設定を保存しました");
});

refreshTopicsBtn?.addEventListener("click", loadTopics);
upsertTopicBtn?.addEventListener("click", upsertTopic);
generateRubricBtn?.addEventListener("click", generateRubric);
refreshRubricsBtn?.addEventListener("click", loadRubrics);
refreshPartiesBtn?.addEventListener("click", loadParties);
createPartyBtn?.addEventListener("click", createParty);
updatePartyBtn?.addEventListener("click", updateParty);
clearPartyFormBtn?.addEventListener("click", clearPartyForm);
discoverPartiesBtn?.addEventListener("click", discoverParties);
savePolicySourcesBtn?.addEventListener("click", async () => {
  if (!selectedParty) {
    alert("先に一覧から政党を選択してください");
    return;
  }
  if (!partyPolicyUrlsEl) {
    alert("policy_base_urls の入力欄がありません");
    return;
  }
  const base_urls = (partyPolicyUrlsEl.value || "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  try {
    const resp = await request(`/admin/parties/${encodeURIComponent(selectedParty.party_id)}/policy-sources`, {
      method: "PUT",
      body: { base_urls },
    });
    const urls = (resp.sources || []).map((s) => s.base_url).filter(Boolean);
    partyPolicyUrlsEl.value = urls.join("\n");
    alert(`policy_base_urls を保存しました（${urls.length}件）`);
  } catch (e) {
    alert(`保存失敗: ${e.message}`);
  }
});
crawlPolicySourcesBtn?.addEventListener("click", async () => {
  if (!selectedParty) {
    alert("先に一覧から政党を選択してください");
    return;
  }
  try {
    const resp = await request(`/admin/parties/${encodeURIComponent(selectedParty.party_id)}/policy-sources/crawl`, {
      method: "POST",
    });
    alert(
      `クロール完了: html=${resp.stats?.fetched_html ?? 0}, pdf=${resp.stats?.fetched_pdf ?? 0}, skipped=${resp.stats?.skipped ?? 0}, errors=${resp.stats?.errors ?? 0}`
    );
  } catch (e) {
    alert(`クロール失敗: ${e.message}`);
  }
});
purgePartiesBtn?.addEventListener("click", () => purge(["parties", "events"]));
purgeTopicsBtn?.addEventListener("click", () => purge(["topics"]));
purgePolicyScoresBtn?.addEventListener("click", () => purge(["policy", "scores"]));
purgeAllBtn?.addEventListener("click", () => purge(["all"]));
runScoringBtn?.addEventListener("click", runScoring);
loadLatestScoresBtn?.addEventListener("click", loadLatestScores);
downloadSnapshotBtn?.addEventListener("click", () =>
  downloadSnapshot().catch((e) => alert(`ダウンロード失敗: ${e.message}`))
);
runSummaryBtn?.addEventListener("click", () => runPartySummaries());

generateDeepResearchPromptBtn?.addEventListener("click", async () => {
  if (!deepResearchPromptOutputEl) return;
  if (!selectedParty) {
    alert("先に政党を選択してください");
    return;
  }
  try {
    const topics = await request("/admin/topics");
    const activeTopics = (topics || []).filter((t) => t && t.is_active !== false);
    const officialHomeUrl = (selectedParty.official_home_url || "").trim();
    const policyBaseUrls = partyPolicyUrlsEl ? _normalizeMultilineUrls(partyPolicyUrlsEl.value) : [];
    const allowedDomains = Array.isArray(selectedParty.allowed_domains) ? selectedParty.allowed_domains : [];
    const maxItemsPerTopic = Number(drMaxItemsPerTopicEl?.value || 2);
    const prompt = _buildDeepResearchPromptAllTopics({
      party: selectedParty,
      topics: activeTopics,
      allowedDomains,
      policyBaseUrls,
      officialHomeUrl,
      maxItemsPerTopic,
    });
    deepResearchPromptOutputEl.value = prompt;
  } catch (e) {
    deepResearchPromptOutputEl.value = `生成失敗: ${e.message}`;
  }
});

copyDeepResearchPromptBtn?.addEventListener("click", async () => {
  if (!deepResearchPromptOutputEl) return;
  const text = deepResearchPromptOutputEl.value || "";
  if (!text.trim()) {
    alert("プロンプトが空です");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    alert("コピーしました");
  } catch {
    // Fallback
    deepResearchPromptOutputEl.focus();
    deepResearchPromptOutputEl.select();
    document.execCommand("copy");
    alert("コピーしました");
  }
});

importResearchPackBtn?.addEventListener("click", async () => {
  if (!researchPackInputEl) return;
  if (!importResearchPackResultEl) return;
  const text = (researchPackInputEl.value || "").trim();
  if (!text) {
    alert("JSONを貼り付けてください");
    return;
  }
  function parseJsonFromText(raw) {
    const s = String(raw || "").trim();
    if (!s) throw new Error("empty input");
    const cleaned = s.replace(/^```(?:json)?\s*/i, "").replace(/```$/m, "").trim();
    function extractObjectBlock(t) {
      const start = t.indexOf("{");
      const end = t.lastIndexOf("}");
      if (start >= 0 && end > start) return t.slice(start, end + 1);
      return "";
    }
    function repairJsonLikelyFromLLM(t) {
      // LLM outputs sometimes include raw newlines inside JSON string literals.
      // JSON requires newlines to be escaped as \\n inside strings.
      let out = "";
      let inStr = false;
      let esc = false;
      for (let i = 0; i < t.length; i++) {
        const ch = t[i];
        if (!inStr) {
          if (ch === '"') inStr = true;
          out += ch;
          continue;
        }
        // in string
        if (esc) {
          out += ch;
          esc = false;
          continue;
        }
        if (ch === "\\") {
          out += ch;
          esc = true;
          continue;
        }
        if (ch === '"') {
          out += ch;
          inStr = false;
          continue;
        }
        if (ch === "\n") {
          out += "\\n";
          continue;
        }
        if (ch === "\r") {
          out += "\\r";
          continue;
        }
        if (ch === "\t") {
          out += "\\t";
          continue;
        }
        out += ch;
      }
      return out;
    }

    const attemptStrings = [];
    attemptStrings.push(cleaned);
    const block = extractObjectBlock(cleaned);
    if (block) attemptStrings.push(block);
    // Try repaired variants (for raw newlines in strings, etc.)
    attemptStrings.push(repairJsonLikelyFromLLM(block || cleaned));

    let lastErr = null;
    for (const candidate of attemptStrings) {
      if (!candidate) continue;
      try {
        return JSON.parse(candidate);
      } catch (e) {
        lastErr = e;
      }
    }
    if (lastErr) throw lastErr;
    throw new Error("no JSON object found");
  }
  let payload;
  try {
    payload = parseJsonFromText(text);
  } catch (e) {
    alert(`JSONのパースに失敗しました: ${e.message}`);
    return;
  }
  importResearchPackResultEl.innerHTML = `<p class="muted">取り込み中...</p>`;
  try {
    const resp = await request("/admin/research/import", { method: "POST", body: payload });
    const stats = resp?.stats || {};
    const errors = Array.isArray(resp?.errors) ? resp.errors : [];
    const errHtml = errors.length
      ? `<details style="margin-top:8px;"><summary class="small">errors (${errors.length})</summary><pre class="small" style="white-space:pre-wrap; margin:8px 0 0;">${escapeHtml(JSON.stringify(errors, null, 2))}</pre></details>`
      : "";
    importResearchPackResultEl.innerHTML = `
      <div class="rubric-item">
        <div class="rubric-meta">parties: ${escapeHtml(stats.parties ?? "")}</div>
        <div class="rubric-meta">items_total: ${escapeHtml(stats.items_total ?? "")}</div>
        <div class="rubric-meta">documents_upserted: ${escapeHtml(stats.documents_upserted ?? "")}</div>
        <div class="rubric-meta">documents_unchanged: ${escapeHtml(stats.documents_unchanged ?? "")}</div>
        <div class="rubric-meta">chunks_written: ${escapeHtml(stats.chunks_written ?? "")}</div>
        <div class="rubric-meta">skipped: ${escapeHtml(stats.skipped ?? "")}</div>
      </div>
      ${errHtml}
    `;
    alert("取り込みが完了しました");
  } catch (e) {
    importResearchPackResultEl.innerHTML = `<p class="muted">取り込み失敗: ${escapeHtml(e.message)}</p>`;
  }
});

// init
if (apiBaseEl) apiBaseEl.value = getApiBase();
if (apiKeyEl) apiKeyEl.value = getApiKey();
if (searchProviderEl) searchProviderEl.value = getSearchProvider();
if (rubricProviderEl) rubricProviderEl.value = getRubricProvider();
if (openaiSearchModelEl) openaiSearchModelEl.value = getModel("partyviz_admin_openai_search_model", "gpt-4o-mini-search-preview");
if (geminiSearchModelEl) geminiSearchModelEl.value = getModel("partyviz_admin_gemini_search_model", "models/gemini-2.5-flash");
if (openaiRubricModelEl) openaiRubricModelEl.value = getModel("partyviz_admin_openai_rubric_model", "gpt-5-mini");
if (geminiRubricModelEl) geminiRubricModelEl.value = getModel("partyviz_admin_gemini_rubric_model", "models/gemini-2.5-flash");
clearPartyForm();
if (topicListEl) loadTopics();
if (partyListEl) loadParties();

if (partyDiscoverQueryEl) {
  partyDiscoverQueryEl.value =
    partyDiscoverQueryEl.value ||
    "日本の国政政党（国会に議席のある政党）と主要な新党・政治団体の公式サイト一覧 チームみらい";
}
