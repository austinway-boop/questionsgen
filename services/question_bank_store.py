import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "question_bank.json"


def _load() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {}


def _save(data: dict):
    DATA_PATH.write_text(json.dumps(data, indent=2))


def get_skill_bank(skill_id: str) -> dict:
    data = _load()
    return data.get(skill_id, {})


def save_concepts(skill_id: str, question_type: str, concepts: list):
    data = _load()
    if skill_id not in data:
        data[skill_id] = {}
    if question_type not in data[skill_id]:
        data[skill_id][question_type] = {"concepts": [], "questions": []}
    data[skill_id][question_type]["concepts"] = concepts
    _save(data)


def save_question(skill_id: str, question_type: str, question_entry: dict):
    data = _load()
    if skill_id not in data:
        data[skill_id] = {}
    if question_type not in data[skill_id]:
        data[skill_id][question_type] = {"concepts": [], "questions": []}
    questions = data[skill_id][question_type]["questions"]
    existing_idx = next(
        (i for i, q in enumerate(questions) if q["id"] == question_entry["id"]),
        None,
    )
    if existing_idx is not None:
        questions[existing_idx] = question_entry
    else:
        questions.append(question_entry)
    _save(data)


def save_questions_batch(skill_id: str, question_type: str, entries: list):
    data = _load()
    if skill_id not in data:
        data[skill_id] = {}
    if question_type not in data[skill_id]:
        data[skill_id][question_type] = {"concepts": [], "questions": []}
    questions = data[skill_id][question_type]["questions"]
    existing_ids = {q["id"]: i for i, q in enumerate(questions)}
    for entry in entries:
        idx = existing_ids.get(entry["id"])
        if idx is not None:
            questions[idx] = entry
        else:
            questions.append(entry)
            existing_ids[entry["id"]] = len(questions) - 1
    _save(data)


def replace_skill_bank(skill_id: str, bank_data: dict):
    data = _load()
    data[skill_id] = bank_data
    _save(data)


def update_validation(skill_id: str, question_type: str, question_id: str, valid: bool, reason: str):
    data = _load()
    bank = data.get(skill_id, {}).get(question_type, {})
    for q in bank.get("questions", []):
        if q["id"] == question_id:
            q["valid"] = valid
            q["validation_reason"] = reason
            break
    _save(data)


def mark_met(skill_id: str, question_type: str, question_id: str, met: bool):
    data = _load()
    bank = data.get(skill_id, {}).get(question_type, {})
    for q in bank.get("questions", []):
        if q["id"] == question_id:
            q["met"] = met
            break
    _save(data)


def get_coverage_status(skill_id: str) -> dict:
    bank = get_skill_bank(skill_id)
    result = {}
    for qtype, type_data in bank.items():
        questions = type_data.get("questions", [])
        dok2 = [q for q in questions if q.get("dok") == "2"]
        dok3 = [q for q in questions if q.get("dok") == "3"]
        no_dok = [q for q in questions if "dok" not in q]

        def _stats(qs):
            return {
                "total": len(qs),
                "met": sum(1 for q in qs if q.get("met")),
                "valid": sum(1 for q in qs if q.get("valid") is True),
                "invalid": sum(1 for q in qs if q.get("valid") is False),
            }

        result[qtype] = {
            "dok2": _stats(dok2),
            "dok3": _stats(dok3),
        }
        if no_dok:
            result[qtype]["other"] = _stats(no_dok)
    return result


def clear_skill_bank(skill_id: str, question_type: str = None):
    data = _load()
    if question_type:
        if skill_id in data and question_type in data[skill_id]:
            del data[skill_id][question_type]
    else:
        if skill_id in data:
            del data[skill_id]
    _save(data)
