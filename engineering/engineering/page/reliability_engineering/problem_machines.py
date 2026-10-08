"""Problem-machine ranking derived from the existing reliability report.

No source metrics or repeat definitions are recalculated here. Fleet maxima
are computed before Top N is applied, so changing Top N cannot change scores.
"""

from collections import defaultdict

import frappe

from engineering.engineering.page.reliability_engineering.reliability_engineering import get_dashboard


def build_problem_report(report, show_top=5):
    show_top = int(show_top)
    if not 1 <= show_top <= 10:
        raise ValueError("Show Top must be between 1 and 10")
    rows = [dict(row) for row in report["ranking"] if row["breakdowns"] > 0]
    problems = defaultdict(lambda: defaultdict(lambda: {"events": 0, "repeats": 0}))
    reasons = defaultdict(dict)
    for event in report["breakdowns"]:
        if not event.get("asset"):
            continue
        counts = problems[event["asset"]][event.get("classification") or "Unclassified"]
        counts["events"] += 1
        counts["repeats"] += bool(event.get("repeat"))
        reason = (event.get("reason") or "").strip()
        if reason:
            reason_counts = reasons[event["asset"]].setdefault(reason.casefold(), {"label": reason, "events": 0})
            reason_counts["label"] = min(reason_counts["label"], reason)
            reason_counts["events"] += 1
    keys = ("breakdown_hours", "breakdowns", "bdfr", "mttr", "repeat_rate", "inverse_mtbf")
    for row in rows:
        # Preserve the original MTBF field, but zero operating hours cannot
        # establish reliability exposure and must not become infinity.
        valid_exposure = row["bdfr"] is not None and row["bdfr"] > 0
        # BDFR retains the ratio when display-rounded hours/MTBF are zero.
        # BDFR / 1,000 = failures / operating hours = inverse MTBF.
        row["score_mtbf"] = (row["mtbf"] or 1000 / row["bdfr"]) if valid_exposure else None
        row["inverse_mtbf"] = row["bdfr"] / 1000 if valid_exposure else None
    maxima = {key: max((row[key] for row in rows if row[key] is not None), default=0) for key in keys}
    for row in rows:
        available = [key for key in keys if row[key] is not None]
        components = [row[key] / maxima[key] if maxima[key] else 0 for key in available]
        score = 100 * sum(components) / len(components)
        row["problem_score"] = round(score, 2)
        row["score_metrics"] = len(available)
        row["missing_metrics"] = ["MTBF" if key == "inverse_mtbf" else key.upper().replace("_", " ") for key in keys if key not in available]
        classes = problems[row["asset"]]
        ordered = sorted(classes, key=lambda name: (-classes[name]["repeats"], -classes[name]["events"], name))
        main = ordered[0] if ordered else "Unclassified"
        row["main_problem"] = main
        row["main_problem_repeats"] = classes[main]["repeats"]
        row["main_problem_events"] = classes[main]["events"]
        row["main_problem_unverified"] = False
        if main == "Unclassified" and reasons[row["asset"]]:
            reason = sorted(reasons[row["asset"]].values(), key=lambda item: (-item["events"], item["label"]))[0]
            row["main_problem"] = reason["label"]
            row["main_problem_events"] = reason["events"]
            row["main_problem_unverified"] = True
        row["_score"] = score
    rows.sort(key=lambda row: (-row["_score"], -row["breakdown_hours"], -row["breakdowns"], row["asset_label"], row["asset"]))
    selected = rows[:show_top]
    for rank, row in enumerate(selected, 1):
        row["rank"] = rank
        row.pop("_score")
        row.pop("inverse_mtbf")
    return {"ranking": selected, "total_machines": len(rows), "show_top": show_top,
            "quality": report["quality"]}


@frappe.whitelist()
def get_problem_machines(from_date=None, to_date=None, location=None, show_top=5):
    try:
        show_top = int(show_top)
        if not 1 <= show_top <= 10:
            raise ValueError
    except (TypeError, ValueError):
        frappe.throw("Show Top must be between 1 and 10")
    # Existing endpoint provides permissions, validation, queries and ratios.
    return build_problem_report(get_dashboard(from_date, to_date, location), show_top)
