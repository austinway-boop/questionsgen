/* ═══════════════════════════════════════════════
   LEARNING ALGORITHM SIMULATION
   ═══════════════════════════════════════════════ */

const STORAGE_KEY = "learnSimState";
const MAX_DOK2_TOTAL = 16;
const DOK3_PER_SKILL = 2;
const WRONG_THRESHOLD = 3;

let treeData = null;
let readySkills = [];       // skills with complete content + bank
let skillTextMap = {};       // skillId -> text
let skillUnitMap = {};       // skillId -> unitIndex
let skillOrderMap = {};      // skillId -> global ordering index
let sourceGroups = {};       // skillId -> [sibling skillIds sharing same content]
let studentState = null;
let currentSession = null;   // active session state
let learnQCounter = 50000;

/* ───────────────────────────────────────────────
   STATE MANAGEMENT (localStorage)
   ─────────────────────────────────────────────── */

function defaultState() {
  return {
    skills: {},
    learningPriority: 2.0,
    simulatedDay: 0,
    startTimestamp: Date.now(),
    totalSessions: 0,
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* corrupt data */ }
  return null;
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(studentState));
}

function getSkillState(skillId) {
  if (!studentState.skills[skillId]) {
    studentState.skills[skillId] = {
      mastery: 0,
      learned: false,
      lastLearned: null,
      lastCovered: null,
    };
  }
  return studentState.skills[skillId];
}

function clampMastery(val) {
  return Math.max(0, Math.min(100, val));
}

function applyDailyDecay(days) {
  for (const sid of Object.keys(studentState.skills)) {
    const s = studentState.skills[sid];
    if (s.mastery > 0) {
      s.mastery = clampMastery(s.mastery - days);
    }
  }
  studentState.simulatedDay += days;
  saveState();
}

function resetSimulation() {
  if (!confirm("Reset all simulation data? This cannot be undone.")) return;
  studentState = defaultState();
  saveState();
  currentSession = null;
  showState("idle");
  refreshDashboard();
}

/* ───────────────────────────────────────────────
   CORE ALGORITHM
   ─────────────────────────────────────────────── */

function getCurrentDay() {
  return studentState.simulatedDay;
}

function daysSinceTimestamp(ts) {
  if (!ts) return 0;
  const sessionStartDay = 0;
  const tsDayOffset = (ts - studentState.startTimestamp) / (1000 * 60 * 60 * 24);
  return Math.max(0, getCurrentDay() - tsDayOffset);
}

function coverPriority(skillState) {
  const lastInteraction = Math.max(skillState.lastLearned || 0, skillState.lastCovered || 0);
  if (!lastInteraction) return 0;
  const days = daysSinceTimestamp(lastInteraction);
  return Math.sqrt(days) * (100 - skillState.mastery) / 100;
}

function getLearnedSkills() {
  return readySkills.filter(sid => {
    const s = studentState.skills[sid];
    return s && s.learned;
  });
}

function getUnlearnedSkills() {
  return readySkills.filter(sid => {
    const s = studentState.skills[sid];
    return !s || !s.learned;
  });
}

function selectNextContent() {
  const learned = getLearnedSkills();
  const unlearned = getUnlearnedSkills();

  let coverScores = [];
  let maxCover = { skillId: null, score: 0 };

  for (const sid of learned) {
    const s = getSkillState(sid);
    const score = coverPriority(s);
    coverScores.push({ skillId: sid, score });
    if (score > maxCover.score) {
      maxCover = { skillId: sid, score };
    }
  }

  coverScores.sort((a, b) => b.score - a.score);

  const lp = studentState.learningPriority;

  if (maxCover.score > lp && maxCover.skillId) {
    return {
      type: "cover",
      skillId: maxCover.skillId,
      coverScore: maxCover.score,
      coverScores,
      learningPriority: lp,
    };
  }

  if (unlearned.length === 0) {
    if (maxCover.skillId) {
      return {
        type: "cover",
        skillId: maxCover.skillId,
        coverScore: maxCover.score,
        coverScores,
        learningPriority: lp,
        reason: "All skills learned; reviewing weakest.",
      };
    }
    return null;
  }

  // Pick unlearned skill: lowest mastery, tiebreak by course order
  let bestSkill = unlearned[0];
  let bestMastery = getSkillState(unlearned[0]).mastery;
  let bestOrder = skillOrderMap[unlearned[0]] || 0;

  for (let i = 1; i < unlearned.length; i++) {
    const sid = unlearned[i];
    const m = getSkillState(sid).mastery;
    const o = skillOrderMap[sid] || 0;
    if (m < bestMastery || (m === bestMastery && o < bestOrder)) {
      bestSkill = sid;
      bestMastery = m;
      bestOrder = o;
    }
  }

  return {
    type: "learn",
    skillId: bestSkill,
    coverScores,
    learningPriority: lp,
  };
}

/* ───────────────────────────────────────────────
   INITIALIZATION
   ─────────────────────────────────────────────── */

async function init() {
  const [treeRes, statusRes, groupsRes] = await Promise.all([
    fetch("/skill-tree"),
    fetch("/pipeline-status"),
    fetch("/skill-source-groups"),
  ]);
  treeData = await treeRes.json();
  const pipelineStatus = await statusRes.json();
  sourceGroups = await groupsRes.json();

  let orderIdx = 0;
  for (const unit of treeData.units) {
    const unitIdx = parseInt(unit.id.replace("U", ""));
    for (const skill of unit.skills) {
      skillTextMap[skill.id] = skill.text;
      skillUnitMap[skill.id] = unitIdx;
      skillOrderMap[skill.id] = orderIdx++;
      if (pipelineStatus[skill.id] === "complete") {
        readySkills.push(skill.id);
      }
    }
  }

  studentState = loadState() || defaultState();
  saveState();

  document.getElementById("loading-indicator").style.display = "none";
  const btn = document.getElementById("start-btn");
  btn.disabled = false;
  if (readySkills.length === 0) {
    btn.textContent = "No completed skills available";
    btn.disabled = true;
  }

  refreshDashboard();
}

function getContentGroup(skillId) {
  const siblings = (sourceGroups[skillId] || [skillId])
    .filter(sid => readySkills.includes(sid));
  return siblings.length > 0 ? siblings : [skillId];
}

/* ───────────────────────────────────────────────
   UI STATE MANAGEMENT
   ─────────────────────────────────────────────── */

function showState(name) {
  document.querySelectorAll(".learn-state").forEach(el => el.classList.remove("active"));
  const el = document.getElementById(`state-${name}`);
  if (el) el.classList.add("active");
}

function updateMasteryBar(prefix, mastery) {
  const val = document.getElementById(`${prefix}-mastery-value`);
  const fill = document.getElementById(`${prefix}-mastery-fill`);
  if (val) val.textContent = Math.round(mastery);
  if (fill) {
    fill.style.width = mastery + "%";
    if (mastery >= 70) fill.style.backgroundColor = "var(--success)";
    else if (mastery >= 40) fill.style.backgroundColor = "var(--primary)";
    else if (mastery > 0) fill.style.backgroundColor = "var(--warning)";
    else fill.style.backgroundColor = "var(--border)";
  }
}

/* ───────────────────────────────────────────────
   DASHBOARD / SIDEBAR
   ─────────────────────────────────────────────── */

function refreshDashboard() {
  // Top bar stats
  const learned = getLearnedSkills();
  document.getElementById("stat-day").textContent = getCurrentDay();
  document.getElementById("stat-learned").textContent = `${learned.length} / ${readySkills.length}`;
  document.getElementById("stat-sessions").textContent = studentState.totalSessions;

  let avgMastery = 0;
  if (learned.length > 0) {
    const total = learned.reduce((sum, sid) => sum + getSkillState(sid).mastery, 0);
    avgMastery = Math.round(total / learned.length);
  }
  document.getElementById("stat-avg-mastery").textContent = avgMastery;

  // Learning priority sync
  document.getElementById("learning-priority-slider").value = studentState.learningPriority;
  document.getElementById("learning-priority-input").value = studentState.learningPriority;

  // Mastery list
  renderMasteryList();
}

function renderMasteryList() {
  const container = document.getElementById("mastery-list");
  const badge = document.getElementById("learned-count-badge");
  const learned = getLearnedSkills();
  badge.textContent = learned.length;

  if (learned.length === 0) {
    container.innerHTML = '<div class="mastery-list-empty">No skills learned yet</div>';
    return;
  }

  const items = learned.map(sid => {
    const s = getSkillState(sid);
    return { sid, mastery: s.mastery, priority: coverPriority(s) };
  }).sort((a, b) => b.priority - a.priority);

  container.innerHTML = items.map(item => {
    const color = item.mastery >= 70 ? "var(--success)" :
                  item.mastery >= 40 ? "var(--primary)" :
                  item.mastery > 0 ? "var(--warning)" : "var(--border)";
    return `
      <div class="mastery-item" data-sid="${item.sid}" title="${skillTextMap[item.sid] || item.sid}">
        <span class="mastery-item-id">${item.sid}</span>
        <div class="mastery-item-bar">
          <div class="mastery-item-fill" style="width:${item.mastery}%;background:${color}"></div>
        </div>
        <span class="mastery-item-score">${Math.round(item.mastery)}</span>
        <span class="mastery-item-priority">${item.priority.toFixed(1)}</span>
      </div>`;
  }).join("");
}

function renderDecision(decision) {
  const container = document.getElementById("decision-display");
  if (!decision) {
    container.innerHTML = '<div class="decision-placeholder">No content available</div>';
    return;
  }

  let html = "";
  if (decision.type === "learn") {
    const group = getContentGroup(decision.skillId);
    html += `<div class="decision-type decision-type-learn">LEARNING — New Content</div>`;
    if (group.length > 1) {
      html += `<div class="decision-detail">Content group: <strong>${group.join(", ")}</strong> (${group.length} skills)</div>`;
    } else {
      html += `<div class="decision-detail">Skill: <strong>${decision.skillId}</strong></div>`;
    }
    html += `<div class="decision-detail" style="font-size:0.76rem;margin-top:0.2rem">${skillTextMap[decision.skillId] || ""}</div>`;
  } else {
    html += `<div class="decision-type decision-type-cover">REVIEW — Cover Content</div>`;
    html += `<div class="decision-detail">Skill: <strong>${decision.skillId}</strong> (score: ${decision.coverScore.toFixed(2)})</div>`;
    if (decision.reason) html += `<div class="decision-detail" style="font-style:italic">${decision.reason}</div>`;
  }

  html += `<div class="decision-threshold"><span>Learning Priority</span><span>${decision.learningPriority.toFixed(1)}</span></div>`;

  if (decision.coverScores && decision.coverScores.length > 0) {
    html += `<div class="decision-scores">`;
    const top = decision.coverScores.slice(0, 8);
    for (const cs of top) {
      const isWinner = decision.type === "cover" && cs.skillId === decision.skillId;
      html += `<div class="decision-score-row${isWinner ? " winner" : ""}">
        <span>${cs.skillId}</span>
        <span>${cs.score.toFixed(2)}</span>
      </div>`;
    }
    if (decision.coverScores.length > 8) {
      html += `<div class="decision-score-row" style="color:var(--text-muted)">...${decision.coverScores.length - 8} more</div>`;
    }
    html += `</div>`;
  }

  container.innerHTML = html;
}

function updateLearningPriority(val) {
  const v = parseFloat(val);
  if (isNaN(v)) return;
  studentState.learningPriority = Math.max(0.5, Math.min(5, v));
  document.getElementById("learning-priority-slider").value = studentState.learningPriority;
  document.getElementById("learning-priority-input").value = studentState.learningPriority;
  saveState();
}

/* ───────────────────────────────────────────────
   TIME CONTROLS
   ─────────────────────────────────────────────── */

function advanceDays(n) {
  applyDailyDecay(n);
  refreshDashboard();
  // Re-run decision display if idle
  if (document.getElementById("state-idle").classList.contains("active")) {
    const decision = selectNextContent();
    if (decision) renderDecision(decision);
  }
}

/* ───────────────────────────────────────────────
   SESSION CONTROL
   ─────────────────────────────────────────────── */

async function startNextSession() {
  const decision = selectNextContent();
  if (!decision) {
    alert("No content available. All skills may be fully mastered or no completed skills exist.");
    return;
  }

  renderDecision(decision);
  studentState.totalSessions++;
  saveState();

  if (decision.type === "learn") {
    await startLearningSession(decision.skillId);
  } else {
    await startCoverSession(decision.skillId, decision.coverScore);
  }

  refreshDashboard();
}

/* ───────────────────────────────────────────────
   LEARNING SESSION (content-group aware)
   ─────────────────────────────────────────────── */

async function startLearningSession(skillId) {
  showState("learning");

  // Expand to full content group (sibling skills sharing the same source material)
  const group = getContentGroup(skillId);

  // Record start mastery for all skills in group
  const startMasteries = {};
  for (const sid of group) {
    startMasteries[sid] = getSkillState(sid).mastery;
  }

  // Header shows the group
  const headerText = group.length > 1
    ? group.map(sid => skillTextMap[sid] || sid).join(" | ")
    : skillTextMap[skillId] || skillId;
  document.getElementById("learn-skill-name").textContent = headerText;
  document.getElementById("learn-skill-id").textContent = group.join(", ");
  renderGroupMasteryBars(group);

  // Fetch skill details + question banks for all skills in the group
  const fetches = group.map(sid => Promise.all([
    fetch(`/skill/${sid}`).then(r => r.json()),
    fetch(`/skill/${sid}/question-bank`).then(r => r.json()),
  ]));
  const results = await Promise.all(fetches);

  const skillDataMap = {};
  const bankMap = {};
  let learningContent = "";
  let sources = [];
  for (let i = 0; i < group.length; i++) {
    const sid = group[i];
    skillDataMap[sid] = results[i][0];
    bankMap[sid] = results[i][1].bank || {};
    // Use the first skill's content (they share the same source material)
    if (i === 0) {
      learningContent = results[i][0].learning_content || "";
      sources = results[i][0].sources || [];
    }
  }

  const basicPerSkill = Math.max(1, Math.floor(MAX_DOK2_TOTAL / group.length));
  const basicQueue = buildInterleavedQueue(group, bankMap, "2", basicPerSkill);
  const advancedQueue = buildInterleavedQueue(group, bankMap, "3", DOK3_PER_SKILL);

  currentSession = {
    type: "learn",
    group,
    primarySkillId: skillId,
    skillDataMap,
    bankMap,
    learningContent,
    sources,
    phase: "content",
    basicQueue,
    advancedQueue,
    queueIndex: 0,
    totalBasic: basicQueue.length,
    totalAdvanced: advancedQueue.length,
    wrongCounts: {},   // per-skill wrong count
    totalAnswered: 0,
    startMasteries,
    rewatchPrompted: false,
  };
  for (const sid of group) currentSession.wrongCounts[sid] = 0;

  showContentPhase(learningContent, sources);
}

function buildInterleavedQueue(group, bankMap, dok, countPerSkill) {
  // For each skill, pick `countPerSkill` random questions of the given DOK
  const perSkill = {};
  for (const sid of group) {
    const bank = bankMap[sid] || {};
    const candidates = [];
    for (const [qtype, typeData] of Object.entries(bank)) {
      for (const q of (typeData.questions || [])) {
        if (!q.question_data || q.valid === false) continue;
        if (q.dok !== dok) continue;
        candidates.push({ qtype, data: q.question_data, dok });
      }
    }
    // Shuffle and take up to countPerSkill
    for (let i = candidates.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [candidates[i], candidates[j]] = [candidates[j], candidates[i]];
    }
    perSkill[sid] = candidates.slice(0, countPerSkill);
  }

  // Interleave: round-robin across skills
  const queue = [];
  for (let round = 0; round < countPerSkill; round++) {
    for (const sid of group) {
      if (round < perSkill[sid].length) {
        queue.push({ skillId: sid, ...perSkill[sid][round] });
      }
    }
  }
  return queue;
}

function renderGroupMasteryBars(group) {
  const container = document.getElementById("learn-mastery-bars");
  if (!container || !group || group.length === 0) return;
  container.innerHTML = group.map(sid => {
    const m = Math.round(getSkillState(sid).mastery);
    const color = m >= 70 ? "var(--success)" : m >= 40 ? "var(--primary)" : m > 0 ? "var(--warning)" : "var(--border)";
    return `
      <div class="group-mastery-row" id="gm-${sid}">
        <span class="group-mastery-id">${sid}</span>
        <div class="group-mastery-bar"><div class="group-mastery-fill" style="width:${m}%;background:${color}"></div></div>
        <span class="group-mastery-score">${m}</span>
      </div>`;
  }).join("");
}

function updateGroupMasteryBars(group) {
  if (!group || group.length === 0) return;
  for (const sid of group) {
    const row = document.getElementById(`gm-${sid}`);
    if (!row) continue;
    const m = Math.round(getSkillState(sid).mastery);
    const color = m >= 70 ? "var(--success)" : m >= 40 ? "var(--primary)" : m > 0 ? "var(--warning)" : "var(--border)";
    const fill = row.querySelector(".group-mastery-fill");
    const score = row.querySelector(".group-mastery-score");
    if (fill) { fill.style.width = m + "%"; fill.style.background = color; }
    if (score) score.textContent = m;
  }
}

function showContentPhase(learningContent, sources) {
  document.getElementById("learn-video-phase").classList.remove("hidden");
  document.getElementById("learn-questions-phase").classList.add("hidden");
  document.getElementById("rewatch-prompt").classList.add("hidden");

  const container = document.getElementById("video-container");
  let html = "";

  if (learningContent.trim()) {
    const paragraphs = learningContent.split(/\n\n+/).filter(p => p.trim());
    html += '<div class="learning-text-content">';
    for (const p of paragraphs) {
      html += `<p>${p.trim()}</p>`;
    }
    html += "</div>";
  } else {
    html += '<div class="no-video">No learning content available for this skill.</div>';
  }

  if (sources.length > 0) {
    html += '<div class="content-sources-hint">';
    html += `<span>Source: ${sources.map(s => `Topic ${s.topic} — ${s.section_label}`).join(", ")}</span>`;
    html += "</div>";
  }

  container.innerHTML = html;
}

function completeVideo() {
  if (!currentSession || currentSession.type !== "learn") return;

  const isRewatch = currentSession.hasWatchedOnce === true;

  if (isRewatch) {
    // Rewatching means they struggled -- penalize mastery
    for (const sid of currentSession.group) {
      const s = getSkillState(sid);
      s.mastery = clampMastery(s.mastery - 10);
    }
  } else {
    // First time reading content: +40 mastery
    for (const sid of currentSession.group) {
      const s = getSkillState(sid);
      s.mastery = clampMastery(s.mastery + 40);
    }
    currentSession.hasWatchedOnce = true;
  }

  saveState();
  updateGroupMasteryBars(currentSession.group);

  currentSession.phase = "basic";
  currentSession.queueIndex = 0;
  showQuestionsPhase();
}

function showQuestionsPhase() {
  document.getElementById("learn-video-phase").classList.add("hidden");
  document.getElementById("rewatch-prompt").classList.add("hidden");
  document.getElementById("learn-questions-phase").classList.remove("hidden");

  const isBasic = currentSession.phase === "basic";
  const queue = isBasic ? currentSession.basicQueue : currentSession.advancedQueue;
  const label = isBasic ? "Basic Questions (DOK 2)" : "Advanced Questions (DOK 3)";

  document.getElementById("questions-phase-label").textContent = label;
  document.getElementById("questions-progress-text").textContent = `0 / ${queue.length}`;
  document.getElementById("learn-question-container").innerHTML = "";

  currentSession.queueIndex = 0;
  serveNextQuestion();
}

function serveNextQuestion() {
  const isBasic = currentSession.phase === "basic";
  const queue = isBasic ? currentSession.basicQueue : currentSession.advancedQueue;

  if (currentSession.queueIndex >= queue.length) {
    if (isBasic) {
      currentSession.phase = "advanced";
      showQuestionsPhase();
    } else {
      completeLearningSession();
    }
    return;
  }

  const item = queue[currentSession.queueIndex];
  const skillLabel = currentSession.group.length > 1 ? ` [${item.skillId}]` : "";

  renderSessionQuestion(item.qtype, item.data, "learn-question-container", (correct) => {
    onLearnAnswer(correct, item.skillId, item.dok);
  }, skillLabel, item.dok);
}

function onLearnAnswer(correct, answeredSkillId, dok) {
  const skillState = getSkillState(answeredSkillId);
  const delta = dok === "3"
    ? (correct ? 20 : -25)
    : (correct ? 10 : -20);
  skillState.mastery = clampMastery(skillState.mastery + delta);
  saveState();
  updateGroupMasteryBars(currentSession.group);

  currentSession.queueIndex++;
  if (!correct) currentSession.wrongCounts[answeredSkillId]++;

  const isBasic = currentSession.phase === "basic";
  const queue = isBasic ? currentSession.basicQueue : currentSession.advancedQueue;
  document.getElementById("questions-progress-text").textContent =
    `${currentSession.queueIndex} / ${queue.length}`;

  // Check rewatch threshold (any skill hitting the threshold triggers it)
  const totalWrong = Object.values(currentSession.wrongCounts).reduce((a, b) => a + b, 0);
  if (totalWrong >= WRONG_THRESHOLD && !currentSession.rewatchPrompted) {
    currentSession.rewatchPrompted = true;
    document.getElementById("learn-questions-phase").classList.add("hidden");
    document.getElementById("rewatch-prompt").classList.remove("hidden");
    return;
  }
}

function rewatchVideo() {
  currentSession.phase = "content";
  for (const sid of currentSession.group) currentSession.wrongCounts[sid] = 0;
  currentSession.queueIndex = 0;
  currentSession.rewatchPrompted = false;
  const basicPerSkill = Math.max(1, Math.floor(MAX_DOK2_TOTAL / currentSession.group.length));
  currentSession.basicQueue = buildInterleavedQueue(currentSession.group, currentSession.bankMap, "2", basicPerSkill);
  currentSession.advancedQueue = buildInterleavedQueue(currentSession.group, currentSession.bankMap, "3", DOK3_PER_SKILL);
  showContentPhase(currentSession.learningContent, currentSession.sources);
}

function skipRewatch() {
  document.getElementById("rewatch-prompt").classList.add("hidden");
  document.getElementById("learn-questions-phase").classList.remove("hidden");
}

function completeLearningSession() {
  const ts = simulatedTimestamp();
  // Mark ALL skills in the group as learned
  for (const sid of currentSession.group) {
    const s = getSkillState(sid);
    s.learned = true;
    s.lastLearned = ts;
  }
  saveState();

  // Build summary across all skills
  const group = currentSession.group;
  const summarySkills = group.map(sid => {
    const before = currentSession.startMasteries[sid];
    const after = getSkillState(sid).mastery;
    return { sid, before, after, delta: after - before };
  });
  const totalDelta = summarySkills.reduce((sum, s) => sum + s.delta, 0);

  showGroupComplete("Learning Complete", summarySkills, totalDelta);
}

/* ───────────────────────────────────────────────
   COVER SESSION
   ─────────────────────────────────────────────── */

async function startCoverSession(skillId, score) {
  showState("cover");

  const skillState = getSkillState(skillId);
  document.getElementById("cover-skill-name").textContent = skillTextMap[skillId] || skillId;
  document.getElementById("cover-skill-id").textContent = skillId;
  updateMasteryBar("cover", skillState.mastery);

  const days = daysSinceTimestamp(Math.max(skillState.lastLearned || 0, skillState.lastCovered || 0));
  document.getElementById("cover-reason").innerHTML =
    `<strong>Why this skill?</strong> Cover priority = sqrt(${days.toFixed(1)} days) &times; (100 - ${Math.round(skillState.mastery)}) / 100 = <strong>${score.toFixed(2)}</strong> (threshold: ${studentState.learningPriority.toFixed(1)})`;

  const bankRes = await fetch(`/skill/${skillId}/question-bank`).then(r => r.json());
  const bank = bankRes.bank || {};

  currentSession = {
    type: "cover",
    skillId,
    bank,
    startMastery: skillState.mastery,
  };

  const question = pickRandomQuestion(bank);
  if (!question) {
    showSessionComplete("Review Complete", skillId, skillState.mastery, skillState.mastery, 0);
    return;
  }

  renderSessionQuestion(question.qtype, question.data, "cover-question-container", (correct) => {
    onCoverAnswer(correct, skillId);
  });
}

function onCoverAnswer(correct, skillId) {
  const skillState = getSkillState(skillId);
  const delta = correct ? 10 : -20;
  skillState.mastery = clampMastery(skillState.mastery + delta);
  skillState.lastCovered = simulatedTimestamp();
  saveState();
  updateMasteryBar("cover", skillState.mastery);

  const masteryDelta = skillState.mastery - currentSession.startMastery;

  setTimeout(() => {
    showSessionComplete("Review Complete", skillId, currentSession.startMastery, skillState.mastery, masteryDelta);
  }, 1500);
}

/* ───────────────────────────────────────────────
   SESSION COMPLETE
   ─────────────────────────────────────────────── */

function showSessionComplete(title, skillId, startMastery, endMastery, delta) {
  showGroupComplete(title, [{ sid: skillId, before: startMastery, after: endMastery, delta }], delta);
}

function showGroupComplete(title, summarySkills, totalDelta) {
  showState("complete");
  document.getElementById("complete-title").textContent = title;

  const icon = document.getElementById("complete-icon");
  if (totalDelta >= 0) {
    icon.innerHTML = "&#10003;";
    icon.style.background = "var(--success-bg)";
    icon.style.color = "var(--success)";
  } else {
    icon.innerHTML = "&#9888;";
    icon.style.background = "var(--warning-bg)";
    icon.style.color = "var(--warning)";
  }

  let html = "";
  for (const s of summarySkills) {
    const sign = s.delta >= 0 ? "+" : "";
    const color = s.delta >= 0 ? "var(--success)" : "var(--error)";
    html += `<div class="summary-line"><span>${s.sid}</span><span>${Math.round(s.before)} &rarr; ${Math.round(s.after)} <span style="color:${color};font-weight:700">(${sign}${Math.round(s.delta)})</span></span></div>`;
  }
  html += `<div class="summary-line" style="border-top:2px solid var(--border);margin-top:0.3rem;padding-top:0.3rem"><span>Day</span><span>${getCurrentDay()}</span></div>`;

  document.getElementById("complete-summary").innerHTML = html;
  refreshDashboard();
}

/* ───────────────────────────────────────────────
   QUESTION PICKING
   ─────────────────────────────────────────────── */

function pickRandomQuestion(bank, dok) {
  const candidates = [];
  for (const [qtype, typeData] of Object.entries(bank)) {
    const questions = typeData.questions || [];
    for (const q of questions) {
      if (!q.question_data) continue;
      if (q.valid === false) continue;
      if (dok && q.dok !== dok) continue;
      candidates.push({ qtype, data: q.question_data });
    }
  }
  if (candidates.length === 0) return null;
  return candidates[Math.floor(Math.random() * candidates.length)];
}

/* ───────────────────────────────────────────────
   RENDER A SESSION QUESTION
   ─────────────────────────────────────────────── */

function renderSessionQuestion(qtype, questionData, containerId, onAnswer, skillLabel, dok) {
  learnQCounter++;
  const num = learnQCounter;
  const container = document.getElementById(containerId);

  const meta = QUESTION_TYPES[qtype];
  if (!meta) {
    container.innerHTML = `<pre>${JSON.stringify(questionData, null, 2)}</pre>`;
    return;
  }

  const q = { ...questionData };
  q._type = qtype;
  q._num = num;
  q.explanation = q.explanation || "";

  const skillTag = skillLabel ? `<span class="question-skill-tag">${skillLabel}</span>` : "";
  const card = document.createElement("div");
  card.className = "learn-question-card";
  card.id = `q-${num}`;
  card.innerHTML = `
    <div class="q-header">
      <span class="question-type-badge ${meta.badge}">${meta.label}</span>${skillTag}
    </div>
    <div class="q-body" id="q-body-${num}"></div>
    <div class="q-footer">
      <button class="check-btn" id="check-${num}">Check Answer</button>
    </div>
    <div class="feedback" id="feedback-${num}"></div>`;

  container.innerHTML = "";
  container.appendChild(card);

  learnQuestionStore[num] = q;
  meta.renderer(q, document.getElementById(`q-body-${num}`), num);

  document.getElementById(`check-${num}`).addEventListener("click", () => {
    const btn = document.getElementById(`check-${num}`);
    if (btn.disabled) return;
    btn.disabled = true;

    const isCorrect = meta.checker(q, num);
    const fb = document.getElementById(`feedback-${num}`);
    fb.classList.add("show", isCorrect ? "correct" : "incorrect");

    let fbHtml = `<div class="answer-label">${isCorrect ? "Correct!" : "Incorrect"}</div>`;
    fbHtml += `<div>${q.explanation || ""}</div>`;
    const fbDelta = dok === "3"
      ? (isCorrect ? 20 : -25)
      : (isCorrect ? 10 : -20);
    const sign = fbDelta > 0 ? "+" : "";
    fbHtml += `<span class="mastery-change ${fbDelta > 0 ? "positive" : "negative"}">${sign}${fbDelta} mastery</span>`;
    fb.innerHTML = fbHtml;

    onAnswer(isCorrect);

    // Auto-serve next question after a delay (learning sessions only)
    if (currentSession && currentSession.type === "learn") {
      if (!document.getElementById("rewatch-prompt").classList.contains("hidden")) return;
      setTimeout(() => serveNextQuestion(), 1200);
    }
  });
}

const learnQuestionStore = {};

/* ───────────────────────────────────────────────
   HELPERS
   ─────────────────────────────────────────────── */

function simulatedTimestamp() {
  return studentState.startTimestamp + studentState.simulatedDay * 24 * 60 * 60 * 1000;
}

/* ═══════════════════════════════════════════════
   QUESTION RENDERERS & CHECKERS
   (ported from app.js for independence)
   ═══════════════════════════════════════════════ */

const QUESTION_TYPES = {
  fill_in_the_blank: { badge: "badge-fill", label: "Fill in the Blank", renderer: renderFillBlank, checker: checkFillBlank },
  true_false_justification: { badge: "badge-tf", label: "True / False + Justification", renderer: renderTrueFalse, checker: checkTrueFalse },
  cause_and_effect: { badge: "badge-cause", label: "Cause & Effect Matching", renderer: renderCauseEffect, checker: checkCauseEffect },
  immediate_vs_long_term: { badge: "badge-immediate", label: "Immediate vs. Long-Term Cause", renderer: renderImmediateLT, checker: checkImmediateLT },
  multiple_choice: { badge: "badge-mcq", label: "Multiple Choice", renderer: renderMCQ, checker: checkMCQ },
  rank_by_significance: { badge: "badge-rank", label: "Rank by Significance", renderer: renderRank, checker: checkRank },
};

function renderFillBlank(q, body, num) {
  const prompt = q.prompt || "";
  const parts = prompt.split(/\{blank\}/i);
  let html = '<p class="question-text">';
  for (let i = 0; i < parts.length; i++) {
    html += parts[i];
    if (i < parts.length - 1) {
      html += `<input type="text" class="blank-input" id="blank-${num}-${i}" placeholder="answer">`;
    }
  }
  html += "</p>";
  body.innerHTML = html;
}

function renderTrueFalse(q, body, num) {
  let html = `<div class="tf-statement">${q.statement}</div><div class="mcq-options">`;
  (q.choices || []).forEach((choice, i) => {
    const badge = choice.isTrue
      ? '<span class="tf-badge tf-badge-true">True</span>'
      : '<span class="tf-badge tf-badge-false">False</span>';
    html += `
      <label class="mcq-option" onclick="learnMcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${badge} ${choice.text.replace(/^(True|False)\s*—?\s*/i, "")}</span>
      </label>`;
  });
  html += "</div>";
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
    html += `<div class="matching-row"><div class="cause-label">${pair.cause}</div><span class="matching-arrow">&#8594;</span><select class="effect-select" id="ce-${num}-${i}"><option value="">-- select effect --</option>`;
    shuffled.forEach((eff, j) => {
      html += `<option value="${j}">${eff.text}</option>`;
    });
    html += "</select></div>";
  });
  html += "</div>";
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
          <button onclick="learnIltSelect(${num},${i},'immediate',this)">Immediate</button>
          <button onclick="learnIltSelect(${num},${i},'long-term',this)">Long-Term</button>
        </div>
      </div>`;
  });
  html += "</div>";
  body.innerHTML = html;
}

function renderMCQ(q, body, num) {
  const choices = q.choices || [];
  let html = `<p class="question-text">${q.questionText}</p><div class="mcq-options">`;
  choices.forEach((choice, i) => {
    html += `
      <label class="mcq-option" onclick="learnMcqSelect(${num}, ${i}, this)">
        <input type="radio" name="mcq-${num}" value="${i}">
        <span class="mcq-label">${String.fromCharCode(65 + i)}. ${choice.text}</span>
      </label>`;
  });
  html += "</div>";
  body.innerHTML = html;
}

function renderRank(q, body, num) {
  let html = `<p class="question-text">${q.prompt}</p><ul class="rank-list" id="rank-list-${num}">`;
  (q.events || []).forEach((evt, i) => {
    html += `
      <li class="rank-item" draggable="true" data-idx="${i}">
        <span class="rank-handle">&#9776;</span>
        <span class="rank-number">${i + 1}</span>
        <span class="rank-text">${evt.text}</span>
      </li>`;
  });
  html += "</ul>";
  body.innerHTML = html;
  initLearnDragAndDrop(num);
}

/* ─── Interaction helpers (global scope for onclick) ─── */

function learnMcqSelect(num, idx, label) {
  const body = label.closest(".q-body");
  body.querySelectorAll(".mcq-option").forEach(o => o.classList.remove("selected"));
  label.classList.add("selected");
}

function learnIltSelect(num, causeIdx, value, btn) {
  const toggle = document.getElementById(`ilt-${num}-${causeIdx}`);
  toggle.querySelectorAll("button").forEach(b => b.classList.remove("selected"));
  btn.classList.add("selected");
  btn.dataset.value = value;
}

function initLearnDragAndDrop(num) {
  const list = document.getElementById(`rank-list-${num}`);
  if (!list) return;
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
      updateLearnRankNumbers(num);
    });
    item.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      item.classList.add("drag-over");
    });
    item.addEventListener("dragleave", () => { item.classList.remove("drag-over"); });
    item.addEventListener("drop", (e) => {
      e.preventDefault();
      if (draggedItem && draggedItem !== item) {
        const allItems = [...list.querySelectorAll(".rank-item")];
        const dragIdx = allItems.indexOf(draggedItem);
        const dropIdx = allItems.indexOf(item);
        if (dragIdx < dropIdx) list.insertBefore(draggedItem, item.nextSibling);
        else list.insertBefore(draggedItem, item);
      }
      item.classList.remove("drag-over");
      updateLearnRankNumbers(num);
    });
  });
}

function updateLearnRankNumbers(num) {
  const list = document.getElementById(`rank-list-${num}`);
  if (!list) return;
  list.querySelectorAll(".rank-item").forEach((item, i) => {
    item.querySelector(".rank-number").textContent = i + 1;
  });
}

/* ─── Checkers ─── */

function normalize(s) {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();
}

function checkFillBlank(q, num) {
  const blanks = q.blanks || [];
  let allCorrect = true;

  blanks.forEach((blank, i) => {
    const input = document.getElementById(`blank-${num}-${i}`);
    if (!input) { allCorrect = false; return; }
    const userNorm = normalize(input.value.trim());
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
  if (choices[userVal] && choices[userVal].explanation) q.explanation = choices[userVal].explanation;
  else if (choices[correctIdx]) q.explanation = choices[correctIdx].explanation;
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
    select.style.borderColor = correct ? "var(--success)" : "var(--error)";
    if (!correct) allCorrect = false;
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
  if (choices[userVal] && choices[userVal].explanation) q.explanation = choices[userVal].explanation;
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
   INIT
   ═══════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {
  init();
});
