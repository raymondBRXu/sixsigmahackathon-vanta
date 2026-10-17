"""Input contracts and real synthetic-data loading."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from dockwatch.data import load_bundle, load_observations, load_settings, load_stations, planned_timestamps


@pytest.fixture
def config():
    stations = load_stations([
        {"station_id": "A", "name": "Station A", "area": "Campus", "type": "academic",
         "latitude": 42.44, "longitude": -76.48, "capacity": 30},
        {"station_id": "B", "name": "Station B", "area": "Town", "type": "residential",
         "latitude": 42.45, "longitude": -76.49, "capacity": 30},
    ])
    settings = load_settings({
        "timezone": "America/New_York", "station_ids": ["A", "B"], "hours": [7, 8, 9],
        "service_dates": ["2026-09-25", "2026-09-28"],
    }, stations)
    return stations, settings


def test_load_upload_sorts_and_preserves_missing_observations(config):
    stations, settings = config
    source = BytesIO(b"timestamp,station_id,bikes\n2026-09-25T08:00:00-04:00,B,14\n2026-09-25T11:00:00Z,A,15\n")
    observations = load_observations(source, stations, settings)
    assert observations["station_id"].tolist() == ["A", "B"]
    assert observations["hour"].tolist() == [7, 8]
    assert str(observations["timestamp"].dt.tz) == "America/New_York"
    assert len(observations) == 2
    assert len(planned_timestamps(settings)) == 6


@pytest.mark.parametrize("column,value,expected", [
    ("timestamp", "2026-09-25T07:00:00", "include a timezone"),
    ("timestamp", "not-a-date", "valid and include"),
    ("timestamp", "2026-09-25T07:30:00-04:00", "not a planned"),
    ("timestamp", "2026-09-26T07:00:00-04:00", "not a planned"),
    ("station_id", "unknown", "unknown station"),
    ("bikes", 31, "outside station capacity"),
    ("bikes", -1, "outside station capacity"),
    ("bikes", 2.5, "finite integer"),
    ("bikes", None, "finite integer"),
    ("bikes", float("inf"), "finite integer"),
])
def test_reject_invalid_rows_with_line_numbers(config, column, value, expected):
    stations, settings = config
    row = {"timestamp": "2026-09-25T07:00:00-04:00", "station_id": "A", "bikes": 15}
    row[column] = value
    with pytest.raises(ValueError, match=f"Row 2:.*{expected}"):
        load_observations(pd.DataFrame([row]), stations, settings)


def test_duplicate_key_is_rejected_even_with_different_timezone_text(config):
    stations, settings = config
    rows = pd.DataFrame({"timestamp": ["2026-09-25T07:00:00-04:00", "2026-09-25T11:00:00Z"],
                         "station_id": ["A", "A"], "bikes": [15, 16]})
    with pytest.raises(ValueError, match="duplicate station/timestamp"):
        load_observations(rows, stations, settings)


def test_empty_file_with_headers_is_valid_and_has_typed_time(config):
    stations, settings = config
    result = load_observations(BytesIO(b"timestamp,station_id,bikes\n"), stations, settings)
    assert result.empty
    assert str(result["timestamp"].dt.tz) == "America/New_York"
    with pytest.raises(ValueError, match="missing columns: bikes"):
        load_observations(pd.DataFrame(columns=["timestamp", "station_id"]), stations, settings)


def test_station_schema_validation(config):
    stations, _ = config
    for capacity in (0, -1, 2.5, float("nan")):
        invalid = stations.copy()
        invalid["capacity"] = capacity
        with pytest.raises(ValueError, match="positive integer"):
            load_stations(invalid)
    with pytest.raises(ValueError, match="unique"):
        load_stations(pd.concat([stations, stations.iloc[:1]]))
    with pytest.raises(ValueError, match="coordinate"):
        load_stations(stations.assign(latitude=91))


def test_collection_plan_is_independent_and_consistent(config):
    stations, settings = config
    with pytest.raises(ValueError, match="unique ordered ISO"):
        load_settings({**settings, "service_dates": list(reversed(settings["service_dates"]))}, stations)
    with pytest.raises(ValueError, match="match the station"):
        load_settings({**settings, "station_ids": ["A"]}, stations)
    with pytest.raises(ValueError, match="unique and ordered"):
        load_settings({**settings, "hours": [8, 7]}, stations)
    with pytest.raises(ValueError, match="timezone"):
        load_settings({**settings, "timezone": "Not/A_Zone"}, stations)


def test_fleet_check_only_uses_complete_snapshots(config):
    stations, settings = config
    rows = pd.DataFrame({"timestamp": ["2026-09-25T07:00:00-04:00"] * 2,
                         "station_id": ["A", "B"], "bikes": [15, 15]})
    with pytest.raises(ValueError, match="300 bikes"):
        load_observations(rows, stations, settings, check_fleet=True)
    assert len(load_observations(rows.iloc[:1], stations, settings, check_fleet=True)) == 1


@pytest.mark.parametrize("filename", ["normal.csv", "disruption.csv", "edge_cases.csv"])
def test_supplied_scenarios_validate(filename):
    directory = Path(__file__).resolve().parents[1] / "data"
    observations, stations, settings = load_bundle(directory, directory / filename, check_fleet=True)
    assert len(observations) == 12000
    assert len(stations) == 20
    assert len(planned_timestamps(settings)) == 600
    assert observations.groupby("timestamp")["bikes"].sum().eq(300).all()


def test_collection_plan_requires_only_service_calendar_and_preserves_generator_metadata(config):
    stations, settings = config
    assert "baseline_dates" not in settings and "monitoring_dates" not in settings
    extra = {"baseline_dates": ["2026-09-25"], "monitoring_dates": ["2026-09-28"], "seed": 42}
    assert load_settings({**settings, **extra}, stations) == {**settings, **extra}
