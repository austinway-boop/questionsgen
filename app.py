import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    map_transcripts_to_skills,
    QUESTION_TYPE_INFO,
)
from services.mmd_parser import parse_skill_tree
from services.skill_store import get_skill, get_all_content_status, save_learning_content, save_relevant_types, get_source_groups
from services.question_bank_store import (
    get_skill_bank,
    save_concepts,
    save_question,
    save_questions_batch,
    replace_skill_bank,
    mark_met,
    get_coverage_status,
    get_all_bank_status,
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


@app.route("/learn")
def learn():
    return render_template("learn.html")


@app.route("/skill-source-groups")
def skill_source_groups():
    return jsonify(get_source_groups())


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

    with ThreadPoolExecutor(max_workers=min(len(type_keys), 4)) as pool:
        fmap = {pool.submit(extract_concepts, skill_text, lc, qt): qt for qt in type_keys}
        for future in as_completed(fmap):
            qtype = fmap[future]
            try:
                concepts = future.result()
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

    tasks = []
    for qtype, type_data in bank.items():
        concepts = type_data.get("concepts", [])
        result[qtype] = []
        for idx, concept in enumerate(concepts):
            tasks.append((qtype, idx, concept))

    def _generate_one(qtype, idx, concept):
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
        return qtype, entry

    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
        futures = [pool.submit(_generate_one, *t) for t in tasks]
        for future in as_completed(futures):
            qtype, entry = future.result()
            result[qtype].append(entry)

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
        return q.get("prompt", "")[:80]
    if qtype == "multiple_choice":
        return q.get("questionText", "")[:80]
    if qtype == "true_false_justification":
        return q.get("statement", "")[:80]
    if qtype == "cause_and_effect":
        return q.get("prompt", "")[:80]
    if qtype == "immediate_vs_long_term":
        return q.get("prompt", "")[:80]
    if qtype == "rank_by_significance":
        return q.get("prompt", "")[:80]
    return str(q)[:80]


# ── Step-based bank building (Vercel-compatible) ─────────────────────

@app.route("/skill/<skill_id>/generate-batch", methods=["POST"])
def generate_batch_endpoint(skill_id):
    data = request.get_json()
    qtype = data.get("question_type", "").strip()
    dok_level = data.get("dok_level", "2")
    exclude_summaries = data.get("exclude_summaries", [])
    count = min(int(data.get("count", BATCH_SIZE)), BATCH_SIZE)

    if not qtype:
        return jsonify({"error": "question_type is required"}), 400

    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content"}), 400

    skill_text = _find_skill_text(skill_id)
    try:
        questions = generate_batch_questions(
            skill_text, lc, qtype, dok_level,
            count=count, exclude_summaries=exclude_summaries,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    summaries = [_summarize_question(qtype, q) for q in questions]
    return jsonify({"questions": questions, "summaries": summaries})


@app.route("/skill/<skill_id>/validate-batch", methods=["POST"])
def validate_batch_endpoint(skill_id):
    data = request.get_json()
    qtype = data.get("question_type", "").strip()
    dok_level = data.get("dok_level", "2")
    questions = data.get("questions", [])

    if not qtype or not questions:
        return jsonify({"error": "question_type and questions are required"}), 400

    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    skill_text = _find_skill_text(skill_id)

    results = []
    for q_data in questions:
        current_q = q_data
        is_valid = False
        val_reason = ""

        for attempt in range(1 + MAX_RETRIES):
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
                try:
                    current_q = regenerate_invalid_question(
                        skill_text, lc, qtype, dok_level, current_q, val_reason,
                    )
                except Exception:
                    pass

        results.append({
            "question_data": current_q,
            "valid": is_valid,
            "validation_reason": val_reason,
        })

    return jsonify({"results": results})


@app.route("/skill/<skill_id>/save-bank", methods=["POST"])
def save_bank_endpoint(skill_id):
    data = request.get_json()
    bank_data = data.get("bank_data")
    if not bank_data:
        return jsonify({"error": "bank_data is required"}), 400
    replace_skill_bank(skill_id, bank_data)
    return jsonify({"ok": True})


# ── SSE-based bank building (local dev) ──────────────────────────────

@app.route("/skill/<skill_id>/build-bank")
def build_bank_stream(skill_id):
    skill_data = get_skill(skill_id)
    lc = skill_data.get("learning_content", "")
    if not lc.strip():
        return jsonify({"error": "No learning content saved for this skill"}), 400

    skill_text = _find_skill_text(skill_id)

    def generate():
        yield _sse_event({"phase": "start", "message": "Starting question bank build..."})

        # Phase 1: Detect types (single call)
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

        # Phase 2: Extract concepts (parallel across types)
        yield _sse_event({"phase": "extract_concepts", "message": "Extracting concepts (parallel)..."})
        all_concepts = {}
        total_concepts = 0
        with ThreadPoolExecutor(max_workers=min(len(types), 4)) as pool:
            fmap = {pool.submit(extract_concepts, skill_text, lc, qt): qt for qt in types}
            for future in as_completed(fmap):
                qtype = fmap[future]
                try:
                    concepts = future.result()
                    save_concepts(skill_id, qtype, concepts)
                    all_concepts[qtype] = concepts
                    total_concepts += len(concepts)
                    yield _sse_event({"phase": "extract_concepts", "message": f"Extracted {len(concepts)} concepts for {qtype}", "qtype": qtype, "count": len(concepts)})
                except Exception as e:
                    all_concepts[qtype] = []
                    yield _sse_event({"phase": "extract_concepts", "message": f"Concept extraction failed for {qtype}: {e}", "qtype": qtype, "error": True})
        yield _sse_event({"phase": "extract_concepts", "message": f"Total: {total_concepts} concepts across {len(types)} types", "done": True})

        # Phase 3: Generate + Validate + Retry (parallel across all qtype/dok combos)
        bank_data = {}
        for qtype in types:
            bank_data[qtype] = {"concepts": all_concepts.get(qtype, []), "questions": []}

        event_q = queue.Queue()
        bank_lock = threading.Lock()
        counters = {"saved": 0, "discarded": 0}
        counter_lock = threading.Lock()

        def _process_combo(qtype, dok):
            dok_label = f"DOK {dok}"
            event_q.put(_sse_event({"phase": "generate", "message": f"Generating {dok_label} {qtype}...", "qtype": qtype, "dok": dok}))

            generated = []
            num_batches = (QUESTIONS_PER_DOK + BATCH_SIZE - 1) // BATCH_SIZE
            exclude_summaries = []

            for batch_idx in range(num_batches):
                remaining = QUESTIONS_PER_DOK - len(generated)
                batch_count = min(BATCH_SIZE, remaining)
                if batch_count <= 0:
                    break

                event_q.put(_sse_event({
                    "phase": "generate",
                    "message": f"Generating {dok_label} {qtype} (batch {batch_idx + 1}/{num_batches})...",
                    "qtype": qtype, "dok": dok,
                    "progress": {"generated": len(generated), "total": QUESTIONS_PER_DOK},
                }))

                try:
                    batch = generate_batch_questions(skill_text, lc, qtype, dok, count=batch_count, exclude_summaries=exclude_summaries)
                    for q in batch:
                        generated.append(q)
                        exclude_summaries.append(_summarize_question(qtype, q))
                except Exception as e:
                    event_q.put(_sse_event({"phase": "generate", "message": f"Batch failed for {dok_label} {qtype}: {e}", "error": True}))

            event_q.put(_sse_event({
                "phase": "validate",
                "message": f"Validating {len(generated)} {dok_label} {qtype} questions...",
                "qtype": qtype, "dok": dok,
            }))

            def _validate_one(q_idx, q_data):
                q_id = f"{skill_id}-{qtype[:4]}-d{dok}-{q_idx}"
                current_q = q_data
                is_valid = False
                val_reason = ""

                for attempt in range(1 + MAX_RETRIES):
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
                        event_q.put(_sse_event({
                            "phase": "retry",
                            "message": f"Retrying {dok_label} {qtype} Q{q_idx + 1} (attempt {attempt + 2}/{1 + MAX_RETRIES})...",
                            "qtype": qtype, "dok": dok,
                        }))
                        try:
                            current_q = regenerate_invalid_question(skill_text, lc, qtype, dok, current_q, val_reason)
                        except Exception:
                            pass

                return q_idx, q_id, current_q, is_valid, val_reason

            # Parallel validation within this combo
            validated = []
            local_discarded = 0
            with ThreadPoolExecutor(max_workers=min(len(generated), 5)) as val_pool:
                val_futures = {val_pool.submit(_validate_one, idx, q): idx for idx, q in enumerate(generated)}
                done_count = 0
                for future in as_completed(val_futures):
                    q_idx, q_id, current_q, is_valid, val_reason = future.result()
                    done_count += 1
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
                        local_discarded += 1

                    if done_count % 5 == 0 or done_count == len(generated):
                        event_q.put(_sse_event({
                            "phase": "validate",
                            "message": f"Validated {done_count}/{len(generated)} {dok_label} {qtype} ({len(validated)} passed)",
                            "qtype": qtype, "dok": dok,
                            "progress": {"checked": done_count, "total": len(generated), "passed": len(validated)},
                        }))

            with bank_lock:
                bank_data[qtype]["questions"].extend(validated)
            with counter_lock:
                counters["saved"] += len(validated)
                counters["discarded"] += local_discarded

            event_q.put(_sse_event({
                "phase": "validate",
                "message": f"{dok_label} {qtype}: {len(validated)} valid, {len(generated) - len(validated)} discarded",
                "qtype": qtype, "dok": dok, "done": True,
                "saved": len(validated), "discarded": len(generated) - len(validated),
            }))

        # Launch all (qtype, dok) combos in parallel
        combo_count = len(types) * 2
        with ThreadPoolExecutor(max_workers=min(combo_count, 6)) as pool:
            futures = []
            for qtype in types:
                for dok in ["2", "3"]:
                    futures.append(pool.submit(_process_combo, qtype, dok))

            while True:
                try:
                    event = event_q.get(timeout=0.5)
                    yield event
                except queue.Empty:
                    if all(f.done() for f in futures):
                        while not event_q.empty():
                            yield event_q.get_nowait()
                        break

            for f in futures:
                try:
                    f.result()
                except Exception:
                    pass

        replace_skill_bank(skill_id, bank_data)

        yield _sse_event({
            "phase": "done",
            "message": f"Question bank complete. {counters['saved']} questions saved, {counters['discarded']} discarded.",
            "total_saved": counters["saved"],
            "total_discarded": counters["discarded"],
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


# ── Transcript data helpers ──────────────────────────────────────────────

_TRANSCRIPTS_PATH = Path(__file__).resolve().parent / "data" / "transcripts.json"
_transcripts_cache = None


def _load_transcripts() -> dict:
    global _transcripts_cache
    if _transcripts_cache is None:
        _transcripts_cache = json.loads(_TRANSCRIPTS_PATH.read_text())
    return _transcripts_cache


def _get_unit_videos(unit_num: int) -> dict:
    """Return {topic_id: video_dict} for a unit, excluding reviews."""
    data = _load_transcripts()
    videos = {}
    for v in data["videos"]:
        if v["unit"] == unit_num and "Review" not in str(v.get("topic", "")):
            videos[v["topic"]] = v
    return videos


def _get_section_transcript(video: dict, section_num: int) -> str:
    sec = None
    for s in video.get("video_sections", []):
        if s["section"] == section_num:
            sec = s
            break
    if not sec:
        return ""
    start = sec["start_seconds"]
    end = sec["end_seconds"]
    segments = video.get("transcript_segments", [])
    words = [s["text"] for s in segments if start <= s["timestamp_seconds"] < end]
    return " ".join(words)


def _build_source_object(video: dict, section_num: int):
    sec = None
    for s in video.get("video_sections", []):
        if s["section"] == section_num:
            sec = s
            break
    if not sec:
        return None
    return {
        "topic": video["topic"],
        "topic_name": video["topic_name"],
        "section": sec["section"],
        "section_label": sec["label"],
        "start_timestamp": sec["start_timestamp"],
        "end_timestamp": sec["end_timestamp"],
        "start_seconds": sec["start_seconds"],
        "video_title": video["video_title"],
        "youtube_url": f"{video['youtube_url']}&t={sec['start_seconds']}",
        "clip": sec.get("clip_filename", ""),
        "summary": sec["content_summary"],
    }


# ── Pipeline status ──────────────────────────────────────────────────────

@app.route("/pipeline-status")
def pipeline_status():
    content_status = get_all_content_status()
    bank_status = get_all_bank_status()

    tree = _get_tree()
    result = {}
    for unit in tree["units"]:
        for skill in unit["skills"]:
            sid = skill["id"]
            cs = content_status.get(sid, {"has_content": False, "content_source": ""})
            has_content = cs["has_content"]
            content_source = cs["content_source"]
            has_bank = bank_status.get(sid, False)
            if has_content and has_bank:
                result[sid] = "complete"
            elif has_content and content_source == "manual":
                result[sid] = "manual_content"
            elif has_content:
                result[sid] = "content_only"
            else:
                result[sid] = "none"
    return jsonify(result)


# ── Transcript mapping SSE ───────────────────────────────────────────────

@app.route("/unit/<int:unit_num>/map-transcripts")
def map_transcripts_stream(unit_num):
    tree = _get_tree()
    unit_data = None
    for u in tree["units"]:
        if u["id"] == f"U{unit_num}":
            unit_data = u
            break
    if not unit_data:
        return jsonify({"error": f"Unit {unit_num} not found"}), 404

    skills = unit_data["skills"]
    videos = _get_unit_videos(unit_num)

    if not videos:
        return jsonify({"error": f"No transcript videos found for unit {unit_num}"}), 404

    video_sections = []
    for topic_id, video in sorted(videos.items()):
        for sec in video.get("video_sections", []):
            video_sections.append({
                "topic": topic_id,
                "topic_name": video["topic_name"],
                "section": sec["section"],
                "label": sec["label"],
                "content_summary": sec["content_summary"],
            })

    def stream():
        yield _sse_event({"phase": "start", "message": f"Mapping transcripts for Unit {unit_num} ({len(skills)} skills, {len(video_sections)} video sections)..."})

        yield _sse_event({"phase": "mapping", "message": "Sending skills and video sections to Claude for alignment..."})
        try:
            mapping = map_transcripts_to_skills(skills, video_sections)
        except Exception as e:
            yield _sse_event({"phase": "error", "message": f"Mapping failed: {e}"})
            return

        mapped_count = sum(1 for refs in mapping.values() if refs)
        empty_count = sum(1 for refs in mapping.values() if not refs)
        yield _sse_event({"phase": "mapping", "message": f"Mapping complete: {mapped_count} skills matched, {empty_count} with no match"})

        yield _sse_event({"phase": "saving", "message": "Extracting transcripts and saving learning content..."})

        saved = 0
        skipped = 0
        for skill in skills:
            sid = skill["id"]
            refs = mapping.get(sid, [])
            if not refs:
                save_learning_content(sid, "", sources=[])
                skipped += 1
                continue

            transcripts = []
            sources = []
            for topic_id, section_num in refs:
                vid = videos.get(topic_id) or videos.get(str(topic_id))
                if not vid:
                    continue
                src = _build_source_object(vid, section_num)
                transcript = _get_section_transcript(vid, section_num)
                if src and transcript:
                    sources.append(src)
                    transcripts.append(transcript)

            content = "\n\n".join(transcripts)
            save_learning_content(sid, content, sources=sources)
            saved += 1

            if saved % 5 == 0:
                yield _sse_event({"phase": "saving", "message": f"Saved {saved} skills..."})

        yield _sse_event({
            "phase": "done",
            "message": f"Done. {saved} skills with content, {skipped} with no matching video sections.",
            "saved": saved,
            "skipped": skipped,
        })

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
