from services import kv_store

_NS = "skill"

_DEFAULT = {
    "learning_content": "",
    "relevant_question_types": [],
    "sources": [],
    "content_source": "",
}


def get_skill(skill_id: str) -> dict:
    entry = kv_store.get_from_namespace(_NS, skill_id)
    if entry is None:
        entry = dict(_DEFAULT)
    for k, v in _DEFAULT.items():
        if k not in entry:
            entry[k] = v
    return entry


def get_all_content_status() -> dict:
    """Return {skill_id: {has_content: bool, content_source: str}}."""
    data = kv_store.get_namespace(_NS)
    result = {}
    for sid, entry in data.items():
        has = bool(entry.get("learning_content", "").strip())
        src = entry.get("content_source", "transcript" if entry.get("sources") else "")
        result[sid] = {"has_content": has, "content_source": src if has else ""}
    return result


def save_learning_content(skill_id: str, content: str, sources: list = None):
    entry = get_skill(skill_id)
    entry["learning_content"] = content
    if sources is not None:
        entry["sources"] = sources
        entry["content_source"] = "transcript" if sources else ""
    else:
        entry["content_source"] = "manual" if content.strip() else ""
    kv_store.set_in_namespace(_NS, skill_id, entry)


def save_relevant_types(skill_id: str, types):
    entry = get_skill(skill_id)
    entry["relevant_question_types"] = types
    kv_store.set_in_namespace(_NS, skill_id, entry)
