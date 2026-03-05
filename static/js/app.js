/* ═══════════════════════════════════════════════
   SKILL TREE BROWSER
   ═══════════════════════════════════════════════ */

let treeData = null;
let questionTypeMeta = {};
let pipelineStatus = {};
let currentSkillId = null;
let genCounter = 0;
let currentCourse = "APHG";

function cq(url) {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}course=${currentCourse}`;
}

async function loadCourses() {
  try {
    const res = await fetch("/api/courses");
    const courses = await res.json();
    const select = document.getElementById("course-select");
    select.innerHTML = "";
    for (const [cid, info] of Object.entries(courses)) {
      const opt = document.createElement("option");
      opt.value = cid;
      opt.textContent = `${info.name} (${info.skills} skills)`;
      if (cid === currentCourse) opt.selected = true;
      select.appendChild(opt);
    }
  } catch (e) { /* silent */ }
}

function switchCourse(courseId) {
  currentCourse = courseId;
  currentSkillId = null;
  document.getElementById("detail-empty").classList.remove("hidden");
  document.getElementById("detail-content").classList.add("hidden");
  initTree();
}

async function initTree() {
  const [treeRes, typesRes, statusRes] = await Promise.all([
    fetch(cq("/skill-tree")),
    fetch("/question-types"),
    fetch(cq("/pipeline-status")),
  ]);
  treeData = await treeRes.json();
  questionTypeMeta = await typesRes.json();
  pipelineStatus = await statusRes.json();
  renderTree();
}

async function refreshPipelineStatus() {
  try {
    const res = await fetch(cq("/pipeline-status"));
    pipelineStatus = await res.json();
    renderTree();
  } catch (e) { /* silent */ }
}

function _statusDotClass(st) {
  if (st === "complete") return "status-complete";
  if (st === "content_only") return "status-content";
  if (st === "manual_content") return "status-manual-content";
  return "status-none";
}

function _statusItemClass(st) {
  if (st === "none") return " status-none-item";
  if (st === "manual_content") return " status-manual-item";
  return "";
}

function renderTree() {
  const list = document.getElementById("tree-list");
  const loading = document.getElementById("tree-loading");
  loading.classList.add("hidden");
  list.innerHTML = "";

  for (const unit of treeData.units) {
    const section = document.createElement("div");
    section.className = "unit-section";
    section.id = `unit-${unit.id}`;

    let redCount = 0, orangeCount = 0, blueCount = 0, greenCount = 0;
    for (const skill of unit.skills) {
      const st = pipelineStatus[skill.id] || "none";
      if (st === "complete") greenCount++;
      else if (st === "content_only") blueCount++;
      else if (st === "manual_content") orangeCount++;
      else redCount++;
    }

    const unitNum = unit.id.replace("U", "");
    const header = document.createElement("div");
    header.className = "unit-header" + (redCount > 0 ? " has-missing" : "");
    header.innerHTML = `
      <span class="unit-chevron">&#9654;</span>
      <span class="unit-label">${unit.title}</span>
      <div class="unit-status-counts">
        ${redCount    ? `<span class="count-dot cnt-red" title="No content">${redCount}</span>` : ""}
        ${orangeCount ? `<span class="count-dot cnt-orange" title="Manual content (flagged)">${orangeCount}</span>` : ""}
        ${blueCount   ? `<span class="count-dot cnt-blue" title="Has content, needs questions">${blueCount}</span>` : ""}
        ${greenCount  ? `<span class="count-dot cnt-green" title="Complete">${greenCount}</span>` : ""}
      </div>
      <button class="unit-map-btn" onclick="event.stopPropagation(); mapUnitTranscripts(${unitNum}, this)" title="Map video transcripts to skills for this unit">Map Transcripts</button>
      <button class="unit-map-btn" onclick="event.stopPropagation(); buildUnitBanks(${unitNum}, this)" title="Build question banks for all skills with content in this unit">Build Unit</button>
      <span class="unit-count">${unit.skills.length}</span>
    `;
    header.addEventListener("click", () => section.classList.toggle("open"));

    const mapLog = document.createElement("div");
    mapLog.className = "unit-map-log";
    mapLog.id = `unit-map-log-${unitNum}`;

    const skillsDiv = document.createElement("div");
    skillsDiv.className = "unit-skills";

    for (const skill of unit.skills) {
      const st = pipelineStatus[skill.id] || "none";
      const item = document.createElement("div");
      item.className = "skill-item" + _statusItemClass(st);
      item.dataset.skillId = skill.id;
      item.innerHTML = `<span class="skill-id-tag">${skill.id}</span>${skill.text}<span class="status-dot ${_statusDotClass(st)}"></span>`;
      item.addEventListener("click", () => selectSkill(skill.id, skill.text));
      skillsDiv.appendChild(item);
    }

    section.appendChild(header);
    section.appendChild(mapLog);
    section.appendChild(skillsDiv);
    list.appendChild(section);
  }
}


/* ── Bulk actions ──────────────────────────────────────────────────── */

function _setGlobalButtons(disabled) {
  document.getElementById("map-all-btn").disabled = disabled;
  document.getElementById("build-all-btn").disabled = disabled;
  document.querySelectorAll(".tree-header-actions .btn").forEach(b => b.disabled = disabled);
  const spinner = document.getElementById("global-spinner");
  if (disabled) spinner.classList.remove("hidden");
  else spinner.classList.add("hidden");
}

function mapUnitTranscripts(unitNum, btn) {
  btn.disabled = true;
  const log = document.getElementById(`unit-map-log-${unitNum}`);
  log.innerHTML = "";
  log.style.display = "block";

  const section = btn.closest(".unit-section");
  if (section && !section.classList.contains("open")) {
    section.classList.add("open");
  }

  return new Promise((resolve) => {
    const es = new EventSource(cq(`/unit/${unitNum}/map-transcripts`));

    es.onmessage = function(event) {
      const data = JSON.parse(event.data);
      const line = document.createElement("div");
      line.className = "log-line" + (data.phase === "error" ? " log-error" : data.phase === "done" ? " log-done" : "");
      line.textContent = data.message;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;

      if (data.phase === "done" || data.phase === "error") {
        es.close();
        btn.disabled = false;
        refreshPipelineStatus();
        resolve(data.phase === "done");
      }
    };

    es.onerror = function() {
      es.close();
      btn.disabled = false;
      const line = document.createElement("div");
      line.className = "log-line log-error";
      line.textContent = "Connection lost.";
      log.appendChild(line);
      refreshPipelineStatus();
      resolve(false);
    };
  });
}

async function mapAllUnits() {
  const progress = document.getElementById("build-all-progress");
  _setGlobalButtons(true);

  const unitNums = treeData.units.map(u => parseInt(u.id.replace("U", "")));
  progress.textContent = `Mapping transcripts for ${unitNums.length} units...`;

  for (let i = 0; i < unitNums.length; i++) {
    const unitNum = unitNums[i];
    progress.textContent = `Mapping Unit ${unitNum} (${i + 1}/${unitNums.length})...`;

    const btn = document.querySelector(`#unit-U${unitNum} .unit-map-btn`);
    if (btn) {
      await mapUnitTranscripts(unitNum, btn);
    }
  }

  _setGlobalButtons(false);
  progress.textContent = `Done. All ${unitNums.length} units mapped. Check orange flags for skills that need manual content.`;
  refreshPipelineStatus();
}

const QUESTIONS_PER_DOK = 10;
const BATCH_SIZE = 5;

async function _postJSON(url, body) {
  const res = await fetch(cq(url), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function _buildBankForSkill(sid, onProgress) {
  const log = (msg) => onProgress && onProgress(sid, msg);
  let totalSaved = 0;
  const BATCH_RETRIES = 2;

  try {
    // Load existing bank to check what's already done
    let existingBank = {};
    try {
      const bankRes = await fetch(cq(`/skill/${sid}/question-bank`));
      const bankJson = await bankRes.json();
      existingBank = bankJson.bank || {};
    } catch (e) { /* no existing bank */ }

    // Use existing types from the bank if available; only detect if none exist
    let typeKeys = Object.keys(existingBank).filter(k => existingBank[k] && typeof existingBank[k] === "object");
    if (typeKeys.length === 0) {
      log("Detecting question types...");
      const detectRes = await _postJSON(`/skill/${sid}/detect-types`, {});
      if (detectRes.error) throw new Error(detectRes.error);
      const types = detectRes.relevant_question_types;
      typeKeys = typeof types === "object" && !Array.isArray(types) ? Object.keys(types) : (types || []);
      if (typeKeys.length === 0) throw new Error("No question types detected");
      log(`Detected ${typeKeys.length} types: ${typeKeys.join(", ")}`);
    } else {
      log(`Using ${typeKeys.length} existing types: ${typeKeys.join(", ")}`);
    }

    // Start with ALL existing bank data (preserves types not in typeKeys)
    const bankData = {};
    for (const [k, v] of Object.entries(existingBank)) {
      if (v && typeof v === "object") bankData[k] = { concepts: v.concepts || [], questions: [...(v.questions || [])] };
    }

    for (const qtype of typeKeys) {
      if (!bankData[qtype]) bankData[qtype] = { concepts: [], questions: [] };
      const existingQuestions = bankData[qtype].questions;

      for (const dok of ["2", "3"]) {
        const dokLabel = `DOK ${dok}`;
        const existingForDok = existingQuestions.filter(q => q.dok === dok);
        const needed = QUESTIONS_PER_DOK - existingForDok.length;

        if (needed <= 0) {
          log(`${qtype} ${dokLabel}: already has ${existingForDok.length}/${QUESTIONS_PER_DOK} — skipping`);
          continue;
        }

        log(`${qtype} ${dokLabel}: need ${needed} more (have ${existingForDok.length})...`);

        let newQuestions = [];
        let excludeSummaries = existingForDok.map(q => JSON.stringify(q.question_data).slice(0, 80));
        const numBatches = Math.ceil(needed / BATCH_SIZE);

        for (let b = 0; b < numBatches; b++) {
          const remaining = needed - newQuestions.length;
          const count = Math.min(BATCH_SIZE, remaining);
          if (count <= 0) break;

          let batchOk = false;
          for (let retry = 0; retry <= BATCH_RETRIES; retry++) {
            if (retry > 0) log(`${qtype} ${dokLabel}: retrying batch ${b + 1} (attempt ${retry + 1})...`);
            else log(`${qtype} ${dokLabel}: generating batch ${b + 1}/${numBatches}...`);

            try {
              const genRes = await _postJSON(`/skill/${sid}/generate-batch`, {
                question_type: qtype,
                dok_level: dok,
                count,
                exclude_summaries: excludeSummaries,
              });
              if (genRes.error) throw new Error(genRes.error);

              newQuestions = newQuestions.concat(genRes.questions || []);
              excludeSummaries = excludeSummaries.concat(genRes.summaries || []);
              batchOk = true;
              break;
            } catch (e) {
              log(`${qtype} ${dokLabel} batch ${b + 1} error: ${e.message}`);
            }
          }

          if (!batchOk) log(`${qtype} ${dokLabel}: batch ${b + 1} failed after ${BATCH_RETRIES + 1} attempts`);
        }

        const baseIdx = existingForDok.length;
        const entries = newQuestions.map((q, i) => ({
          id: `${sid}-${qtype.slice(0, 4)}-d${dok}-${baseIdx + i}`,
          dok,
          question_data: q,
          valid: true,
          validation_reason: "",
          met: false,
        }));

        bankData[qtype].questions = bankData[qtype].questions.concat(entries);
        totalSaved += entries.length;
        log(`${qtype} ${dokLabel}: ${entries.length} new + ${existingForDok.length} existing = ${entries.length + existingForDok.length} total`);
      }
    }

    log("Saving bank...");
    const saveRes = await _postJSON(`/skill/${sid}/save-bank`, { bank_data: bankData });
    if (saveRes.error) throw new Error(saveRes.error);

    log(`Done. ${totalSaved} new questions saved.`);
    return { sid, ok: true, saved: totalSaved };
  } catch (e) {
    log(`FAILED: ${e.message}`);
    return { sid, ok: false, saved: totalSaved, message: e.message };
  }
}

async function buildAllBanks() {
  const progress = document.getElementById("build-all-progress");
  _setGlobalButtons(true);

  const skillsToBuild = [];
  for (const [sid, st] of Object.entries(pipelineStatus)) {
    if (st === "content_only" || st === "manual_content") skillsToBuild.push(sid);
  }

  if (skillsToBuild.length === 0) {
    progress.textContent = "Nothing to build. All skills with content already have question banks.";
    _setGlobalButtons(false);
    return;
  }

  let completed = 0;
  let failed = 0;
  let totalSaved = 0;

  progress.innerHTML = `<strong>Building banks: 0/${skillsToBuild.length}</strong> — starting...`;

  function onProgress(sid, msg) {
    progress.innerHTML = `<strong>Building banks: ${completed}/${skillsToBuild.length}</strong> — ${sid}: ${msg} (${failed} failed, ${totalSaved} Qs saved)`;
  }

  for (const sid of skillsToBuild) {
    const skillItem = document.querySelector(`.skill-item[data-skill-id="${sid}"]`);
    if (skillItem) skillItem.style.outline = "2px solid var(--primary)";

    const result = await _buildBankForSkill(sid, onProgress);

    if (skillItem) skillItem.style.outline = "";

    if (result.ok) {
      completed++;
      totalSaved += result.saved;
    } else {
      failed++;
    }

    progress.innerHTML = `<strong>Building banks: ${completed}/${skillsToBuild.length}</strong> — ${result.sid} ${result.ok ? "done" : "FAILED"} (${failed} failed, ${totalSaved} Qs saved)`;
  }

  _setGlobalButtons(false);
  progress.innerHTML = `<strong>Done.</strong> ${completed} banks built, ${failed} failed, ${totalSaved} total questions saved.`;
  refreshPipelineStatus();
}

async function fillGaps() {
  const progress = document.getElementById("build-all-progress");
  _setGlobalButtons(true);

  progress.innerHTML = "<strong>Scanning for incomplete banks...</strong>";

  // Find all "complete" skills and check which have gaps
  const skillsWithGaps = [];
  for (const [sid, st] of Object.entries(pipelineStatus)) {
    if (st !== "complete") continue;
    try {
      const bankRes = await fetch(cq(`/skill/${sid}/question-bank`));
      const bankJson = await bankRes.json();
      const bank = bankJson.bank || {};
      let hasGap = false;
      for (const [qtype, typeData] of Object.entries(bank)) {
        if (!typeData || typeof typeData !== "object") continue;
        const questions = typeData.questions || [];
        const dok2 = questions.filter(q => q.dok === "2").length;
        const dok3 = questions.filter(q => q.dok === "3").length;
        if (dok2 < QUESTIONS_PER_DOK || dok3 < QUESTIONS_PER_DOK) {
          hasGap = true;
          break;
        }
      }
      if (hasGap) skillsWithGaps.push(sid);
    } catch (e) { /* skip */ }
  }

  if (skillsWithGaps.length === 0) {
    progress.innerHTML = "<strong>No gaps found.</strong> All banks are complete.";
    _setGlobalButtons(false);
    return;
  }

  progress.innerHTML = `<strong>Filling gaps for ${skillsWithGaps.length} skills...</strong>`;

  let completed = 0;
  let failed = 0;
  let totalSaved = 0;

  for (const sid of skillsWithGaps) {
    progress.innerHTML = `<strong>Fill Gaps: ${completed}/${skillsWithGaps.length}</strong> — ${sid}... (${totalSaved} Qs added)`;

    const result = await _buildBankForSkill(sid, (s, msg) => {
      progress.innerHTML = `<strong>Fill Gaps: ${completed}/${skillsWithGaps.length}</strong> — ${s}: ${msg} (${totalSaved} Qs added)`;
    });

    if (result.ok) {
      completed++;
      totalSaved += result.saved;
    } else {
      failed++;
    }
  }

  _setGlobalButtons(false);
  progress.innerHTML = `<strong>Fill Gaps done.</strong> ${completed} skills patched, ${failed} failed, ${totalSaved} questions added.`;
  refreshPipelineStatus();
}

function exportCourse() {
  window.open(cq("/api/export"), "_blank");
}

function regenQuestionsByType(qtype, triggerBtn) {
  const progress = document.getElementById("build-all-progress");
  _setGlobalButtons(true);

  const label = qtype.replace(/_/g, " ");
  progress.innerHTML = `<strong>Regenerating ${label}...</strong> Connecting...`;

  const es = new EventSource(`/regenerate-questions-by-type?qtype=${encodeURIComponent(qtype)}&course=${currentCourse}`);

  es.onmessage = function(event) {
    const data = JSON.parse(event.data);
    progress.innerHTML = `<strong>Regen ${label}:</strong> ${data.message}`;

    if (data.phase === "done" || data.phase === "error") {
      es.close();
      _setGlobalButtons(false);
      refreshPipelineStatus();
      if (currentSkillId) loadQuestionBank();
    }
  };

  es.onerror = function() {
    es.close();
    _setGlobalButtons(false);
    progress.innerHTML = `<strong>Regen ${label}:</strong> Connection lost.`;
    refreshPipelineStatus();
  };
}

async function buildUnitBanks(unitNum, btn) {
  const unit = treeData.units.find(u => u.id === `U${unitNum}`);
  if (!unit) return;

  btn.disabled = true;
  const log = document.getElementById(`unit-map-log-${unitNum}`);
  log.innerHTML = "";
  log.style.display = "block";

  const section = btn.closest(".unit-section");
  if (section && !section.classList.contains("open")) {
    section.classList.add("open");
  }

  const skillsToBuild = unit.skills
    .map(s => s.id)
    .filter(sid => {
      const st = pipelineStatus[sid];
      return st === "content_only" || st === "manual_content" || st === "complete";
    });

  if (skillsToBuild.length === 0) {
    appendLog(log, "No skills need building in this unit.", "done");
    btn.disabled = false;
    return;
  }

  appendLog(log, `Building banks for ${skillsToBuild.length} skills concurrently...`);

  let completed = 0;
  let failed = 0;
  let totalSaved = 0;

  function onProgress(sid, msg) {
    updateOrAppendLog(log, `build-${sid}`, `${sid}: ${msg}`);
    log.scrollTop = log.scrollHeight;
  }

  const promises = skillsToBuild.map(async (sid) => {
    const skillItem = document.querySelector(`.skill-item[data-skill-id="${sid}"]`);
    if (skillItem) skillItem.style.outline = "2px solid var(--primary)";

    const result = await _buildBankForSkill(sid, onProgress);

    if (skillItem) skillItem.style.outline = "";

    if (result.ok) {
      completed++;
      totalSaved += result.saved;
      updateOrAppendLog(log, `build-${sid}`, `${sid}: done (${result.saved} Qs)`, "ok");
    } else {
      failed++;
      updateOrAppendLog(log, `build-${sid}`, `${sid}: FAILED — ${result.message || "unknown"}`, "error");
    }
    appendLog(log, `Progress: ${completed + failed}/${skillsToBuild.length} (${completed} done, ${failed} failed, ${totalSaved} Qs)`);
    log.scrollTop = log.scrollHeight;
  });

  await Promise.all(promises);

  appendLog(log, `Unit ${unitNum} complete. ${completed} banks built, ${failed} failed, ${totalSaved} total questions.`, "done");
  btn.disabled = false;
  refreshPipelineStatus();
}

async function selectSkill(id, text) {
  currentSkillId = id;

  document.querySelectorAll(".skill-item.active").forEach(el => el.classList.remove("active"));
  const activeItem = document.querySelector(`.skill-item[data-skill-id="${id}"]`);
  if (activeItem) activeItem.classList.add("active");

  document.getElementById("detail-empty").classList.add("hidden");
  document.getElementById("detail-content").classList.remove("hidden");
  document.getElementById("detail-skill-text").textContent = text;
  document.getElementById("detail-skill-id").textContent = id;

  document.getElementById("lc-status").textContent = "";
  document.getElementById("sources-list").innerHTML = "";
  document.getElementById("types-chips").innerHTML = "";
  document.getElementById("gen-output").innerHTML = "";
  document.getElementById("qbank-progress-log").innerHTML = "";
  document.getElementById("qbank-coverage").innerHTML = "";
  document.getElementById("qbank-questions").innerHTML = "";
  currentBankData = null;
  populateTypeDropdown([]);

  try {
    const res = await fetch(cq(`/skill/${id}`));
    const data = await res.json();

    document.getElementById("lc-textarea").value = data.learning_content || "";
    renderSources(data.sources || []);

    const rqt = data.relevant_question_types;
    if (rqt && (Array.isArray(rqt) ? rqt.length > 0 : Object.keys(rqt).length > 0)) {
      renderTypeChips(rqt);
      populateTypeDropdown(rqt);
    }

    loadQuestionBank();
  } catch (e) {
    document.getElementById("lc-textarea").value = "";
    document.getElementById("sources-list").innerHTML = "";
  }
}

function renderSources(sources) {
  const container = document.getElementById("sources-list");
  const section = document.getElementById("sources-section");
  container.innerHTML = "";
  if (!sources || sources.length === 0) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  for (const src of sources) {
    const card = document.createElement("div");
    card.className = "source-card";
    card.innerHTML = `
      <div class="source-topic">Topic ${src.topic} — ${src.topic_name}</div>
      <div class="source-section">Section ${src.section}: "${src.section_label}" <span class="source-time">(${src.start_timestamp}–${src.end_timestamp})</span></div>
      <div class="source-summary">${src.summary}</div>
      <div class="source-links">
        <a href="${src.youtube_url}" target="_blank" class="source-link">Watch on YouTube</a>
        ${src.clip ? `<span class="source-clip">Clip: ${src.clip}</span>` : ""}
      </div>
    `;
    container.appendChild(card);
  }
}

async function saveLearningContent() {
  if (!currentSkillId) return;
  const content = document.getElementById("lc-textarea").value;
  const status = document.getElementById("lc-status");
  const btn = document.getElementById("lc-save-btn");

  btn.disabled = true;
  status.textContent = "Saving...";
  status.style.color = "var(--text-muted)";

  try {
    await fetch(cq(`/skill/${currentSkillId}/learning-content`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ learning_content: content }),
    });
    status.textContent = "Saved";
    status.style.color = "var(--success)";

    refreshPipelineStatus();
  } catch (e) {
    status.textContent = "Error saving";
    status.style.color = "var(--error)";
  }
  btn.disabled = false;
}

async function detectTypes() {
  if (!currentSkillId) return;
  const btn = document.getElementById("detect-btn");
  const spinner = document.getElementById("detect-spinner");
  const chips = document.getElementById("types-chips");

  btn.disabled = true;
  spinner.classList.remove("hidden");
  chips.innerHTML = "";

  try {
    const res = await fetch(cq(`/skill/${currentSkillId}/detect-types`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const rqt = data.relevant_question_types;
    renderTypeChips(rqt);
    populateTypeDropdown(rqt);
  } catch (e) {
    chips.innerHTML = `<span style="color:var(--error);font-size:0.85rem">${e.message}</span>`;
  }

  btn.disabled = false;
  spinner.classList.add("hidden");
}

function _typeEntries(types) {
  if (Array.isArray(types)) return types.map(t => [t, null]);
  if (types && typeof types === "object") return Object.entries(types);
  return [];
}

function renderTypeChips(types) {
  const chips = document.getElementById("types-chips");
  chips.innerHTML = "";
  for (const [t, weight] of _typeEntries(types)) {
    const label = questionTypeMeta[t] ? questionTypeMeta[t].label : t;
    const chip = document.createElement("span");
    chip.className = `type-chip chip-${t}`;
    chip.innerHTML = weight != null
      ? `${label} <span class="chip-weight">${weight}%</span>`
      : label;
    chips.appendChild(chip);
  }
}

function populateTypeDropdown(types) {
  const entries = _typeEntries(types);
  const select = document.getElementById("gen-type-select");
  select.innerHTML = '<option value="">-- pick a question type --</option>';
  if (entries.length > 1) {
    const allOpt = document.createElement("option");
    allOpt.value = "__all__";
    allOpt.textContent = "All relevant types";
    select.appendChild(allOpt);
  }
  for (const [t, weight] of entries) {
    const label = questionTypeMeta[t] ? questionTypeMeta[t].label : t;
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = weight != null ? `${label} (${weight}%)` : label;
    select.appendChild(opt);
  }
}

async function generateQuestion() {
  if (!currentSkillId) return;
  const select = document.getElementById("gen-type-select");
  const selectedType = select.value;
  if (!selectedType) return;

  const dokLevel = document.getElementById("gen-dok-select").value;
  const btn = document.getElementById("gen-btn");
  const spinner = document.getElementById("gen-spinner");
  const output = document.getElementById("gen-output");

  btn.disabled = true;
  spinner.classList.remove("hidden");
  output.innerHTML = "";

  const typesToGenerate = [];
  if (selectedType === "__all__") {
    for (const opt of select.options) {
      if (opt.value && opt.value !== "__all__") typesToGenerate.push(opt.value);
    }
  } else {
    typesToGenerate.push(selectedType);
  }

  const results = await Promise.all(typesToGenerate.map(async (qtype) => {
    try {
      const res = await fetch(cq(`/skill/${currentSkillId}/generate`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_type: qtype, dok_level: dokLevel }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      return { qtype, data, error: null };
    } catch (e) {
      return { qtype, data: null, error: e.message };
    }
  }));

  for (const r of results) {
    if (r.error) {
      const err = document.createElement("p");
      err.style.color = "var(--error)";
      err.textContent = `${r.qtype}: ${r.error}`;
      output.appendChild(err);
    } else {
      renderGeneratedQuestion(r.data.question_type, r.data.question, output, true);
    }
  }

  btn.disabled = false;
  spinner.classList.add("hidden");
}

function renderGeneratedQuestion(qtype, q, container, append) {
  genCounter++;
  const num = 9000 + genCounter;

  const typeMap = {
    fill_in_the_blank: { badge: "badge-fill", label: "Fill in the Blank", renderer: renderFillBlank, checker: checkFillBlank },
    true_false_justification: { badge: "badge-tf", label: "True / False + Justification", renderer: renderTrueFalse, checker: checkTrueFalse },
    cause_and_effect: { badge: "badge-cause", label: "Cause & Effect Matching", renderer: renderCauseEffect, checker: checkCauseEffect },
    immediate_vs_long_term: { badge: "badge-immediate", label: "Immediate vs. Long-Term Cause", renderer: renderImmediateLT, checker: checkImmediateLT },
    multiple_choice: { badge: "badge-mcq", label: "Multiple Choice", renderer: renderMCQ, checker: checkMCQ },
    rank_by_significance: { badge: "badge-rank", label: "Rank by Significance", renderer: renderRank, checker: checkRank },
  };

  const meta = typeMap[qtype];
  if (!meta) {
    container.innerHTML += `<pre>${JSON.stringify(q, null, 2)}</pre>`;
    return;
  }

  q._type = qtype;
  q._badge = meta.badge;
  q._label = meta.label;
  q._num = num;
  q._renderer = meta.renderer;
  q._checker = meta.checker;
  q.explanation = q.explanation || "";

  const card = document.createElement("div");
  card.className = "gen-question-card";
  card.id = `q-${num}`;
  card.innerHTML = `
    <div class="q-header">
      <span class="question-type-badge ${meta.badge}">${meta.label}</span>
    </div>
    <div class="q-body" id="q-body-${num}"></div>
    <div class="q-footer">
      <button class="check-btn" id="check-${num}" onclick="checkGenAnswer(${num})">Check Answer</button>
    </div>
    <div class="feedback" id="feedback-${num}"></div>
  `;

  if (!append) container.innerHTML = "";
  container.appendChild(card);

  generatedQuestions[num] = q;
  meta.renderer(q, document.getElementById(`q-body-${num}`), num);
}

const generatedQuestions = {};

function checkGenAnswer(num) {
  const q = generatedQuestions[num];
  if (!q) return;
  const btn = document.getElementById(`check-${num}`);
  if (btn.disabled) return;
  btn.disabled = true;

  const isCorrect = q._checker(q, num);

  const fb = document.getElementById(`feedback-${num}`);
  fb.classList.add("show", isCorrect ? "correct" : "incorrect");
  fb.innerHTML = `<div class="answer-label">${isCorrect ? "Correct!" : "Incorrect"}</div><div>${q.explanation || ""}</div>`;
}


/* ═══════════════════════════════════════════════
   EXISTING QUIZ RENDERERS & CHECKERS
   (unchanged, used by both the old 21-q flow
    and the new single-question generation)
   ═══════════════════════════════════════════════ */

let allQuestions = [];
let answeredCount = 0;
let correctCount = 0;
const totalQuestions = 18;

async function startGeneration() {
  const skill = document.getElementById("skill-input").value.trim();
  if (!skill) return;

  const btn = document.getElementById("generate-btn");
  const loading = document.getElementById("loading");
  const errorMsg = document.getElementById("error-msg");

  btn.disabled = true;
  loading.classList.remove("hidden");
  errorMsg.classList.add("hidden");

  const phases = [
    "Generating questions with Claude\u2026",
    "Building fill-in-the-blank questions\u2026",
    "Crafting true/false justifications\u2026",
    "Designing cause & effect matching\u2026",
    "Analyzing immediate vs. long-term causes\u2026",
    "Creating map-based questions\u2026",
    "Generating political cartoon images\u2026",
    "Ranking events by significance\u2026",
    "Finalizing your quiz\u2026"
  ];
  let phaseIdx = 0;
  const phaseInterval = setInterval(() => {
    phaseIdx = Math.min(phaseIdx + 1, phases.length - 1);
    document.getElementById("loading-text").textContent = phases[phaseIdx];
  }, 8000);

  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill }),
    });

    clearInterval(phaseInterval);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Server error");
    }

    const data = await res.json();
    buildQuiz(data, skill);
  } catch (e) {
    clearInterval(phaseInterval);
    errorMsg.textContent = e.message;
    errorMsg.classList.remove("hidden");
    btn.disabled = false;
    loading.classList.add("hidden");
  }
}

function buildQuiz(data, skill) {
  allQuestions = [];
  answeredCount = 0;
  correctCount = 0;

  const typeOrder = [
    { key: "fill_in_the_blank", badge: "badge-fill", label: "Fill in the Blank", renderer: renderFillBlank, checker: checkFillBlank },
    { key: "true_false_justification", badge: "badge-tf", label: "True / False + Justification", renderer: renderTrueFalse, checker: checkTrueFalse },
    { key: "cause_and_effect", badge: "badge-cause", label: "Cause & Effect Matching", renderer: renderCauseEffect, checker: checkCauseEffect },
    { key: "immediate_vs_long_term", badge: "badge-immediate", label: "Immediate vs. Long-Term Cause", renderer: renderImmediateLT, checker: checkImmediateLT },
    { key: "multiple_choice", badge: "badge-mcq", label: "Multiple Choice", renderer: renderMCQ, checker: checkMCQ },
    { key: "rank_by_significance", badge: "badge-rank", label: "Rank by Significance", renderer: renderRank, checker: checkRank },
  ];

  let qNum = 0;
  for (const type of typeOrder) {
    const questions = data[type.key] || [];
    for (const q of questions) {
      qNum++;
      allQuestions.push({ ...q, _type: type.key, _badge: type.badge, _label: type.label, _num: qNum, _renderer: type.renderer, _checker: type.checker });
    }
  }

  const container = document.getElementById("questions-container");
  container.innerHTML = "";

  for (const q of allQuestions) {
    const card = document.createElement("div");
    card.className = "question-card";
    card.id = `q-${q._num}`;
    card.innerHTML = `
      <div class="q-header">
        <span class="question-type-badge ${q._badge}">${q._label}</span>
        <span class="q-number">Question ${q._num} of ${totalQuestions}</span>
      </div>
      <div class="q-body" id="q-body-${q._num}"></div>
      <div class="q-footer">
        <button class="check-btn" id="check-${q._num}" onclick="checkAnswer(${q._num})">Check Answer</button>
      </div>
      <div class="feedback" id="feedback-${q._num}"></div>
    `;
    container.appendChild(card);
    q._renderer(q, document.getElementById(`q-body-${q._num}`), q._num);
  }

  document.getElementById("quiz-topic").textContent = skill;
  document.getElementById("tree-screen").classList.remove("active");
  document.getElementById("quiz-screen").classList.add("active");
  updateProgress();
}

function goBack() {
  document.getElementById("quiz-screen").classList.remove("active");
  document.getElementById("tree-screen").classList.add("active");
  document.getElementById("score-summary").classList.add("hidden");
  document.getElementById("questions-container").innerHTML = "";
}

function updateProgress() {
  const pct = (answeredCount / totalQuestions) * 100;
  document.getElementById("progress-fill").style.width = pct + "%";
  document.getElementById("progress-text").textContent = `${answeredCount} / ${totalQuestions}`;
}

function checkAnswer(num) {
  const q = allQuestions[num - 1];
  const btn = document.getElementById(`check-${num}`);
  if (btn.disabled) return;
  btn.disabled = true;

  const isCorrect = q._checker(q, num);

  answeredCount++;
  if (isCorrect) correctCount++;
  updateProgress();

  const fb = document.getElementById(`feedback-${num}`);
  fb.classList.add("show", isCorrect ? "correct" : "incorrect");
  fb.innerHTML = `<div class="answer-label">${isCorrect ? "Correct!" : "Incorrect"}</div><div>${q.explanation || ""}</div>`;

  if (answeredCount === totalQuestions) showSummary();
}

function showSummary() {
  document.getElementById("final-score").textContent = correctCount;
  document.getElementById("total-possible").textContent = totalQuestions;
  const pct = Math.round((correctCount / totalQuestions) * 100);
  let msg = "";
  if (pct >= 90) msg = "Outstanding! You have mastered this material.";
  else if (pct >= 70) msg = "Great job! You have a strong understanding.";
  else if (pct >= 50) msg = "Good effort! Review the incorrect answers to strengthen your knowledge.";
  else msg = "Keep studying! Review the explanations above and try again.";
  document.getElementById("score-message").textContent = msg;
  document.getElementById("score-summary").classList.remove("hidden");
  document.getElementById("score-summary").scrollIntoView({ behavior: "smooth" });
}


/* ─── RENDERERS ─── */

function renderFillBlank(q, body, num) {
  const prompt = q.prompt || "";
  const parts = prompt.split(/\{blank\}/i);
  let html = `<p class="question-text">`;
  for (let i = 0; i < parts.length; i++) {
    html += parts[i];
    if (i < parts.length - 1) {
      html += `<input type="text" class="blank-input" id="blank-${num}-${i}" placeholder="answer">`;
    }
  }
  html += `</p>`;
  body.innerHTML = html;
}

function renderTrueFalse(q, body, num) {
  let html = `<div class="tf-statement">${q.statement}</div>`;
  html += `<div class="mcq-options">`;
  (q.choices || []).forEach((choice, i) => {
    const badge = choice.isTrue
      ? '<span class="tf-badge tf-badge-true">True</span>'
      : '<span class="tf-badge tf-badge-false">False</span>';
    html += `
      <label class="mcq-option" onclick="mcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${badge} ${choice.text.replace(/^(True|False)\s*—?\s*/i, '')}</span>
      </label>`;
  });
  html += `</div>`;
  body.innerHTML = html;
}

function renderCauseEffect(q, body, num) {
  const pairs = q.pairs || [];
  const distractors = q.distractors || [];
  const allEffects = pairs.map(p => p.effect).concat(distractors);
  const shuffled = allEffects.map((e, i) => ({ text: e, origIdx: i }));
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }

  let html = `<p class="question-text">${q.prompt}</p><div class="matching-grid">`;
  pairs.forEach((pair, i) => {
    html += `
      <div class="matching-row">
        <div class="cause-label">${pair.cause}</div>
        <span class="matching-arrow">&#8594;</span>
        <select class="effect-select" id="ce-${num}-${i}">
          <option value="">-- select effect --</option>`;
    shuffled.forEach((eff, j) => {
      html += `<option value="${j}">${eff.text}</option>`;
    });
    html += `</select></div>`;
  });
  html += `</div>`;
  body.innerHTML = html;
  body._ceShuffled = shuffled;
}

function renderImmediateLT(q, body, num) {
  let html = `<p class="question-text">${q.prompt}</p><div class="cause-classification">`;
  q.causes.forEach((c, i) => {
    html += `
      <div class="cause-item">
        <span class="cause-text">${c.text}</span>
        <div class="cause-toggle" id="ilt-${num}-${i}">
          <button onclick="iltSelect(${num},${i},'immediate',this)">Immediate</button>
          <button onclick="iltSelect(${num},${i},'long-term',this)">Long-Term</button>
        </div>
      </div>`;
  });
  html += `</div>`;
  body.innerHTML = html;
}

function iltSelect(num, causeIdx, value, btn) {
  const toggle = document.getElementById(`ilt-${num}-${causeIdx}`);
  toggle.querySelectorAll("button").forEach(b => b.classList.remove("selected"));
  btn.classList.add("selected");
  btn.dataset.value = value;
}

function renderMapBased(q, body, num) {
  let html = `<p class="question-text">${q.question_text}</p>`;
  html += `<div class="map-container" id="map-${num}"></div>`;
  html += `<div class="mcq-options">`;
  q.options.forEach((opt, i) => {
    html += `
      <label class="mcq-option" onclick="mcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${String.fromCharCode(65 + i)}. ${opt}</span>
      </label>`;
  });
  html += `</div>`;
  body.innerHTML = html;

  setTimeout(() => {
    const center = q.map_center || [20, 0];
    const zoom = q.map_zoom || 4;
    const map = L.map(`map-${num}`, { scrollWheelZoom: false }).setView(center, zoom);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18,
    }).addTo(map);

    const colors = ["#dc2626", "#2563eb", "#16a34a", "#d97706"];
    (q.markers || []).forEach((m, i) => {
      const icon = L.divIcon({
        className: "map-marker-icon",
        html: `<div class="map-marker" style="background:${colors[i % 4]}">${m.label}</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });
      L.marker([m.lat, m.lng], { icon }).addTo(map);
    });

    setTimeout(() => map.invalidateSize(), 200);
  }, 100);
}

function renderCartoon(q, body, num) {
  let html = `<p class="question-text">${q.question_text}</p>`;
  html += `<div class="cartoon-card">`;
  if (q.scene_title) {
    html += `<div class="cartoon-title">${q.scene_title}</div>`;
  }
  const desc = q.scene_description || q.image_prompt || "";
  html += `<div class="cartoon-description">${desc}</div>`;
  if (q.historical_context) {
    html += `<div class="cartoon-context">${q.historical_context}</div>`;
  }
  html += `</div>`;
  html += `<div class="mcq-options">`;
  q.options.forEach((opt, i) => {
    html += `
      <label class="mcq-option" onclick="mcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${String.fromCharCode(65 + i)}. ${opt}</span>
      </label>`;
  });
  html += `</div>`;
  body.innerHTML = html;
}

function renderMCQ(q, body, num) {
  const choices = q.choices || [];
  let html = `<p class="question-text">${q.questionText}</p>`;
  html += `<div class="mcq-options">`;
  choices.forEach((choice, i) => {
    html += `
      <label class="mcq-option" onclick="mcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${String.fromCharCode(65 + i)}. ${choice.text}</span>
      </label>`;
  });
  html += `</div>`;
  body.innerHTML = html;
}

function checkMCQ(q, num) {
  const selected = document.querySelector(`input[name="mcq-${num}"]:checked`);
  const userVal = selected ? parseInt(selected.value) : -1;
  const correctIdx = q.correctIndex;
  const isCorrect = userVal === correctIdx;

  const body = document.getElementById(`q-body-${num}`);
  body.querySelectorAll(".mcq-option").forEach((opt, i) => {
    if (i === correctIdx) opt.style.borderColor = "var(--success)";
    else if (i === userVal && !isCorrect) opt.style.borderColor = "var(--error)";
  });

  const choices = q.choices || [];
  if (choices[userVal] && choices[userVal].explanation) {
    q.explanation = choices[userVal].explanation;
  }
  return isCorrect;
}

function mcqSelect(num, idx, label) {
  const body = label.closest(".q-body");
  body.querySelectorAll(".mcq-option").forEach(o => o.classList.remove("selected"));
  label.classList.add("selected");
}

function renderRank(q, body, num) {
  let html = `<p class="question-text">${q.prompt}</p>`;
  html += `<ul class="rank-list" id="rank-list-${num}">`;
  (q.events || []).forEach((evt, i) => {
    html += `
      <li class="rank-item" draggable="true" data-idx="${i}">
        <span class="rank-handle">&#9776;</span>
        <span class="rank-number">${i + 1}</span>
        <span class="rank-text">${evt.text}</span>
      </li>`;
  });
  html += `</ul>`;
  body.innerHTML = html;
  initDragAndDrop(num);
}

function initDragAndDrop(num) {
  const list = document.getElementById(`rank-list-${num}`);
  let draggedItem = null;

  list.querySelectorAll(".rank-item").forEach(item => {
    item.addEventListener("dragstart", (e) => {
      draggedItem = item;
      item.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });

    item.addEventListener("dragend", () => {
      item.classList.remove("dragging");
      list.querySelectorAll(".rank-item").forEach(i => i.classList.remove("drag-over"));
      updateRankNumbers(num);
    });

    item.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      item.classList.add("drag-over");
    });

    item.addEventListener("dragleave", () => {
      item.classList.remove("drag-over");
    });

    item.addEventListener("drop", (e) => {
      e.preventDefault();
      if (draggedItem && draggedItem !== item) {
        const allItems = [...list.querySelectorAll(".rank-item")];
        const dragIdx = allItems.indexOf(draggedItem);
        const dropIdx = allItems.indexOf(item);
        if (dragIdx < dropIdx) {
          list.insertBefore(draggedItem, item.nextSibling);
        } else {
          list.insertBefore(draggedItem, item);
        }
      }
      item.classList.remove("drag-over");
      updateRankNumbers(num);
    });
  });
}

function updateRankNumbers(num) {
  const list = document.getElementById(`rank-list-${num}`);
  list.querySelectorAll(".rank-item").forEach((item, i) => {
    item.querySelector(".rank-number").textContent = i + 1;
  });
}


/* ─── CHECKERS ─── */

function normalize(s) {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();
}

function checkFillBlank(q, num) {
  const blanks = q.blanks || [];
  let allCorrect = true;

  blanks.forEach((blank, i) => {
    const input = document.getElementById(`blank-${num}-${i}`);
    if (!input) { allCorrect = false; return; }
    const userRaw = input.value.trim();
    const userNorm = normalize(userRaw);

    const validAnswers = [blank.answer, ...(blank.alternates || [])];
    const isCorrect = validAnswers.some(ans => {
      const normAns = normalize(ans);
      return userNorm === normAns
        || (normAns.includes(userNorm) && userNorm.length > 2)
        || (userNorm.includes(normAns) && normAns.length > 2);
    });

    input.style.borderColor = isCorrect ? "var(--success)" : "var(--error)";
    input.style.borderStyle = "solid";
    if (!isCorrect) allCorrect = false;
  });

  if (!allCorrect) {
    const answers = blanks.map(b => b.answer).join(", ");
    q.explanation = `Acceptable answers: <strong>${answers}</strong>. ${q.explanation || ""}`;
  }
  return allCorrect;
}

function checkTrueFalse(q, num) {
  const selected = document.querySelector(`input[name="mcq-${num}"]:checked`);
  const userVal = selected ? parseInt(selected.value) : -1;
  const correctIdx = q.correctIndex;
  const isCorrect = userVal === correctIdx;

  const body = document.getElementById(`q-body-${num}`);
  body.querySelectorAll(".mcq-option").forEach((opt, i) => {
    if (i === correctIdx) opt.style.borderColor = "var(--success)";
    else if (i === userVal && !isCorrect) opt.style.borderColor = "var(--error)";
  });

  const choices = q.choices || [];
  if (choices[userVal] && choices[userVal].explanation) {
    q.explanation = choices[userVal].explanation;
  } else if (choices[correctIdx]) {
    q.explanation = choices[correctIdx].explanation;
  }
  return isCorrect;
}

function checkCauseEffect(q, num) {
  const pairs = q.pairs || [];
  const body = document.getElementById(`q-body-${num}`);
  const shuffled = body._ceShuffled || [];
  let allCorrect = true;

  pairs.forEach((pair, i) => {
    const select = document.getElementById(`ce-${num}-${i}`);
    const userVal = select.value;
    const selectedEffect = userVal !== "" ? shuffled[parseInt(userVal)] : null;
    const correct = selectedEffect && selectedEffect.origIdx === i;
    if (correct) {
      select.style.borderColor = "var(--success)";
    } else {
      select.style.borderColor = "var(--error)";
      allCorrect = false;
    }
  });
  return allCorrect;
}

function checkImmediateLT(q, num) {
  let allCorrect = true;
  const explanations = [];
  q.causes.forEach((c, i) => {
    const toggle = document.getElementById(`ilt-${num}-${i}`);
    const selected = toggle.querySelector(".selected");
    const userVal = selected ? selected.dataset.value : null;
    const item = toggle.closest(".cause-item");
    if (userVal === c.type) {
      item.style.borderColor = "var(--success)";
    } else {
      item.style.borderColor = "var(--error)";
      allCorrect = false;
    }
    if (c.explanation) explanations.push(c.explanation);
  });
  if (explanations.length) q.explanation = explanations.join("<br><br>");
  return allCorrect;
}

function checkMapBased(q, num) {
  const selected = document.querySelector(`input[name="mcq-${num}"]:checked`);
  const userVal = selected ? parseInt(selected.value) : -1;
  const isCorrect = userVal === q.correct_answer;

  const body = document.getElementById(`q-body-${num}`);
  body.querySelectorAll(".mcq-option").forEach((opt, i) => {
    if (i === q.correct_answer) opt.style.borderColor = "var(--success)";
    else if (i === userVal && !isCorrect) opt.style.borderColor = "var(--error)";
  });
  return isCorrect;
}

function checkCartoon(q, num) {
  const selected = document.querySelector(`input[name="mcq-${num}"]:checked`);
  const userVal = selected ? parseInt(selected.value) : -1;
  const isCorrect = userVal === q.correct_answer;

  const body = document.getElementById(`q-body-${num}`);
  body.querySelectorAll(".mcq-option").forEach((opt, i) => {
    if (i === q.correct_answer) opt.style.borderColor = "var(--success)";
    else if (i === userVal && !isCorrect) opt.style.borderColor = "var(--error)";
  });
  return isCorrect;
}

function checkRank(q, num) {
  const list = document.getElementById(`rank-list-${num}`);
  const items = list.querySelectorAll(".rank-item");
  const events = q.events || [];

  let allCorrect = true;
  items.forEach((item, position) => {
    const evtIdx = parseInt(item.dataset.idx);
    const evt = events[evtIdx];
    const correctRank = evt ? evt.correctRank : -1;
    const userRank = position + 1;
    if (userRank === correctRank) {
      item.style.borderColor = "var(--success)";
    } else {
      item.style.borderColor = "var(--error)";
      allCorrect = false;
    }
  });

  if (!allCorrect) {
    const sorted = [...events].sort((a, b) => a.correctRank - b.correctRank);
    const lines = sorted.map(e => `${e.correctRank}. ${e.text}${e.explanation ? " — " + e.explanation : ""}`);
    q.explanation = `Correct order:<br>${lines.join("<br>")}`;
  }
  return allCorrect;
}


/* ═══════════════════════════════════════════════
   QUESTION BANK UI (Single-button SSE pipeline)
   ═══════════════════════════════════════════════ */

let currentBankData = null;


async function buildQuestionBank() {
  if (!currentSkillId) return;
  const btn = document.getElementById("qbank-build-btn");
  const spinner = document.getElementById("qbank-spinner");
  const log = document.getElementById("qbank-progress-log");

  btn.disabled = true;
  spinner.classList.remove("hidden");
  log.innerHTML = "";
  document.getElementById("qbank-coverage").innerHTML = "";
  document.getElementById("qbank-questions").innerHTML = "";

  appendLog(log, "Starting question bank build...");

  function logProgress(sid, msg) {
    appendLog(log, msg);
    log.scrollTop = log.scrollHeight;
  }

  const result = await _buildBankForSkill(currentSkillId, logProgress);

  if (result.ok) {
    appendLog(log, `Done. ${result.saved} questions saved.`, "done");
  } else {
    appendLog(log, `Build failed: ${result.message || "unknown error"}`, "error");
  }

  btn.disabled = false;
  spinner.classList.add("hidden");
  loadQuestionBank();
  refreshPipelineStatus();
}

function appendLog(container, text, cls) {
  const line = document.createElement("div");
  line.className = "log-line" + (cls ? ` log-${cls}` : "");
  line.textContent = text;
  container.appendChild(line);
}

function updateOrAppendLog(container, key, text, cls) {
  let line = container.querySelector(`[data-log-key="${key}"]`);
  if (!line) {
    line = document.createElement("div");
    line.className = "log-line";
    line.dataset.logKey = key;
    container.appendChild(line);
  }
  line.className = "log-line" + (cls ? ` log-${cls}` : "");
  line.textContent = text;
}

async function loadQuestionBank() {
  if (!currentSkillId) return;
  try {
    const res = await fetch(cq(`/skill/${currentSkillId}/question-bank`));
    const data = await res.json();
    currentBankData = data;
    renderCoverage(data.coverage);
    renderBankQuestions(data.bank);
  } catch (e) {
    // no bank yet
  }
}

function renderCoverage(coverage) {
  const container = document.getElementById("qbank-coverage");
  container.innerHTML = "";
  if (!coverage || Object.keys(coverage).length === 0) return;

  for (const [qtype, dokStats] of Object.entries(coverage)) {
    const label = questionTypeMeta[qtype] ? questionTypeMeta[qtype].label : qtype;
    const row = document.createElement("div");
    row.className = "coverage-row";

    let html = `<div class="coverage-type-label"><span class="type-chip chip-${qtype}">${label}</span></div>`;

    for (const [dokKey, dokLabel] of [["dok2", "DOK 2"], ["dok3", "DOK 3"]]) {
      const stats = dokStats[dokKey] || { total: 0, met: 0, valid: 0, invalid: 0 };
      if (stats.total === 0) continue;
      const pct = Math.round((stats.met / stats.total) * 100);
      html += `
        <div class="coverage-dok-row">
          <span class="coverage-dok-label">${dokLabel}</span>
          <span class="coverage-stats">${stats.met}/${stats.total} met</span>
          <div class="coverage-bar"><div class="coverage-fill" style="width:${pct}%"></div></div>
        </div>`;
    }
    row.innerHTML = html;
    container.appendChild(row);
  }
}

let bankQuestionCounter = 20000;

const rendererMap = {
  fill_in_the_blank: renderFillBlank,
  true_false_justification: renderTrueFalse,
  cause_and_effect: renderCauseEffect,
  immediate_vs_long_term: renderImmediateLT,
  multiple_choice: renderMCQ,
  rank_by_significance: renderRank,
};

function renderBankQuestions(bank) {
  const container = document.getElementById("qbank-questions");
  container.innerHTML = "";
  if (!bank || Object.keys(bank).length === 0) return;

  for (const [qtype, typeData] of Object.entries(bank)) {
    const questions = typeData.questions || [];
    if (questions.length === 0) continue;

    const label = questionTypeMeta[qtype] ? questionTypeMeta[qtype].label : qtype;
    const section = document.createElement("div");
    section.className = "bank-type-section";

    const header = document.createElement("div");
    header.className = "bank-type-header";
    header.innerHTML = `<span class="type-chip chip-${qtype}">${label}</span> <span class="bank-type-count">${questions.length} questions</span>`;
    header.addEventListener("click", () => section.classList.toggle("open"));
    section.appendChild(header);

    const body = document.createElement("div");
    body.className = "bank-type-body";

    const dok2 = questions.filter(q => q.dok === "2");
    const dok3 = questions.filter(q => q.dok === "3");
    const other = questions.filter(q => q.dok !== "2" && q.dok !== "3");

    for (const [dokQuestions, dokLabel] of [[dok2, "DOK 2 — Fact Recall"], [dok3, "DOK 3 — Application"], [other, "Other"]]) {
      if (dokQuestions.length === 0) continue;

      const dokHeader = document.createElement("div");
      dokHeader.className = "bank-dok-header";
      const metCount = dokQuestions.filter(q => q.met).length;
      dokHeader.textContent = `${dokLabel} (${metCount}/${dokQuestions.length} met)`;
      body.appendChild(dokHeader);

      for (const entry of dokQuestions) {
        renderBankQuestionCard(entry, qtype, body);
      }
    }

    section.appendChild(body);
    container.appendChild(section);
  }
}

function renderBankQuestionCard(entry, qtype, container) {
  const qCard = document.createElement("div");
  qCard.className = "bank-q-card" + (entry.met ? " met" : "");

  const qHeader = document.createElement("div");
  qHeader.className = "bank-q-header";

  const metBadge = entry.met
    ? '<span class="met-badge met">Met</span>'
    : '<span class="met-badge unmet">Not Met</span>';

  const dokTag = entry.dok ? `<span class="dok-tag dok-${entry.dok}">DOK ${entry.dok}</span>` : "";

  qHeader.innerHTML = `
    <div class="bank-q-badges">${dokTag}${metBadge}</div>`;
  qCard.appendChild(qHeader);

  if (entry.question_data) {
    bankQuestionCounter++;
    const num = bankQuestionCounter;
    const qBody = document.createElement("div");
    qBody.className = "bank-q-body";
    qBody.id = `q-body-${num}`;
    qCard.appendChild(qBody);

    const qFooter = document.createElement("div");
    qFooter.className = "bank-q-footer";
    qFooter.innerHTML = `<button class="check-btn" id="check-${num}" onclick="checkBankAnswer(${num}, '${qtype}', '${entry.id}')">Check Answer</button>`;
    qCard.appendChild(qFooter);

    const feedback = document.createElement("div");
    feedback.className = "feedback";
    feedback.id = `feedback-${num}`;
    qCard.appendChild(feedback);

    const q = { ...entry.question_data };
    q._type = qtype;
    q._num = num;
    q.explanation = q.explanation || "";
    generatedQuestions[num] = q;

    container.appendChild(qCard);

    const renderer = rendererMap[qtype];
    if (renderer) {
      setTimeout(() => renderer(q, document.getElementById(`q-body-${num}`), num), 0);
    }
  } else {
    container.appendChild(qCard);
  }
}

const checkerMap = {
  fill_in_the_blank: checkFillBlank,
  true_false_justification: checkTrueFalse,
  cause_and_effect: checkCauseEffect,
  immediate_vs_long_term: checkImmediateLT,
  multiple_choice: checkMCQ,
  rank_by_significance: checkRank,
};

async function checkBankAnswer(num, qtype, questionId) {
  const q = generatedQuestions[num];
  if (!q) return;
  const btn = document.getElementById(`check-${num}`);
  if (btn.disabled) return;
  btn.disabled = true;

  const checker = checkerMap[qtype];
  const isCorrect = checker ? checker(q, num) : false;

  const fb = document.getElementById(`feedback-${num}`);
  fb.classList.add("show", isCorrect ? "correct" : "incorrect");
  fb.innerHTML = `<div class="answer-label">${isCorrect ? "Correct!" : "Incorrect"}</div><div>${q.explanation || ""}</div>`;

  if (isCorrect && currentSkillId) {
    try {
      await fetch(cq(`/skill/${currentSkillId}/question-bank/mark`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_type: qtype, question_id: questionId, met: true }),
      });
      const card = btn.closest(".bank-q-card");
      if (card) card.classList.add("met");
      const metBadge = card ? card.querySelector(".met-badge") : null;
      if (metBadge) {
        metBadge.className = "met-badge met";
        metBadge.textContent = "Met";
      }
      loadQuestionBank();
    } catch (e) {
      // silent
    }
  }
}


/* ─── INIT ─── */

document.addEventListener("DOMContentLoaded", () => {
  loadCourses().then(() => initTree());
});
