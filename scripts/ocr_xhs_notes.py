from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR Xiaohongshu note images and save enriched note JSON.")
    parser.add_argument(
        "--notes-index",
        required=True,
        help="Path to merged notes_index.json.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to sibling directory notes_ocr under the notes index parent.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum OCR confidence kept in the final output.",
    )
    return parser


def image_ocr_payload(engine: RapidOCR, image_path: str, min_confidence: float) -> dict:
    result, _ = engine(image_path)
    lines: list[dict] = []
    texts: list[str] = []

    for item in result or []:
        if len(item) < 3:
            continue
        text = (item[1] or "").strip()
        confidence = float(item[2] or 0.0)
        if not text or confidence < min_confidence:
            continue
        lines.append(
            {
                "text": text,
                "confidence": confidence,
            }
        )
        texts.append(text)

    return {
        "image_path": image_path,
        "line_count": len(lines),
        "text": "\n".join(texts),
        "lines": lines,
    }


def main() -> int:
    args = build_parser().parse_args()
    notes_index_path = Path(args.notes_index).expanduser().resolve()
    notes = json.loads(notes_index_path.read_text(encoding="utf-8"))

    base_dir = notes_index_path.parent
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else base_dir / "notes_ocr"
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = RapidOCR()
    enriched_notes = []

    for note in notes:
        image_payloads = []
        combined_parts = []
        for image_path in note.get("images", []):
            payload = image_ocr_payload(engine, image_path, args.min_confidence)
            image_payloads.append(payload)
            if payload["text"]:
                combined_parts.append(payload["text"])

        enriched = dict(note)
        enriched["ocr"] = {
            "image_count": len(image_payloads),
            "images": image_payloads,
            "full_text": "\n\n".join(combined_parts),
        }
        enriched_notes.append(enriched)

        note_path = output_dir / f"{int(note['index']):03d}_{note['note_id']}.json"
        note_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "source": "xhs_notes_ocr",
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "notes_index": str(notes_index_path),
        "note_count": len(enriched_notes),
        "output_dir": str(output_dir),
        "min_confidence": args.min_confidence,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "notes_index_ocr.json").write_text(
        json.dumps(enriched_notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
