"""Framework-free DockWatch inventory and conditional Individuals-chart calculations.

All clocks are timezone aware. Operational 6/24 thresholds are business rules,
not statistical control limits. Statistical patterns require a fixed, completed
reference period and explicit review before being labeled statistical signals.
Formula source: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm
"""
from __future__ import annotations

import csv
import io
import math
from collections import Counter
from datetime import datetime, time
from statistics import mean
from zoneinfo import ZoneInfo


class DataValidationError(ValueError):
    """An input does not satisfy the documented automatic-snapshot schema."""


def aware_time(value, timezone="America/New_York"):
    """Parse an ISO timestamp and reject ambiguity from an absent UTC offset."""
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("timezone required")
        return stamp.astimezone(ZoneInfo(timezone))
    except (ValueError, TypeError) as exc:
        raise DataValidationError("Timestamp must be an ISO datetime with timezone offset.") from exc


def _station_map(stations):
    result = {}
    for station in stations:
        sid, capacity = station.get("station_id"), station.get("capacity")
        if not sid or sid in result or isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise DataValidationError("Stations need unique IDs and positive integer capacities.")
        result[sid] = station
    if not result:
        raise DataValidationError("At least one configured station is required.")
    return result


def _calendar(settings):
    dates = settings.get("service_dates", [])
    hours = settings.get("hours", [])
    baseline = settings.get("baseline_dates", [])
    if not dates or dates != sorted(set(dates)):
        raise DataValidationError("Service dates must be a nonempty ordered unique calendar.")
    try:
        for day in dates:
            datetime.strptime(day, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise DataValidationError("Service dates must use YYYY-MM-DD.") from exc
    if not hours or hours != sorted(set(hours)) or any(type(h) is not int or not 0 <= h <= 23 for h in hours):
        raise DataValidationError("Hours must be ordered unique integers in 0–23.")
    if baseline != dates[:25] or len(baseline) != 25:
        raise DataValidationError("The baseline must contain the first 25 planned service dates.")
    ZoneInfo(settings.get("timezone", "America/New_York"))
    return dates, hours, baseline


def validate_rows(rows, stations, settings):
    """Reject invalid/duplicate observations; allow absent rows without filling them.

    Output is sorted by timestamp/station with normalized aware datetime values.
    Missingness is accounted for against settings, never converted into zero bikes.
    """
    config = _station_map(stations)
    dates, hours, _ = _calendar(settings)
    expected_ids = settings.get("station_ids")
    if expected_ids is not None and set(expected_ids) != set(config):
        raise DataValidationError("Station configuration and settings IDs disagree.")
    dates, hours = set(dates), set(hours)
    result, seen = [], set()
    for index, row in enumerate(rows, 1):
        if not all(key in row for key in ("timestamp", "station_id", "bikes")):
            raise DataValidationError(f"Row {index}: timestamp, station_id and bikes are required.")
        sid = row["station_id"]
        if sid not in config:
            raise DataValidationError(f"Row {index}: unknown station ID.")
        stamp = aware_time(row["timestamp"], settings.get("timezone", "America/New_York"))
        if stamp.date().isoformat() not in dates or stamp.hour not in hours or stamp.minute or stamp.second or stamp.microsecond:
            raise DataValidationError(f"Row {index}: timestamp is outside the planned hourly calendar.")
        value = row["bikes"]
        if isinstance(value, str):
            value = value.strip()
            if not value or not value.isascii() or not value.isdecimal():
                raise DataValidationError(f"Row {index}: bikes must be a nonnegative integer.")
            value = int(value)
        if type(value) is not int or not 0 <= value <= config[sid]["capacity"]:
            raise DataValidationError(f"Row {index}: bikes must be an integer between zero and capacity.")
        key = (stamp, sid)
        if key in seen:
            raise DataValidationError(f"Row {index}: duplicate station/timestamp.")
        seen.add(key)
        result.append({"timestamp": stamp, "station_id": sid, "bikes": value})
    return sorted(result, key=lambda row: (row["timestamp"], row["station_id"]))


def parse_csv(text, stations, settings):
    """Parse the documented three-column automatic sensor CSV."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if reader.fieldnames != ["timestamp", "station_id", "bikes"]:
        raise DataValidationError("CSV header must be timestamp,station_id,bikes.")
    rows = list(reader)
    if not rows:
        raise DataValidationError("CSV contains no observations.")
    if any(None in row for row in rows):
        raise DataValidationError("A CSV row contains extra columns.")
    return validate_rows(rows, stations, settings)


def snapshot_metrics(counts, capacities, expected_count=None):
    """Descriptive proportions among valid readings, with explicit coverage."""
    if len(counts) != len(capacities):
        raise ValueError("Counts and capacities must have the same length.")
    if any(type(x) is not int or type(c) is not int or c <= 0 or not 0 <= x <= c for x, c in zip(counts, capacities)):
        raise ValueError("Metrics require valid integer counts and positive capacities.")
    n = len(counts)
    expected = n if expected_count is None else expected_count
    if expected < n or expected < 0:
        raise ValueError("Expected count cannot be below observed count.")
    empty = sum(x == 0 for x in counts)
    full = sum(x == c for x, c in zip(counts, capacities))
    available = n - empty - full
    return {"n": n, "expected": expected, "coverage": n / expected if expected else None,
            "empty_count": empty, "full_count": full, "available_count": available,
            "empty_fraction": empty / n if n else None, "full_fraction": full / n if n else None,
            "availability": available / n if n else None,
            "mean_occupancy": mean(x / c for x, c in zip(counts, capacities)) if n else None}


def i_chart_limits(values):
    """Arithmetic-only MR/1.128 limits; None marks missing scheduled positions.

    This function deliberately has no production eligibility/review gate. The
    chart wrapper enforces those. Limits are not clipped to physical capacity.
    """
    if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)) for value in values):
        raise ValueError("Chart values must be finite numbers or None.")
    observed = [value for value in values if value is not None]
    ranges = [abs(right - left) for left, right in zip(values, values[1:]) if left is not None and right is not None]
    center = mean(observed) if observed else None
    mr_bar = mean(ranges) if ranges else None
    sigma = mr_bar / 1.128 if mr_bar is not None else None
    usable = sigma is not None and sigma > 0
    return {"center": center, "moving_ranges": ranges, "mr_bar": mr_bar, "sigma": sigma,
            "lcl": center - 3 * sigma if usable else None,
            "ucl": center + 3 * sigma if usable else None,
            "n": len(observed), "pairs": len(ranges), "constant": len(set(observed)) <= 1 if observed else False}


def detect_rules(points, limits):
    """Three strict rules evaluated at each arrival, never backdated.

    points contains scheduled positions with date, timestamp, bikes (or None).
    Only monitoring positions should be passed. Missing points reset all runs.
    Equality to center breaks same-side runs; tied values break trends. A longer
    run can trigger again when another complete sliding window arrives.
    """
    if limits.get("lcl") is None or limits.get("ucl") is None:
        return []
    events = []
    center = limits["center"]
    for index, point in enumerate(points):
        value = point.get("bikes")
        if value is None:
            continue
        def emit(rule, direction, window, detail):
            events.append({"rule": rule, "direction": direction, "date": point["date"],
                           "timestamp": point["timestamp"], "bikes": value,
                           "window_start": window[0]["date"], "window_end": point["date"],
                           "window_dates": [p["date"] for p in window], "description": detail})
        if value < limits["lcl"] or value > limits["ucl"]:
            direction = "low" if value < limits["lcl"] else "high"
            emit("beyond_limit", direction, [point], f"Point {direction} of the frozen {'LCL' if direction == 'low' else 'UCL'}.")
        if index >= 7:
            window = points[index - 7:index + 1]
            values = [p.get("bikes") for p in window]
            if all(x is not None and x > center for x in values):
                emit("eight_same_side", "high", window, "Eight consecutive readings strictly above the center line.")
            elif all(x is not None and x < center for x in values):
                emit("eight_same_side", "low", window, "Eight consecutive readings strictly below the center line.")
        if index >= 5:
            window = points[index - 5:index + 1]
            values = [p.get("bikes") for p in window]
            if all(x is not None for x in values):
                if all(a < b for a, b in zip(values, values[1:])):
                    emit("six_trend", "increasing", window, "Six consecutive readings strictly increasing.")
                elif all(a > b for a, b in zip(values, values[1:])):
                    emit("six_trend", "decreasing", window, "Six consecutive readings strictly decreasing.")
    return events


def _correlation(left, right):
    if len(left) < 2:
        return None
    avg_left, avg_right = mean(left), mean(right)
    numerator = sum((a - avg_left) * (b - avg_right) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - avg_left) ** 2 for a in left) * sum((b - avg_right) ** 2 for b in right))
    return numerator / denominator if denominator else None


def baseline_diagnostics(points, capacity, limits):
    values = [p["bikes"] for p in points if p["bikes"] is not None]
    pairs = [(a["bikes"], b["bikes"]) for a, b in zip(points, points[1:]) if a["bikes"] is not None and b["bikes"] is not None]
    corr = _correlation([p[0] for p in pairs], [p[1] for p in pairs])
    boundary_fraction = sum(x in (0, capacity) for x in values) / len(values) if values else None
    violations = detect_rules(points, limits)
    warnings = []
    if corr is not None and abs(corr) >= 0.5:
        warnings.append("Strong lag-one correlation is a review cue; independence is not established.")
    if boundary_fraction is not None and boundary_fraction >= 0.2:
        warnings.append("Frequent empty/full readings may undermine the approximate Individuals model.")
    if violations:
        warnings.append("Reference-period rule violations require investigation before approval.")
    return {"lag_one_correlation": corr, "boundary_fraction": boundary_fraction,
            "distribution": [{"bikes": key, "count": value} for key, value in sorted(Counter(values).items())],
            "baseline_events": violations, "warnings": warnings,
            "note": "Diagnostic cutoffs are review aids, not a statistical suitability test or proof of independence."}


def _stamp(day, hour, tz):
    return datetime.combine(datetime.fromisoformat(day).date(), time(hour), tzinfo=ZoneInfo(tz))


def _analyze(index, station, settings, as_of, hour, reviewed=False):
    dates, _, baseline_dates = _calendar(settings)
    sid, tz = station["station_id"], settings.get("timezone", "America/New_York")
    today = as_of.date().isoformat()
    elapsed = [day for day in baseline_dates if day < today]
    completed = len(elapsed) == len(baseline_dates)
    series = []
    for day in dates:
        stamp = _stamp(day, hour, tz)
        if stamp > as_of:
            continue
        row = index.get((stamp, sid))
        series.append({"date": day, "timestamp": stamp.isoformat(), "bikes": row["bikes"] if row else None,
                       "phase": "baseline" if day in baseline_dates else "monitoring"})
    baseline = [p for p in series if p["date"] in elapsed]
    raw_limits = i_chart_limits([p["bikes"] for p in baseline])
    diagnostics = baseline_diagnostics(baseline, station["capacity"], raw_limits)
    eligible = completed and raw_limits["n"] >= 20 and raw_limits["pairs"] >= 15 and raw_limits["lcl"] is not None
    approved = reviewed is True or reviewed == "approved"
    unsuitable = reviewed == "unsuitable"
    if not completed:
        status, reason = "accumulating", f"Collecting completed baseline days: {len(elapsed)} of {len(baseline_dates)}. Today's readings cannot train today's reference."
    elif raw_limits["n"] < 20 or raw_limits["pairs"] < 15:
        status, reason = "insufficient", "At least 20 valid dates and 15 adjacent scheduled-date pairs are required."
    elif raw_limits["lcl"] is None:
        status, reason = "constant", "Zero moving-range variation: statistical assessment unavailable."
    elif unsuitable:
        status, reason = "unsuitable", "This station/hour baseline was marked unsuitable; descriptive history only."
    elif approved:
        status, reason = "reviewed", "Station/hour baseline explicitly reviewed; signals are investigation cues, not proof of a cause."
    else:
        status, reason = "unreviewed", "Exploratory patterns only. Review stationarity, serial dependence, distribution and boundaries before enabling statistical signals."
    limits = raw_limits if eligible else None
    events = detect_rules([p for p in series if p["phase"] == "monitoring"], raw_limits) if eligible and not unsuitable else []
    kind = "statistical_signal" if status == "reviewed" else "exploratory_pattern"
    for event in events:
        event.update({"station_id": sid, "station_name": station["name"], "hour": hour, "kind": kind,
                      "baseline_start": baseline_dates[0], "baseline_end": baseline_dates[-1],
                      "center": raw_limits["center"], "lcl": raw_limits["lcl"], "ucl": raw_limits["ucl"]})
    event_rules = {}
    for event in events:
        event_rules.setdefault(event["date"], []).append(event["rule"])
    for point in series:
        point["rules"] = event_rules.get(point["date"], [])
    return {"station_id": sid, "station_name": station["name"], "capacity": station["capacity"],
            "hour": hour, "status": status, "reason": reason, "reviewed": status == "reviewed",
            "baseline": {"start": baseline_dates[0], "end": baseline_dates[-1], "planned_days": 25,
                         "completed_days": len(elapsed), "valid_days": raw_limits["n"],
                         "adjacent_pairs": raw_limits["pairs"], "frozen": completed,
                         "eligible": eligible, "sequence": baseline},
            "limits": limits, "diagnostics": diagnostics, "series": series, "events": events,
            "rules": {"beyond_limit": "Strictly outside LCL/UCL", "eight_same_side": "8 strictly on one side of CL", "six_trend": "6 strictly increasing or decreasing"}}


def station_hour_analysis(rows, stations, settings, as_of, station_id, hour, reviewed=False):
    """Public independent same-station/hour chart with fixed reference and gates."""
    config = _station_map(stations)
    if station_id not in config or hour not in settings["hours"]:
        raise DataValidationError("Choose a configured station and scheduled hour.")
    stamp = aware_time(as_of, settings.get("timezone", "America/New_York"))
    clean = validate_rows(rows, stations, settings)
    index = {(row["timestamp"], row["station_id"]): row for row in clean if row["timestamp"] <= stamp}
    return _analyze(index, config[station_id], settings, stamp, hour, reviewed)


def _operations(rows, stations, settings, as_of, station_id):
    latest = {}
    for row in rows:
        if row["timestamp"] <= as_of:
            latest[row["station_id"]] = row
    current, actions = [], []
    for station in stations:
        sid, capacity = station["station_id"], station["capacity"]
        target, low, high = capacity // 2, capacity * .2, capacity * .8
        row = latest.get(sid)
        age = (as_of - row["timestamp"]).total_seconds() / 60 if row else None
        fresh = row is not None and age < 60
        bikes = row["bikes"] if row else None
        status = "missing" if row is None else "stale" if not fresh else "empty" if bikes == 0 else "full" if bikes == capacity else "low" if bikes < low else "high" if bikes > high else "balanced"
        item = {**station, "bikes": bikes, "docks": capacity - bikes if bikes is not None else None,
                "occupancy": bikes / capacity if bikes is not None else None,
                "observed_at": row["timestamp"].isoformat() if row else None, "age_minutes": age,
                "fresh": fresh, "status": status, "target": target,
                "threshold_low": low, "threshold_high": high}
        current.append(item)
        if status in ("missing", "stale"):
            action = {**item, "priority": "Refresh", "priority_rank": 3, "direction": "refresh", "quantity": None,
                      "title": "Refresh data", "reason": "A current automatic reading is required before recommending a move."}
        elif status in ("empty", "full", "low", "high"):
            add = bikes < target
            quantity = abs(target - bikes)
            reason = {"empty": "No bikes available to borrow.", "full": "No free docks available for returns.",
                      "low": "Below the 20% inventory threshold.", "high": "Above the 80% inventory threshold."}[status]
            action = {**item, "priority": "P1" if status in ("empty", "full") else "P2", "priority_rank": 1 if status in ("empty", "full") else 2,
                      "direction": "add" if add else "remove", "quantity": quantity,
                      "title": f"{'Add' if add else 'Remove'} {quantity} bikes", "reason": f"{bikes} bikes available out of {capacity}. {reason} Consider {'adding' if add else 'removing'} {quantity} bikes to reach the provisional target of {target}."}
        else:
            continue
        actions.append(action)
    actions.sort(key=lambda a: (a["priority_rank"], -abs(a["bikes"] - a["target"]) if a["bikes"] is not None else 0, a["station_id"]))
    fresh = [s for s in current if s["fresh"]]
    metrics = snapshot_metrics([s["bikes"] for s in fresh], [s["capacity"] for s in fresh], len(stations))
    same_timestamp = len({s["observed_at"] for s in fresh}) == 1
    docked = sum(s["bikes"] for s in fresh)
    fleet = settings.get("fleet_size", 300)
    can_infer = len(fresh) == len(stations) == 20 and same_timestamp and 0 <= docked <= fleet
    metrics.update({"docked_bikes": docked if fresh else None, "in_transit": fleet - docked if can_infer else None,
                    "fleet_size": fleet, "in_transit_note": "Only inferred from complete simultaneous observations and the closed, fault-free 300-bike fleet assumption.",
                    "urgent_count": sum(a["priority"] == "P1" for a in actions),
                    "attention_count": sum(a["priority"] == "P2" for a in actions),
                    "refresh_count": sum(a["priority"] == "Refresh" for a in actions),
                    "action_count": sum(a["priority"] in ("P1", "P2") for a in actions)})
    day_series = []
    by_time = {row["timestamp"]: row for row in rows if row["station_id"] == station_id and row["timestamp"].date() == as_of.date() and row["timestamp"] <= as_of}
    previous_value, previous_stamp = None, None
    for hour in settings["hours"]:
        stamp = _stamp(as_of.date().isoformat(), hour, settings.get("timezone", "America/New_York"))
        if stamp > as_of:
            continue
        row = by_time.get(stamp)
        value = row["bikes"] if row else None
        change = value - previous_value if value is not None and previous_value is not None and previous_stamp is not None and (stamp - previous_stamp).total_seconds() == 3600 else None
        day_series.append({"timestamp": stamp.isoformat(), "hour": hour, "bikes": value, "net_change": change})
        previous_value, previous_stamp = value, stamp
    return {"stations": current, "actions": actions, "kpis": metrics, "day_series": day_series,
            "thresholds": {"low": 6, "target": 15, "high": 24, "kind": "operational_policy"},
            "ranking_note": "Empty/full first, then low/high; ties use distance from the provisional target and station ID. This is not an optimized dispatch route."}


def build_dashboard(rows, stations, settings, as_of, station_id, hour, reviewed=False):
    """Compose all user-visible numbers; no web imports, future scores or writes.

    reviewed=True applies only to selected station/hour. A dict can specify
    approved/unsuitable for individual stations at this hour; callers must scope
    reviews to the active dataset as well. No review is automatically inherited.
    """
    config = _station_map(stations)
    if station_id not in config or type(hour) is not int or hour not in settings["hours"]:
        raise DataValidationError("Choose a configured station and scheduled hour.")
    clock = aware_time(as_of, settings.get("timezone", "America/New_York"))
    clean = [row for row in validate_rows(rows, stations, settings) if row["timestamp"] <= clock]
    index = {(row["timestamp"], row["station_id"]): row for row in clean}
    analyses = {}
    for sid, station in config.items():
        review = reviewed.get(sid, False) if isinstance(reviewed, dict) else reviewed if sid == station_id else False
        analyses[sid] = _analyze(index, station, settings, clock, hour, review)
    inbox = [event for analysis in analyses.values() for event in analysis["events"]]
    inbox.sort(key=lambda event: (event["timestamp"], event["station_id"], event["rule"]), reverse=True)
    return {"as_of": clock.isoformat(), "timezone": settings.get("timezone", "America/New_York"),
            "synthetic": True, "station_id": station_id, "hour": hour,
            "operations": _operations(clean, stations, settings, clock, station_id), "analysis": analyses[station_id],
            "company": {"events": inbox, "counts": {"statistical_signals": sum(e["kind"] == "statistical_signal" for e in inbox),
                         "exploratory_patterns": sum(e["kind"] == "exploratory_pattern" for e in inbox),
                         "stations_with_events": len({e["station_id"] for e in inbox})},
                        "statuses": [{"station_id": sid, "status": a["status"], "reason": a["reason"]} for sid, a in analyses.items()]}}
