"""Known-answer, degeneracy and chronology tests for the plain statistical core."""

import numpy as np
import pandas as pd
import pytest

from dockwatch.data import load_observations, load_settings, load_stations, planned_timestamps
from dockwatch.qc import (
    hourly_changes, individual_limits, realtime_history, snapshot_at, snapshot_metrics,
    station_history, station_hour_history,
)


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


@pytest.mark.parametrize("cursor,expected_counts", [
    (0, [10]),
    (7, [10, 12, 11, 13, 14, 25, 22, 24]),
    (8, [12, 11, 13, 14, 25, 22, 24, 20]),
])
def test_realtime_window_known_answers_and_overnight_schedule(interval_data, cursor, expected_counts):
    observations, settings = interval_data
    plan = planned_timestamps(settings)
    history = realtime_history(observations, settings, plan[cursor])
    first = history.loc[history["station_id"].eq("S01")]
    second = history.loc[history["station_id"].eq("S02")]
    assert first["bikes"].tolist() == expected_counts
    assert second["bikes"].tolist() == [0] * len(expected_counts)
    assert first["timestamp"].tolist() == list(plan[max(0, cursor - 7):cursor + 1])
    assert second["timestamp"].tolist() == first["timestamp"].tolist()
    assert len(history) == len(expected_counts) * 2


def test_realtime_window_retains_missing_slots_and_stations(interval_data):
    observations, settings = interval_data
    plan = planned_timestamps(settings)
    reduced = observations.loc[observations["station_id"].eq("S01")
                               & observations["timestamp"].ne(plan[2])]
    history = realtime_history(reduced, settings, plan[7])
    first = history.loc[history["station_id"].eq("S01")].reset_index(drop=True)
    assert len(first) == 8 and pd.isna(first.loc[2, "bikes"])
    assert first.loc[1, "bikes"] == 12 and first.loc[3, "bikes"] == 13
    assert first.loc[2, "timestamp"] == plan[2]
    assert history.loc[history["station_id"].eq("S02"), "bikes"].isna().all()
    empty = realtime_history(observations.iloc[:0], settings, plan[7])
    assert len(empty) == 16 and empty["bikes"].isna().all()


def test_realtime_cutoff_rewind_and_source_isolation(interval_data):
    observations, settings = interval_data
    plan = planned_timestamps(settings)
    original = observations.copy(deep=True)
    first = realtime_history(observations, settings, plan[7])
    changed = observations.copy()
    changed.loc[changed["timestamp"].gt(plan[7]), "bikes"] = 30
    pd.testing.assert_frame_equal(first, realtime_history(changed, settings, plan[7]))
    realtime_history(observations, settings, plan[-1])
    pd.testing.assert_frame_equal(first, realtime_history(observations, settings, plan[7]))
    pd.testing.assert_frame_equal(first, realtime_history(observations, settings, "2026-09-29T09:30:00-04:00"))
    other_source = observations.copy()
    other_source["bikes"] = 15
    assert realtime_history(other_source, settings, plan[7])["bikes"].eq(15).all()
    pd.testing.assert_frame_equal(observations, original)
    pd.testing.assert_frame_equal(first, realtime_history(observations, settings, plan[7]))


def test_realtime_empty_elapsed_calendar_and_timezone_validation(interval_data):
    observations, settings = interval_data
    history = realtime_history(observations, settings, "2026-09-28T06:00:00-04:00")
    assert history.empty
    assert history.columns.tolist() == ["station_id", "timestamp", "bikes"]
    with pytest.raises(ValueError, match="timezone"):
        realtime_history(observations, settings, "2026-09-28 09:00")


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


def test_balanced_and_polarized_fixture_has_same_occupancy_but_different_availability():
    stations = make_stations(20)
    observations = observations_for([
        (f"2026-09-28T{hour:02}:00:00-04:00", station_id, bikes)
        for hour, counts in ((9, [15] * 20), (10, [0] * 10 + [30] * 10))
        for station_id, bikes in zip(stations["station_id"], counts)
    ])
    balanced = snapshot_metrics(snapshot_at(observations, stations, "2026-09-28T09:00:00-04:00"))
    polarized = snapshot_metrics(snapshot_at(observations, stations, "2026-09-28T10:00:00-04:00"))
    assert balanced["mean_occupancy"] == polarized["mean_occupancy"] == 0.5
    assert balanced["availability"] == 1 and polarized["availability"] == 0


@pytest.fixture
def same_hour_data():
    stations = make_stations(2)
    settings = load_settings({"timezone": "America/New_York", "station_ids": ["S01", "S02"],
                              "hours": [7, 8, 9],
                              "service_dates": ["2026-09-24", "2026-09-25", "2026-09-28",
                                                "2026-09-29", "2026-09-30"]}, stations)
    rows = [(f"{day}T08:00:00-04:00", "S01", count)
            for day, count in zip(settings["service_dates"], [10, 12, 11, 13, 14])]
    rows += [(f"{day}T{hour:02}:00:00-04:00", station, 30)
             for day in settings["service_dates"] for hour in settings["hours"]
             for station in settings["station_ids"] if (station, hour) != ("S01", 8)]
    return load_observations(observations_for(rows), stations, settings), settings


def test_same_hour_known_answer_includes_consecutive_service_dates_across_weekend(same_hour_data):
    observations, settings = same_hour_data
    history, summary = station_hour_history(observations, settings, "S01", "2026-09-24",
                                            "2026-09-30", 8, "2026-09-30T09:00:00-04:00")
    assert history["bikes"].tolist() == [10, 12, 11, 13, 14]
    assert history["timestamp"].dt.strftime("%Y-%m-%d").tolist() == settings["service_dates"]
    assert history["timestamp"].dt.hour.eq(8).all()
    assert (summary["n"], summary["planned"], summary["pairs"], summary["hour"]) == (5, 5, 4, 8)
    assert summary["cl"] == 12
    assert summary["limits"] == pytest.approx({
        "cl": 12, "lcl": 8.01063829787234, "ucl": 15.98936170212766,
        "mr_mean": 1.5, "sigma": 1.3297872340425534, "n": 5, "pairs": 4,
    })


def test_same_hour_isolates_station_hour_dates_and_future_slots(same_hour_data):
    observations, settings = same_hour_data
    args = (settings, "S01", "2026-09-25", "2026-09-30", 8, "2026-09-30T07:00:00-04:00")
    history, summary = station_hour_history(observations, *args)
    assert history["bikes"].tolist() == [12, 11, 13]
    assert (summary["planned"], summary["pairs"]) == (3, 2)
    altered = observations.copy()
    outside = ~altered["timestamp"].isin(history["timestamp"]) | altered["station_id"].ne("S01")
    altered.loc[outside, "bikes"] = 0
    changed_history, changed_summary = station_hour_history(altered, *args)
    pd.testing.assert_frame_equal(history, changed_history)
    assert summary == changed_summary
    elapsed, _ = station_hour_history(observations, settings, "S01", "2026-09-25", "2026-09-30",
                                       8, "2026-09-30T08:00:00-04:00")
    assert elapsed["bikes"].tolist() == [12, 11, 13, 14]


def test_missing_same_hour_service_date_breaks_pairs(same_hour_data):
    observations, settings = same_hour_data
    observations = observations.loc[~observations["timestamp"].eq(pd.Timestamp("2026-09-28T08:00:00-04:00"))]
    history, summary = station_hour_history(observations, settings, "S01", "2026-09-24", "2026-09-30",
                                            8, "2026-09-30T09:00:00-04:00")
    assert pd.isna(history.loc[2, "bikes"])
    assert (summary["n"], summary["planned"], summary["pairs"]) == (4, 5, 2)
    assert summary["cl"] == 12.25
    assert summary["limits"]["mr_mean"] == 1.5


@pytest.mark.parametrize("values,expected_mean,expected_pairs,reason", [
    ([15, 15, 15, 15, 15], 15, 4, "Zero moving-range"),
    ([10, None, None, None, None], 10, 0, "consecutive scheduled service dates"),
    ([10, None, 20, None, 30], 20, 0, "consecutive scheduled service dates"),
    ([None, None, None, None, None], None, 0, "No observed readings"),
])
def test_degenerate_same_hour_keeps_mean_and_missingness(same_hour_data, values, expected_mean, expected_pairs, reason):
    observations, settings = same_hour_data
    observations = observations.loc[observations["station_id"].eq("S01") & observations["timestamp"].dt.hour.eq(8)].copy()
    observations["bikes"] = values
    history, summary = station_hour_history(observations.dropna(subset=["bikes"]), settings, "S01",
                                            "2026-09-24", "2026-09-30", 8, "2026-09-30T09:00:00-04:00")
    assert len(history) == 5 and summary["cl"] == expected_mean
    assert summary["limits"] is None and summary["pairs"] == expected_pairs
    assert reason in summary["reason"]


@pytest.mark.parametrize("day,cutoff,expected_count", [
    ("2026-09-24", "2026-09-24T07:00:00-04:00", 0),
    ("2026-09-24", "2026-09-24T08:00:00-04:00", 1),
    ("2026-09-26", "2026-09-30T09:00:00-04:00", 0),
])
def test_same_hour_single_date_and_empty_elapsed_calendar(same_hour_data, day, cutoff, expected_count):
    observations, settings = same_hour_data
    history, summary = station_hour_history(observations, settings, "S01", day, day, 8, cutoff)
    assert len(history) == summary["planned"] == summary["n"] == expected_count
    assert summary["limits"] is None and summary["pairs"] == 0 and summary["reason"]


@pytest.mark.parametrize("overrides,message", [
    ({"station_id": "S99"}, "configured station"),
    ({"hour": 6}, "operating hour"),
    ({"hour": 8.5}, "operating hour"),
    ({"start_date": "2026-09-31"}, "ISO date"),
    ({"start_date": "2026-09-24T08:00:00"}, "ISO date"),
    ({"start_date": "2026-09-30", "end_date": "2026-09-24"}, "start_date"),
    ({"end_date": "2026-10-01"}, "playback date"),
    ({"as_of_time": "2026-09-30 09:00"}, "timezone"),
])
def test_same_hour_validates_inputs(same_hour_data, overrides, message):
    observations, settings = same_hour_data
    params = {"station_id": "S01", "start_date": "2026-09-24", "end_date": "2026-09-30",
              "hour": 8, "as_of_time": "2026-09-30T09:00:00-04:00", **overrides}
    with pytest.raises(ValueError, match=message):
        station_hour_history(observations, settings, **params)
