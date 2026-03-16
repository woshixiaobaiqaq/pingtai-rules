from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

MATCHABLE_CHAR_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class FuzzyMatchResult:
    query: str
    matched_text: str
    start: int
    end: int
    score: float


def text_similarity(left: str, right: str) -> float:
    left_normalized, _ = _normalize_with_mapping(left)
    right_normalized, _ = _normalize_with_mapping(right)
    return _normalized_similarity(left_normalized, right_normalized)


def find_fuzzy_match(text: str, query: str) -> FuzzyMatchResult | None:
    normalized_text, text_mapping = _normalize_with_mapping(text)
    normalized_query, _ = _normalize_with_mapping(query)

    if len(normalized_query) < 3 or len(normalized_text) < len(normalized_query) - 1:
        return None

    exact_index = normalized_text.find(normalized_query)
    if exact_index >= 0:
        start = text_mapping[exact_index]
        end = text_mapping[exact_index + len(normalized_query) - 1] + 1
        return FuzzyMatchResult(
            query=query,
            matched_text=text[start:end],
            start=start,
            end=end,
            score=1.0,
        )

    best_score = 0.0
    best_window: tuple[int, int] | None = None
    delta = max(1, len(normalized_query) // 3)
    min_window = max(3, len(normalized_query) - delta)
    max_window = min(len(normalized_text), len(normalized_query) + delta)

    for window_size in range(min_window, max_window + 1):
        for start_index in range(0, len(normalized_text) - window_size + 1):
            end_index = start_index + window_size
            candidate = normalized_text[start_index:end_index]
            score = _normalized_similarity(normalized_query, candidate)
            if score > best_score:
                best_score = score
                best_window = (start_index, end_index)

    if best_window is None or best_score < _default_threshold(len(normalized_query)):
        return None

    window_text = normalized_text[best_window[0] : best_window[1]]
    if len(set(window_text).intersection(set(normalized_query))) < max(2, len(set(normalized_query)) // 2):
        return None

    start = text_mapping[best_window[0]]
    end = text_mapping[best_window[1] - 1] + 1
    return FuzzyMatchResult(
        query=query,
        matched_text=text[start:end],
        start=start,
        end=end,
        score=round(best_score, 4),
    )


def _normalize_with_mapping(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    mapping: list[int] = []
    for index, char in enumerate(text.lower()):
        if MATCHABLE_CHAR_PATTERN.fullmatch(char):
            normalized_chars.append(char)
            mapping.append(index)
    return "".join(normalized_chars), mapping


def _normalized_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    ngram_size = 2 if min(len(left), len(right)) >= 2 else 1
    left_ngrams = _build_ngrams(left, ngram_size)
    right_ngrams = _build_ngrams(right, ngram_size)
    overlap = 0.0
    if left_ngrams and right_ngrams:
        overlap = (2 * len(left_ngrams.intersection(right_ngrams))) / (len(left_ngrams) + len(right_ngrams))

    sequence_ratio = SequenceMatcher(None, left, right).ratio()
    char_overlap = len(set(left).intersection(set(right))) / max(len(set(left)), 1)
    length_ratio = min(len(left), len(right)) / max(len(left), len(right))

    score = (0.65 * sequence_ratio) + (0.25 * overlap) + (0.1 * char_overlap * length_ratio)
    return round(score, 4)


def _build_ngrams(text: str, size: int) -> set[str]:
    if len(text) <= size:
        return {text}
    return {text[index : index + size] for index in range(0, len(text) - size + 1)}


def _default_threshold(query_length: int) -> float:
    if query_length <= 3:
        return 0.88
    if query_length <= 4:
        return 0.8
    if query_length <= 6:
        return 0.76
    return 0.72
