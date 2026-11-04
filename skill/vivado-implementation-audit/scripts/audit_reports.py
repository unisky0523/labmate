#!/usr/bin/env python3
"""Audit Vivado post-route timing, utilization and DRC text reports."""
import argparse
import json
from pathlib import Path
import re


RESOURCE_LABELS = {
    "lut": ("Slice LUTs", "CLB LUTs"),
    "ff": ("Slice Registers", "CLB Registers"),
    "bram36_equivalent": ("Block RAM Tile",),
    "dsp": ("DSPs", "DSP Slices"),
    "slice_or_clb": ("Slice", "CLB"),
}
COVERAGE = ("no_clock", "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay")


def header(report, key):
    match = re.search(rf"^\|\s*{re.escape(key)}\s*:\s*(.+)$", report, re.M)
    return match[1].strip() if match else None


def timing_summary(report):
    lines = report.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "| Design Timing Summary"), None)
    if start is None:
        raise ValueError("Design Timing Summary not found")
    title = next((i for i in range(start + 1, min(start + 12, len(lines)))
                  if lines[i].lstrip().startswith("WNS(ns)") and "WPWS(ns)" in lines[i]), None)
    if title is None:
        raise ValueError("Unsupported timing table header")
    data = lines[title + 2].split()
    if len(data) != 12:
        raise ValueError("Expected the 12-column Vivado design timing summary")
    groups = {}
    for name, index in zip(("setup", "hold", "pulse_width"), (0, 4, 8)):
        worst, total = map(float, data[index:index + 2])
        failing, endpoints = map(int, data[index + 2:index + 4])
        groups[name] = dict(worst_slack_ns=worst, total_slack_ns=total,
                            failing_endpoints=failing, total_endpoints=endpoints)
    coverage = {}
    for key in COVERAGE:
        match = re.search(rf"^\s*\d+\. checking {key} \((\d+)\)\s*$", report, re.M)
        coverage[key] = int(match[1]) if match else None
    return groups, coverage


def utilization(report):
    rows = [tuple(cell.strip().rstrip("*").strip() for cell in line.strip().strip("|").split("|"))
            for line in report.splitlines() if line.lstrip().startswith("|")]
    result = {}
    for kind, labels in RESOURCE_LABELS.items():
        row = next((row for row in rows if row[0] in labels and len(row) in (5, 6)), None)
        if row is None:
            if kind == "slice_or_clb":
                continue
            raise ValueError(f"Missing utilization row for {kind}")
        used, capacity, percent = (float(row[i].replace(",", "")) for i in (1, -2, -1))
        result[kind] = dict(used=used, available=capacity, percent=percent)
    return result


def drc_counts(report):
    total = re.search(r"^\s*Violations found:\s*(\d+)\s*$", report, re.M)
    if not total:
        raise ValueError("DRC summary count not found")
    summary = report[total.end():].split("2. REPORT DETAILS", 1)[0]
    counts = {}
    for _, severity, count in re.findall(r"^\|\s*(\S+)\s*\|\s*([^|]+?)\s*\|[^|]*\|\s*(\d+)\s*\|\s*$", summary, re.M):
        counts[severity] = counts.get(severity, 0) + int(count)
    if sum(counts.values()) != int(total[1]):
        raise ValueError("DRC table does not reconcile with reported total")
    return counts


def audit(directory):
    def read(name):
        return (directory / name).read_text(encoding="utf-8-sig", errors="replace")

    timing, util, drc = (read(name) for name in ("timing.rpt", "utilization.rpt", "drc.rpt"))
    designs = [header(text, "Design") for text in (timing, util, drc)]
    if None in designs or len(set(designs)) != 1:
        raise ValueError("Reports must identify the same top-level design")
    stage = header(util, "Design State")
    if not stage or "route" not in stage.lower() or header(drc, "Design State") != "Fully Routed":
        raise ValueError("Provide reports from an implemented routed design")
    paths, coverage = timing_summary(timing)
    resources, counts = utilization(util), drc_counts(drc)
    timing_ok = all(row["total_endpoints"] > 0 and row["failing_endpoints"] == 0
                    and row["worst_slack_ns"] >= 0 and row["total_slack_ns"] >= 0 for row in paths.values())
    drc_ok = all(severity.lower() in ("warning", "advisory", "info", "informational")
                 for severity in counts)
    resource_ok = all(row["used"] <= row["available"] for row in resources.values())
    return dict(design=designs[0], device=header(util, "Device"), stage=stage, timing=paths,
                constrained_timing_pass=timing_ok, coverage=coverage,
                coverage_review_required=any(count != 0 for count in coverage.values()),
                utilization=resources, resource_capacity_pass=resource_ok, drc=counts,
                drc_no_error_or_critical=drc_ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.report_dir)
    except (OSError, ValueError, IndexError) as error:
        parser.exit(1, f"Report input error: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    if not all(result[key] for key in ("constrained_timing_pass", "resource_capacity_pass", "drc_no_error_or_critical")):
        return 1
    return 2 if result["coverage_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
