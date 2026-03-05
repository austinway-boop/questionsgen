from services import kv_store


def _ns(course_id="APHG"):
    return "skill" if course_id == "APHG" else f"skill_{course_id}"


_DEFAULT = {
    "learning_content": "",
    "relevant_question_types": [],
    "sources": [],
    "content_source": "",
}


def get_skill(skill_id: str, course_id="APHG") -> dict:
    entry = kv_store.get_from_namespace(_ns(course_id), skill_id)
    if entry is None:
        entry = dict(_DEFAULT)
    for k, v in _DEFAULT.items():
        if k not in entry:
            entry[k] = v
    return entry


def get_all_content_status(course_id="APHG") -> dict:
    """Return {skill_id: {has_content: bool, content_source: str}}."""
    data = kv_store.get_namespace(_ns(course_id))
    result = {}
    for sid, entry in data.items():
        has = bool(entry.get("learning_content", "").strip())
        src = entry.get("content_source", "transcript" if entry.get("sources") else "")
        result[sid] = {"has_content": has, "content_source": src if has else ""}
    return result


def save_learning_content(skill_id: str, content: str, sources: list = None, course_id="APHG"):
    entry = get_skill(skill_id, course_id)
    entry["learning_content"] = content
    if sources is not None:
        entry["sources"] = sources
        entry["content_source"] = "transcript" if sources else ""
    else:
        entry["content_source"] = "manual" if content.strip() else ""
    kv_store.set_in_namespace(_ns(course_id), skill_id, entry)


def get_source_groups(course_id="APHG") -> dict:
    """Return {skillId: [list of sibling skillIds sharing the same source sections]}."""
    data = kv_store.get_namespace(_ns(course_id))
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


def save_relevant_types(skill_id: str, types, course_id="APHG"):
    entry = get_skill(skill_id, course_id)
    entry["relevant_question_types"] = types
    kv_store.set_in_namespace(_ns(course_id), skill_id, entry)
