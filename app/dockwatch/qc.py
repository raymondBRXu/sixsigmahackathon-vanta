"""Framework-free inventory summaries and exploratory Individuals estimates.

The moving-range estimator follows the course process-control helpers, using
NIST's deterministic d2=1.128. Selected-interval limits describe the data; they
do not establish process stability or a calibrated false-alarm rate.
"""

from datetime import date

import numpy as np
import pandas as pd

from .data import planned_timestamps


REALTIME_WINDOW_SIZE = 8


def _as_of(value, timezone):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("as_of_time must include a timezone.")
    return stamp.tz_convert(timezone)


def snapshot_at(observations, stations, as_of_time):
    """Return every station, exact-current counts and separately labeled past readings.

    Suggested changes are single-station target differences, not transport plans.
    No previous observation is substituted for a missing current count.
    """
    timezone = observations["timestamp"].dt.tz
    now = _as_of(as_of_time, timezone)
    current = observations.loc[observations["timestamp"].eq(now), ["station_id", "bikes"]]
    latest = (observations.loc[observations["timestamp"].le(now)]
              .sort_values("timestamp").drop_duplicates("station_id", keep="last")
              [["station_id", "timestamp", "bikes"]]
              .rename(columns={"timestamp": "latest_timestamp", "bikes": "latest_bikes"}))
    snapshot = stations.merge(current, on="station_id", how="left").merge(latest, on="station_id", how="left")
    snapshot["bikes"] = pd.to_numeric(snapshot["bikes"], errors="coerce").astype(float)
    snapshot["as_of_time"] = now
    snapshot["age_minutes"] = (now - snapshot["latest_timestamp"]).dt.total_seconds() / 60
    snapshot["occupancy"] = snapshot["bikes"] / snapshot["capacity"]
    snapshot["free_docks"] = snapshot["capacity"] - snapshot["bikes"]
    snapshot["status"] = "normal"
    snapshot.loc[snapshot["occupancy"].lt(0.2), "status"] = "low"
    snapshot.loc[snapshot["occupancy"].gt(0.8), "status"] = "high"
    snapshot.loc[snapshot["bikes"].eq(0), "status"] = "empty"
    snapshot.loc[snapshot["bikes"].eq(snapshot["capacity"]), "status"] = "full"
    snapshot.loc[snapshot["bikes"].isna(), "status"] = "missing"
    snapshot.loc[snapshot["bikes"].isna() & snapshot["age_minutes"].ge(60), "status"] = "stale"
    snapshot["target_bikes"] = snapshot["capacity"] // 2
    snapshot["suggested_change"] = 0.0
    actionable = snapshot["status"].isin(["empty", "full", "low", "high"])
    snapshot.loc[actionable, "suggested_change"] = snapshot.loc[actionable, "target_bikes"] - snapshot.loc[actionable, "bikes"]
    snapshot.loc[snapshot["bikes"].isna(), "suggested_change"] = np.nan
    snapshot["action"] = snapshot["status"].map({
        "empty": "Add bikes", "low": "Add bikes", "full": "Remove bikes",
        "high": "Remove bikes", "normal": "No threshold action",
        "missing": "Reinspect", "stale": "Reinspect",
    })
    snapshot["priority"] = snapshot["status"].map({
        "empty": 1, "full": 1, "low": 2, "high": 2,
        "missing": 3, "stale": 3, "normal": 4,
    })
    return snapshot


def snapshot_metrics(snapshot):
    """Summarize valid current station observations, always reporting coverage."""
    valid = snapshot[snapshot["bikes"].notna()]
    n, planned = len(valid), len(snapshot)
    empty = int(valid["bikes"].eq(0).sum())
    full = int(valid["bikes"].eq(valid["capacity"]).sum())
    available = n - empty - full
    return {
        "n": n, "planned": planned, "coverage": n / planned if planned else None,
        "empty_count": empty, "full_count": full, "available_count": available,
        "empty_rate": empty / n if n else None, "full_rate": full / n if n else None,
        "availability": available / n if n else None,
        "mean_occupancy": float((valid["bikes"] / valid["capacity"]).mean()) if n else None,
    }


def hourly_changes(observations):
    """Add net_change only for adjacent one-hour readings within a service day."""
    result = observations.sort_values(["station_id", "timestamp"]).copy()
    groups = result.groupby("station_id")
    previous_time = groups["timestamp"].shift()
    adjacent = result["timestamp"].sub(previous_time).dt.total_seconds().eq(3600)
    same_day = result["timestamp"].dt.date.eq(previous_time.dt.date)
    result["net_change"] = groups["bikes"].diff().where(adjacent & same_day)
    return result.sort_values(["timestamp", "station_id"]).reset_index(drop=True)


def realtime_history(observations, settings, as_of_time):
    """Return every station's last eight elapsed scheduled slots in calendar order.

    The collection calendar determines the window, including missing readings
    and overnight transitions. Reindexing preserves missing counts without
    carrying earlier readings forward. No future slots or observations enter
    the result, and fewer than eight elapsed slots produce a shorter history.
    Input observations are already validated against the collection settings.
    """
    now = _as_of(as_of_time, settings["timezone"])
    stamps = planned_timestamps(settings)
    stamps = stamps[stamps <= now][-REALTIME_WINDOW_SIZE:]
    grid = pd.MultiIndex.from_product(
        [settings["station_ids"], stamps], names=["station_id", "timestamp"]
    )
    counts = observations.set_index(["station_id", "timestamp"])["bikes"]
    return counts.reindex(grid).rename("bikes").reset_index()


def _individual_data(values, timestamps=None):
    sequence = pd.Series(values, dtype=float).reset_index(drop=True)
    if np.isinf(sequence).any():
        raise ValueError("Individuals values must be finite or missing.")
    ranges = sequence.diff().abs()
    if timestamps is not None:
        stamps = pd.Series(pd.DatetimeIndex(timestamps)).reset_index(drop=True)
        if len(stamps) != len(sequence):
            raise ValueError("Values and timestamps must have the same length.")
        if stamps.isna().any() or stamps.duplicated().any() or not stamps.is_monotonic_increasing:
            raise ValueError("Timestamps must be valid, unique and chronological.")
        adjacent = stamps.diff().dt.total_seconds().eq(3600)
        same_day = stamps.dt.date.eq(stamps.shift().dt.date)
        ranges = ranges.where(adjacent & same_day)
    return sequence, ranges.dropna()


def individual_limits(values, timestamps=None):
    """Estimate CL and three-sigma Individuals limits from adjacent moving ranges.

    NaNs preserve gaps. When timestamps are supplied, only consecutive one-hour
    observations within a local service day contribute a moving range. The mean
    includes every valid observation, even those without an adjacent pair.
    """
    sequence, ranges = _individual_data(values, timestamps)
    if ranges.empty:
        raise ValueError("At least two adjacent valid observations are required.")
    mr_mean = float(ranges.mean())
    if mr_mean == 0:
        raise ValueError("Zero moving-range variation does not support control limits.")
    center = float(sequence.mean())
    sigma = mr_mean / 1.128
    return {"cl": center, "lcl": center - 3 * sigma, "ucl": center + 3 * sigma,
            "mr_mean": mr_mean, "sigma": sigma, "n": int(sequence.count()), "pairs": len(ranges)}


def station_history(observations, settings, station_id, start_time, end_time):
    """Return all scheduled hourly readings and I estimates in an inclusive range.

    The caller caps end_time at the playback timestamp. Data outside the selected
    interval never contribute to its mean or moving-range estimate.
    """
    if station_id not in settings["station_ids"]:
        raise ValueError("Select a configured station.")
    start = _as_of(start_time, settings["timezone"])
    end = _as_of(end_time, settings["timezone"])
    if start > end:
        raise ValueError("The interval start must not be after its end.")
    stamps = planned_timestamps(settings)
    stamps = stamps[(stamps >= start) & (stamps <= end)]
    counts = observations.loc[observations["station_id"].eq(station_id)].set_index("timestamp")["bikes"]
    history = pd.DataFrame({"timestamp": stamps, "bikes": counts.reindex(stamps).to_numpy(),
                            "station_id": station_id})
    values, ranges = _individual_data(history["bikes"], history["timestamp"])
    n = int(values.count())
    summary = {"limits": None, "cl": float(values.mean()) if n else None,
               "n": n, "planned": len(history), "pairs": len(ranges), "reason": ""}
    if not n:
        summary["reason"] = "No observed readings in the selected interval."
    elif ranges.empty:
        summary["reason"] = "UCL/LCL need two adjacent valid hourly readings within a service day."
    elif ranges.mean() == 0:
        summary["reason"] = "Zero moving-range variation: UCL/LCL cannot be estimated."
    else:
        summary["limits"] = individual_limits(values, history["timestamp"])
    return history, summary


def _service_date(value, name):
    """Parse a date without accepting an implicit time or timezone conversion."""
    try:
        parsed = date.fromisoformat(str(value))
        if parsed.isoformat() != str(value):
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD).") from error
    return parsed


def station_hour_history(observations, settings, station_id, start_date, end_date, hour, as_of_time):
    """Compare one station/hour across an inclusive scheduled service-date range.

    Reindex to every elapsed selected-hour slot before estimating moving ranges.
    Consecutive scheduled dates form pairs even across non-service days; missing
    scheduled readings break pairs. The clock cutoff excludes future slots from
    both observations and planned coverage. Limits use the same d2=1.128 estimator
    as ``individual_limits``, applied to this ordered same-hour sequence.
    """
    if station_id not in settings["station_ids"]:
        raise ValueError("Select a configured station.")
    if type(hour) is not int or hour not in settings["hours"]:
        raise ValueError("Select a scheduled operating hour.")
    start = _service_date(start_date, "start_date")
    end = _service_date(end_date, "end_date")
    now = _as_of(as_of_time, settings["timezone"])
    if start > end:
        raise ValueError("The start_date must not be after end_date.")
    if end > now.date():
        raise ValueError("The end_date must not be after the playback date.")
    stamps = planned_timestamps(settings)
    stamps = stamps[(stamps.date >= start) & (stamps.date <= end)
                    & (stamps.hour == hour) & (stamps <= now)]
    counts = observations.loc[observations["station_id"].eq(station_id)].set_index("timestamp")["bikes"]
    history = pd.DataFrame({"timestamp": stamps, "bikes": counts.reindex(stamps).to_numpy(),
                            "station_id": station_id})
    values, ranges = _individual_data(history["bikes"])
    n = int(values.count())
    summary = {"limits": None, "cl": float(values.mean()) if n else None,
               "n": n, "planned": len(history), "pairs": len(ranges), "reason": "", "hour": hour}
    if not len(history):
        summary["reason"] = "No elapsed scheduled readings at this hour in the selected date range."
    elif not n:
        summary["reason"] = "No observed readings at this hour in the selected date range."
    elif ranges.empty:
        summary["reason"] = "UCL/LCL need valid readings at this hour on two consecutive scheduled service dates."
    elif ranges.mean() == 0:
        summary["reason"] = "Zero moving-range variation: UCL/LCL cannot be estimated."
    else:
        summary["limits"] = individual_limits(values)
    return history, summary
