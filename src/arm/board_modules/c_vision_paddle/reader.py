from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import c_vision.reader as original_reader

from c_vision_paddle.backend import ocr_cache_scope, paddle_text, paddle_words
from c_vision_paddle.measurements import locate_panel, read_rows


@contextmanager
def paddle_backend() -> Iterator[None]:
    original_text = original_reader.tesseract_text
    original_words = original_reader.tesseract_words
    original_rows = original_reader.read_dynamic_measurement_rows
    original_panel = original_reader.locate_measurement_panel
    original_reader.tesseract_text = paddle_text
    original_reader.tesseract_words = paddle_words
    original_reader.read_dynamic_measurement_rows = read_rows
    original_reader.locate_measurement_panel = locate_panel
    try:
        with ocr_cache_scope():
            yield
    finally:
        original_reader.tesseract_text = original_text
        original_reader.tesseract_words = original_words
        original_reader.read_dynamic_measurement_rows = original_rows
        original_reader.locate_measurement_panel = original_panel


