from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Iterator

import c_vision.reader as original_reader

from c_vision_paddle.backend import ocr_cache_scope, paddle_text, paddle_words
from c_vision_paddle.measurements import locate_panel, read_rows


DEFAULT_CONFIG = Path("c_vision/configs/keysight_scope_measure.json")
DEFAULT_OUTPUT = Path("c_vision_paddle/runs")


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


def read_image(
    image_path: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
    out_dir: str | Path = DEFAULT_OUTPUT,
    request_id: str | None = None,
):
    with paddle_backend():
        return original_reader.read_instrument_image(
            Path(image_path), Path(config_path), Path(out_dir), request_id
        )


def read_directory(
    input_dir: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
    out_dir: str | Path = DEFAULT_OUTPUT,
):
    with paddle_backend():
        return original_reader.read_instrument_directory(
            Path(input_dir), Path(config_path), Path(out_dir)
        )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        description="Run the LabMate OpenCV pipeline with PaddleOCR."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--input-dir", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--request-id")
    args = parser.parse_args()

    if args.input_dir is not None:
        if args.request_id is not None:
            parser.error("--request-id is only available with --image")
        results = read_directory(args.input_dir, args.config, args.out)
        summary = [
            {
                "image": path.name,
                "run_dir": str(Path(result.image_path).parent),
                "valid": result.valid,
                "error_code": result.error_code,
                "measurements": [asdict(item) for item in result.measurements],
            }
            for path, result in results
        ]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(
            f"Processed {len(results)} image(s): "
            f"{sum(result.valid for _, result in results)} valid, "
            f"{sum(not result.valid for _, result in results)} failed."
        )
        if results:
            print(f"Batch folder: {Path(results[0][1].image_path).parent.parent}")
    else:
        result = read_image(args.image, args.config, args.out, args.request_id)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

