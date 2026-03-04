import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from services.claude_service import (
    generate_questions,
    detect_relevant_types,
    generate_single_question,
    extract_concepts,
    generate_question_for_concept,
    generate_batch_questions,
    regenerate_invalid_question,
    validate_question,
    QUESTION_TYPE_INFO,
)
from services.mmd_parser import parse_skill_tree
from services.skill_store import get_skill, get_all_content_status, save_learning_content, save_relevant_types
from services.question_bank_store import (
    get_skill_bank,
    save_concepts,
    save_question,
    save_questions_batch,
    replace_skill_bank,
    mark_met,
    get_coverage_status,
)

app = Flask(__name__)

_skill_tree_cache = None


def _get_tree():
    global _skill_tree_cache
    if _skill_tree_cache is None:
        _skill_tree_cache = parse_skill_tree()
    return _skill_tree_cache


def _type_keys(types_data) -> list:
    if isinstance(types_data, dict):
        return list(types_data.keys())
    if isinstance(types_data, list):
        return types_data
    return []


def _find_skill_text(skill_id: str) -> str:
    tree = _get_tree()
    for unit in tree["units"]:
        for s in unit["skills"]:
            if s["id"] == skill_id:
                return s["text"]
    return skill_id


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/skill-tree")
def skill_tree():
    return jsonify(_get_tree())


@app.route("/question-types")
def question_types():
    return jsonify({
        key: {"label": info["label"], "description": info["description"]}
        for key, info in QUESTION_TYPE_INFO.items()
    })


@app.route("/skill-content-status")
def skill_content_status():
    return jsonify(get_all_content_status())


@app.route("/skill/<skill_id>")
def skill_detail(skill_id):
    return jsonify(get_skill(skill_id))


@app.route("/skill/<skill_id>/learning-content", methods=["POST"])
def update_learning_content(skill_id):
    data = request.get_json()
    content = data.get("learning_content", "")
    save_learning_content(skill_id, content)
    return jsonify({"ok": True})


@app.route("/skill/<skill_id>/detect-types", methods=["POST"])
def detect_types(skill_id):
    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    skill_text = _find_skill_text(skill_id)
    try:
        types = detect_relevant_types(skill_text, lc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    save_relevant_types(skill_id, types)
    return jsonify({"relevant_question_types": types})


@app.route("/skill/<skill_id>/generate", methods=["POST"])
def generate_skill_question(skill_id):
    data = request.get_json()
    qtype = data.get("question_type", "").strip()
    if not qtype:
        return jsonify({"error": "question_type is required"}), 400

    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    dok_level = data.get("dok_level", "2")
    skill_text = _find_skill_text(skill_id)
    try:
        question = generate_single_question(skill_text, lc, qtype, dok_level=dok_level)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"question_type": qtype, "question": question})


@app.route("/skill/<skill_id>/extract-concepts", methods=["POST"])
def extract_skill_concepts(skill_id):
    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    types_raw = skill_data.get("relevant_question_types", {})
    type_keys = _type_keys(types_raw)
    if not type_keys:
        return jsonify({"error": "No relevant question types detected yet"}), 400

    skill_text = _find_skill_text(skill_id)
    result = {}
    for qtype in type_keys:
        try:
            concepts = extract_concepts(skill_text, lc, qtype)
            save_concepts(skill_id, qtype, concepts)
            result[qtype] = concepts
        except Exception as e:
            result[qtype] = {"error": str(e)}

    return jsonify(result)


@app.route("/skill/<skill_id>/generate-question-bank", methods=["POST"])
def generate_skill_question_bank(skill_id):
    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    bank = get_skill_bank(skill_id)
    if not bank:
        return jsonify({"error": "No concepts extracted yet. Run extract-concepts first."}), 400

    skill_text = _find_skill_text(skill_id)
    result = {}

    for qtype, type_data in bank.items():
        concepts = type_data.get("concepts", [])
        if not concepts:
            continue

        generated = []
        for idx, concept in enumerate(concepts):
            q_id = f"{skill_id}-{qtype[:4]}-{idx}"
            try:
                question_data = generate_question_for_concept(skill_text, lc, qtype, concept)
                validation = validate_question(lc, qtype, question_data)

                entry = {
                    "id": q_id,
                    "concept": concept,
                    "question_data": question_data,
                    "valid": validation["valid"],
                    "validation_reason": validation["reason"],
                    "met": False,
                }
                save_question(skill_id, qtype, entry)
                generated.append(entry)
            except Exception as e:
                entry = {
                    "id": q_id,
                    "concept": concept,
                    "question_data": None,
                    "valid": False,
                    "validation_reason": f"Generation failed: {str(e)}",
                    "met": False,
                }
                save_question(skill_id, qtype, entry)
                generated.append(entry)

        result[qtype] = generated

    return jsonify(result)


@app.route("/skill/<skill_id>/question-bank")
def get_skill_question_bank(skill_id):
    bank = get_skill_bank(skill_id)
    coverage = get_coverage_status(skill_id)
    return jsonify({"bank": bank, "coverage": coverage})


@app.route("/skill/<skill_id>/question-bank/mark", methods=["POST"])
def mark_question_met(skill_id):
    data = request.get_json()
    qtype = data.get("question_type", "")
    q_id = data.get("question_id", "")
    met = data.get("met", True)

    if not qtype or not q_id:
        return jsonify({"error": "question_type and question_id are required"}), 400

    mark_met(skill_id, qtype, q_id, met)
    return jsonify({"ok": True})


MAX_RETRIES = 2
QUESTIONS_PER_DOK = 20
BATCH_SIZE = 5


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _summarize_question(qtype, q):
    if qtype == "fill_in_the_blank":
        return q.get("question_text", "")[:80]
    if qtype == "multiple_choice":
        return q.get("question_text", "")[:80]
    if qtype == "true_false_justification":
        return q.get("statement", "")[:80]
    if qtype == "cause_and_effect":
        return q.get("instruction", "")[:80]
    if qtype == "immediate_vs_long_term":
        return q.get("context", "")[:80]
    if qtype == "rank_by_significance":
        return q.get("instruction", "")[:80]
    if qtype == "select_all_true":
        return q.get("statement", "")[:80]
    return str(q)[:80]


@app.route("/skill/<skill_id>/build-bank")
def build_bank_stream(skill_id):
    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    skill_text = _find_skill_text(skill_id)

    def generate():
        yield _sse_event({"phase": "start", "message": "Starting question bank build..."})

        # Phase 1: Detect types (returns weighted dict)
        yield _sse_event({"phase": "detect_types", "message": "Detecting relevant question types..."})
        try:
            type_weights = detect_relevant_types(skill_text, lc)
            save_relevant_types(skill_id, type_weights)
        except Exception as e:
            yield _sse_event({"phase": "error", "message": f"Type detection failed: {e}"})
            return
        types = list(type_weights.keys())
        weight_summary = ", ".join(f"{k} ({v}%)" for k, v in type_weights.items())
        yield _sse_event({"phase": "detect_types", "message": f"Detected {len(types)} types: {weight_summary}", "types": types, "weights": type_weights})

        # Phase 2: Extract concepts
        yield _sse_event({"phase": "extract_concepts", "message": "Extracting concepts..."})
        all_concepts = {}
        total_concepts = 0
        for qtype in types:
            try:
                concepts = extract_concepts(skill_text, lc, qtype)
                save_concepts(skill_id, qtype, concepts)
                all_concepts[qtype] = concepts
                total_concepts += len(concepts)
                yield _sse_event({"phase": "extract_concepts", "message": f"Extracted {len(concepts)} concepts for {qtype}", "qtype": qtype, "count": len(concepts)})
            except Exception as e:
                all_concepts[qtype] = []
                yield _sse_event({"phase": "extract_concepts", "message": f"Concept extraction failed for {qtype}: {e}", "qtype": qtype, "error": True})
        yield _sse_event({"phase": "extract_concepts", "message": f"Total: {total_concepts} concepts across {len(types)} types", "done": True})

        # Phase 3: Generate + Validate + Retry
        bank_data = {}
        total_saved = 0
        total_discarded = 0

        for qtype in types:
            bank_data[qtype] = {"concepts": all_concepts.get(qtype, []), "questions": []}

            for dok in ["2", "3"]:
                dok_label = "DOK 2" if dok == "2" else "DOK 3"
                yield _sse_event({"phase": "generate", "message": f"Generating {dok_label} {qtype}...", "qtype": qtype, "dok": dok})

                generated = []
                num_batches = (QUESTIONS_PER_DOK + BATCH_SIZE - 1) // BATCH_SIZE
                exclude_summaries = []

                for batch_idx in range(num_batches):
                    remaining = QUESTIONS_PER_DOK - len(generated)
                    batch_count = min(BATCH_SIZE, remaining)
                    if batch_count <= 0:
                        break

                    yield _sse_event({
                        "phase": "generate",
                        "message": f"Generating {dok_label} {qtype} (batch {batch_idx + 1}/{num_batches})...",
                        "qtype": qtype, "dok": dok,
                        "progress": {"generated": len(generated), "total": QUESTIONS_PER_DOK},
                    })

                    try:
                        batch = generate_batch_questions(skill_text, lc, qtype, dok, count=batch_count, exclude_summaries=exclude_summaries)
                        for q in batch:
                            generated.append(q)
                            exclude_summaries.append(_summarize_question(qtype, q))
                    except Exception as e:
                        yield _sse_event({"phase": "generate", "message": f"Batch failed for {dok_label} {qtype}: {e}", "error": True})

                # Validate
                yield _sse_event({
                    "phase": "validate",
                    "message": f"Validating {len(generated)} {dok_label} {qtype} questions...",
                    "qtype": qtype, "dok": dok,
                })

                validated = []
                for q_idx, q_data in enumerate(generated):
                    q_id = f"{skill_id}-{qtype[:4]}-d{dok}-{q_idx}"
                    attempts = 0
                    current_q = q_data
                    is_valid = False
                    val_reason = ""

                    for attempt in range(1 + MAX_RETRIES):
                        attempts += 1
                        try:
                            val = validate_question(lc, qtype, current_q)
                            is_valid = val["valid"]
                            val_reason = val["reason"]
                        except Exception as e:
                            is_valid = False
                            val_reason = f"Validation call failed: {e}"

                        if is_valid:
                            break

                        if attempt < MAX_RETRIES:
                            yield _sse_event({
                                "phase": "retry",
                                "message": f"Retrying {dok_label} {qtype} Q{q_idx + 1} (attempt {attempt + 2}/{1 + MAX_RETRIES})...",
                                "qtype": qtype, "dok": dok,
                            })
                            try:
                                current_q = regenerate_invalid_question(skill_text, lc, qtype, dok, current_q, val_reason)
                            except Exception:
                                pass

                    if is_valid:
                        validated.append({
                            "id": q_id,
                            "dok": dok,
                            "question_data": current_q,
                            "valid": True,
                            "validation_reason": val_reason,
                            "met": False,
                        })
                    else:
                        total_discarded += 1

                    if (q_idx + 1) % 5 == 0 or q_idx == len(generated) - 1:
                        yield _sse_event({
                            "phase": "validate",
                            "message": f"Validated {q_idx + 1}/{len(generated)} {dok_label} {qtype} ({len(validated)} passed)",
                            "qtype": qtype, "dok": dok,
                            "progress": {"checked": q_idx + 1, "total": len(generated), "passed": len(validated)},
                        })

                bank_data[qtype]["questions"].extend(validated)
                total_saved += len(validated)
                yield _sse_event({
                    "phase": "validate",
                    "message": f"{dok_label} {qtype}: {len(validated)} valid, {len(generated) - len(validated)} discarded",
                    "qtype": qtype, "dok": dok, "done": True,
                    "saved": len(validated), "discarded": len(generated) - len(validated),
                })

        # Save everything at once
        replace_skill_bank(skill_id, bank_data)

        yield _sse_event({
            "phase": "done",
            "message": f"Question bank complete. {total_saved} questions saved, {total_discarded} discarded.",
            "total_saved": total_saved,
            "total_discarded": total_discarded,
        })

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    skill = data.get("skill", "").strip()
    if not skill:
        return jsonify({"error": "Skill/topic is required"}), 400

    try:
        questions = generate_questions(skill)
    except Exception as e:
        return jsonify({"error": f"Question generation failed: {str(e)}"}), 500

    return jsonify(questions)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
