from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar

import numpy as np


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    x: int
    y: int
    w: int
    h: int


_ocr_cache: ContextVar[dict[tuple[tuple[int, ...], bytes], list[OcrLine]] | None] = ContextVar(
    "paddle_ocr_cache", default=None
)


@contextmanager
def ocr_cache_scope():
    token = _ocr_cache.set({})
    try:
        yield
    finally:
        _ocr_cache.reset(token)


def recognize(image: np.ndarray, minimum_score: float = 0.20) -> list[OcrLine]:
    raise RuntimeError("Use c_vision_lite.board_reader with an initialized LiteOcr engine")


def paddle_text(
    image: np.ndarray,
    psm: int,
    allowlist: str,
    lang: str | None = None,
) -> str:
    del psm, lang, allowlist
    text = "\n".join(line.text for line in recognize(image))
    return text.strip()


def paddle_words(
    image: np.ndarray,
    psm: int,
    lang: str,
) -> list[tuple[str, int, int, int, int]]:
    del psm, lang
    return [(line.text, line.x, line.y, line.w, line.h) for line in recognize(image)]

