from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import cv2
import numpy as np

CN_TZ = timezone(timedelta(hours=8))
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
TEMPLATE_LABELS = {"frequency": "频率", "peak_to_peak": "峰峰值", "phase": "相移"}


@dataclass
class Roi:
    x: int
    y: int
    w: int
    h: int


@dataclass
class DetectionResult:
    screen_roi: Roi | None
    debug_image: np.ndarray
    error_code: str
    screen_quad: np.ndarray | None = None


@dataclass
class ReadingResult:
    request_id: str
    device_id: str
    source: str
    value: float | None
    unit: str
    valid: bool
    captured_at: str
    image_path: str
    error_code: str
    confidence: float
    raw_text: str
    value_roi_path: str
    unit_roi_path: str
    processed_value_path: str
    measurements: list[MeasurementReading] = field(default_factory=list)


@dataclass
class MeasurementReading:
    measurement_id: str
    label: str
    channel: str
    label_source: str
    value: float | None
    unit: str
    valid: bool
    error_code: str
    raw_text: str
    row_roi_path: str
    value_roi_path: str
    processed_value_path: str


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_roi(data: dict[str, Any], name: str) -> Roi | None:
    roi = data.get(name)
    if not roi:
        return None
    return Roi(x=int(roi["x"]), y=int(roi["y"]), w=int(roi["w"]), h=int(roi["h"]))


def parse_relative_roi(data: dict[str, Any], name: str, parent: Roi) -> Roi | None:
    roi = data.get(name)
    if not roi:
        return None
    return Roi(
        x=parent.x + int(float(roi["x"]) * parent.w),
        y=parent.y + int(float(roi["y"]) * parent.h),
        w=int(float(roi["w"]) * parent.w),
        h=int(float(roi["h"]) * parent.h),
    )


def crop_roi(image: np.ndarray, roi: Roi) -> np.ndarray:
    height, width = image.shape[:2]
    x0 = max(0, roi.x)
    y0 = max(0, roi.y)
    x1 = min(width, roi.x + roi.w)
    y1 = min(height, roi.y + roi.h)
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"Invalid ROI outside image: {roi}")
    return image[y0:y1, x0:x1]


def order_quad_points(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype=np.float32,
    )


def detect_screen_quad(
    contours: list[np.ndarray],
    image_shape: tuple[int, ...],
    settings: dict[str, Any],
) -> np.ndarray | None:
    perspective = settings.get("perspective", {})
    if not bool(perspective.get("enabled", False)):
        return None
    image_area = image_shape[0] * image_shape[1]
    min_area_ratio = float(perspective.get("min_area_ratio", 0.1))
    min_aspect = float(perspective.get("min_aspect", 1.35))
    max_aspect = float(perspective.get("max_aspect", 2.4))
    candidates: list[tuple[float, np.ndarray]] = []

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        polygon = cv2.approxPolyDP(contour, float(perspective.get("epsilon", 0.02)) * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        area_ratio = abs(cv2.contourArea(polygon)) / image_area
        if area_ratio < min_area_ratio:
            continue
        quad = order_quad_points(polygon.reshape(4, 2))
        top = np.linalg.norm(quad[1] - quad[0])
        bottom = np.linalg.norm(quad[2] - quad[3])
        left = np.linalg.norm(quad[3] - quad[0])
        right = np.linalg.norm(quad[2] - quad[1])
        aspect = (top + bottom) / max(left + right, 1.0)
        if not min_aspect <= aspect <= max_aspect:
            continue
        center = quad.mean(axis=0)
        center_distance = abs(center[0] - image_shape[1] / 2) / image_shape[1]
        center_distance += abs(center[1] - image_shape[0] / 2) / image_shape[0]
        candidates.append((area_ratio - 0.08 * center_distance, quad))

    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def rectified_screen_size(settings: dict[str, Any]) -> tuple[int, int]:
    perspective = settings.get("perspective", {})
    return int(perspective.get("width", 1600)), int(perspective.get("height", 934))


def perspective_matrices(quad: np.ndarray, settings: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    width, height = rectified_screen_size(settings)
    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    forward = cv2.getPerspectiveTransform(order_quad_points(quad), destination)
    return forward, np.linalg.inv(forward)


def rectify_screen(image: np.ndarray, detection: DetectionResult, settings: dict[str, Any]) -> np.ndarray:
    if detection.screen_quad is None:
        if detection.screen_roi is None:
            raise ValueError("Cannot rectify a missing screen")
        return crop_roi(image, detection.screen_roi)
    width, height = rectified_screen_size(settings)
    forward, _ = perspective_matrices(detection.screen_quad, settings)
    return cv2.warpPerspective(image, forward, (width, height), flags=cv2.INTER_CUBIC)


def project_rectified_roi(roi: Roi, detection: DetectionResult, settings: dict[str, Any]) -> np.ndarray | None:
    if detection.screen_quad is None:
        return None
    _, inverse = perspective_matrices(detection.screen_quad, settings)
    corners = np.array(
        [[[roi.x, roi.y], [roi.x + roi.w, roi.y], [roi.x + roi.w, roi.y + roi.h], [roi.x, roi.y + roi.h]]],
        dtype=np.float32,
    )
    return cv2.perspectiveTransform(corners, inverse)[0]


def recover_sidebar_screen(
    screen: Roi,
    contours: list[np.ndarray],
    image_shape: tuple[int, ...],
    settings: dict[str, Any],
) -> Roi:
    recovery = settings.get("sidebar_recovery")
    if not recovery:
        return screen
    edge = screen.x + screen.w
    boxes = [cv2.boundingRect(contour) for contour in contours]
    sidebar_boxes = [
        (x, y, w, h) for x, y, w, h in boxes
        if x > screen.x + 0.8 * screen.w
        and x + w > edge + 0.08 * screen.w
        and w > 0.05 * screen.w
        and screen.y <= y < screen.y + screen.h
    ]
    if len(sidebar_boxes) < 2:
        return screen

    right = max(x + w for x, y, w, h in sidebar_boxes)
    right += round(float(recovery["right_margin_ratio"]) * screen.w)
    if right > edge + 0.3 * screen.w:
        return screen
    top = max(0, screen.y - round(float(recovery["top_margin_ratio"]) * screen.h))
    width = min(image_shape[1], right) - screen.x
    height = min(image_shape[0] - top, round(width / float(recovery["screen_aspect_ratio"])))
    return Roi(screen.x, top, width, height)


def detect_screen_roi(image: np.ndarray, settings: dict[str, Any]) -> DetectionResult:
    height, width = image.shape[:2]
    debug = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(gray, int(settings.get("canny_low", 50)), int(settings.get("canny_high", 150)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[-2:]

    screen_quad = detect_screen_quad(contours, image.shape, settings)
    if screen_quad is not None:
        x, y, w, h = cv2.boundingRect(screen_quad.astype(np.int32))
        screen_roi = Roi(x=x, y=y, w=w, h=h)
        cv2.polylines(debug, [screen_quad.astype(np.int32)], True, (0, 255, 0), 3)
        return DetectionResult(
            screen_roi=screen_roi,
            debug_image=debug,
            error_code="",
            screen_quad=screen_quad,
        )

    min_area_ratio = float(settings.get("min_area_ratio", 0.02))
    max_area_ratio = float(settings.get("max_area_ratio", 0.8))
    min_aspect = float(settings.get("min_aspect", 1.2))
    max_aspect = float(settings.get("max_aspect", 8.0))
    image_area = width * height
    candidates: list[tuple[float, Roi]] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        area_ratio = area / image_area
        aspect = w / max(h, 1)
        if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
            continue
        if aspect < min_aspect or aspect > max_aspect:
            continue

        center_x = x + w / 2
        center_y = y + h / 2
        center_distance = abs(center_x - width / 2) / width + abs(center_y - height / 2) / height
        score = area_ratio - 0.15 * center_distance
        candidates.append((score, Roi(x=x, y=y, w=w, h=h)))

    if not candidates:
        return DetectionResult(screen_roi=None, debug_image=debug, error_code="SCREEN_NOT_FOUND")

    candidates.sort(key=lambda item: item[0], reverse=True)
    screen_roi = recover_sidebar_screen(candidates[0][1], contours, image.shape, settings)
    cv2.rectangle(
        debug,
        (screen_roi.x, screen_roi.y),
        (screen_roi.x + screen_roi.w, screen_roi.y + screen_roi.h),
        (0, 255, 0),
        3,
    )
    return DetectionResult(screen_roi=screen_roi, debug_image=debug, error_code="")


def resolve_rois(image: np.ndarray, config: dict[str, Any]) -> tuple[Roi, Roi | None, DetectionResult | None]:
    locator = config.get("locator", {})
    mode = locator.get("mode", "fixed_roi")
    if mode == "auto_lcd":
        detection = detect_screen_roi(image, locator)
        if detection.screen_roi is None:
            if config.get("measurements"):
                return Roi(0, 0, w=image.shape[1], h=image.shape[0]), None, detection
            value_roi = parse_roi(config, "value_roi")
            if value_roi is None:
                raise ValueError("Auto screen detection failed and config has no fixed value_roi fallback")
            return value_roi, parse_roi(config, "unit_roi"), detection
        value_roi = parse_relative_roi(config, "value_roi_relative", detection.screen_roi)
        if value_roi is None:
            value_roi = detection.screen_roi
        return value_roi, parse_relative_roi(config, "unit_roi_relative", detection.screen_roi), detection

    value_roi = parse_roi(config, "value_roi")
    if value_roi is None:
        raise ValueError("Config must include value_roi")
    return value_roi, parse_roi(config, "unit_roi"), None


def preprocess_for_digits(image: np.ndarray, settings: dict[str, Any]) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = float(settings.get("scale", 1.0))
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    threshold_mode = settings.get("threshold", "otsu")
    if threshold_mode == "adaptive":
        processed = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
    elif threshold_mode == "none":
        processed = gray
    else:
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if bool(settings.get("invert", False)):
        processed = cv2.bitwise_not(processed)
    return processed


def tesseract_text(*args, **kwargs):
    raise RuntimeError("Initialize the Paddle-Lite backend before reading images")


def tesseract_words(*args, **kwargs):
    raise RuntimeError("Initialize the Paddle-Lite backend before reading images")


def detect_row_channels(row: np.ndarray) -> list[str]:
    """Read Keysight channel digits from their fixed yellow/green colours."""
    title = row[:max(35, row.shape[0] // 2)]
    hsv = cv2.cvtColor(title, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (15, 70, 70), (45, 255, 255))
    green = cv2.inRange(hsv, (45, 55, 50), (95, 255, 255))
    union = cv2.bitwise_or(yellow, green)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    union = cv2.morphologyEx(union, cv2.MORPH_CLOSE, kernel)
    _, _, stats, _ = cv2.connectedComponentsWithStats(union, 8)
    channels: list[tuple[int, str]] = []
    for x, y, w, h, area in stats[1:]:
        # Ignore the panel border and coloured label strokes on the far left.
        if (x < 0.20 * row.shape[1] or area < 45 or
                h < 0.25 * title.shape[0] or w > 0.15 * row.shape[1]):
            continue
        component = hsv[y:y + h, x:x + w]
        hues = component[:, :, 0][(component[:, :, 1] > 55) & (component[:, :, 2] > 50)]
        if not hues.size:
            continue
        median_hue = float(np.median(hues))
        if 34 <= median_hue <= 41:
            continue
        channels.append((x, "1" if median_hue < 34 else "2"))
    channels.sort()
    return [channel for _, channel in channels]


def detect_text_channels(text: str) -> list[str]:
    """Recover Keysight channel markers when color segmentation is unclear."""
    compact = re.sub(r"\s+", "", text)
    found: list[str] = []
    # The scope prints channels in brackets or parentheses, e.g. [1], [2],
    # and [1-2]. Restrict this fallback to those markers so value digits are
    # never mistaken for a channel.
    pattern = r"[\[({（【]([12])(?:[-→>+]+([12]))?[\])}）】|]?"
    for match in re.finditer(pattern, compact):
        channel = match.group(1)
        if match.group(2):
            channel += "-" + match.group(2)
        if channel not in found:
            found.append(channel)
    return found


def template_edges(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.Canny(gray, 35, 110)


@lru_cache(maxsize=1)
def load_measurement_templates() -> tuple[tuple[str, np.ndarray], ...]:
    root = Path(__file__).parent / "templates"
    templates = []
    for path in sorted(root.glob("*.png")):
        key = path.stem.rsplit("_", 1)[0]
        if key not in TEMPLATE_LABELS:
            continue
        image = cv2.imread(str(path))
        if image is not None:
            templates.append((TEMPLATE_LABELS[key], image))
    return tuple(templates)


def measurement_template_scores(row: np.ndarray) -> dict[str, float]:
    templates = load_measurement_templates()
    if not templates:
        return {}
    scale_to_reference = 320 / row.shape[1]
    normalized = cv2.resize(row, None, fx=scale_to_reference, fy=scale_to_reference, interpolation=cv2.INTER_CUBIC)
    search = normalized[:min(62, normalized.shape[0]), :min(175, normalized.shape[1])]
    search_edges = template_edges(search)
    scores: dict[str, float] = {label: -1.0 for label in TEMPLATE_LABELS.values()}
    for label, template in templates:
        for scale in np.linspace(0.78, 1.22, 10):
            candidate = cv2.resize(template, None, fx=float(scale), fy=float(scale), interpolation=cv2.INTER_CUBIC)
            edges = template_edges(candidate)
            if edges.shape[0] > search_edges.shape[0] or edges.shape[1] > search_edges.shape[1]:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(search_edges, edges, cv2.TM_CCOEFF_NORMED))[1])
            scores[label] = max(scores[label], score)
    return scores


def match_measurement_template(
    row: np.ndarray,
    allowed_labels: set[str] | None = None,
) -> tuple[str | None, float, float]:
    scores = measurement_template_scores(row)
    if allowed_labels is not None:
        scores = {label: score for label, score in scores.items() if label in allowed_labels}
    if not scores:
        return None, 0.0, 0.0
    ranked = sorted(((score, label) for label, score in scores.items()), reverse=True)
    best_score, best_label = ranked[0]
    margin = best_score - ranked[1][0] if len(ranked) > 1 else best_score
    return (best_label if best_score >= 0.32 and margin >= 0.025 else None), best_score, margin


def parse_dynamic_value(text: str) -> tuple[float | None, str]:
    normalized = text.replace(",", ".").replace("−", "-").replace("µ", "u").replace("μ", "u")
    normalized = normalized.replace("¥", "").replace("￥", "").replace("~", "-")
    normalized = re.sub(r"(?<=[0-9OQ])R(?=[0-9OQ])", ".", normalized)
    normalized = re.sub(r"m[vVyY]+", "mV", normalized)
    normalized = re.sub(r"(?i)khz", "kHz", normalized)
    normalized = re.sub(r"(?i)mhz", "MHz", normalized)
    normalized = re.sub(r"(?i)(?<![km])hz", "Hz", normalized)
    normalized = re.sub(r"([+\->])\s+(?=[0-9OQ])", r"\1", normalized)
    normalized = re.sub(r"(?<=[0-9OQ])\s*\.\s*(?=[0-9OQ])", ".", normalized)
    patterns = (
        r"([+\->]?[0-9OQ]+(?:\.[0-9OQ]+)?)\s*(mV|uV|V|kHz|MHz|Hz|°|deg|%)",
        r"([+\->]?[0-9OQ]+\.[0-9OQ]+)\s*([eE])\b",
    )
    candidates: list[tuple[tuple[int, int, int], float, str]] = []
    for pattern in patterns:
      for match in re.finditer(pattern, normalized):
        number = match.group(1).replace("O", "0").replace("Q", "0")
        if number.startswith(">"):
            number = "-" + number[1:]
        unit = "deg" if match.group(2) in {"°", "deg", "e", "E"} else match.group(2)
        try:
            score = (int(number.startswith(("-", "+"))), int("." in number), len(re.sub(r"\D", "", number)))
            candidates.append((score, float(number), unit))
        except ValueError:
            pass
    if not candidates:
        return None, ""
    _, value, unit = max(candidates, key=lambda item: item[0])
    return value, unit


def extract_dynamic_values(text: str) -> list[tuple[float, str]]:
    values = []
    for line in text.splitlines():
        value, unit = parse_dynamic_value(line)
        if value is not None and unit:
            values.append((value, unit))
    return values


def select_consensus_value(candidates: list[tuple[float | None, str]]) -> tuple[float | None, str, bool]:
    usable = [(value, unit) for value, unit in candidates if value is not None and unit]
    if not usable:
        return None, "", False
    groups: list[list[tuple[float, str]]] = []
    for value, unit in usable:
        target = next((group for group in groups if group[0][1] == unit
                       and abs(group[0][0] - value) <= max(1e-6 * abs(value), 1e-6)), None)
        if target is None:
            groups.append([(value, unit)])
        else:
            target.append((value, unit))
    best = max(groups, key=len)
    return best[0][0], best[0][1], len(best) >= 2


def confirm_dynamic_value(
    value: float | None,
    unit: str,
    candidates: list[tuple[float | None, str]],
    panel_candidate: tuple[float, str] | None,
    label: str | None,
    channel: str,
) -> bool:
    """Combine OCR agreement with aligned panel and field evidence."""
    if value is None or not unit:
        return False
    matching = [(candidate, candidate_unit) for candidate, candidate_unit in candidates
                if candidate is not None and candidate_unit == unit
                and abs(candidate - value) <= max(1e-6 * abs(value), 1e-6)]
    if len(matching) >= 2:
        return True
    if panel_candidate is None or not label or not channel:
        return False
    panel_value, panel_unit = panel_candidate
    if panel_unit != unit or abs(panel_value - value) > max(1e-6 * abs(value), 1e-6):
        return False
    conflicts = [(candidate, candidate_unit) for candidate, candidate_unit in candidates
                 if candidate is not None and candidate_unit == unit
                 and abs(candidate - value) > max(1e-6 * abs(value), 1e-6)]
    return not conflicts


def classify_measurement_label(text: str, unit: str, channel_count: int = 0) -> str | None:
    translation = str.maketrans({"喉": "峰", "岫": "峰", "峄": "峰", "峪": "峰", "峥": "峰",
                                 "坂": "峰", "俐": "值", "倚": "值", "袋": "移", "真": "相"})
    candidates = {"频率": "频率", "相移": "相移", "峰峰值": "峰峰值", "峰值": "峰值", "幅值": "幅值",
                  "平均值": "平均值", "最大值": "最大值", "最小值": "最小值"}
    best: tuple[float, float, str] | None = None
    for line in text.splitlines():
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", line.translate(translation)))
        if not chinese:
            continue
        scores = sorted(((SequenceMatcher(None, chinese, key).ratio(), value)
                         for key, value in candidates.items()), reverse=True)
        candidate = (scores[0][0], scores[0][0] - scores[1][0], scores[0][1])
        if best is None or candidate > best:
            best = candidate
    label = best[2] if best and best[0] >= 0.58 and best[1] >= 0.08 else None
    if unit in {"Hz", "kHz", "MHz"}:
        return None if re.search(r"(?:1\s*/|Δ\s*[Xx]|delta)", text, re.IGNORECASE) else "频率"
    if unit == "deg":
        return "相移" if label == "相移" or channel_count >= 2 else None
    return label if label not in {"频率", "相移"} else None


def infer_configured_measurement_label(
    unit: str,
    channel: str,
    config: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """Infer a fixed-device label without depending on Chinese OCR."""
    rules = (config or {}).get("label_inference", {})
    if not rules.get("enabled") or not channel:
        return None, "unrecognized"
    mapping = rules.get("unit_to_label", {})
    label = mapping.get(unit)
    if not label:
        return None, "unrecognized"
    return str(label), "configured-unit"


def parse_measurement_label(text: str) -> tuple[str, str] | None:
    compact = re.sub(r"\s+", "", text)
    name = re.split(r"[\[({（【]", compact, maxsplit=1)[0]
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", name))
    candidates = {"频率": "频率", "峰峰值": "峰峰值", "相移": "相移"}
    scores = sorted(((SequenceMatcher(None, chinese, key).ratio(), value)
                     for key, value in candidates.items()), reverse=True)
    if not chinese or scores[0][0] < 0.66 or scores[0][0] - scores[1][0] < 0.15:
        return None
    label = scores[0][1]
    if label == "峰峰值" and len(chinese) < 3:
        return None
    channels = re.search(r"[\[({（【]([12])(?:\s*[-→>]+\s*([12]))?[\])}）】]", compact)
    if not channels:
        return None
    channel = channels.group(1)
    if label == "相移":
        if not channels.group(2):
            return None
        channel += "-" + channels.group(2)
    return label, channel


def detect_measurement_rows(panel_image: np.ndarray) -> list[Roi]:
    """Split a frontal Keysight measurement panel at its full-width dividers."""
    height, width = panel_image.shape[:2]
    gray = cv2.cvtColor(panel_image, cv2.COLOR_BGR2GRAY)
    # Sample full-width paths directly: text cannot supply a continuous divider.
    xs = np.arange(int(width * 0.06), int(width * 0.94))
    ys = np.arange(height)[:, None]
    scores = np.zeros(height, dtype=np.float32)
    for slope in np.linspace(-0.12, 0.12, 49):
        positions = np.rint(ys + slope * (xs - width / 2)).astype(int)
        support = np.zeros_like(positions, dtype=bool)
        for offset in (-1, 0, 1):
            sample_y = positions + offset
            inside = (sample_y >= 0) & (sample_y < height)
            support |= inside & (gray[np.clip(sample_y, 0, height - 1), xs] > 65)
        scores = np.maximum(scores, support.mean(axis=1))
    supported = np.flatnonzero(scores > 0.72)
    clusters = np.split(supported, np.flatnonzero(np.diff(supported) > 5) + 1)
    dividers = [int(group[np.argmax(scores[group])]) for group in clusters if len(group)]
    dividers = [y for y in dividers if height * 0.10 < y < height * 0.90]
    # Bright, tilted photos can wash a thin divider below the absolute gray
    # threshold above. Recover long near-horizontal edges in that case.
    hough_y = []
    if not dividers:
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 18, 70)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=max(30, int(width * 0.20)),
            minLineLength=int(width * 0.60), maxLineGap=int(width * 0.10),
        )
        if lines is not None:
            for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
                left, right = min(x1, x2), max(x1, x2)
                if (left <= width * 0.40 and right >= width * 0.78
                        and abs(y2 - y1) <= max(12, int(abs(x2 - x1) * 0.16))):
                    y = int(round((y1 + y2) / 2))
                    if height * 0.10 < y < height * 0.90:
                        hough_y.append(y)
    if hough_y:
        hough_y.sort()
        hough_groups = np.split(hough_y, np.flatnonzero(np.diff(hough_y) > 8) + 1)
        hough_dividers = [int(round(float(np.median(group)))) for group in hough_groups if len(group)]
        combined = sorted(dividers + hough_dividers)
        merged = np.split(combined, np.flatnonzero(np.diff(combined) > 10) + 1)
        dividers = [int(round(float(np.median(group)))) for group in merged if len(group)]
    bounds = [0, *dividers, height]
    rows = []
    for top, bottom in zip(bounds, bounds[1:]):
        if bottom - top < 45:
            continue
        margin = max(10, int(width * 0.12))
        content = gray[top + 12:bottom - 15, margin:width - margin]
        if content.size and np.mean(content > 100) > 0.02:
            rows.append(Roi(0, top, width, bottom - top))
    return rows if 1 <= len(rows) <= 4 else []


def read_dynamic_measurement_rows(
    panel_image: np.ndarray,
    run_dir: Path,
    config: dict[str, Any] | None = None,
) -> list[MeasurementReading]:
    row_rois = detect_measurement_rows(panel_image)
    dynamic_rules = (config or {}).get("dynamic_measurements", {})
    if isinstance(dynamic_rules, bool):
        dynamic_rules = {}
    min_rows = int(dynamic_rules.get("min_rows", 1))
    max_rows = int(dynamic_rules.get("max_rows", 4))
    if len(row_rois) < min_rows or len(row_rois) > max_rows:
        return []
    try:
        panel_text = tesseract_text(panel_image, 6, "", lang="chi_sim+eng")
        panel_values = extract_dynamic_values(panel_text)
    except Exception:
        panel_text, panel_values = "", []
    try:
        panel_words = tesseract_words(panel_image, 11, "chi_sim+eng")
    except Exception:
        panel_words = []
    results = []
    for index, roi in enumerate(row_rois, start=1):
        row = crop_roi(panel_image, roi)
        row_path = save_image(run_dir / f"measurement_row_{index}.png", row)
        value_image = row[int(row.shape[0] * 0.35):, int(row.shape[1] * 0.35):]
        value_path = save_image(run_dir / f"measurement_row_{index}_value.png", value_image)
        processed = preprocess_for_digits(value_image, {"scale": 3, "threshold": "none"})
        processed_path = save_image(run_dir / f"measurement_row_{index}_processed.png", processed)
        try:
            row_text = tesseract_text(row, 6, "", lang="chi_sim+eng")
            raw_value_reads = [
                tesseract_text(processed, psm, "0123456789+-.VvMmUuKkHhZz°", lang="eng")
                for psm in (6, 7, 11)
            ]
            raw_value = " / ".join(text for text in raw_value_reads if text)
            row_words = [text for text, x, y, w, h in panel_words if roi.y <= y + h / 2 < roi.y + roi.h]
            positioned_text = " ".join(row_words)
            raw_label = positioned_text + "\n" + row_text
            value_candidates = [parse_dynamic_value(positioned_text), parse_dynamic_value(row_text)]
            raw_value_candidates = [parse_dynamic_value(text) for text in raw_value_reads]
            raw_candidate_value, raw_candidate_unit, raw_confirmed = select_consensus_value(raw_value_candidates)
            if raw_confirmed:
                # A numeric crop with repeated agreement outranks a noisy
                # full-row OCR result that may have dropped the first digit.
                value_candidates.append((raw_candidate_value, raw_candidate_unit))
            panel_candidate = panel_values[index - 1] if len(panel_values) == len(row_rois) else None
            if panel_candidate is not None:
                value_candidates.append(panel_candidate)
            value, unit, value_confirmed = select_consensus_value(value_candidates)
            if panel_candidate is None and value is not None and unit:
                matching_panel_values = [
                    candidate for candidate in panel_values
                    if candidate[1] == unit
                    and abs(candidate[0] - value) <= max(1e-6 * abs(value), 1e-6)
                ]
                if len(matching_panel_values) == 1:
                    panel_candidate = matching_panel_values[0]
                    value_candidates.append(panel_candidate)
            channel_parts = detect_row_channels(row)
            text_channels = detect_text_channels(raw_label)
            if not channel_parts and text_channels:
                channel_parts = text_channels[0].split("-")
            elif len(channel_parts) < 2 and text_channels:
                # A color marker can be lost for a phase row; use the explicit
                # [1-2] text marker only when it supplies the missing pair.
                pair = next((item for item in text_channels if "-" in item), None)
                if pair:
                    channel_parts = pair.split("-")
            label = classify_measurement_label(raw_label, unit, 0)
            label_source = "ocr+unit" if label else "unrecognized"
            if label is None:
                label = classify_measurement_label(raw_label, unit, len(channel_parts))
                if label is not None:
                    label_source = "channel+unit"
            if label is None:
                inferred_label, inferred_source = infer_configured_measurement_label(
                    unit, "-".join(channel_parts[:2]) if len(channel_parts) >= 2 else (channel_parts[-1] if channel_parts else ""),
                    config,
                )
                if inferred_label is not None:
                    label, label_source = inferred_label, inferred_source
            if label is None and unit:
                allowed_templates = ({"频率"} if unit in {"Hz", "kHz", "MHz"} else
                                     {"相移"} if unit == "deg" else {"峰峰值"})
                template_label, _, _ = match_measurement_template(row, allowed_templates)
                if template_label is not None:
                    label, label_source = template_label, "template+unit"
            elif unit in {"V", "mV", "uV"}:
                template_label, template_score, _ = match_measurement_template(row, {"峰峰值"})
                if template_label is not None and template_score >= 0.40:
                    label, label_source = template_label, "template+unit"
            if label == "相移":
                channel = "-".join(channel_parts[:2]) if len(channel_parts) >= 2 else ""
            else:
                channel = channel_parts[-1] if channel_parts else ""
            value_confirmed = value_confirmed or confirm_dynamic_value(
                value, unit, value_candidates, panel_candidate, label, channel
            )
            error = ("LABEL_UNRECOGNIZED" if label is None else
                     "CHANNEL_UNRECOGNIZED" if not channel else
                     "VALUE_PARSE_FAILED" if value is None else
                     "UNIT_MISSING" if not unit else
                     "VALUE_UNCONFIRMED" if not value_confirmed else "")
        except Exception as exc:
            raw_label, raw_value, label, label_source, channel, value, unit = "", "", None, "unrecognized", "", None, ""
            error = f"OCR_FAILED:{type(exc).__name__}"
        if not error:
            allowed = {
                "频率": {"Hz", "kHz", "MHz"}, "峰峰值": {"V", "mV", "uV"},
                "峰值": {"V", "mV", "uV"},
                "幅值": {"V", "mV", "uV"}, "平均值": {"V", "mV", "uV"},
                "最大值": {"V", "mV", "uV"}, "最小值": {"V", "mV", "uV"},
                "相移": {"deg"},
            }
            if unit not in allowed[label]:
                error = "UNIT_MISMATCH"
            elif label in {"峰峰值", "频率"} and value is not None and value < 0:
                error = "VALUE_INCONSISTENT"
            elif label == "相移" and len(channel.split("-")) == 2:
                source, target = channel.split("-", 1)
                if source == target and value is not None and abs(value) > 0.05:
                    error = "VALUE_INCONSISTENT"
        results.append(MeasurementReading(
            measurement_id=f"row_{index}", label=label or "", channel=channel,
            label_source=label_source, value=value, unit=unit,
            valid=not bool(error), error_code=error, raw_text=f"{raw_label} | {raw_value}",
            row_roi_path=row_path, value_roi_path=value_path, processed_value_path=processed_path,
        ))
    while results and not results[-1].label and not results[-1].channel and results[-1].value is None:
        results.pop()
    return results


def parse_value(text: str) -> float | None:
    normalized = text.replace(",", ".").replace("−", "-").replace("O", "0").replace("µ", "u").replace("μ", "u")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_value_and_unit(text: str) -> tuple[float | None, str]:
    normalized = text.replace(",", ".").replace("−", "-").replace("O", "0").replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*(mV|uV|V|mA|uA|A|kHz|MHz|Hz|°|deg|%)?\s*", normalized, re.I)
    if not match:
        return None, ""
    unit = match.group(2) or ""
    return float(match.group(1)), "deg" if unit == "°" else unit


def clean_unit(text: str, default_unit: str) -> str:
    unit = text.strip().replace(" ", "")
    unit = unit.replace("Ω", "ohm")
    unit = re.sub(r"[^A-Za-z0-9%/._-]", "", unit)
    return unit or default_unit


def estimate_confidence(value: float | None, unit: str, raw_text: str) -> float:
    score = 0.0
    if value is not None:
        score += 0.65
    if unit:
        score += 0.2
    if raw_text and len(raw_text) <= 24:
        score += 0.15
    return min(score, 1.0)


def save_image(path: Path, image: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return str(path.resolve())


def save_reading_result(run_dir: Path, result: ReadingResult) -> None:
    with (run_dir / "reading.json").open("w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)


def validate_measurement_layout(screen_image: np.ndarray, config: dict[str, Any]) -> bool:
    validation = config.get("layout_validation")
    if not validation:
        return True
    height, width = screen_image.shape[:2]
    panel = validation["panel_roi_relative"]
    x0 = max(0, int(float(panel["x"]) * width))
    x1 = min(width, int((float(panel["x"]) + float(panel["w"])) * width))
    gray = cv2.cvtColor(screen_image, cv2.COLOR_BGR2GRAY)
    vertical_gradient = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    scores = []
    for start, end in validation["activity_bands"]:
        y0 = max(0, int(float(start) * height))
        y1 = min(height, int(float(end) * height))
        band = vertical_gradient[y0:y1, x0:x1]
        scores.append(float(band.mean()) if band.size else 0.0)
    if len(scores) < 2:
        return False
    reference = float(np.median(scores[:-1]))
    if reference < float(validation.get("min_reference_activity", 5.0)):
        return False
    return scores[-1] >= reference * float(validation.get("min_last_band_ratio", 0.45))


def detect_measurement_panel(screen_image: np.ndarray) -> Roi | None:
    """Locate the frontal scope's measurement section from its blue header and border."""
    height, width = screen_image.shape[:2]
    search_x = int(width * 0.72)
    hsv = cv2.cvtColor(screen_image[:, search_x:], cv2.COLOR_BGR2HSV)
    blue = ((hsv[:, :, 0] >= 95) & (hsv[:, :, 0] <= 145)
            & (hsv[:, :, 1] >= 35) & (hsv[:, :, 2] >= 35))
    coverage = blue.mean(axis=1)
    start, stop = int(height * 0.45), int(height * 0.70)
    candidates = np.flatnonzero(coverage[start:stop] > 0.60) + start
    if candidates.size == 0:
        return None
    groups = np.split(candidates, np.flatnonzero(np.diff(candidates) > 4) + 1)
    headers = [group for group in groups if len(group) >= 5]
    if not headers:
        return None
    header_bottom = int(headers[0][-1]) + 2
    bottom = height
    if bottom - header_bottom < height * 0.15:
        return None

    header_columns = np.flatnonzero(blue[headers[0]].mean(axis=0) > 0.50)
    column_groups = (np.split(header_columns, np.flatnonzero(np.diff(header_columns) > 3) + 1)
                     if header_columns.size else [])
    header_spans = [group for group in column_groups
                    if len(group) >= width * 0.10 and group[-1] >= blue.shape[1] * 0.85]
    header_left = search_x + int(header_spans[-1][0]) if header_spans else int(width * 0.78)

    gray = cv2.cvtColor(screen_image, cv2.COLOR_BGR2GRAY)
    gradient = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    edge_start, edge_stop = int(width * 0.72), int(width * 0.85)
    edge_scores = np.percentile(gradient[header_bottom:, edge_start:edge_stop], 75, axis=0)
    edge_offset = int(np.argmax(edge_scores)) if edge_scores.size else 0
    edge_x = edge_start + edge_offset
    if edge_scores.size and edge_scores[edge_offset] >= 80:
        panel_left = edge_x - max(8, int(width * 0.008))
    else:
        panel_left = header_left
    panel_left = max(search_x, min(panel_left, int(width * 0.82)))
    return Roi(panel_left, header_bottom, width - panel_left, bottom - header_bottom)


def configured_measurement_panel(
    screen_image: np.ndarray,
    config: dict[str, Any],
) -> Roi | None:
    """Use the known device layout as a guarded fallback for poor exposure.

    The automatic blue-header detector is preferred. This fallback is still
    configuration-driven and is accepted only when row geometry is visible,
    so a blank or unrelated screen is not silently treated as a panel.
    """
    validation = config.get("layout_validation", {})
    relative = validation.get("panel_roi_relative")
    if not relative:
        return None
    parent = Roi(0, 0, screen_image.shape[1], screen_image.shape[0])
    panel = parse_relative_roi({"panel": relative}, "panel", parent)
    if panel is None:
        return None
    try:
        panel_image = crop_roi(screen_image, panel)
    except ValueError:
        return None
    return panel if detect_measurement_rows(panel_image) else None


def locate_measurement_panel(
    screen_image: np.ndarray,
    config: dict[str, Any],
) -> Roi | None:
    """Locate the panel automatically, then use a guarded known-layout fallback."""
    return detect_measurement_panel(screen_image) or configured_measurement_panel(screen_image, config)


def read_measurement_rows(
    image: np.ndarray,
    screen: Roi,
    config: dict[str, Any],
    run_dir: Path,
) -> list[MeasurementReading]:
    settings = config.get("preprocess", {})
    ocr = config.get("ocr", {})
    results = []
    for item in config["measurements"]:
        row_roi = parse_relative_roi(item, "row_roi_relative", screen)
        value_roi = parse_relative_roi(item, "value_roi_relative", screen)
        if row_roi is None or value_roi is None:
            raise ValueError("Each measurement needs row_roi_relative and value_roi_relative")
        measurement_id = str(item["id"])
        row_path = save_image(run_dir / f"{measurement_id}_row.png", crop_roi(image, row_roi))
        value_path = save_image(run_dir / f"{measurement_id}_value.png", crop_roi(image, value_roi))
        processed = preprocess_for_digits(crop_roi(image, value_roi), settings)
        processed_path = save_image(run_dir / f"{measurement_id}_processed.png", processed)
        raw_text = ""
        error_code = ""
        try:
            raw_text = tesseract_text(
                processed,
                int(ocr.get("value_psm", 7)),
                str(ocr.get("value_allowlist", "")),
            )
        except RuntimeError:
            error_code = "OCR_UNAVAILABLE"
        except Exception as exc:
            error_code = f"OCR_FAILED:{type(exc).__name__}"
        value, detected_unit = parse_value_and_unit(raw_text)
        # The configured unit is a fallback only; the row image remains available for review.
        unit = (detected_unit or str(item.get("default_unit", ""))) if value is not None else ""
        if not error_code and value is not None and bool(item.get("require_detected_unit", False)) and not detected_unit:
            error_code = "UNIT_MISSING"
        allowed_units = [str(candidate).lower() for candidate in item.get("allowed_units", [])]
        if not error_code and detected_unit and allowed_units and detected_unit.lower() not in allowed_units:
            error_code = "UNIT_MISMATCH"
        if not error_code and value is not None and "min_value" in item and value < float(item["min_value"]):
            error_code = "VALUE_OUT_OF_RANGE"
        if not error_code and value is not None and "max_value" in item and value > float(item["max_value"]):
            error_code = "VALUE_OUT_OF_RANGE"
        if not error_code and value is None:
            error_code = "VALUE_PARSE_FAILED"
        results.append(MeasurementReading(
            measurement_id=measurement_id,
            label=str(item["label"]),
            channel=str(item.get("channel", "")),
            label_source="config",
            value=value,
            unit=unit,
            valid=not bool(error_code),
            error_code=error_code,
            raw_text=raw_text,
            row_roi_path=row_path,
            value_roi_path=value_path,
            processed_value_path=processed_path,
        ))
    return results


def read_instrument_image(
    image_path: Path,
    config_path: Path,
    out_dir: Path,
    request_id: str | None = None,
    run_dir: Path | None = None,
) -> ReadingResult:
    config = load_config(config_path)
    request_id = request_id or str(uuid.uuid4())
    captured_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
    if run_dir is None:
        run_dir = out_dir / f"{datetime.now(CN_TZ).strftime('%Y%m%d_%H%M%S')}_{request_id[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    original_copy = run_dir / image_path.name
    shutil.copy2(image_path, original_copy)

    image = cv2.imread(str(image_path))
    if image is None:
        result = ReadingResult(
            request_id=request_id,
            device_id=config.get("device_id", ""),
            source=config.get("source", "vision"),
            value=None,
            unit=config.get("default_unit", ""),
            valid=False,
            captured_at=captured_at,
            image_path=str(original_copy.resolve()),
            error_code="IMAGE_READ_FAILED",
            confidence=0.0,
            raw_text="",
            value_roi_path="",
            unit_roi_path="",
            processed_value_path="",
        )
        save_reading_result(run_dir, result)
        return result

    value_roi, unit_roi, detection = resolve_rois(image, config)
    preprocess_settings = config.get("preprocess", {})
    ocr_settings = config.get("ocr", {})

    screen_image = None
    if detection is not None:
        save_image(run_dir / "screen_detection.png", detection.debug_image)
        if detection.screen_roi is not None:
            screen_image = rectify_screen(image, detection, config.get("locator", {}))
            save_image(run_dir / "screen_roi.png", screen_image)
            if detection.screen_quad is not None:
                save_image(run_dir / "screen_rectified.png", screen_image)
            if config.get("measurements"):
                panel = locate_measurement_panel(screen_image, config)
                if panel is not None:
                    panel_image = crop_roi(screen_image, panel)
                    save_image(run_dir / "measurement_panel.png", panel_image)
                    for index, row in enumerate(detect_measurement_rows(panel_image), start=1):
                        save_image(run_dir / f"measurement_row_{index}.png", crop_roi(panel_image, row))
                    try:
                        panel_text = tesseract_text(panel_image, 6, "", lang="chi_sim+eng")
                    except Exception as exc:
                        panel_text = f"OCR_FAILED: {type(exc).__name__}"
                    (run_dir / "measurement_panel_ocr.txt").write_text(panel_text, encoding="utf-8")

    if config.get("measurements") or config.get("dynamic_measurements"):
        if detection is None or detection.screen_roi is None:
            measurements = []
            multi_error = "SCREEN_NOT_FOUND"
        else:
            if screen_image is None:
                raise RuntimeError("Detected screen image was not prepared")
            if config.get("dynamic_measurements"):
                panel = locate_measurement_panel(screen_image, config)
                measurements = read_dynamic_measurement_rows(
                    crop_roi(screen_image, panel), run_dir, config
                ) if panel else []
                multi_error = next((item.error_code for item in measurements if item.error_code), "")
                if not measurements:
                    multi_error = "MEASUREMENT_ROWS_NOT_FOUND"
            elif not validate_measurement_layout(screen_image, config):
                measurements = []
                multi_error = "LAYOUT_MISMATCH"
            else:
                normalized_screen = Roi(0, 0, w=screen_image.shape[1], h=screen_image.shape[0])
                measurements = read_measurement_rows(screen_image, normalized_screen, config, run_dir)
                multi_error = next((item.error_code for item in measurements if item.error_code), "")
        result = ReadingResult(
            request_id=request_id,
            device_id=config.get("device_id", ""),
            source=config.get("source", "vision"),
            value=None,
            unit="",
            valid=bool(measurements) and not multi_error,
            captured_at=captured_at,
            image_path=str(original_copy.resolve()),
            error_code=multi_error,
            confidence=(round(0.9 * sum(item.valid for item in measurements) / len(measurements), 2)
                        if measurements else 0.0),
            raw_text="",
            value_roi_path="",
            unit_roi_path="",
            processed_value_path="",
            measurements=measurements,
        )
        save_reading_result(run_dir, result)
        return result

    value_image = crop_roi(image, value_roi)
    unit_image = crop_roi(image, unit_roi) if unit_roi else np.zeros((1, 1, 3), dtype=np.uint8)
    processed_value = preprocess_for_digits(value_image, preprocess_settings)
    processed_unit = preprocess_for_digits(unit_image, {**preprocess_settings, "threshold": "none"})

    value_roi_path = save_image(run_dir / "value_roi.png", value_image)
    unit_roi_path = save_image(run_dir / "unit_roi.png", unit_image)
    processed_value_path = save_image(run_dir / "value_processed.png", processed_value)
    save_image(run_dir / "unit_processed.png", processed_unit)

    raw_value_text = ""
    raw_unit_text = ""
    error_code = ""
    try:
        raw_value_text = tesseract_text(
            processed_value,
            int(ocr_settings.get("value_psm", 7)),
            str(ocr_settings.get("value_allowlist", "")),
        )
        if unit_roi:
            raw_unit_text = tesseract_text(
                processed_unit,
                int(ocr_settings.get("unit_psm", 7)),
                str(ocr_settings.get("unit_allowlist", "")),
            )
    except RuntimeError:
        error_code = "OCR_UNAVAILABLE"
    except Exception as exc:  # OCR engines can fail for environment-specific reasons.
        error_code = f"OCR_FAILED:{type(exc).__name__}"

    value = parse_value(raw_value_text)
    unit = clean_unit(raw_unit_text, config.get("default_unit", ""))
    raw_text = " ".join(part for part in [raw_value_text, raw_unit_text] if part).strip()
    confidence = estimate_confidence(value, unit, raw_text)

    if not error_code and detection is not None and detection.error_code:
        error_code = detection.error_code
    if not error_code and value is None:
        error_code = "VALUE_PARSE_FAILED"

    result = ReadingResult(
        request_id=request_id,
        device_id=config.get("device_id", ""),
        source=config.get("source", "vision"),
        value=value,
        unit=unit,
        valid=(value is not None and not error_code),
        captured_at=captured_at,
        image_path=str(original_copy.resolve()),
        error_code=error_code,
        confidence=confidence,
        raw_text=raw_text,
        value_roi_path=value_roi_path,
        unit_roi_path=unit_roi_path,
        processed_value_path=processed_value_path,
    )

    save_reading_result(run_dir, result)

    return result


