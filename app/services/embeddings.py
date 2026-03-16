from __future__ import annotations

import hashlib
import math
import re

from app.core.config import get_settings

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class HashEmbeddingService:
    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension or get_settings().pgvector_dimension

    def embed(self, text: str) -> list[float]:
        tokens = TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 8) for value in vector]

