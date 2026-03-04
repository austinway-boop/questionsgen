import json
import os
import anthropic

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are an expert educational assessment designer. You create rigorous, thought-provoking questions that test deep understanding, not just memorization.

CRITICAL CONTEXT — STANDALONE QUESTIONS:
The "learning content" you receive is a transcript/summary of a VIDEO the student has already watched. The student does NOT have this text in front of them when answering questions. Every question you generate MUST be fully self-contained and answerable from what the student LEARNED (i.e. retained from watching the video), NOT from reading a passage.

NEVER write questions that:
- Reference "the learning content", "the passage", "the text", "the reading", "the article", or "the material"
- Require the student to look something up in a provided document
- Use phrases like "according to the passage", "based on the reading", "the text states that", "as described in the content"
- Assume the student can re-read or search the source material

DO write questions that:
- Test knowledge the student should have internalized from studying the topic
- Are phrased as standalone knowledge questions, as if on a closed-book test
- Provide necessary context within the question itself when needed (e.g. a brief scenario, a specific claim to evaluate)

EXPLANATION STYLE — Wise Feedback (David Yeager):
All "explanation" fields MUST follow Yeager's wise feedback principles from "10 to 25". Every explanation should:
1. Set a high standard — be direct and precise about what the correct understanding is. Do not sugarcoat or hedge.
2. Express belief in the student — use language that signals "you can get this" (e.g. "Here's the key distinction to lock in…", "This is a rigorous concept — the important thing to understand is…", "Once you see why, this clicks…").
3. Teach, don't just reveal — explain the WHY behind the correct answer in a way that deepens understanding. Connect to the bigger picture.
4. Be concise and respectful — no condescension, no filler. Speak to the student like a capable person who just needs the right framing.
Never say "Good try" or "Don't worry." Never use a compliment sandwich. Be honest, clear, and encouraging through substance.

You MUST respond with valid JSON only — no markdown fences, no explanation, no text outside the JSON object."""

QUESTION_TYPE_INFO = {
    "fill_in_the_blank": {
        "label": "Fill in the Blank",
        "description": "A sentence with key terms blanked out. Tests recall of essential vocabulary and concepts.",
        "schema": """{
  "prompt": "The {blank} Purchase of {blank} doubled the size of the United States.",
  "blanks": [
    {"answer": "Louisiana", "alternates": ["louisiana"]},
    {"answer": "1803", "alternates": []}
  ],
  "explanation": "Why this matters for understanding"
}""",
        "rules": """Use {blank} tokens in the prompt — each {blank} maps 1-to-1 to an entry in the blanks array. You may use 1 or 2 blanks per question.

ONLY blank out proper terms or key vocabulary words — never blank a common word like "the", "is", "are", etc. The blanked term must be a specific concept name, defined term, or technical phrase (e.g. "spatial patterns", "absolute distance", "choropleth map"). The sentence around the blank must give enough context that there is exactly ONE correct term per blank.

Each blank's "alternates" array MUST list 3-6 entries: common synonyms, abbreviations, plural/singular variants, and likely misspellings. Be generous — if the answer shows understanding, it should count.

NEVER blank out a proper noun that is just a name (e.g. "Brooklyn"), or trivial filler.

The question must be self-contained — NEVER reference "the learning content", "the passage", "the text", or "the reading". The student does not have any source material in front of them.""",
    },
    "true_false_justification": {
        "label": "True / False + Justification",
        "description": "A statement with four justification choices — students pick the one with the correct truth value AND correct reasoning.",
        "schema": """{
  "statement": "A clear factual claim about the topic",
  "choices": [
    {"text": "True — because [correct reasoning]", "isTrue": true, "isCorrectJustification": true, "explanation": "Why this is the right answer"},
    {"text": "True — because [wrong reasoning]", "isTrue": true, "isCorrectJustification": false, "explanation": "The statement IS true, but this reasoning is wrong because..."},
    {"text": "False — because [plausible but wrong]", "isTrue": false, "isCorrectJustification": false, "explanation": "The statement is actually true, so this is wrong..."},
    {"text": "False — because [another wrong reason]", "isTrue": false, "isCorrectJustification": false, "explanation": "The statement is actually true, so this is wrong..."}
  ],
  "correctIndex": 0
}""",
        "rules": """Exactly 4 choices — 2 with isTrue: true and 2 with isTrue: false. Exactly ONE choice has isCorrectJustification: true AND its isTrue value must match the actual truth of the statement. The correctIndex must point to that one choice.

The statement must be a single, unambiguous factual claim that is CLEARLY true or CLEARLY false. Do NOT write statements that are debatable or partially true.

Each choice text must start with "True — " or "False — " followed by a justification. The justification explains WHY the student believes the statement is true or false. Each choice must have its own explanation field explaining why it's right or wrong.

NEVER reference "the learning content", "the passage", or "the text". Write as a standalone claim.""",
    },
    "cause_and_effect": {
        "label": "Cause & Effect Matching",
        "description": "Students match causes to their effects by dragging effect chips. Tests understanding of causal relationships.",
        "schema": """{
  "prompt": "Match each cause to its effect",
  "pairs": [
    {"cause": "Introduction of maize to Europe", "effect": "Significant European population growth"},
    {"cause": "Introduction of European diseases", "effect": "Catastrophic decline of indigenous populations"}
  ],
  "distractors": ["Immediate industrialization of European economies", "Unification of all Native American groups"]
}""",
        "rules": """Exactly 4 pairs. Each pair has a "cause" and its correct "effect". Correct matching is determined by array index — pairs[0].cause matches pairs[0].effect, etc. Include 1-2 distractors (extra wrong effects that don't match any cause).

Each cause must map to EXACTLY one effect with no ambiguity. Each cause-effect pair must be a genuinely causal relationship stated or directly implied in the content. Write causes and effects as SHORT, specific phrases (under 15 words each). All effects (including distractors) should be plausible enough that the student needs real knowledge to match correctly.

The question must be self-contained — NEVER reference "the learning content", "the passage", "the text", or "the reading".""",
    },
    "immediate_vs_long_term": {
        "label": "Immediate vs. Long-Term Cause",
        "description": "Students classify causes as immediate or long-term. Tests temporal reasoning about events.",
        "schema": """{
  "prompt": "Classify each cause of European exploration and colonization:",
  "causes": [
    {"text": "Columbus's 1492 voyage proved westward travel could reach new lands", "type": "immediate", "explanation": "This is an immediate cause because..."},
    {"text": "Centuries of trade with Asia created European demand for spices", "type": "long-term", "explanation": "This is a long-term cause because..."}
  ]
}""",
        "rules": """Exactly 5 causes, mix of "immediate" and "long-term" (use a hyphen, NOT underscore). Each cause must have a "text", "type", and "explanation" field.

The prompt must describe a specific event or outcome. Each cause must be UNAMBIGUOUSLY classifiable — if a reasonable person could argue a cause is both, do not use it. Immediate = direct trigger or proximate cause. Long-term = underlying condition, structural factor, or gradual process. Write each cause as a short phrase (under 15 words).

The question must be self-contained — NEVER reference "the learning content", "the passage", "the text", or "the reading". The prompt must provide enough information for the student to understand the scenario.""",
    },
    "multiple_choice": {
        "label": "Multiple Choice",
        "description": "A standard 4-option multiple choice question. Tests comprehension and application of concepts.",
        "schema": """{
  "questionText": "Which of the following best explains...?",
  "choices": [
    {"text": "Answer A text", "explanation": "Why A is right/wrong"},
    {"text": "Answer B text", "explanation": "Why B is right/wrong"},
    {"text": "Answer C text", "explanation": "Why C is right/wrong"},
    {"text": "Answer D text", "explanation": "Why D is right/wrong"}
  ],
  "correctIndex": 0
}""",
        "rules": """Exactly 4 choices. Each choice has a "text" and "explanation" field. correctIndex is the 0-based index. The question MUST be self-contained — NEVER reference "the learning content", "the passage", or "the text".

VALIDATION-CRITICAL RULES:
- There must be exactly ONE correct answer. If two choices could both be justified, the question is bad.
- All four choices MUST be approximately the same length and level of detail.
- Distractors must be WRONG but PLAUSIBLE — they should sound like they could be right to someone who didn't study, but be clearly incorrect to someone who did.
- Ask about concepts, definitions, relationships, or applications — not trivia like specific numbers or proper nouns unless they are central to the concept.
- The correct answer must be directly supported by the source material.
- Each choice's explanation must explain why that specific choice is right or wrong.""",
    },
    "rank_by_significance": {
        "label": "Rank by Significance",
        "description": "Students rank events/factors by significance according to a specified criterion. Tests evaluative thinking.",
        "schema": """{
  "prompt": "Rank these consequences by impact on global population, from greatest (#1) to least (#4).",
  "events": [
    {"id": "r1", "text": "Spread of European diseases to the Americas", "correctRank": 1, "explanation": "Ranked #1 because..."},
    {"id": "r2", "text": "Transfer of nutrient-rich crops to Europe", "correctRank": 2, "explanation": "Ranked #2 because..."},
    {"id": "r3", "text": "Forced migration through the slave trade", "correctRank": 3, "explanation": "Ranked #3 because..."},
    {"id": "r4", "text": "Introduction of European livestock", "correctRank": 4, "explanation": "Ranked #4 because..."}
  ]
}""",
        "rules": """Exactly 4 or 5 events. Each event has "id" (short unique string like "r1"), "text", "correctRank" (1-indexed), and "explanation". The prompt MUST specify a clear, objective criterion.

VALIDATION-CRITICAL: The ranking must be defensible, not subjective opinion. If two items could reasonably swap positions, the question is bad. Choose items with CLEARLY different levels of significance so the ordering is unambiguous. Write each event as a short phrase (under 12 words).

The question must be self-contained — NEVER reference "the learning content", "the passage", "the text", or "the reading".""",
    },
}

def build_user_prompt(skill: str) -> str:
    return f"""Generate exactly 18 questions about the following skill/topic: "{skill}"

Return a JSON object with exactly these 6 keys. Each key maps to an array of exactly 3 question objects.

SCHEMA:

{{
  "fill_in_the_blank": [
    {{
      "prompt": "The {{blank}} is the study of spatial patterns on Earth's surface.",
      "blanks": [{{"answer": "geography", "alternates": ["Geography", "human geography"]}}],
      "explanation": "Why this matters"
    }}
  ],

  "true_false_justification": [
    {{
      "statement": "A clear factual claim",
      "choices": [
        {{"text": "True — because [reasoning]", "isTrue": true, "isCorrectJustification": true, "explanation": "Why correct"}},
        {{"text": "True — because [wrong reasoning]", "isTrue": true, "isCorrectJustification": false, "explanation": "Why wrong"}},
        {{"text": "False — because [reasoning]", "isTrue": false, "isCorrectJustification": false, "explanation": "Why wrong"}},
        {{"text": "False — because [reasoning]", "isTrue": false, "isCorrectJustification": false, "explanation": "Why wrong"}}
      ],
      "correctIndex": 0
    }}
  ],

  "cause_and_effect": [
    {{
      "prompt": "Match each cause to its effect",
      "pairs": [
        {{"cause": "cause text", "effect": "effect text"}}
      ],
      "distractors": ["wrong effect 1", "wrong effect 2"]
    }}
  ],

  "immediate_vs_long_term": [
    {{
      "prompt": "Classify each cause:",
      "causes": [
        {{"text": "A cause", "type": "immediate", "explanation": "Why immediate"}},
        {{"text": "Another cause", "type": "long-term", "explanation": "Why long-term"}}
      ]
    }}
  ],

  "multiple_choice": [
    {{
      "questionText": "Which of the following best explains...?",
      "choices": [
        {{"text": "Answer A", "explanation": "Why A is right/wrong"}},
        {{"text": "Answer B", "explanation": "Why B is right/wrong"}},
        {{"text": "Answer C", "explanation": "Why C is right/wrong"}},
        {{"text": "Answer D", "explanation": "Why D is right/wrong"}}
      ],
      "correctIndex": 0
    }}
  ],

  "rank_by_significance": [
    {{
      "prompt": "Rank from most to least significant in terms of [criterion]",
      "events": [
        {{"id": "r1", "text": "Event 1", "correctRank": 1, "explanation": "Why #1"}},
        {{"id": "r2", "text": "Event 2", "correctRank": 2, "explanation": "Why #2"}}
      ]
    }}
  ]
}}

IMPORTANT RULES:
0. ALL questions must be fully self-contained. The student learned this material by watching a video — they do NOT have any text, passage, or reading in front of them. NEVER reference "the learning content", "the passage", "the text", "the reading", or "the material". Write every question as a standalone, closed-book knowledge question.
1. For fill_in_the_blank: Use {{blank}} tokens in the prompt. Each blank's alternates must list synonyms, misspellings, and variants. Be generous.
2. For true_false_justification: Exactly 4 choices — 2 True, 2 False. Exactly 1 has isCorrectJustification: true. correctIndex points to it.
3. For cause_and_effect: Exactly 4 pairs + 1-2 distractors. Correct matching is by array index.
4. For immediate_vs_long_term: Exactly 5 causes, mix of "immediate" and "long-term" (hyphen). Each cause has its own explanation.
5. For multiple_choice: Exactly 4 choices with per-choice explanations. correctIndex is 0-based.
6. For rank_by_significance: 4-5 events, each with id, text, correctRank (1-indexed), and explanation.

Respond with ONLY the JSON object. No other text."""


def generate_questions(skill: str) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        temperature=1,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000
        },
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_user_prompt(skill)}
        ]
    )

    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines)

    questions = json.loads(raw_text)

    expected_keys = [
        "fill_in_the_blank", "true_false_justification", "cause_and_effect",
        "immediate_vs_long_term", "multiple_choice", "rank_by_significance"
    ]
    for key in expected_keys:
        if key not in questions:
            raise ValueError(f"Missing question type: {key}")
        if not isinstance(questions[key], list) or len(questions[key]) != 3:
            raise ValueError(f"{key} must have exactly 3 questions, got {len(questions.get(key, []))}")

    return questions


def _call_claude(system: str, user: str, max_tokens: int = 8000) -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    budget = 5000
    actual_max = max(max_tokens, budget + 1024)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=actual_max,
        temperature=1,
        thinking={"type": "enabled", "budget_tokens": budget},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = ""
    for block in response.content:
        if block.type == "text":
            raw += block.text
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw


def detect_relevant_types(skill_text: str, learning_content: str) -> dict:
    type_descriptions = "\n".join(
        f'- "{key}": {info["label"]} — {info["description"]}'
        for key, info in QUESTION_TYPE_INFO.items()
    )

    prompt = f"""Given the following skill and source material, determine which question types are appropriate for testing this material AND assign a weight (percentage) to each.

SKILL: "{skill_text}"

SOURCE MATERIAL (transcript/summary of a video the student watched):
{learning_content}

AVAILABLE QUESTION TYPES:
{type_descriptions}

For each relevant type, assign a weight from 1-100 representing what percentage of the student's question exposure should be that type. The weights of ALL included types MUST sum to exactly 100.

Higher weight = the content is especially well-suited for that question style, so the student should see more of it. Only include types where the content genuinely supports that style. For example, "cause_and_effect" only applies if there are clear causal relationships; "immediate_vs_long_term" only applies if there are temporal cause distinctions.

Return a JSON object mapping question type keys to their integer weights, e.g.:
{{"fill_in_the_blank": 30, "multiple_choice": 40, "true_false_justification": 30}}

The values MUST sum to exactly 100. Return ONLY the JSON object."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=1000)
    weights = json.loads(raw)
    valid_keys = set(QUESTION_TYPE_INFO.keys())
    filtered = {k: int(v) for k, v in weights.items() if k in valid_keys and int(v) > 0}
    if not filtered:
        return {}
    total = sum(filtered.values())
    if total != 100:
        for k in filtered:
            filtered[k] = round(filtered[k] * 100 / total)
        diff = 100 - sum(filtered.values())
        if diff != 0:
            top_key = max(filtered, key=filtered.get)
            filtered[top_key] += diff
    return filtered


DOK_INSTRUCTIONS = {
    "2": "Generate a DOK 2 (fact recall / skill) question that tests whether the student can remember and explain key terms, definitions, or concepts they learned from studying this topic. The answer should be something a student who paid attention would know.",
    "3": "Generate a DOK 3 (strategic thinking / application) question that requires the student to analyze, compare, apply concepts to new scenarios, or draw conclusions that go beyond simple recall. The student should need to reason, not just remember facts.",
}


def generate_single_question(skill_text: str, learning_content: str, question_type: str, dok_level: str = "2") -> dict:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]
    dok_instruction = DOK_INSTRUCTIONS.get(dok_level, DOK_INSTRUCTIONS["2"])

    prompt = f"""Generate exactly 1 question of type "{info['label']}" about the following skill.

SKILL: "{skill_text}"

SOURCE MATERIAL (for your reference only — the student does NOT see this text; they learned this content by watching a video):
{learning_content}

COGNITIVE DEPTH:
{dok_instruction}

QUESTION TYPE: {info['label']}
SCHEMA (your response must match this structure exactly):
{info['schema']}

RULES:
{info['rules']}

REMINDER: The student watched a video covering this material. They do NOT have any text, passage, or reading in front of them. Every question must be a standalone, closed-book knowledge question.

Return ONLY the JSON object for the single question. No wrapping array, no extra keys."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=4000)
    return json.loads(raw)


def extract_concepts(skill_text: str, learning_content: str, question_type: str) -> list:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]

    prompt = f"""Analyze the following source material and identify the CORE testable concepts — the big ideas a student must understand.

SKILL: "{skill_text}"

SOURCE MATERIAL (transcript/summary of a video the student watched):
{learning_content}

RULES — READ CAREFULLY:
1. Return between 3 and 8 concepts. Most content has 4-6 core ideas. If you find more than 8, you are being too granular — merge related ideas.
2. Each concept should be a DISTINCT big idea, not a sub-detail. For example, if the content covers "relative distance" and mentions it involves social, cultural, and political differences, that is ONE concept ("relative distance"), NOT three.
3. DO NOT split a single idea into multiple entries. "X measures social differences" and "X measures cultural differences" is the SAME concept.
4. DO NOT include trivial facts, specific examples, or numbers as concepts. "954 miles between parks" is NOT a concept — it's an illustrative detail.
5. Each concept should be a short phrase (3-8 words) naming the idea, e.g. "absolute vs relative distance", "choropleth maps", "spatial patterns definition".

Return a JSON array of strings. Return ONLY the JSON array."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=2000)
    concepts = json.loads(raw)
    if not isinstance(concepts, list):
        raise ValueError("Expected a JSON array of concept strings")
    return [c for c in concepts if isinstance(c, str) and c.strip()][:10]


def generate_question_for_concept(skill_text: str, learning_content: str, question_type: str, concept: str) -> dict:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]

    prompt = f"""Generate exactly 1 question of type "{info['label']}" about a specific concept.

SKILL: "{skill_text}"

CONCEPT TO TEST: "{concept}"

SOURCE MATERIAL (for your reference only — the student does NOT see this text; they learned this content by watching a video):
{learning_content}

QUESTION TYPE: {info['label']}
SCHEMA (your response must match this structure exactly):
{info['schema']}

RULES:
{info['rules']}

CRITICAL: The question MUST specifically test the concept "{concept}". Do not invent facts not covered in the source material. The student watched a video covering this material — they do NOT have any text in front of them. Write a standalone, closed-book knowledge question.

Return ONLY the JSON object for the single question. No wrapping array, no extra keys."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=4000)
    return json.loads(raw)


def generate_batch_questions(skill_text: str, learning_content: str, question_type: str, dok_level: str, count: int = 5, exclude_summaries: list = None) -> list:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]
    dok_instruction = DOK_INSTRUCTIONS.get(dok_level, DOK_INSTRUCTIONS["2"])

    exclude_block = ""
    if exclude_summaries:
        numbered = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(exclude_summaries))
        exclude_block = f"\n\nDO NOT DUPLICATE — these questions have already been generated:\n{numbered}\n\nEvery question you create must be meaningfully different from the ones above."

    prompt = f"""Generate exactly {count} questions of type "{info['label']}" about the following skill.

SKILL: "{skill_text}"

SOURCE MATERIAL (for your reference only — the student does NOT see this text; they learned this content by watching a video):
{learning_content}

COGNITIVE DEPTH:
{dok_instruction}

QUESTION TYPE: {info['label']}
SCHEMA (each question in the array must match this structure):
{info['schema']}

RULES:
{info['rules']}{exclude_block}

REMINDER: The student watched a video covering this material. They do NOT have any text, passage, or reading in front of them. Every question must be a standalone, closed-book knowledge question.

Return a JSON array of exactly {count} question objects. No wrapping object, just the array."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=16000)
    questions = json.loads(raw)
    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array")
    return questions


def regenerate_invalid_question(skill_text: str, learning_content: str, question_type: str, dok_level: str, failed_question: dict, validation_reason: str) -> dict:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]
    dok_instruction = DOK_INSTRUCTIONS.get(dok_level, DOK_INSTRUCTIONS["2"])
    failed_json = json.dumps(failed_question, indent=2)

    prompt = f"""A previously generated question was INVALID. Generate a corrected replacement.

SKILL: "{skill_text}"

SOURCE MATERIAL (for your reference only — the student does NOT see this text; they learned this content by watching a video):
{learning_content}

COGNITIVE DEPTH:
{dok_instruction}

QUESTION TYPE: {info['label']}
SCHEMA:
{info['schema']}

RULES:
{info['rules']}

THE PREVIOUS QUESTION THAT FAILED VALIDATION:
{failed_json}

REASON IT WAS INVALID:
{validation_reason}

Generate a NEW, DIFFERENT question that fixes the issue described above. There must be exactly one correct answer with no ambiguity. The student does NOT have any text in front of them — write a standalone, closed-book question.

Return ONLY the JSON object for the single replacement question."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=4000)
    return json.loads(raw)


VALIDATION_SYSTEM = """You are a strict question validator. You will be given source material and a question. Your job is to determine whether the question is valid.

CONTEXT: The student learned this material by watching a video. They do NOT have any text, passage, or reading in front of them when answering. Questions must be standalone.

A question is VALID if:
1. It can be answered correctly using knowledge from the source material (no outside knowledge needed).
2. There is exactly one clearly correct answer (no ambiguity).
3. It is fully self-contained — it does NOT reference "the passage", "the text", "the reading", "the learning content", "the article", "the material", or any other source document the student supposedly has access to.

A question is INVALID if:
- The answer requires knowledge NOT present in the source material.
- Multiple answers could be justified as correct.
- The question is poorly worded or ambiguous.
- The stated correct answer is wrong according to the source material.
- The question references a passage, text, reading, or material that the student does not have. This is an automatic failure.

You MUST respond with valid JSON only — no markdown fences, no explanation outside the JSON."""


def validate_question(learning_content: str, question_type: str, question_data: dict) -> dict:
    question_json = json.dumps(question_data, indent=2)

    prompt = f"""You may ONLY reference the source material below. You have no other knowledge. Pretend you know nothing except what is written here.

SOURCE MATERIAL:
{learning_content}

QUESTION TYPE: {question_type}
QUESTION:
{question_json}

TASK:
1. FIRST, check whether the question references "the passage", "the text", "the reading", "the learning content", "the article", "the material", or any similar phrase that assumes the student has a document in front of them. If it does, the question is AUTOMATICALLY INVALID — the student watched a video and has no text to reference.
2. Attempt to answer this question using ONLY the source material above.
3. Check whether the stated correct answer matches what the source material says.
4. Check whether there is any ambiguity (could multiple answers be correct?).

Return a JSON object:
{{
  "valid": true or false,
  "reason": "Brief explanation of why this question is valid or invalid"
}}"""

    raw = _call_claude(VALIDATION_SYSTEM, prompt, max_tokens=2000)
    result = json.loads(raw)
    return {
        "valid": bool(result.get("valid", False)),
        "reason": result.get("reason", ""),
    }


# ---------------------------------------------------------------------------
# Transcript-to-skill mapping
# ---------------------------------------------------------------------------

MAPPER_SYSTEM = """You are an expert curriculum alignment specialist for AP Human Geography. You map video lecture sections to specific learning objectives (skills).

You MUST respond with valid JSON only — no markdown fences, no explanation, no text outside the JSON object."""


def map_transcripts_to_skills(skills: list, video_sections: list) -> dict:
    """Given a list of skill dicts ({id, text}) and video section dicts
    ({topic, topic_name, section, label, content_summary}), return a mapping
    of skill_id -> [(topic_id, section_num), ...].

    Skills with no matching video content map to an empty list.
    """
    skills_block = "\n".join(
        f'  {s["id"]}: "{s["text"]}"' for s in skills
    )
    sections_block = "\n".join(
        f'  Topic {vs["topic"]} §{vs["section"]} "{vs["label"]}": {vs["content_summary"]}'
        for vs in video_sections
    )

    prompt = f"""You are mapping Heimler's History AP Human Geography video sections to specific skill objectives.

SKILLS (the learning objectives a student must master):
{skills_block}

AVAILABLE VIDEO SECTIONS (each has a topic ID and section number):
{sections_block}

TASK:
For each skill, identify which video section(s) teach that skill's content. A skill may map to 0, 1, or multiple sections. A section may be used for multiple skills.

RULES:
- Only assign a section to a skill if the section's content summary clearly covers the skill's topic.
- If no section covers a skill, map it to an empty array.
- Be precise — don't assign a section just because it's from the same topic. The content summary must actually cover what the skill describes.
- Each mapping value is an array of [topic_id, section_number] pairs.

Return a JSON object where keys are skill IDs and values are arrays of [topic_id, section_number] pairs:
{{
  "U2S1": [["2.1", 1]],
  "U2S2": [["2.1", 2], ["2.1", 3]],
  "U2S3": []
}}

Return ONLY the JSON object."""

    raw = _call_claude(MAPPER_SYSTEM, prompt, max_tokens=8000)
    mapping = json.loads(raw)

    result = {}
    for skill in skills:
        sid = skill["id"]
        refs = mapping.get(sid, [])
        result[sid] = [(str(r[0]), int(r[1])) for r in refs if isinstance(r, list) and len(r) == 2]
    return result
