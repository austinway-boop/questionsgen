import re
from pathlib import Path
from typing import Optional, Union

MMD_PATH = Path(__file__).resolve().parent.parent / "skill_tree.mmd"


def parse_skill_tree(path: Optional[Union[str, Path]] = None) -> dict:
    path = Path(path) if path else MMD_PATH
    text = path.read_text()

    units = []
    cross_unit_edges = []

    unit_blocks = re.findall(
        r'subgraph\s+(U\d+)\["(.+?)"\]\s*\n(.*?)\n\s*end',
        text,
        re.DOTALL,
    )

    all_skill_ids_by_unit: dict[str, str] = {}

    for unit_id, unit_title, block in unit_blocks:
        skills = []
        edges = []

        for match in re.finditer(r'(U\d+S\d+)\["(.+?)"\]', block):
            sid, label = match.group(1), match.group(2)
            skills.append({"id": sid, "text": label})
            all_skill_ids_by_unit[sid] = unit_id

        for match in re.finditer(r'(U\d+S\d+)\s*-->\s*(U\d+S\d+)', block):
            edges.append([match.group(1), match.group(2)])

        units.append({
            "id": unit_id,
            "title": unit_title,
            "skills": skills,
            "edges": edges,
        })

    for match in re.finditer(r'(U\d+S\d+)\s*-->\s*(U\d+S\d+)', text):
        src, dst = match.group(1), match.group(2)
        src_unit = all_skill_ids_by_unit.get(src)
        dst_unit = all_skill_ids_by_unit.get(dst)
        if src_unit and dst_unit and src_unit != dst_unit:
            pair = [src, dst]
            if pair not in cross_unit_edges:
                cross_unit_edges.append(pair)

    units.sort(key=lambda u: int(re.search(r'\d+', u["id"]).group()))

    return {"units": units, "cross_unit_edges": cross_unit_edges}
