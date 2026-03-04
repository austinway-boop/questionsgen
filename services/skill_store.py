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


def get_source_groups() -> dict:
    """Return {skillId: [list of sibling skillIds sharing the same source sections]}.

    Groups skills by their sorted source fingerprint (topic:section keys).
    Skills with no sources are singletons.
    """
    data = kv_store.get_namespace(_NS)
    fingerprint_to_skills = {}
    for sid, entry in data.items():
        sources = entry.get("sources", [])
        if not sources:
            continue
        fp = tuple(sorted(f"{s.get('topic', '')}:{s.get('section', '')}" for s in sources))
        fingerprint_to_skills.setdefault(fp, []).append(sid)
    result = {}
    for fp, sids in fingerprint_to_skills.items():
        for sid in sids:
            result[sid] = sorted(sids)
    return result


def save_relevant_types(skill_id: str, types):
    entry = get_skill(skill_id)
    entry["relevant_question_types"] = types
    kv_store.set_in_namespace(_NS, skill_id, entry)
