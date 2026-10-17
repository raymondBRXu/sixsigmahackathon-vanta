"""Known-answer, degeneracy and chronology tests for the plain statistical core."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dockwatch.data import load_bundle, load_observations, load_settings, load_stations
from dockwatch.qc import hourly_changes, individual_limits, snapshot_at, snapshot_metrics, station_history


def make_stations(n=1):
    return load_stations([
        {"station_id": f"S{i:02}", "name": f"Station {i}", "area": "Campus", "type": "academic",
         "capacity": 30, "latitude": 42.44, "longitude": -76.48} for i in range(1, n + 1)
    ])


def observations_for(rows):
    observations = pd.DataFrame(rows, columns=["timestamp", "station_id", "bikes"])
    observations["timestamp"] = pd.to_datetime(observations["timestamp"], utc=True).dt.tz_convert("America/New_York")
    return observations


def test_snapshot_known_answer_is_cross_sectional():
    now = "2026-09-28T08:00:00-04:00"
    stations = make_stations(5)
    observations = observations_for([(now, station, count) for station, count in zip(stations["station_id"], [0, 0, 9, 15, 30])])
    snapshot = snapshot_at(observations, stations, now)
    result = snapshot_metrics(snapshot)
    assert result["empty_rate"] == pytest.approx(0.4)
    assert result["full_rate"] == pytest.approx(0.2)
    assert result["availability"] == pytest.approx(0.4)
    assert result["mean_occupancy"] == pytest.approx(0.36)
    assert (result["n"], result["planned"], result["coverage"]) == (5, 5, 1)


def test_hourly_change_fixture_is_a_separate_same_station_series():
    observations = observations_for([(f"2026-09-28T{hour:02}:00:00-04:00", "S01", count)
                                     for hour, count in zip(range(7, 12), [0, 0, 9, 15, 30])])
    result = hourly_changes(observations)
    assert pd.isna(result["net_change"].iloc[0])
    assert result["net_change"].iloc[1:].tolist() == [0, 9, 6, 15]


def test_hourly_changes_do_not_cross_stations_gaps_or_calendar_days():
    observations = observations_for([
        ("2026-09-28T07:00:00-04:00", "S01", 10),
        ("2026-09-28T09:00:00-04:00", "S01", 15),
        ("2026-09-28T23:00:00-04:00", "S01", 17),
        ("2026-09-29T00:00:00-04:00", "S01", 18),
        ("2026-09-28T08:00:00-04:00", "S02", 20),
    ])
    assert hourly_changes(observations)["net_change"].isna().all()


def test_missing_current_counts_never_use_past_or_future_values():
    observations = observations_for([
        ("2026-09-28T07:00:00-04:00", "S01", 0),
        ("2026-09-28T09:00:00-04:00", "S01", 30),
        ("2026-09-28T08:00:00-04:00", "S02", 15),
    ])
    snapshot = snapshot_at(observations, make_stations(3), "2026-09-28T08:00:00-04:00")
    old = snapshot.set_index("station_id").loc["S01"]
    assert pd.isna(old["bikes"])
    assert old["latest_bikes"] == 0
    assert old["age_minutes"] == 60
    assert old["status"] == "stale"
    assert old["action"] == "Reinspect"
    assert pd.isna(old["suggested_change"])
    assert snapshot.set_index("station_id").loc["S03", "status"] == "missing"
    metrics = snapshot_metrics(snapshot)
    assert metrics["n"] == 1
    assert metrics["coverage"] == pytest.approx(1 / 3)
    assert metrics["empty_count"] == 0
    assert metrics["availability"] == 1


def test_empty_snapshot_has_no_data_proportions():
    observations = observations_for([])
    snapshot = snapshot_at(observations, make_stations(2), "2026-09-28T08:00:00-04:00")
    metrics = snapshot_metrics(snapshot)
    assert metrics["n"] == 0 and metrics["coverage"] == 0
    assert metrics["empty_rate"] is None
    assert metrics["availability"] is None
    assert snapshot["status"].eq("missing").all()


def test_operational_boundaries_and_target_differences():
    now = "2026-09-28T08:00:00-04:00"
    stations = make_stations(10)
    counts = [0, 3, 5, 6, 15, 24, 25, 27, 30, 9]
    observations = observations_for([(now, station, count) for station, count in zip(stations["station_id"], counts)])
    result = snapshot_at(observations, stations, now)
    assert result["status"].tolist() == ["empty", "low", "low", "normal", "normal", "normal", "high", "high", "full", "normal"]
    assert result["suggested_change"].tolist() == [15, 12, 10, 0, 0, 0, -10, -12, -15, 0]
    assert result["priority"].tolist() == [1, 2, 2, 4, 4, 4, 2, 2, 1, 4]


def test_individual_limits_known_answer_and_determinism():
    result = individual_limits([10, 12, 11, 13, 14])
    assert result["cl"] == 12
    assert result["mr_mean"] == 1.5
    assert result["sigma"] == pytest.approx(1.329787234)
    assert result["lcl"] == pytest.approx(8.010638298)
    assert result["ucl"] == pytest.approx(15.989361702)
    assert result == individual_limits([10, 12, 11, 13, 14])
    assert 7 < result["lcl"] and 17 > result["ucl"]


@pytest.mark.parametrize("values", [[], [10], [None], [10, 10, 10], [10, None, 12], [10, float("inf")]])
def test_degenerate_formula_inputs_are_unsupported(values):
    with pytest.raises(ValueError):
        individual_limits(values)


def test_formula_preserves_missing_pairs_and_physical_limits_are_not_clipped():
    result = individual_limits([0, 30, None, 5, 6])
    assert result["pairs"] == 2
    assert result["mr_mean"] == 15.5
    assert result["lcl"] < 0 and result["ucl"] > 30


@pytest.fixture
def interval_data():
    stations = make_stations(2)
    settings = load_settings({"timezone": "America/New_York", "station_ids": ["S01", "S02"],
                              "hours": list(range(7, 12)),
                              "service_dates": ["2026-09-28", "2026-09-29"]}, stations)
    counts = [[10, 12, 11, 13, 14], [25, 22, 24, 20, 21]]
    rows = [(f"{date}T{hour:02}:00:00-04:00", "S01", count)
            for date, day_counts in zip(settings["service_dates"], counts)
            for hour, count in zip(settings["hours"], day_counts)]
    rows += [(f"{date}T{hour:02}:00:00-04:00", "S02", 0)
             for date in settings["service_dates"] for hour in settings["hours"]]
    return load_observations(observations_for(rows), stations, settings), settings


def test_selected_interval_known_answer_includes_all_hours(interval_data):
    observations, settings = interval_data
    start, end = "2026-09-28T07:00:00-04:00", "2026-09-28T11:00:00-04:00"
    history, summary = station_history(observations, settings, "S01", start, end)
    assert history["bikes"].tolist() == [10, 12, 11, 13, 14]
    assert history["timestamp"].min() == pd.Timestamp(start)
    assert history["timestamp"].max() == pd.Timestamp(end)
    assert set(history.columns) == {"timestamp", "bikes", "station_id"}
    assert (summary["n"], summary["planned"], summary["pairs"]) == (5, 5, 4)
    assert summary["cl"] == 12
    assert summary["limits"] == individual_limits([10, 12, 11, 13, 14])
    assert summary["reason"] == ""


def test_selected_window_ignores_outside_data_and_other_stations(interval_data):
    observations, settings = interval_data
    start, end = "2026-09-28T08:00:00-04:00", "2026-09-28T10:00:00-04:00"
    history, summary = station_history(observations, settings, "S01", start, end)
    altered = observations.copy()
    outside = ~altered["timestamp"].between(pd.Timestamp(start), pd.Timestamp(end))
    altered.loc[outside | altered["station_id"].ne("S01"), "bikes"] = 30
    changed_history, changed_summary = station_history(altered, settings, "S01", start, end)
    pd.testing.assert_frame_equal(history, changed_history)
    assert summary == changed_summary
    assert summary["limits"] == individual_limits([12, 11, 13])
    _, wider = station_history(observations, settings, "S01", start, "2026-09-29T11:00:00-04:00")
    assert wider["cl"] != summary["cl"]
    assert wider["limits"] != summary["limits"]


def test_selected_history_reindexes_missing_hours_and_excludes_overnight_pairs(interval_data):
    observations, settings = interval_data
    missing = pd.Timestamp("2026-09-28T09:00:00-04:00")
    reduced = observations.loc[~observations["timestamp"].eq(missing)]
    history, summary = station_history(reduced, settings, "S01",
                                       "2026-09-28T07:00:00-04:00", "2026-09-29T11:00:00-04:00")
    assert len(history) == 10 and pd.isna(history.loc[2, "bikes"])
    assert summary["n"] == 9 and summary["pairs"] == 6
    assert summary["cl"] == pytest.approx(161 / 9)
    assert summary["limits"]["mr_mean"] == pytest.approx(13 / 6)


def test_timestamped_formula_excludes_clock_gaps_and_midnight_pairs():
    times = pd.to_datetime(["2026-09-28 07:00", "2026-09-28 08:00", "2026-09-28 10:00",
                            "2026-09-28 23:00", "2026-09-29 00:00", "2026-09-29 01:00"]).tz_localize("America/New_York")
    result = individual_limits([10, 12, 30, 0, 30, 26], times)
    assert result["pairs"] == 2
    assert result["mr_mean"] == 3
    assert result["cl"] == 18


@pytest.mark.parametrize("values,expected_mean,expected_pairs", [
    ([15, 15, 15, 15, 15], 15, 4),
    ([10, None, None, None, None], 10, 0),
    ([10, None, 20, None, 30], 20, 0),
    ([None, None, None, None, None], None, 0),
])
def test_degenerate_interval_keeps_observations_and_mean(interval_data, values, expected_mean, expected_pairs):
    observations, settings = interval_data
    selected = observations.loc[observations["station_id"].eq("S01")].iloc[:5].copy()
    selected["bikes"] = values
    selected = selected.dropna(subset=["bikes"])
    history, summary = station_history(selected, settings, "S01",
                                       "2026-09-28T07:00:00-04:00", "2026-09-28T11:00:00-04:00")
    assert len(history) == 5
    assert summary["limits"] is None and summary["reason"]
    assert summary["cl"] == expected_mean
    assert summary["pairs"] == expected_pairs
    assert summary["n"] == sum(value is not None for value in values)


def test_single_slot_and_empty_scheduled_interval(interval_data):
    observations, settings = interval_data
    instant = "2026-09-28T09:00:00-04:00"
    history, summary = station_history(observations, settings, "S01", instant, instant)
    assert len(history) == 1 and summary["cl"] == 11
    assert summary["limits"] is None and summary["pairs"] == 0
    history, summary = station_history(observations, settings, "S01",
                                       "2026-09-28T22:00:00-04:00", "2026-09-29T06:00:00-04:00")
    assert history.empty and summary["n"] == summary["planned"] == 0
    assert summary["limits"] is None and summary["cl"] is None


def test_zero_within_day_ranges_do_not_use_between_day_jumps(interval_data):
    observations, settings = interval_data
    altered = observations.copy()
    altered["bikes"] = np.where(altered["timestamp"].dt.day.eq(28), 10, 20)
    _, summary = station_history(altered, settings, "S01",
                                  "2026-09-28T07:00:00-04:00", "2026-09-29T11:00:00-04:00")
    assert summary["cl"] == 15 and summary["pairs"] == 8
    assert summary["limits"] is None
    assert "Zero moving-range" in summary["reason"]


def test_interval_and_timestamp_input_validation(interval_data):
    observations, settings = interval_data
    start, end = "2026-09-28T07:00:00-04:00", "2026-09-28T11:00:00-04:00"
    with pytest.raises(ValueError, match="start"):
        station_history(observations, settings, "S01", end, start)
    with pytest.raises(ValueError, match="configured station"):
        station_history(observations, settings, "unknown", start, end)
    with pytest.raises(ValueError, match="timezone"):
        station_history(observations, settings, "S01", "2026-09-28 07:00", end)
    with pytest.raises(ValueError, match="same length"):
        individual_limits([10, 12], [pd.Timestamp(start)])
    with pytest.raises(ValueError, match="chronological"):
        individual_limits([10, 12], [pd.Timestamp(end), pd.Timestamp(start)])


def test_real_edge_cases_show_same_occupancy_and_different_availability():
    directory = Path(__file__).resolve().parents[1] / "data"
    observations, stations, settings = load_bundle(directory, directory / "edge_cases.csv")
    balanced = snapshot_metrics(snapshot_at(observations, stations, "2026-09-28T09:00:00-04:00"))
    polarized = snapshot_metrics(snapshot_at(observations, stations, "2026-09-28T10:00:00-04:00"))
    assert balanced["mean_occupancy"] == polarized["mean_occupancy"] == 0.5
    assert balanced["availability"] == 1 and polarized["availability"] == 0
