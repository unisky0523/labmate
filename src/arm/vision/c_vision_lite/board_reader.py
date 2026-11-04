"""Run the PC measurement workflow with ARM Paddle-Lite tensor inference."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import blake2b
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterator
from datetime import datetime
import uuid

import cv2
import numpy as np
import pyclipper

from c_vision_paddle.backend import OcrLine
import c_vision_paddle.backend as backend
from c_vision_paddle.reader import paddle_backend
import c_vision_paddle.measurements as measurements
import c_vision.reader as base


SHAPE = re.compile(r"output 0 shape:((?:\s+\d+)+)")


def detector_input(image: np.ndarray, resize_long: int = 960) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        raise ValueError("Expected a nonempty BGR image")
    height, width = image.shape[:2]
    scale = resize_long / max(height, width)
    target_height = max(128, int(np.ceil(int(height * scale) / 128) * 128))
    target_width = max(128, int(np.ceil(int(width * scale) / 128) * 128))
    resized = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
    values = resized.astype(np.float32) / 255.0
    values = (values - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32)
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None])


def recognition_input(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if height < 1 or width < 1:
        raise ValueError("Empty recognition crop")
    target_width = min(3200, max(320, int(np.ceil(48 * width / height))))
    resized_width = min(target_width, int(np.ceil(48 * width / height)))
    resized = cv2.resize(image, (resized_width, 48)).astype(np.float32)
    tensor = np.zeros((1, 3, 48, target_width), dtype=np.float32)
    tensor[0, :, :, :resized_width] = (resized.transpose(2, 0, 1) / 255.0 - 0.5) / 0.5
    return tensor


def decode_ctc(output: np.ndarray, alphabet: list[str]) -> tuple[str, float]:
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[2] != len(alphabet):
        raise ValueError("Recognition output does not match alphabet")
    indices = output[0].argmax(axis=-1)
    scores = output[0].max(axis=-1)
    text, accepted = [], []
    previous = 0
    for index, score in zip(indices, scores):
        index = int(index)
        if index != 0 and index != previous:
            text.append(alphabet[index])
            accepted.append(float(score))
        previous = index
    return "".join(text), float(np.mean(accepted)) if accepted else 0.0


def _ordered_box(contour: np.ndarray) -> tuple[np.ndarray, float]:
    rectangle = cv2.minAreaRect(contour.astype(np.float32))
    points = sorted(cv2.boxPoints(rectangle), key=lambda point: point[0])
    left = sorted(points[:2], key=lambda point: point[1])
    right = sorted(points[2:], key=lambda point: point[1])
    return np.array([left[0], right[0], right[1], left[1]], dtype=np.float32), min(rectangle[1])


def _box_score(map_values: np.ndarray, box: np.ndarray) -> float:
    height, width = map_values.shape
    xmin = int(np.clip(np.floor(box[:, 0].min()), 0, width - 1))
    xmax = int(np.clip(np.ceil(box[:, 0].max()), 0, width - 1))
    ymin = int(np.clip(np.floor(box[:, 1].min()), 0, height - 1))
    ymax = int(np.clip(np.ceil(box[:, 1].max()), 0, height - 1))
    mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
    shifted = box - np.array([xmin, ymin], dtype=np.float32)
    cv2.fillPoly(mask, shifted.reshape(1, -1, 2).astype(np.int32), 1)
    return float(cv2.mean(map_values[ymin:ymax + 1, xmin:xmax + 1], mask)[0])


def detection_boxes(probability: np.ndarray, image_shape: tuple[int, int],
                    min_score: float = 0.60) -> list[np.ndarray]:
    if probability.ndim != 4 or probability.shape[:2] != (1, 1):
        raise ValueError("Expected DB detection map with shape 1,1,H,W")
    heatmap = probability[0, 0]
    mask = np.uint8(heatmap > 0.30) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[-2:]
    height, width = image_shape
    result = []
    for contour in contours[:1000]:
        box, short_side = _ordered_box(contour)
        if short_side < 3:
            continue
        if _box_score(heatmap, box) < min_score:
            continue
        area = abs(float(cv2.contourArea(box)))
        perimeter = float(cv2.arcLength(box, True))
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(box, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(area * 1.5 / max(perimeter, 1.0))
        if len(expanded) != 1:
            continue
        box, short_side = _ordered_box(np.asarray(expanded[0], dtype=np.float32))
        if short_side < 5:
            continue
        box[:, 0] = np.clip(np.round(box[:, 0] / heatmap.shape[1] * width), 0, width - 1)
        box[:, 1] = np.clip(np.round(box[:, 1] / heatmap.shape[0] * height), 0, height - 1)
        if (np.linalg.norm(box[0] - box[1]) > 3 and
                np.linalg.norm(box[0] - box[3]) > 3):
            result.append(box.astype(np.float32))
    return sorted(result, key=lambda box: (box[0, 1], box[0, 0]))


def rotate_crop(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    top = max(1, int(max(np.linalg.norm(points[0] - points[1]),
                         np.linalg.norm(points[2] - points[3]))))
    side = max(1, int(max(np.linalg.norm(points[0] - points[3]),
                          np.linalg.norm(points[1] - points[2]))))
    target = np.array([[0, 0], [top, 0], [top, side], [0, side]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(points.astype(np.float32), target)
    cropped = cv2.warpPerspective(image, matrix, (top, side),
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
    return np.rot90(cropped) if side / top >= 1.5 else cropped


class LiteOcr:
    def __init__(self, directory: Path, detector_size: int = 960):
        if detector_size < 128:
            raise ValueError("detector_size must be at least 128")
        self.directory = directory.resolve()
        self.detector_size = detector_size
        self.runner = self.directory / "smoke_infer"
        self.detector = self.directory / "PP-OCRv5_mobile_det.nb"
        self.recognizer = self.directory / "PP-OCRv5_mobile_rec.nb"
        dictionary = (self.directory / "alphabet.bin").read_bytes()
        self.alphabet = [item.decode("utf-8") for item in dictionary.split(b"\0") if item]
        for path in (self.runner, self.detector, self.recognizer):
            if not path.is_file():
                raise FileNotFoundError(path)
        self.cache: dict[tuple[tuple[int, ...], bytes], list[OcrLine]] = {}

    def infer(self, model: Path, tensor: np.ndarray) -> np.ndarray:
        with tempfile.TemporaryDirectory(prefix="labmate_lite_") as temporary:
            root = Path(temporary)
            input_file, output_file = root / "input.f32", root / "output.f32"
            np.ascontiguousarray(tensor, dtype=np.float32).tofile(input_file)
            shape = ",".join(str(dimension) for dimension in tensor.shape)
            environment = os.environ.copy()
            environment["LD_LIBRARY_PATH"] = str(self.directory) + ":" + environment.get(
                "LD_LIBRARY_PATH", "")
            completed = subprocess.run(
                [str(self.runner), str(model), shape, str(input_file), str(output_file)],
                capture_output=True, text=True, errors="replace", timeout=180,
                env=environment, check=False)
            if completed.returncode:
                raise RuntimeError(f"Lite inference failed ({completed.returncode}): "
                                   f"{completed.stderr[-1200:]}")
            match = SHAPE.search(completed.stdout)
            if not match:
                raise RuntimeError("Lite output shape missing")
            output_shape = tuple(int(part) for part in match.group(1).split())
            output = np.fromfile(output_file, dtype=np.float32)
            if output.size != int(np.prod(output_shape)):
                raise RuntimeError("Lite output tensor size mismatch")
            return output.reshape(output_shape)

    def recognize(self, image: np.ndarray, minimum_score: float = 0.20) -> list[OcrLine]:
        key = (image.shape, blake2b(image.tobytes(), digest_size=16).digest())
        if key not in self.cache:
            heatmap = self.infer(self.detector, detector_input(image, self.detector_size))
            lines = []
            for box in detection_boxes(heatmap, image.shape[:2]):
                crop = rotate_crop(image, box)
                text, score = decode_ctc(
                    self.infer(self.recognizer, recognition_input(crop)), self.alphabet)
                if text.strip():
                    x0, y0 = box.min(axis=0).astype(int)
                    x1, y1 = box.max(axis=0).astype(int)
                    lines.append(OcrLine(text.strip(), score, int(x0), int(y0),
                                         int(x1 - x0), int(y1 - y0)))
            self.cache[key] = lines
        return [line for line in self.cache[key] if line.score >= minimum_score]


@contextmanager
def lite_backend(engine: LiteOcr) -> Iterator[None]:
    previous_measurements = measurements.recognize
    previous_backend = backend.recognize
    with paddle_backend():
        measurements.recognize = engine.recognize
        backend.recognize = engine.recognize
        try:
            yield
        finally:
            measurements.recognize = previous_measurements
            backend.recognize = previous_backend


def read_image(image: Path, config: Path, output: Path, engine: LiteOcr,
               request_id: str | None = None):
    with lite_backend(engine):
        return base.read_instrument_image(image, config, output, request_id)


def capture_frame(camera: str, output: Path, width: int = 0, height: int = 0) -> Path:
    source = int(camera) if camera.isdecimal() else camera
    device = cv2.VideoCapture(source)
    if not device.isOpened():
        raise RuntimeError(f"Cannot open camera: {camera}")
    try:
        if width:
            device.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            device.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        for _ in range(3):
            device.grab()
        ready, frame = device.read()
    finally:
        device.release()
    if not ready or frame is None or frame.size == 0:
        raise RuntimeError(f"Camera did not return a frame: {camera}")
    output.mkdir(parents=True, exist_ok=True)
    image = output / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    if not cv2.imwrite(str(image), frame):
        raise RuntimeError(f"Cannot save captured frame: {image}")
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--camera", type=str)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).resolve().parent.parent /
                        "c_vision/configs/keysight_scope_measure.json")
    parser.add_argument("--out", type=Path, default=Path("runs"))
    parser.add_argument("--detector-size", type=int, default=960)
    parser.add_argument("--request-id", type=str)
    parser.add_argument("--camera-width", type=int, default=0)
    parser.add_argument("--camera-height", type=int, default=0)
    args = parser.parse_args()
    request_id = args.request_id or str(uuid.uuid4())
    image = args.image
    try:
        if image is None:
            image = capture_frame(args.camera, args.out,
                                  args.camera_width, args.camera_height)
        result = read_image(image, args.config, args.out,
                            LiteOcr(args.bundle, args.detector_size), request_id)
        payload = asdict(result)
    except (OSError, RuntimeError, ValueError, cv2.error) as error:
        payload = {"request_id": request_id, "source": "vision",
                   "image_path": str(image) if image else "", "valid": False,
                   "error_code": "VISION_RUNTIME_FAILED",
                   "detail": f"{type(error).__name__}: {error}", "measurements": []}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"failure_{request_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
