import threading
from services import kv_store

_NS = "bank"

# Thread lock for read-modify-write sequences in JSON mode.
# KV mode is inherently atomic per key, but we still lock for
# multi-step operations that read then write the same key.
_lock = threading.Lock()


def get_skill_bank(skill_id: str) -> dict:
    return kv_store.get_from_namespace(_NS, skill_id) or {}


def save_concepts(skill_id: str, question_type: str, concepts: list):
    with _lock:
        bank = get_skill_bank(skill_id)
        if question_type not in bank:
            bank[question_type] = {"concepts": [], "questions": []}
        bank[question_type]["concepts"] = concepts
        kv_store.set_in_namespace(_NS, skill_id, bank)


def save_question(skill_id: str, question_type: str, question_entry: dict):
    with _lock:
        bank = get_skill_bank(skill_id)
        if question_type not in bank:
            bank[question_type] = {"concepts": [], "questions": []}
        questions = bank[question_type]["questions"]
        existing_idx = next(
            (i for i, q in enumerate(questions) if q["id"] == question_entry["id"]),
            None,
        )
        if existing_idx is not None:
            questions[existing_idx] = question_entry
        else:
            questions.append(question_entry)
        kv_store.set_in_namespace(_NS, skill_id, bank)


def save_questions_batch(skill_id: str, question_type: str, entries: list):
    with _lock:
        bank = get_skill_bank(skill_id)
        if question_type not in bank:
            bank[question_type] = {"concepts": [], "questions": []}
        questions = bank[question_type]["questions"]
        existing_ids = {q["id"]: i for i, q in enumerate(questions)}
        for entry in entries:
            idx = existing_ids.get(entry["id"])
            if idx is not None:
                questions[idx] = entry
            else:
                questions.append(entry)
                existing_ids[entry["id"]] = len(questions) - 1
        kv_store.set_in_namespace(_NS, skill_id, bank)


def replace_skill_bank(skill_id: str, bank_data: dict):
    with _lock:
        kv_store.set_in_namespace(_NS, skill_id, bank_data)


def update_validation(skill_id: str, question_type: str, question_id: str, valid: bool, reason: str):
    with _lock:
        bank = get_skill_bank(skill_id)
        type_data = bank.get(question_type, {})
        for q in type_data.get("questions", []):
            if q["id"] == question_id:
                q["valid"] = valid
                q["validation_reason"] = reason
                break
        kv_store.set_in_namespace(_NS, skill_id, bank)


def mark_met(skill_id: str, question_type: str, question_id: str, met: bool):
    with _lock:
        bank = get_skill_bank(skill_id)
        type_data = bank.get(question_type, {})
        for q in type_data.get("questions", []):
            if q["id"] == question_id:
                q["met"] = met
                break
        kv_store.set_in_namespace(_NS, skill_id, bank)


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
    with _lock:
        if question_type:
            bank = get_skill_bank(skill_id)
            bank.pop(question_type, None)
            kv_store.set_in_namespace(_NS, skill_id, bank)
        else:
            kv_store.delete(f"{_NS}:{skill_id}")


def get_all_bank_status() -> dict:
    """Return {skill_id: bool} — True if the skill has any questions."""
    data = kv_store.get_namespace(_NS)
    result = {}
    for skill_id, bank in data.items():
        has_questions = any(
            len(type_data.get("questions", [])) > 0
            for type_data in bank.values()
            if isinstance(type_data, dict)
        )
        result[skill_id] = has_questions
    return result
