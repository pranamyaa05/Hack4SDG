"""Evaluate supplied physical reference data; never generate trial results."""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

REQUIRED = {"object_id", "method", "dimension", "estimate_mm", "reference_mm"}


def evaluate(rows):
    groups = defaultdict(list)
    repeats = defaultdict(list)
    count = 0
    for row in rows:
        if not REQUIRED.issubset(row):
            raise ValueError("CSV must include: " + ", ".join(sorted(REQUIRED)))
        estimate, reference = float(row["estimate_mm"]), float(row["reference_mm"])
        if not all(math.isfinite(v) and v > 0 for v in (estimate, reference)):
            raise ValueError("Estimates and references must be positive finite values")
        if any(not row[k].strip() for k in ("object_id", "method", "dimension")):
            raise ValueError("Object ID, method, and dimension must be nonempty")
        key = (row["method"], row["dimension"])
        groups[key].append(estimate - reference)
        repeats[(*key, row["object_id"])].append(estimate)
        count += 1
    if count == 0:
        raise ValueError(
            "No measurements supplied; empty templates are not evaluation results"
        )
    results = []
    for (method, dimension), errors in sorted(groups.items()):
        repetition = [
            stdev(values)
            for (m, d, o), values in repeats.items()
            if (m, d) == (method, dimension) and len(values) > 1
        ]
        results.append(
            dict(
                method=method,
                dimension=dimension,
                n=len(errors),
                objects=len(
                    {o for m, d, o in repeats if (m, d) == (method, dimension)}
                ),
                mean_absolute_error_mm=mean(abs(e) for e in errors),
                max_absolute_error_mm=max(abs(e) for e in errors),
                bias_mm=mean(errors),
                within_1_mm_fraction=mean(abs(e) <= 1 for e in errors),
                mean_within_object_sd_mm=mean(repetition) if repetition else None,
            )
        )
    return {
        "kind": "supplied_reference_measurement_evaluation",
        "rows": count,
        "results": results,
        "limitations": [
            "Ground-truth quality and independence are the experimenter's responsibility.",
            "Results apply only to the supplied objects and capture conditions.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        with args.csv_file.open(newline="", encoding="utf-8-sig") as handle:
            report = evaluate(csv.DictReader(handle))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    payload = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
