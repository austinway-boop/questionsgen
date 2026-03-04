import json
import os
import anthropic

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are an expert educational assessment designer. You create rigorous, thought-provoking questions that test deep understanding, not just memorization.

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
        "description": "A sentence with a key term blanked out. Tests recall of essential vocabulary and concepts.",
        "schema": """{
  "question_text": "Sentence with _____ for the blank",
  "acceptable_answers": ["best answer", "also valid", "another synonym"],
  "explanation": "Why this matters for understanding"
}""",
        "rules": """ONLY blank out a single proper term or key vocabulary word — never blank a common word like "the", "is", "are", etc. The blanked term must be a specific concept name, defined term, or technical phrase from the content (e.g. "spatial patterns", "absolute distance", "choropleth map"). The sentence around the blank must give enough context that there is exactly ONE correct term. If a reasonable student could fill in two different terms and both be right, the question is bad — rewrite it.

acceptable_answers MUST list 5-8 entries: the exact term, common synonyms, abbreviations, plural/singular variants, and likely misspellings. For "environmental determinism" also accept "determinism", "enviromental determinism", etc. Be generous — if the answer shows understanding, it should count.

NEVER blank out a number, a proper noun that is just a name (e.g. "Brooklyn"), or trivial filler.""",
    },
    "true_false_justification": {
        "label": "True / False + Justification",
        "description": "A single statement the student must judge as true or false, plus a justification they must evaluate. Tests critical reasoning.",
        "schema": """{
  "statement": "A clear factual claim about the topic",
  "is_true": true or false,
  "justification": "A reasoning given for why the statement is true or false",
  "justification_correct": true or false,
  "explanation": "Full explanation of whether the statement is true/false and whether the justification is correct or flawed"
}""",
        "rules": """The statement must be a single, unambiguous factual claim that is CLEARLY true or CLEARLY false based on the learning content. Do NOT write statements that are debatable or partially true. A student who read the material should be able to judge it with confidence.

The justification is a separate piece of reasoning that attempts to explain why the statement is true/false. It can be correct or incorrect REGARDLESS of the statement's truth value. The four possible combos: true statement + correct justification, true statement + wrong justification, false statement + correct justification (explaining why it's false), false statement + wrong justification.

NEVER reference "the learning content", "the passage", or "the text". Write as a standalone claim. Keep the statement to one sentence. Keep the justification to one sentence.""",
    },
    "cause_and_effect": {
        "label": "Cause & Effect Matching",
        "description": "Students match causes to their effects. Tests understanding of causal relationships.",
        "schema": """{
  "instruction": "Match each cause to its effect",
  "causes": ["cause1", "cause2", "cause3", "cause4"],
  "effects": ["effect1", "effect2", "effect3", "effect4"],
  "correct_mapping": {"0": 2, "1": 0, "2": 3, "3": 1},
  "explanation": "Why each cause leads to its effect"
}""",
        "rules": """Exactly 4 causes and 4 effects. correct_mapping maps cause index (string) to effect index (integer). Each cause must map to EXACTLY one effect with no ambiguity — a cause that could plausibly match two effects makes the question unfair. Each cause-effect pair must be a genuinely causal relationship stated or directly implied in the content, not a vague association. Write causes and effects as SHORT, specific phrases (under 15 words each). All effects should be different enough that the mapping is testable.""",
    },
    "immediate_vs_long_term": {
        "label": "Immediate vs. Long-Term Cause",
        "description": "Students classify causes as immediate or long-term. Tests temporal reasoning about events.",
        "schema": """{
  "context": "A scenario or event description",
  "causes": [
    {"text": "A cause", "type": "immediate" or "long_term"}
  ],
  "explanation": "Why each cause is classified that way"
}""",
        "rules": """Exactly 5 causes, mix of "immediate" and "long_term". The context must describe a specific event or outcome from the content. Each cause must be UNAMBIGUOUSLY classifiable — if a reasonable person could argue a cause is both, do not use it. Immediate = direct trigger or proximate cause. Long-term = underlying condition, structural factor, or gradual process. Write each cause as a short phrase (under 15 words).""",
    },
    "multiple_choice": {
        "label": "Multiple Choice",
        "description": "A standard 4-option multiple choice question. Tests comprehension and application of concepts.",
        "schema": """{
  "question_text": "The question being asked",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_answer": 0,
  "explanation": "Why the correct answer is right and why the distractors are wrong"
}""",
        "rules": """Exactly 4 options. correct_answer is the 0-based index. The question MUST be self-contained — NEVER reference "the learning content", "the passage", or "the text".

VALIDATION-CRITICAL RULES:
- There must be exactly ONE correct answer. If two options could both be justified, the question is bad.
- All four options MUST be approximately the same length and level of detail.
- Distractors must be WRONG but PLAUSIBLE — they should sound like they could be right to someone who didn't study, but be clearly incorrect to someone who did.
- Ask about concepts, definitions, relationships, or applications — not trivia like specific numbers or proper nouns unless they are central to the concept.
- The correct answer must be directly supported by the learning content.""",
    },
    "rank_by_significance": {
        "label": "Rank by Significance",
        "description": "Students rank events/factors by significance according to a specified criterion. Tests evaluative thinking.",
        "schema": """{
  "instruction": "Rank these events from most to least significant in terms of [specific criterion]",
  "events": ["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"],
  "correct_order": [2, 0, 4, 1, 3],
  "explanation": "Why this ranking reflects their relative significance"
}""",
        "rules": """Exactly 5 events/factors. correct_order is an array of indices from the events array in ranked order. The instruction MUST specify a clear, objective criterion (e.g. "in terms of geographic scope", "in terms of impact on population distribution").

VALIDATION-CRITICAL: The ranking must be defensible based on the learning content, not subjective opinion. If two items could reasonably swap positions, the question is bad. Choose items with CLEARLY different levels of significance so the ordering is unambiguous. Write each event as a short phrase (under 12 words).""",
    },
    "select_all_true": {
        "label": "Select All That Are True",
        "description": "A statement or concept is presented, followed by 5-6 options. The student must select every option that is true about the statement.",
        "schema": """{
  "statement": "The statement or concept to evaluate",
  "options": [
    {"text": "Option A text", "is_true": true},
    {"text": "Option B text", "is_true": false},
    {"text": "Option C text", "is_true": true},
    {"text": "Option D text", "is_true": false},
    {"text": "Option E text", "is_true": true}
  ],
  "explanation": "Why each option is true or false"
}""",
        "rules": """Exactly 5 options. At least 2 must be true and at least 1 must be false. The statement must be self-contained — NEVER reference "the learning content" or "the passage".

VALIDATION-CRITICAL:
- Each option must be UNAMBIGUOUSLY true or false based on the content. If there is any room for debate, do not include that option.
- False options must be clearly wrong but plausible — they should use real terminology from the content but make an incorrect claim.
- True options must be directly supported by the content, not inferred.
- All options should be approximately the same length.
- The statement should name a specific concept, term, or topic from the content (e.g. "relative distance" not "types of distance").""",
    },
}

def build_user_prompt(skill: str) -> str:
    return f"""Generate exactly 18 questions about the following skill/topic: "{skill}"

Return a JSON object with exactly these 6 keys. Each key maps to an array of exactly 3 question objects.

SCHEMA:

{{
  "fill_in_the_blank": [
    {{
      "question_text": "Sentence with _____ for the blank",
      "acceptable_answers": ["best answer", "also valid", "another synonym"],
      "explanation": "Why this matters for understanding"
    }}
  ],

  "true_false_justification": [
    {{
      "statement": "A clear factual claim about the topic",
      "is_true": true or false,
      "justification": "A reasoning given for why the statement is true or false",
      "justification_correct": true or false,
      "explanation": "Full explanation of whether the statement is true/false and whether the justification is correct or flawed"
    }}
  ],

  "cause_and_effect": [
    {{
      "instruction": "Match each cause to its effect",
      "causes": ["cause1", "cause2", "cause3", "cause4"],
      "effects": ["effect1", "effect2", "effect3", "effect4"],
      "correct_mapping": {{"0": 2, "1": 0, "2": 3, "3": 1}},
      "explanation": "Why each cause leads to its effect"
    }}
  ],

  "immediate_vs_long_term": [
    {{
      "context": "A scenario or event description",
      "causes": [
        {{"text": "A cause", "type": "immediate" or "long_term"}},
        ... (exactly 5 causes per question, mix of immediate and long_term)
      ],
      "explanation": "Why each cause is classified that way"
    }}
  ],

  "multiple_choice": [
    {{
      "question_text": "The question being asked",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": 0,
      "explanation": "Why the correct answer is right and why the distractors are wrong"
    }}
  ],

  "rank_by_significance": [
    {{
      "instruction": "Rank these events from most to least significant in terms of [specific criterion]",
      "events": ["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"],
      "correct_order": [2, 0, 4, 1, 3],
      "explanation": "Why this ranking reflects their relative significance"
    }}
  ]
}}

IMPORTANT RULES:
1. For fill_in_the_blank: Be VERY selective. Only include blanks for terms that are truly essential for understanding. Never ask for obscure trivia. IMPORTANT: acceptable_answers must list ALL reasonably correct responses a student might give — include synonyms, abbreviations, and closely related terms. For example if the answer is "raw materials", also accept "raw goods", "commodities", "goods", "resources", "crops and raw materials", etc. Be generous — if a student's answer shows they understand the concept, it should count.
2. For true_false_justification: Each question is a single statement with a single justification. The statement must be a clear, self-contained factual claim — NEVER reference 'the learning content', 'the passage', or 'the text'. The justification may be correct or incorrect. Make it substantive and arguable.
3. For cause_and_effect: correct_mapping maps cause index (as string) to effect index (as integer).
4. For immediate_vs_long_term: Provide exactly 5 causes per question.
5. For multiple_choice: Exactly 4 options. correct_answer is the 0-based index. Distractors should be plausible but clearly wrong. Test understanding, not trivia.
6. For rank_by_significance: correct_order is an array of indices from the events array in the correct ranked order. The instruction must specify the criterion for ranking.

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

    prompt = f"""Given the following skill and learning content, determine which question types are appropriate for testing this material AND assign a weight (percentage) to each.

SKILL: "{skill_text}"

LEARNING CONTENT:
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
    "2": "Generate a DOK 2 (fact recall / skill) question that tests whether the student can remember and explain key terms, definitions, or concepts directly from the learning content. The answer should be clearly stated in or directly derivable from the material.",
    "3": "Generate a DOK 3 (strategic thinking / application) question that requires the student to analyze, compare, apply concepts to new scenarios, or draw conclusions beyond what is explicitly stated in the learning content. The student should need to reason, not just recall.",
}


def generate_single_question(skill_text: str, learning_content: str, question_type: str, dok_level: str = "2") -> dict:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]
    dok_instruction = DOK_INSTRUCTIONS.get(dok_level, DOK_INSTRUCTIONS["2"])

    prompt = f"""Generate exactly 1 question of type "{info['label']}" about the following skill, using the provided learning content as your source material.

SKILL: "{skill_text}"

LEARNING CONTENT:
{learning_content}

COGNITIVE DEPTH:
{dok_instruction}

QUESTION TYPE: {info['label']}
SCHEMA (your response must match this structure exactly):
{info['schema']}

RULES:
{info['rules']}

Return ONLY the JSON object for the single question. No wrapping array, no extra keys."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=4000)
    return json.loads(raw)


def extract_concepts(skill_text: str, learning_content: str, question_type: str) -> list:
    if question_type not in QUESTION_TYPE_INFO:
        raise ValueError(f"Unknown question type: {question_type}")

    info = QUESTION_TYPE_INFO[question_type]

    prompt = f"""Analyze the following learning content and identify the CORE testable concepts — the big ideas a student must understand.

SKILL: "{skill_text}"

LEARNING CONTENT:
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

    prompt = f"""Generate exactly 1 question of type "{info['label']}" about a specific concept, using the provided learning content as your ONLY source material.

SKILL: "{skill_text}"

CONCEPT TO TEST: "{concept}"

LEARNING CONTENT:
{learning_content}

QUESTION TYPE: {info['label']}
SCHEMA (your response must match this structure exactly):
{info['schema']}

RULES:
{info['rules']}

CRITICAL: The question MUST specifically test the concept "{concept}". The answer must be derivable from the learning content provided. Do not invent facts not present in the content.

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

    prompt = f"""Generate exactly {count} questions of type "{info['label']}" about the following skill, using the provided learning content as your ONLY source material.

SKILL: "{skill_text}"

LEARNING CONTENT:
{learning_content}

COGNITIVE DEPTH:
{dok_instruction}

QUESTION TYPE: {info['label']}
SCHEMA (each question in the array must match this structure):
{info['schema']}

RULES:
{info['rules']}{exclude_block}

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

LEARNING CONTENT:
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

Generate a NEW, DIFFERENT question that fixes the issue described above. The answer must be clearly derivable from the learning content. There must be exactly one correct answer with no ambiguity.

Return ONLY the JSON object for the single replacement question."""

    raw = _call_claude(SYSTEM_PROMPT, prompt, max_tokens=4000)
    return json.loads(raw)


VALIDATION_SYSTEM = """You are a strict question validator. You will be given learning content and a question. Your job is to determine whether the question is valid.

A question is VALID if:
1. It can be answered correctly using ONLY the provided learning content (no outside knowledge needed).
2. There is exactly one clearly correct answer (no ambiguity).

A question is INVALID if:
- The answer requires knowledge NOT present in the learning content.
- Multiple answers could be justified as correct.
- The question is poorly worded or ambiguous.
- The stated correct answer is wrong according to the content.

You MUST respond with valid JSON only — no markdown fences, no explanation outside the JSON."""


def validate_question(learning_content: str, question_type: str, question_data: dict) -> dict:
    question_json = json.dumps(question_data, indent=2)

    prompt = f"""You may ONLY reference the learning content below. You have no other knowledge. Pretend you know nothing except what is written here.

LEARNING CONTENT:
{learning_content}

QUESTION TYPE: {question_type}
QUESTION:
{question_json}

TASK:
1. Attempt to answer this question using ONLY the learning content above.
2. Check whether the stated correct answer matches what the content says.
3. Check whether there is any ambiguity (could multiple answers be correct?).

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
