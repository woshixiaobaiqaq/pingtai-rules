from __future__ import annotations

import re

from app.schemas.common import SentenceSegment

SENTENCE_PATTERN = re.compile(r".+?(?:[。！？!?；;…]+|$)", re.S)


class TextProcessor:
    def clean_text(self, content: str) -> str:
        cleaned = content.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def split_sentences(self, content: str) -> list[SentenceSegment]:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        segments: list[SentenceSegment] = []
        sentence_id = 1
        cursor = 0
        for line in normalized.splitlines(keepends=True):
            line_body = line[:-1] if line.endswith("\n") else line
            for match in SENTENCE_PATTERN.finditer(line_body):
                raw_sentence = match.group(0)
                left_trim = len(raw_sentence) - len(raw_sentence.lstrip())
                right_trim = len(raw_sentence) - len(raw_sentence.rstrip())
                start = cursor + match.start() + left_trim
                end = cursor + match.end() - right_trim
                text = raw_sentence.strip()
                if not text:
                    continue
                segments.append(
                    SentenceSegment(
                        sentence_id=sentence_id,
                        text=text,
                        start=start,
                        end=end,
                    )
                )
                sentence_id += 1
            cursor += len(line)
        return segments
