"""Summarize independently graded review runs. The input belongs to the scorer."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def require_object(value, label):
    if not isinstance(value, dict) or any(not key.strip() for key in value):
        raise ValueError(f"{label}: expected an object with nonempty keys")
    return value


def require_id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected a nonempty identifier")
    return value


def ratio(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def load_run(path):
    data = require_object(json.loads(path.read_text(encoding="utf-8-sig"),
                                     object_pairs_hook=unique_object), "input")
    for field in ("dataset", "grader", "reviewer"):
        require_id(data.get(field), field)
    if data.get("split") not in ("tuning", "holdout"):
        raise ValueError("split: expected tuning or holdout")
    rounds = data.get("rounds")
    if type(rounds) is not int or rounds < 1:
        raise ValueError("rounds: expected a positive integer")
    if data["split"] == "holdout" and rounds != 3:
        raise ValueError("holdout acceptance requires three independently graded rounds")

    defects = require_object(data.get("defects"), "defects")
    defect_prs = set()
    for key, defect in defects.items():
        require_object(defect, key)
        defect_prs.add(require_id(defect.get("pr"), f"{key}.pr"))
        if type(defect.get("critical")) is not bool:
            raise ValueError(f"{key}.critical: expected true or false")
        hits = defect.get("hits")
        if (not isinstance(hits, list) or len(hits) != rounds
                or any(type(hit) is not bool for hit in hits)):
            raise ValueError(f"{key}.hits: expected {rounds} adjudicated booleans")

    clean_prs = require_object(data.get("clean_prs"), "clean_prs")
    if defect_prs.intersection(clean_prs):
        raise ValueError("a confirmed defect PR also appears in the clean cohort")
    for pr, opinions in clean_prs.items():
        require_object(opinions, pr)
        if any(label not in ("invalid", "harmful") for label in opinions.values()):
            raise ValueError(f"{pr}: clean opinions require a final invalid or harmful label")

    feedback = require_object(data.get("real_feedback"), "real_feedback")
    allowed = ("accepted", "wrong", "intentional", "low_value", "pending")
    if any(label not in allowed for label in feedback.values()):
        raise ValueError(f"real_feedback: expected one of {', '.join(allowed)}")
    return data


def summarize(run):
    defects = run["defects"]
    per_round = [
        ratio(sum(item["hits"][index] for item in defects.values()), len(defects))
        for index in range(run["rounds"])
    ]
    feedback = Counter(run["real_feedback"].values())
    invalid = feedback["wrong"] + feedback["intentional"] + feedback["low_value"]
    clean = run["clean_prs"]
    return {
        "reviewer": run["reviewer"],
        "round_recall": per_round,
        "pooled_recall": ratio(sum(row["numerator"] for row in per_round),
                               len(defects) * run["rounds"]),
        "hits_by_defect": {key: sum(item["hits"]) for key, item in defects.items()},
        "real_invalid_rate": ratio(invalid, invalid + feedback["accepted"]),
        "pending_feedback": feedback["pending"],
        "real_feedback_counts": dict(feedback),
        "clean_invalid_per_pr": ratio(sum(len(items) for items in clean.values()), len(clean)),
    }


def harmful_opinions(run):
    return {(pr, key) for pr, items in run["clean_prs"].items()
            for key, label in items.items() if label == "harmful"}


def defect_manifest(run):
    return {key: (item["pr"], item["critical"]) for key, item in run["defects"].items()}


def build_report(baseline, candidate=None):
    context = ("dataset", "grader", "split", "rounds")
    report = {key: baseline[key] for key in context}
    report["baseline"] = summarize(baseline)
    if candidate is None:
        return report
    for key in context:
        if baseline[key] != candidate[key]:
            raise ValueError(f"comparison requires the same {key}")
    if (defect_manifest(baseline) != defect_manifest(candidate)
            or baseline["clean_prs"].keys() != candidate["clean_prs"].keys()):
        raise ValueError("comparison requires matching defect IDs, PR snapshots, critical flags and clean PRs")

    report["candidate"] = summarize(candidate)
    changes = []
    critical_regressions = []
    for key, previous in baseline["defects"].items():
        current = candidate["defects"][key]
        old_count, new_count = sum(previous["hits"]), sum(current["hits"])
        if previous["critical"] and new_count < old_count:
            critical_regressions.append(key)
        changes.append({
            "defect": key, "pr": previous["pr"], "critical": previous["critical"],
            "baseline_hits": previous["hits"], "candidate_hits": current["hits"],
            "hit_count_change": new_count - old_count,
        })
    new_harm = harmful_opinions(candidate) - harmful_opinions(baseline)
    report["defect_comparison"] = changes
    report["manual_review_triggers"] = {
        "critical_regressions": critical_regressions,
        "new_harmful_suggestions": [
            {"pr": pr, "suggestion": key} for pr, key in sorted(new_harm)
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        baseline = load_run(args.baseline)
        candidate = load_run(args.candidate) if args.candidate else None
        report = build_report(baseline, candidate)
    except (ValueError, OSError) as error:
        parser.exit(2, f"score_eval: {error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
