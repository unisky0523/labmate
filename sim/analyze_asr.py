#!/usr/bin/env python3
"""Summarize paired ASR measurements, including team-reported manual timings."""
import argparse
import csv
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def analyze(path):
    rows = list(csv.DictReader(Path(path).open(encoding='utf-8-sig', newline='')))
    if not rows:
        raise ValueError('No rows.')
    kinds = {row['kind'] for row in rows}
    if kinds != {'measurement'}:
        raise ValueError('All rows must be measurements.')
    selected = []
    methods = []
    for row in rows:
        eligible = {'correct', 'measured'}
        if row['status_a'] in eligible and row['status_b'] in eligible:
            if not row['response_a_s'] or not row['response_b_s']:
                continue
            method = row.get('measurement_method', '').strip() or 'not_recorded'
            if 'measured' in (row['status_a'], row['status_b']) and method != 'manual':
                raise ValueError('The measured status requires measurement_method=manual.')
            a, b = float(row['response_a_s']), float(row['response_b_s'])
            if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < 0:
                raise ValueError('Response time must be finite and nonnegative.')
            selected.append((a, b))
            methods.append(method)
    result = {'kind': next(iter(kinds)), 'rows': len(rows), 'accepted_pairs': len(selected),
              'status_counts_a': dict(Counter(row['status_a'] for row in rows)),
              'status_counts_b': dict(Counter(row['status_b'] for row in rows)),
              'measurement_methods': dict(Counter(methods))}
    if selected:
        a, b = zip(*selected)
        ma, mb = statistics.median(a), statistics.median(b)
        result.update(median_a_s=round(ma, 6), median_b_s=round(mb, 6), median_difference_s=round(ma-mb, 6),
                      median_reduction_percent=round((ma-mb)/ma*100, 6) if ma else None,
                      range_a_s=[min(a), max(a)], range_b_s=[min(b), max(b)])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    args = parser.parse_args()
    print(json.dumps(analyze(args.csv), indent=2, ensure_ascii=False))
