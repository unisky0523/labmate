"""Parse spatial PaddleOCR evidence without discarding SI prefixes."""
from __future__ import annotations

from dataclasses import asdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Any

import cv2
import numpy as np

from c_vision import reader as base
from c_vision_paddle.backend import recognize

ORIGINAL_LOCATE_PANEL = base.locate_measurement_panel

VOLTAGE = {"V", "mV", "uV", "nV"}
FREQUENCY = {"Hz", "mHz", "kHz", "MHz", "GHz"}
TIME = {"s", "ms", "us", "ns", "ps"}
LABEL_UNITS = {
    "峰峰值": VOLTAGE, "峰值": VOLTAGE, "幅值": VOLTAGE,
    "平均值": VOLTAGE, "最大值": VOLTAGE, "最小值": VOLTAGE,
    "高电平": VOLTAGE, "低电平": VOLTAGE, "高值": VOLTAGE,
    "低值": VOLTAGE, "最大电平": VOLTAGE, "有效值": VOLTAGE,
    "平均-FS": VOLTAGE,
    "频率": FREQUENCY, "周期": TIME, "相移": {"deg"},
    "+占空比": {"%"}, "-占空比": {"%"}, "占空比": {"%"},
    "上升时间": TIME, "下降时间": TIME,
}
ALIASES = {
    "峰-峰值": "峰峰值", "峰－峰值": "峰峰值", "均方根": "有效值",
    # PP-OCRv5 repeatedly confuses the small second character in 相移 with 卷.
    # Keep this correction exact so unrelated labels are not accepted.
    "相卷": "相移", "相修": "相移",
    "低道": "低值",
}
VALUE = re.compile(
    r"(?<![\w.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*"
    r"(GHz|MHz|kHz|mHz|Hz|nV|uV|mV|V|ps|ns|us|ms|s|deg|°|%)"
    r"(?![A-Za-z])"
)
CURSOR_UNITS = {"ΔX": TIME, "1/ΔX": FREQUENCY, "ΔY": VOLTAGE}


def values(text: str) -> list[tuple[float, str]]:
    text = text.replace("−", "-").replace("µ", "u").replace("μ", "u")
    text = re.sub(r"(?<=\d)[QO](?=\d)", "0", text)
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    # Only normalize the Hz suffix, never the SI prefix (m and M differ).
    text = re.sub(r"[Hh][Zz]", "Hz", text)
    text = re.sub(r"(?<=\d)([mnu]?)v\b", r"\1V", text)
    return [(float(match[1]), "deg" if match[2] == "°" else match[2])
            for match in VALUE.finditer(text)]


def label_from_text(text: str) -> str | None:
    for alias, name in ALIASES.items():
        text = text.replace(alias, name)
    if re.search(r"平均\s*[-－]?\s*FS", text, re.IGNORECASE):
        return "平均-FS"
    if re.search(r"[\u4e00-\u9fff]-[\u4e00-\u9fff]值", text):
        return "峰峰值"
    text = text.replace("頻率", "频率")
    exact_names = []
    fuzzy_names = []
    for line in text.splitlines():
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", line))
        if not chinese:
            continue
        if chinese in LABEL_UNITS:
            name = chinese
            if name == "占空比" and line.lstrip().startswith(("+", "-")):
                name = line.lstrip()[0] + name
            exact_names.append(name)
            continue
        scores = sorted(((SequenceMatcher(None, chinese, name).ratio(), name)
                         for name in LABEL_UNITS if name not in {"+占空比", "-占空比"}), reverse=True)
        if scores[0][0] >= 0.72 and scores[0][0] - scores[1][0] >= 0.12:
            fuzzy_names.append(scores[0][1])
    # A literal supported label is stronger than a fuzzy guess from another
    # OCR pass over the same title. Conflicting literal labels stay invalid.
    unique_exact = set(exact_names)
    if len(unique_exact) == 1:
        return exact_names[0]
    if len(unique_exact) > 1:
        return None
    unique = set(fuzzy_names)
    return next(iter(unique)) if len(unique) == 1 else None


def locate_panel(screen: np.ndarray, config: dict[str, Any]) -> base.Roi | None:
    found = ORIGINAL_LOCATE_PANEL(screen, config)
    height, width = screen.shape[:2]
    sidebar_x = int(width * 0.76)
    sidebar = screen[int(height * 0.35):int(height * 0.94), sidebar_x:]
    lines = recognize(sidebar, minimum_score=0.50)
    titles = [line for line in lines if line.y > sidebar.shape[0] * 0.15
              and label_from_text(line.text)]
    if len(titles) >= 2:
        start = int(height * 0.35) + titles[0].y - 12
        if found is None or found.y > start + 8:
            return base.Roi(sidebar_x, max(0, start), width - sidebar_x,
                            height - max(0, start))
    headers = [line for line in lines if "测量" in line.text or "測量" in line.text]
    if len(headers) == 1:
        start = int(height * 0.35) + headers[0].y + headers[0].h
        bottom = height
        if bottom - start >= height * 0.12:
            if found is None or found.y > start + 30:
                return base.Roi(sidebar_x, start, width - sidebar_x, bottom - start)
            return found

    # The blue header can be washed out and its Chinese text lost, while the
    # repeated value/unit lines remain legible. Use their layout as an anchor.
    numeric = [line for line in lines if line.score >= 0.80 and len(values(line.text)) == 1
               and line.y > sidebar.shape[0] * 0.15]
    numeric.sort(key=lambda line: line.y)
    if not 2 <= len(numeric) <= 4:
        return found
    centers = [line.y + line.h / 2 for line in numeric]
    gaps = np.diff(centers)
    if (not len(gaps) or min(gaps) < height * 0.045
            or max(gaps) > height * 0.14):
        return found
    first_y = int(height * 0.35) + numeric[0].y
    start = max(0, first_y - int(np.median(gaps) * 0.75))
    # OCR may miss the final value, so do not truncate at its last detection.
    bottom = height
    if bottom - start < height * 0.12:
        return found
    if found is not None and found.y <= start + 30:
        return found
    return base.Roi(sidebar_x, start, width - sidebar_x, bottom - start)


def rows_from_ocr(lines: list[Any], height: int, width: int) -> list[base.Roi]:
    numeric = sorted((line for line in lines if values(line.text) and line.score >= 0.75),
                     key=lambda line: line.y)
    if not 2 <= len(numeric) <= 4:
        return []
    bounds = [0]
    for line in numeric[:-1]:
        bounds.append(min(height, line.y + line.h + max(2, int(line.h * 0.12))))
    gap = int(np.median(np.diff([line.y + line.h / 2 for line in numeric])))
    bounds.append(min(height, numeric[-1].y + numeric[-1].h + max(4, gap // 4)))
    if any(b - a < 38 for a, b in zip(bounds, bounds[1:])):
        return []
    return [base.Roi(0, a, width, b - a) for a, b in zip(bounds, bounds[1:])]


def channels_from_title(text: str) -> list[str]:
    text = text.replace("（", "(").replace("）", ")")
    pairs = re.findall(r"[\[({]\s*([12])\s*[-→>]+\s*([12])", text)
    if pairs:
        return list(dict.fromkeys(a + "-" + b for a, b in pairs))
    singles = re.findall(r"[\[({]\s*([12])\s*[\])}]", text)
    # Some photos lose the opening bracket; accept only after a known title.
    if not singles:
        for line in text.splitlines():
            if label_from_text(line):
                match = re.search(r"[\u4e00-\u9fff]\s*([12])\s*[\])}]", line)
                if not match:
                    match = re.search(r"[\u4e00-\u9fff]\s*([12])\s*$", line)
                if match:
                    singles.append(match[1])
    if not singles and label_from_text(text) and not values(text):
        if re.search(r"(?:[（(]\s*)?M\s*(?:[）):：])?\s*$", text, re.IGNORECASE):
            singles.append("M")
    return list(dict.fromkeys(singles))


def cursor_title(text: str) -> tuple[str, str] | None:
    compact = re.sub(r"\s+", "", text).replace("∆", "Δ").replace("△", "Δ")
    compact = compact.rstrip(":：")
    # Small delta is often read as A, and the slash in 1/ΔX as I.
    if re.fullmatch(r"1[/I|7]?[ΔA]X(?:C)?", compact, re.IGNORECASE):
        return "1/ΔX", ""
    if re.fullmatch(r"[ΔA]X", compact, re.IGNORECASE):
        return "ΔX", ""
    match = re.fullmatch(r"[ΔA]Y(?:[（(]([12])[）)]|([12]))", compact, re.IGNORECASE)
    if match:
        return "ΔY", match[1] or match[2]
    return None


def read_cursor_rows(panel: np.ndarray, run_dir: Path, lines: list[Any]
                     ) -> list[base.MeasurementReading] | None:
    titles = [(line, cursor_title(line.text)) for line in lines]
    titles = [(line, title) for line, title in titles if title is not None]
    if len(titles) < 2:
        return None

    title_gaps = np.diff([line.y for line, _ in titles])
    panel_end = min(panel.shape[0], int(titles[-1][0].y + 1.5 * np.median(title_gaps)))
    panel_lines = [line for line in lines if line.y + line.h / 2 < panel_end]

    audit: dict[str, Any] = {
        "method": "cursor_panel_ocr", "panel_lines": [asdict(line) for line in lines],
        "cursor_panel_end": panel_end, "rows": []
    }
    results = []
    seen: set[tuple[str, str]] = set()
    assigned_numeric: set[int] = set()
    for index, (title_line, (label, channel)) in enumerate(titles, 1):
        next_y = titles[index][0].y if index < len(titles) else panel_end
        row_start = max(0, title_line.y - 5)
        row_end = min(panel.shape[0], next_y)
        row = panel[row_start:row_end]
        row_path = base.save_image(run_dir / f"measurement_row_{index}.png", row)
        candidates = [(value, unit, line_index, line)
                      for line_index, line in enumerate(panel_lines)
                      if title_line.y + title_line.h / 2 < line.y + line.h / 2 < next_y
                      for value, unit in values(line.text)]
        assigned_numeric.update(item[2] for item in candidates)
        value, unit = (candidates[0][0], candidates[0][1]) if len(candidates) == 1 else (None, "")
        duplicate = (label, channel) in seen
        seen.add((label, channel))
        error = ("CURSOR_DUPLICATE" if duplicate else
                 "VALUE_AMBIGUOUS" if len(candidates) > 1 else
                 "VALUE_PARSE_FAILED" if value is None else
                 "UNIT_MISMATCH" if unit not in CURSOR_UNITS[label] else
                 "VALUE_LOW_CONFIDENCE" if candidates[0][3].score < 0.80 else "")
        raw = "\n".join(line.text for line in panel_lines
                        if row_start <= line.y + line.h / 2 < row_end)
        results.append(base.MeasurementReading(
            measurement_id=f"row_{index}", label=label, channel=channel,
            label_source="paddle-cursor-title", value=value, unit=unit,
            valid=not error, error_code=error, raw_text=raw,
            row_roi_path=row_path, value_roi_path="", processed_value_path=""))
        audit["rows"].append({
            "row": index, "title": title_line.text,
            "numeric_candidates": [{"value": v, "unit": u, "score": line.score, "text": line.text}
                                   for v, u, _, line in candidates],
            "error_code": error,
        })

    unassigned = [line.text for line_index, line in enumerate(panel_lines)
                  if line_index not in assigned_numeric and values(line.text)]
    if unassigned:
        results.append(base.MeasurementReading(
            measurement_id=f"row_{len(results) + 1}", label="", channel="",
            label_source="unrecognized", value=None, unit="", valid=False,
            error_code="CURSOR_INCOMPLETE", raw_text="\n".join(unassigned),
            row_roi_path="", value_roi_path="", processed_value_path=""))
        audit["error_code"] = "CURSOR_INCOMPLETE"
    (run_dir / "paddle_evidence.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def read_rows(panel: np.ndarray, run_dir: Path,
              config: dict[str, Any] | None = None) -> list[base.MeasurementReading]:
    rules = (config or {}).get("dynamic_measurements", {})
    if not isinstance(rules, dict):
        rules = {}
    # Fail loudly on environment/model errors, rather than reporting missing rows.
    lines = recognize(panel, minimum_score=0.55)
    cursor_results = read_cursor_rows(panel, run_dir, lines)
    if cursor_results is not None:
        return cursor_results
    rois = base.detect_measurement_rows(panel)
    alternate = rows_from_ocr(lines, panel.shape[0], panel.shape[1])
    def complete_pairs(rows: list[base.Roi]) -> int:
        return sum(bool(label_from_text("\n".join(
                       line.text for line in lines
                       if roi.y <= line.y + line.h / 2 < roi.y + roi.h)))
                   and sum(bool(values(line.text)) for line in lines
                           if roi.y <= line.y + line.h / 2 < roi.y + roi.h) == 1
                   for roi in rows)
    if alternate and (complete_pairs(alternate) > complete_pairs(rois)
                      or (complete_pairs(alternate) == len(alternate)
                          and complete_pairs(rois) == len(alternate)
                          and len(alternate) < len(rois))):
        rois = alternate
    if not int(rules.get("min_rows", 1)) <= len(rois) <= int(rules.get("max_rows", 4)):
        rois = alternate
    if not int(rules.get("min_rows", 1)) <= len(rois) <= int(rules.get("max_rows", 4)):
        return []
    audit: dict[str, Any] = {"method": "single_panel_ocr", "panel_lines": [asdict(line) for line in lines], "rows": []}
    results = []
    cursor_page = any(re.search(r"光标|[Δ∆][XY]|1\s*/\s*[Δ∆]|1/AX", line.text)
                      for line in lines)
    for index, roi in enumerate(rois, 1):
        row = base.crop_roi(panel, roi)
        row_path = base.save_image(run_dir / f"measurement_row_{index}.png", row)
        panel_lines = [line for line in lines if roi.y <= line.y + line.h / 2 < roi.y + roi.h]
        title_lines = [line for line in panel_lines if line.y + line.h / 2 - roi.y < roi.h * 0.57]
        title = "\n".join(line.text for line in title_lines)
        label = label_from_text(title)
        channel_candidates = channels_from_title(title)
        if label is None:
            # A row title can disappear from the full-panel detector. Re-read
            # only that title, leaving numeric OCR and its unit untouched.
            title_crop = row[:max(1, int(roi.h * 0.57)), :max(1, int(roi.w * 0.70))]
            enlarged = cv2.resize(title_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            fallback_lines = recognize(enlarged, minimum_score=0.58)
            fallback_title = "\n".join(line.text for line in fallback_lines)
            fallback_label = label_from_text(fallback_title)
            if fallback_label:
                label = fallback_label
                title = fallback_title
                channel_candidates = channels_from_title(title)
        colors = base.detect_row_channels(row)
        channel = channel_candidates[0] if len(channel_candidates) == 1 else ""
        if not channel and not channel_candidates and label:
            if label == "相移" and len(colors) == 2:
                channel = "-".join(colors)
            elif label != "相移" and len(set(colors)) == 1:
                channel = colors[0]
        number_lines = [line for line in panel_lines if line.y + line.h / 2 - roi.y >= roi.h * 0.40]
        candidates = [(value, unit, line) for line in number_lines
                      for value, unit in values(line.text)]
        value, unit = (candidates[0][0], candidates[0][1]) if len(candidates) == 1 else (None, "")
        score = candidates[0][2].score if len(candidates) == 1 else 0.0
        error = ("UNSUPPORTED_PAGE" if cursor_page else
                 "LABEL_UNRECOGNIZED" if label is None else
                 "CHANNEL_UNRECOGNIZED" if not channel or (label == "相移" and "-" not in channel) else
                 "VALUE_AMBIGUOUS" if len(candidates) > 1 else
                 "VALUE_PARSE_FAILED" if value is None else
                 "UNIT_MISMATCH" if unit not in LABEL_UNITS[label] else
                 "VALUE_LOW_CONFIDENCE" if score < 0.80 else "")
        if not error and value is not None:
            if ((label in {"峰峰值", "频率", "周期", "上升时间", "下降时间", "有效值"} and value < 0)
                    or (label in {"占空比", "+占空比", "-占空比"} and not 0 <= value <= 100)
                    or (label == "相移" and abs(value) > 360)
                    or (label == "相移" and channel.split("-")[0] == channel.split("-")[1] and abs(value) > 0.05)):
                error = "VALUE_INCONSISTENT"
        raw = "\n".join(line.text for line in panel_lines)
        results.append(base.MeasurementReading(
            measurement_id=f"row_{index}", label=label or "", channel=channel,
            label_source="paddle-title" if label else "unrecognized",
            value=value, unit=unit, valid=not error, error_code=error, raw_text=raw,
            row_roi_path=row_path, value_roi_path="", processed_value_path=""))
        audit["rows"].append({"row": index, "title": title,
                              "assigned_lines": [asdict(line) for line in panel_lines],
                              "numeric_candidates": [
                                  {"value": v, "unit": u, "score": line.score, "text": line.text}
                                  for v, u, line in candidates],
                              "error_code": error})
    detected_titles = [line for line in lines if label_from_text(line.text)]
    unavailable = [line for line in lines if re.search(
        r"(?:无|無)(?:边|邊)[缘緣沿]|(?:无|無)信号|超(?:出)?范围|无效", line.text)]
    if unavailable or len(detected_titles) > len(results):
        error = "MEASUREMENT_UNAVAILABLE" if unavailable else "MEASUREMENT_INCOMPLETE"
        results.append(base.MeasurementReading(
            measurement_id=f"row_{len(results) + 1}", label="", channel="",
            label_source="unrecognized", value=None, unit="", valid=False,
            error_code=error,
            raw_text="\n".join(line.text for line in unavailable or detected_titles),
            row_roi_path="", value_roi_path="", processed_value_path=""))
        audit["error_code"] = error
    (run_dir / "paddle_evidence.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
