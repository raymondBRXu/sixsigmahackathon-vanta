"""Plain, deterministic matching of the eight course-image Individuals rules.

The caller supplies the existing Individuals CL and moving-range sigma estimate.
These retrospective patterns are exploratory matches, not calibrated alarms or
evidence of a particular physical cause. Indices include missing scheduled slots.
"""

from math import isfinite, isnan


RULESET = "course-eight-tests-v1"
RULES = {
    "T1": (1, "Point beyond 3 sigma", "One point lies strictly beyond 3 sigma from the centerline."),
    "T2": (3, "Two of three beyond 2 sigma", "At least two of three consecutive points lie beyond 2 sigma on the same side."),
    "T3": (5, "Four of five beyond 1 sigma", "At least four of five consecutive points lie beyond 1 sigma on the same side."),
    "T4": (8, "Eight points on one side", "Eight consecutive points lie strictly on the same side of the centerline."),
    "T5": (6, "Six-point trend", "Six consecutive points strictly increase or strictly decrease."),
    "T6": (15, "Fifteen points within 1 sigma", "Fifteen consecutive points lie within the inclusive 1-sigma band."),
    "T7": (8, "Eight points outside 1 sigma", "Eight consecutive points lie outside the 1-sigma band, with both sides represented."),
    "T8": (14, "Fourteen alternating points", "Fourteen consecutive points alternate upward and downward, with no equal adjacent values."),
}
SIGMA_RULES = {"T1", "T2", "T3", "T6", "T7"}
ORDER_RULES = {"T5", "T8"}


def _finite_number(value):
    if value is None:
        return None
    number = float(value)
    return number if isfinite(number) else None


def _match(rule, values, centerline, sigma):
    """Return (direction, relative contributing indices), or None."""
    all_indices = list(range(len(values)))
    if rule in ORDER_RULES:
        differences = [right - left for left, right in zip(values, values[1:])]
        if rule == "T5":
            if all(difference > 0 for difference in differences):
                return "increasing", all_indices
            if all(difference < 0 for difference in differences):
                return "decreasing", all_indices
        elif all(difference != 0 for difference in differences) and all(
            (left > 0) != (right > 0) for left, right in zip(differences, differences[1:])
        ):
            return "alternating", all_indices
        return None

    deviations = [value - centerline for value in values]
    if rule == "T1":
        if abs(deviations[0]) > 3 * sigma:
            return ("above" if deviations[0] > 0 else "below"), all_indices
    elif rule in {"T2", "T3"}:
        threshold, required = (2 * sigma, 2) if rule == "T2" else (sigma, 4)
        for direction, sign in (("above", 1), ("below", -1)):
            contributors = [index for index, deviation in enumerate(deviations) if sign * deviation > threshold]
            if len(contributors) >= required:
                return direction, contributors
    elif rule == "T4":
        if all(deviation > 0 for deviation in deviations):
            return "above", all_indices
        if all(deviation < 0 for deviation in deviations):
            return "below", all_indices
    elif rule == "T6":
        if all(abs(deviation) <= sigma for deviation in deviations):
            return "within", all_indices
    elif rule == "T7":
        if (all(abs(deviation) > sigma for deviation in deviations)
                and any(deviation > 0 for deviation in deviations)
                and any(deviation < 0 for deviation in deviations)):
            return "both", all_indices
    return None


def detect_special_causes(values, centerline, sigma):
    """Match all eight rules without removing gaps or estimating new limits.

    Missing values (None/NaN) interrupt every candidate window. Strict thresholds
    exclude equality except T6's inclusive band. T4 needs CL; T5/T8 need no
    estimates; other rules require a finite CL and positive finite sigma.
    """
    sequence = [float("nan") if value is None else float(value) for value in values]
    if any(not isfinite(value) and not isnan(value) for value in sequence):
        raise ValueError("Pattern values must be finite or missing.")
    centerline = _finite_number(centerline)
    sigma = _finite_number(sigma)
    result = {"status": "enabled", "ruleset": RULESET, "rule_status": {}, "events": [], "issues": []}

    for rule, (size, title, description) in RULES.items():
        reason = None
        if rule not in ORDER_RULES and centerline is None:
            reason = "A finite centerline is unavailable."
        elif rule in SIGMA_RULES and (sigma is None or sigma <= 0):
            reason = "A positive finite Individuals sigma estimate is unavailable."
        events = []
        evaluated = 0
        if reason is None:
            for start in range(len(sequence) - size + 1):
                window = sequence[start:start + size]
                if any(isnan(value) for value in window):
                    continue
                evaluated += 1
                match = _match(rule, window, centerline, sigma)
                if match is not None:
                    direction, contributors = match
                    events.append({
                        "rule": rule, "start_index": start, "end_index": start + size - 1,
                        "trigger_index": start + size - 1,
                        "contributing_indices": [start + index for index in contributors],
                        "direction": direction,
                    })
            if not evaluated:
                reason = f"Requires {size} consecutive observed reading{'s' if size != 1 else ''}."
        result["rule_status"][rule] = {
            "status": "unavailable" if reason else "detected" if events else "not_detected",
            "reason": reason, "evaluated_windows": evaluated,
        }
        result["events"].extend(events)
        if events:
            result["issues"].append({
                "id": rule, "title": title, "description": description,
                "point_indices": sorted({index for event in events for index in event["contributing_indices"]}),
                "event_count": len(events),
            })
    return result
