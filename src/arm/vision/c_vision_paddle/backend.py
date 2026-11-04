from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from hashlib import blake2b
from typing import Any, Iterable

import numpy as np
import cv2


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


def _result_dict(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        data = item
    else:
        data = getattr(item, "json", None)
        if callable(data):
            data = data()
    if not isinstance(data, dict):
        return None
    nested = data.get("res")
    return nested if isinstance(nested, dict) else data


def _box_bounds(box: Any) -> tuple[int, int, int, int]:
    points = np.asarray(box, dtype=np.float32)
    if points.shape == (4,):
        x0, y0, x1, y1 = points.tolist()
    else:
        points = points.reshape(-1, 2)
        x0, y0 = points.min(axis=0).tolist()
        x1, y1 = points.max(axis=0).tolist()
    x, y = int(round(x0)), int(round(y0))
    return x, y, max(1, int(round(x1 - x0))), max(1, int(round(y1 - y0)))


def _v3_lines(results: Iterable[Any]) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for item in results:
        data = _result_dict(item)
        if not data:
            continue
        texts = list(data.get("rec_texts", []))
        scores = list(data.get("rec_scores", [1.0] * len(texts)))
        boxes = data.get("rec_boxes")
        if boxes is None or len(boxes) == 0:
            boxes = data.get("rec_polys")
        if boxes is None:
            boxes = []
        for text, score, box in zip(texts, scores, boxes):
            cleaned = str(text).strip()
            if cleaned:
                lines.append(OcrLine(cleaned, float(score), *_box_bounds(box)))
    return lines


def _v2_lines(results: Any) -> list[OcrLine]:
    pages = results if isinstance(results, list) else []
    if len(pages) == 1 and isinstance(pages[0], list):
        pages = pages[0]
    lines: list[OcrLine] = []
    for item in pages:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        box, recognition = item
        if not isinstance(recognition, (list, tuple)) or len(recognition) < 2:
            continue
        text, score = str(recognition[0]).strip(), float(recognition[1])
        if text:
            lines.append(OcrLine(text, score, *_box_bounds(box)))
    return lines


@lru_cache(maxsize=1)
def paddle_engine() -> Any:
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR is unavailable. Install c_vision_paddle/requirements.txt first."
        ) from exc

    options = {
        "enable_mkldnn": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "text_recognition_model_name": "PP-OCRv5_mobile_rec",
    }
    try:
        return PaddleOCR(**options)
    except TypeError:
        options.pop("text_detection_model_name")
        options.pop("text_recognition_model_name")
        return PaddleOCR(**options)


def recognize(image: np.ndarray, minimum_score: float = 0.20) -> list[OcrLine]:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("PaddleOCR input must be a grayscale or BGR image")
    cache = _ocr_cache.get()
    key = (image.shape, blake2b(image.tobytes(), digest_size=16).digest()) if cache is not None else None
    if cache is not None and key in cache:
        lines = cache[key]
    else:
        engine = paddle_engine()
        if hasattr(engine, "predict"):
            lines = _v3_lines(engine.predict(input=image))
        else:
            lines = _v2_lines(engine.ocr(image, cls=False))
        if cache is not None:
            cache[key] = lines
    return sorted(
        (line for line in lines if line.score >= minimum_score),
        key=lambda line: (line.y, line.x),
    )


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

