from services import kv_store

_NS = "skill"


def get_skill(skill_id: str) -> dict:
    entry = kv_store.get_from_namespace(_NS, skill_id)
    if entry is None:
        entry = {"learning_content": "", "relevant_question_types": [], "sources": []}
    if "sources" not in entry:
        entry["sources"] = []
    return entry


def get_all_content_status() -> dict:
    data = kv_store.get_namespace(_NS)
    return {
        sid: bool(entry.get("learning_content", "").strip())
        for sid, entry in data.items()
    }


def save_learning_content(skill_id: str, content: str, sources: list = None):
    entry = get_skill(skill_id)
    entry["learning_content"] = content
    if sources is not None:
        entry["sources"] = sources
    kv_store.set_in_namespace(_NS, skill_id, entry)


def save_relevant_types(skill_id: str, types):
    entry = get_skill(skill_id)
    entry["relevant_question_types"] = types
    kv_store.set_in_namespace(_NS, skill_id, entry)
