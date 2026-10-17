"""Load the three-column observations and the independent collection plan."""

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def _read_json(source):
    if isinstance(source, (str, Path)):
        return json.loads(Path(source).read_text())
    return source


def load_stations(source):
    """Return station metadata after checking identifiers, coordinates and capacity."""
    stations = pd.DataFrame(_read_json(source)).copy()
    required = {"station_id", "name", "area", "type", "latitude", "longitude", "capacity"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station configuration is missing columns: {', '.join(sorted(missing))}.")
    if stations.empty:
        raise ValueError("Station configuration must contain at least one station.")
    for column in ("station_id", "name", "area", "type"):
        if stations[column].isna().any() or stations[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Station {column} must not be empty.")
        stations[column] = stations[column].astype(str)
    if stations["station_id"].duplicated().any():
        raise ValueError("Station identifiers must be unique.")
    for column, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180)):
        stations[column] = pd.to_numeric(stations[column], errors="coerce")
        if not stations[column].between(lower, upper).all():
            raise ValueError(f"Station {column} is outside its coordinate range.")
    capacity = pd.to_numeric(stations["capacity"], errors="coerce")
    if not (np.isfinite(capacity) & capacity.gt(0) & capacity.mod(1).eq(0)).all():
        raise ValueError("Station capacity must be a positive integer.")
    stations["capacity"] = capacity.astype(int)
    return stations.reset_index(drop=True)


def load_settings(source, stations):
    """Validate the predeclared calendar; never infer it from uploaded rows."""
    settings = dict(_read_json(source))
    required = {"timezone", "service_dates", "hours", "station_ids"}
    missing = required - settings.keys()
    if missing:
        raise ValueError(f"Collection plan is missing fields: {', '.join(sorted(missing))}.")
    try:
        ZoneInfo(settings["timezone"])
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("Collection plan must name a valid timezone.") from error
    dates = settings["service_dates"]
    if not isinstance(dates, list) or not dates:
        raise ValueError("service_dates must be a nonempty ordered list.")
    try:
        valid_dates = all(pd.Timestamp(date).strftime("%Y-%m-%d") == date for date in dates)
    except (ValueError, TypeError):
        valid_dates = False
    if not valid_dates or dates != sorted(set(dates)):
        raise ValueError("service_dates must contain unique ordered ISO dates.")
    hours = settings["hours"]
    if not isinstance(hours, list) or not hours or any(type(hour) is not int or not 0 <= hour <= 23 for hour in hours):
        raise ValueError("Planned hours must be integers from 0 through 23.")
    if hours != sorted(set(hours)):
        raise ValueError("Planned hours must be unique and ordered.")
    identifiers = settings["station_ids"]
    if not isinstance(identifiers, list) or len(identifiers) != len(set(identifiers)):
        raise ValueError("Planned station identifiers must be a unique list.")
    if set(identifiers) != set(stations["station_id"]):
        raise ValueError("Planned station identifiers must match the station configuration.")
    return settings


def planned_timestamps(settings):
    """Return the scheduled local instants in chronological order."""
    return pd.DatetimeIndex([
        pd.Timestamp(f"{date} {hour:02}:00", tz=settings["timezone"])
        for date in settings["service_dates"] for hour in settings["hours"]
    ])


def load_observations(source, stations, settings, check_fleet=False):
    """Validate all CSV rows or raise one readable error with CSV row numbers.

    Missing rows remain absent. Explicit blank counts are invalid measurements.
    The optional fleet check applies only to complete synthetic snapshots.
    """
    if isinstance(source, pd.DataFrame):
        observations = source.copy().reset_index(drop=True)
    else:
        observations = pd.read_csv(source, dtype={"station_id": "string"})
    required = {"timestamp", "station_id", "bikes"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"Observation CSV is missing columns: {', '.join(sorted(missing))}.")
    observations = observations[["timestamp", "station_id", "bikes"]].copy()
    errors = []

    def report(mask, message):
        for index in observations.index[mask]:
            errors.append(f"Row {index + 2}: {message}")

    parsed = []
    for index, value in observations["timestamp"].items():
        try:
            stamp = pd.Timestamp(value)
            if pd.isna(stamp) or stamp.tzinfo is None:
                raise ValueError("Missing timezone")
            parsed.append(stamp.tz_convert(settings["timezone"]))
        except (ValueError, TypeError, OverflowError):
            errors.append(f"Row {index + 2}: timestamp must be valid and include a timezone.")
            parsed.append(pd.NaT)
    observations["timestamp"] = pd.Series(
        parsed, dtype=pd.DatetimeTZDtype(tz=settings["timezone"], unit="ns")
    )
    observations["station_id"] = observations["station_id"].astype("string")
    report(~observations["station_id"].isin(stations["station_id"]), "unknown station_id.")
    counts = pd.to_numeric(observations["bikes"], errors="coerce")
    integer_counts = np.isfinite(counts) & counts.mod(1).eq(0)
    report(~integer_counts, "bikes must be a finite integer.")
    capacities = observations["station_id"].map(stations.set_index("station_id")["capacity"])
    report(integer_counts & (counts.lt(0) | counts.gt(capacities)), "bikes is outside station capacity.")
    valid_timestamps = observations["timestamp"].notna()
    report(valid_timestamps & ~observations["timestamp"].isin(planned_timestamps(settings)),
           "timestamp is not a planned hourly observation.")
    report(observations.duplicated(["timestamp", "station_id"], keep=False), "duplicate station/timestamp.")
    if errors:
        suffix = f"\n... {len(errors) - 20} more validation errors." if len(errors) > 20 else ""
        raise ValueError("\n".join(errors[:20]) + suffix)
    observations["bikes"] = counts.astype(int)
    observations["station_id"] = observations["station_id"].astype(str)
    observations = observations.sort_values(["timestamp", "station_id"]).reset_index(drop=True)
    observations["service_date"] = observations["timestamp"].dt.strftime("%Y-%m-%d")
    observations["hour"] = observations["timestamp"].dt.hour
    if check_fleet:
        totals = observations.groupby("timestamp")["bikes"].agg(["count", "sum"])
        incorrect = totals[totals["count"].eq(len(stations)) & totals["sum"].ne(300)]
        if not incorrect.empty:
            raise ValueError(f"Complete synthetic snapshot must total 300 bikes: {incorrect.index[0]}.")
    return observations


def load_bundle(data_dir, source=None, check_fleet=False):
    """Load observations (normal.csv by default), stations and the collection plan."""
    directory = Path(data_dir)
    stations = load_stations(directory / "stations.json")
    settings = load_settings(directory / "settings.json", stations)
    observations = load_observations(
        directory / "normal.csv" if source is None else source,
        stations, settings, check_fleet=check_fleet,
    )
    return observations, stations, settings
