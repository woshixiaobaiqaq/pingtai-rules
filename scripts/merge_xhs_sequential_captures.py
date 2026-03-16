from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "data" / "source_archives" / "xiaohongshu_rule_baike"
    capture_dirs = sorted(base.glob("sequential_content_capture_*"))
    merged_dir = base / f"sequential_content_merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    merged_notes_dir = merged_dir / "notes"
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged_notes_dir.mkdir(parents=True, exist_ok=True)

    notes_by_index: dict[int, dict] = {}
    source_dirs: list[str] = []

    for capture_dir in capture_dirs:
        manifest_path = capture_dir / "manifest.json"
        notes_dir = capture_dir / "notes"
        if not manifest_path.exists() or not notes_dir.exists():
            continue
        source_dirs.append(str(capture_dir))
        for note_path in sorted(notes_dir.glob("*.json")):
            note = json.loads(note_path.read_text(encoding="utf-8"))
            index = int(note["index"])
            notes_by_index[index] = note
            merged_note_path = merged_notes_dir / note_path.name
            merged_note_path.write_text(
                json.dumps(note, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    merged_notes = [notes_by_index[index] for index in sorted(notes_by_index)]
    manifest = {
        "source": "xiaohongshu_note_html_fetch_merged",
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "source_dirs": source_dirs,
        "note_count": len(merged_notes),
        "notes_path": str(merged_notes_dir),
        "missing_indexes": [index for index in range(1, 32) if index not in notes_by_index],
    }

    (merged_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (merged_dir / "notes_index.json").write_text(
        json.dumps(merged_notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(merged_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
