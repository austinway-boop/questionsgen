import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "skill_data.json"


def _load() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {}


def _save(data: dict):
    DATA_PATH.write_text(json.dumps(data, indent=2))


def get_skill(skill_id: str) -> dict:
    data = _load()
    default = {
        "learning_content": "",
        "relevant_question_types": [],
        "sources": [],
    }
    entry = data.get(skill_id, default)
    if "sources" not in entry:
        entry["sources"] = []
    return entry


def get_all_content_status() -> dict:
    data = _load()
    return {
        sid: bool(entry.get("learning_content", "").strip())
        for sid, entry in data.items()
    }


def save_learning_content(skill_id: str, content: str, sources: list = None):
    data = _load()
    if skill_id not in data:
        data[skill_id] = {"learning_content": "", "relevant_question_types": [], "sources": []}
    data[skill_id]["learning_content"] = content
    if sources is not None:
        data[skill_id]["sources"] = sources
    _save(data)


def save_relevant_types(skill_id: str, types):
    data = _load()
    if skill_id not in data:
        data[skill_id] = {"learning_content": "", "relevant_question_types": {}, "sources": []}
    data[skill_id]["relevant_question_types"] = types
    _save(data)
