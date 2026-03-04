"""
One-time import script: reads Heimler AP Human Geography transcripts and
extracts the relevant video section data for each Unit 1 skill node into skill_data.json.
"""

import json
import sys
from pathlib import Path

TRANSCRIPTS_PATH = Path.home() / "Downloads" / "ap-human-geography-transcripts.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from services.skill_store import save_learning_content


def load_unit1_videos() -> dict:
    with open(TRANSCRIPTS_PATH) as f:
        data = json.load(f)
    videos = {}
    for v in data["videos"]:
        if v["unit"] == 1 and "Review" not in str(v["topic"]):
            videos[v["topic"]] = v
    return videos


def get_section_transcript(video: dict, section_num: int) -> str:
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


def build_source_object(video: dict, section_num: int) -> dict:
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


# Maps each skill to a list of (topic_id, section_number) tuples.
# Empty list = no matching Heimler content.
MAPPING = {
    # --- Topic 1.1: Introduction to Maps ---
    "U1S1":  [("1.1", 1)],                # spatial patterns defined
    "U1S2":  [],                           # physical vs human geography — not taught
    "U1S3":  [("1.1", 3)],                # reference maps
    "U1S4":  [("1.1", 3)],                # thematic maps
    "U1S5":  [("1.1", 3)],                # choropleth maps (introduced in section 3)
    "U1S6":  [("1.1", 4)],                # dot distribution maps
    "U1S7":  [("1.1", 4)],                # graduated symbol maps
    "U1S8":  [("1.1", 4)],                # isoline maps
    "U1S9":  [("1.1", 4)],                # cartograms
    "U1S10": [("1.4", 2)],                # absolute location (lat/long)
    "U1S11": [("1.4", 2)],                # relative location
    "U1S12": [("1.1", 1)],                # absolute vs relative distance
    "U1S13": [("1.1", 2)],                # absolute vs relative direction
    "U1S14": [("1.1", 2), ("1.4", 5)],    # clustered patterns
    "U1S15": [("1.1", 2), ("1.4", 5)],    # dispersed patterns
    "U1S16": [("1.4", 5)],                # linear patterns
    "U1S17": [("1.1", 2)],                # map scale
    "U1S18": [("1.1", 2)],                # large-scale vs small-scale maps
    "U1S19": [("1.1", 5)],                # map projections distort
    "U1S20": [("1.1", 5)],                # Mercator projection
    "U1S21": [("1.1", 5)],                # equal-area (Peters) projection
    # --- Topic 1.2: Geographic Data ---
    "U1S22": [("1.2", 3)],                # GIS
    "U1S23": [("1.2", 3)],                # GPS
    "U1S24": [("1.2", 3)],                # remote sensing
    "U1S25": [("1.2", 2)],                # quantitative vs qualitative data
    "U1S26": [("1.2", 1)],                # fieldwork methods
    # --- Topic 1.3: The Power of Geographic Data ---
    "U1S27": [("1.3", 3)],                # geospatial data → government policy
    "U1S28": [("1.3", 3)],                # geospatial data → businesses
    # --- Topic 1.4: Spatial Concepts ---
    "U1S29": [("1.4", 3)],                # space
    "U1S30": [("1.4", 3)],                # place
    "U1S31": [],                           # site — not covered
    "U1S32": [],                           # situation — not covered
    "U1S33": [("1.4", 4)],                # distance decay
    "U1S34": [("1.4", 4)],                # time-space compression
    "U1S35": [("1.4", 3)],                # spatial interaction / flow
    "U1S36": [("1.4", 5)],                # pattern
    # --- Topic 1.5: Human-Environmental Interaction ---
    "U1S37": [("1.5", 2)],                # sustainability
    "U1S38": [("1.5", 1)],                # human-environment interaction
    "U1S39": [("1.5", 1)],                # natural resources
    "U1S40": [("1.5", 1)],                # renewable vs nonrenewable
    "U1S41": [("1.5", 3)],                # environmental determinism
    "U1S42": [("1.5", 3)],                # possibilism
    # --- Topic 1.6: Scales of Analysis ---
    "U1S43": [("1.6", 1)],                # four scales of analysis
    "U1S44": [("1.6", 2), ("1.6", 3)],    # different scales reveal different patterns
    # --- Topic 1.7: Regional Analysis ---
    "U1S45": [("1.7", 1)],                # formal regions
    "U1S46": [("1.7", 2)],                # functional regions
    "U1S47": [("1.7", 3)],                # perceptual/vernacular regions
    "U1S48": [("1.7", 1)],                # regions constructed by geographers
    "U1S49": [("1.7", 3)],                # regional boundaries overlap and change
}


def main():
    videos = load_unit1_videos()

    imported = 0
    empty = 0

    for skill_id in sorted(MAPPING.keys(), key=lambda s: int(s.replace("U1S", ""))):
        section_refs = MAPPING[skill_id]
        if not section_refs:
            save_learning_content(skill_id, "", sources=[])
            empty += 1
            print(f"  {skill_id}: NO CONTENT (flagged red)")
            continue

        transcripts = []
        sources = []
        for topic_id, section_num in section_refs:
            vid = videos.get(topic_id)
            if not vid:
                print(f"  WARNING: {skill_id} — topic {topic_id} not found")
                continue
            src = build_source_object(vid, section_num)
            transcript = get_section_transcript(vid, section_num)
            if src and transcript:
                sources.append(src)
                transcripts.append(transcript)
            else:
                print(f"  WARNING: {skill_id} — section {section_num} not found in topic {topic_id}")

        content = "\n\n".join(transcripts)
        save_learning_content(skill_id, content, sources=sources)
        imported += 1
        print(f"  {skill_id}: {len(content)} chars, {len(sources)} source(s)")

    print(f"\nDone. {imported} skills with content, {empty} skills with no content.")


if __name__ == "__main__":
    main()
