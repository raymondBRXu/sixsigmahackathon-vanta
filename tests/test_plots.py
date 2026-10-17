"""Check that plotting preserves intervals, missingness and exploratory limits."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from dockwatch.plots import history_plot, inventory_plot, occupancy_heatmap
from dockwatch.qc import individual_limits, station_hour_history


@pytest.fixture
def chart_data():
    timezone = "America/New_York"
    observations = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-28 07:00", "2026-09-28 09:00", "2026-09-28 10:00"]).tz_localize(timezone),
        "station_id": ["S01"] * 3, "bikes": [12, 15, 30],
    })
    stations = pd.DataFrame({"station_id": ["S01", "S02"], "capacity": [30, 30]})
    settings = {"timezone": timezone, "station_ids": ["S01", "S02"],
                "hours": [7, 8, 9, 10], "service_dates": ["2026-09-28"]}
    times = pd.to_datetime(["2026-09-28 07:00", "2026-09-28 08:00", "2026-09-28 09:00",
                            "2026-09-28 10:00", "2026-09-28 11:00", "2026-09-29 07:00",
                            "2026-09-29 08:00"]).tz_localize(timezone)
    history = pd.DataFrame({"timestamp": times, "bikes": [10, 12, np.nan, 11, 13, 17, 12],
                            "station_id": "S01"})
    limits = individual_limits(history["bikes"], history["timestamp"])
    summary = {"limits": limits, "cl": limits["cl"], "n": 6, "planned": 7, "pairs": 3, "reason": ""}
    return observations, stations, settings, summary, history


def line_layers(plot):
    return [layer for layer in plot.layers if type(layer.geom).__name__ == "geom_line"]


def limit_layers(plot):
    return [layer for layer in plot.layers if type(layer.geom).__name__ == "geom_hline"]


def test_inventory_never_reads_future_and_does_not_connect_missing_hour(chart_data):
    observations, _, _, _, _ = chart_data
    plot = inventory_plot(observations, "S01", "2026-09-28T09:00:00-04:00", 30)
    assert plot.data["hour"].tolist() == [7, 8, 9]
    assert pd.isna(plot.data.loc[1, "bikes"])
    assert 30 not in plot.data["bikes"].tolist()
    assert plot.data.loc[0, "segment"] != plot.data.loc[2, "segment"]
    assert line_layers(plot)[0]._data.empty


def test_inventory_uses_configured_hours_without_connecting_clock_gap(chart_data):
    observations, _, _, _, _ = chart_data
    plot = inventory_plot(observations, "S01", "2026-09-28T09:00:00-04:00", 30, planned_hours=[7, 9])
    assert plot.data["hour"].tolist() == [7, 9]
    assert line_layers(plot)[0]._data.empty


def test_heatmap_has_elapsed_planned_cells_and_visible_missingness(chart_data):
    observations, stations, settings, _, _ = chart_data
    plot = occupancy_heatmap(observations, stations, "2026-09-28T09:00:00-04:00", settings)
    assert len(plot.data) == 6
    assert set(plot.data["hour"]) == {7, 8, 9}
    assert plot.data["occupancy"].isna().sum() == 4
    assert plot.data["occupancy"].dropna().tolist() == [0.4, 0.5]
    assert "2/6" in plot.labels.subtitle


def test_history_draws_selected_estimates_without_review_or_crossing_markers(chart_data):
    _, _, _, summary, history = chart_data
    plot = history_plot(history, summary, 30)
    assert limit_layers(plot)[0]._data["level"].tolist() == [summary["cl"], summary["limits"]["lcl"], summary["limits"]["ucl"]]
    point_layers = [layer for layer in plot.layers if type(layer.geom).__name__ == "geom_point"]
    assert len(point_layers) == 1
    assert len(point_layers[0]._data) == 6
    assert plot.data["timestamp"].tolist() == history["timestamp"].tolist()
    assert all("\n" in label and ":" in label for label in plot.scales.get_scales("x").labels)
    assert "Exploratory limits" in plot.labels.caption
    assert "autocorrelation" in plot.labels.caption


def test_history_limits_are_not_clipped_to_capacity(chart_data):
    _, _, _, summary, history = chart_data
    plot = history_plot(history, {**summary, "cl": 15, "limits": {"cl": 15, "lcl": -5, "ucl": 35}}, 30)
    assert limit_layers(plot)[0]._data["level"].tolist() == [15, -5, 35]
    assert plot.scales.get_scales("y").limits == (-5.5, 35.5)


def test_history_does_not_bridge_missing_or_overnight_slots(chart_data):
    _, _, _, summary, history = chart_data
    plot = history_plot(history, summary, 30)
    assert pd.isna(plot.data.loc[2, "bikes"])
    assert plot.data.loc[1, "segment"] != plot.data.loc[3, "segment"]
    assert plot.data.loc[4, "segment"] != plot.data.loc[5, "segment"]
    for _, line in line_layers(plot)[0]._data.groupby("segment"):
        assert line["timestamp"].diff().dropna().dt.total_seconds().eq(3600).all()
        assert line["timestamp"].dt.date.nunique() == 1


def test_all_plot_types_render_to_matplotlib_without_changing_inputs(chart_data):
    observations, stations, settings, summary, history = chart_data
    original = history.copy(deep=True)
    plots = [inventory_plot(observations, "S01", "2026-09-28T09:00:00-04:00", 30),
             occupancy_heatmap(observations, stations, "2026-09-28T09:00:00-04:00", settings),
             history_plot(history, summary, 30)]
    for plot in plots:
        figure = plot.draw()
        assert figure.axes
        figure.canvas.draw()
        plt.close(figure)
    pd.testing.assert_frame_equal(history, original)


@pytest.mark.parametrize("count,value", [(0, None), (1, 15), (5, 15), (5, None)])
def test_degenerate_history_renders_available_mean_without_limits(chart_data, count, value):
    _, _, _, _, history = chart_data
    selected = history.iloc[:count].assign(bikes=value)
    summary = {"cl": value if count else None, "limits": None, "n": count if value is not None else 0,
               "planned": count, "pairs": max(count - 1, 0) if value is not None else 0,
               "reason": "UCL/LCL cannot be estimated."}
    plot = history_plot(selected, summary, 30)
    if count and value is not None:
        assert limit_layers(plot)[0]._data["level"].tolist() == [value]
    else:
        assert not limit_layers(plot)
    figure = plot.draw()
    figure.canvas.draw()
    plt.close(figure)


@pytest.fixture
def same_hour_chart():
    settings = {"timezone": "America/New_York", "station_ids": ["S01"], "hours": [9],
                "service_dates": ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30"]}
    observations = pd.DataFrame({
        "timestamp": pd.to_datetime([f"{day} 09:00" for day in settings["service_dates"]]).tz_localize(settings["timezone"]),
        "station_id": "S01", "bikes": [10, 12, 11, 13, 14],
    })
    return observations, settings


def test_same_hour_plot_keeps_limits_date_axis_and_weekend_connections(same_hour_chart):
    observations, settings = same_hour_chart
    history, summary = station_hour_history(observations, settings, "S01", "2026-09-24", "2026-09-30",
                                            9, "2026-09-30T09:00:00-04:00")
    plot = history_plot(history, summary, 30)
    assert plot.labels.x == "Scheduled service date"
    assert plot.scales.get_scales("x").labels == ["Sep 24", "Sep 25", "Sep 28", "Sep 29", "Sep 30"]
    assert "09:00" in plot.labels.subtitle and "4 consecutive service-date pairs" in plot.labels.subtitle
    assert limit_layers(plot)[0]._data["level"].tolist() == pytest.approx([12, 8.010638298, 15.989361702])
    assert line_layers(plot)[0]._data["segment"].nunique() == 1
    assert len(line_layers(plot)[0]._data) == 5
    figure = plot.draw()
    figure.canvas.draw()
    plt.close(figure)


def test_same_hour_plot_breaks_lines_at_missing_scheduled_dates(same_hour_chart):
    observations, settings = same_hour_chart
    history, summary = station_hour_history(observations.drop(index=2), settings, "S01", "2026-09-24",
                                            "2026-09-30", 9, "2026-09-30T09:00:00-04:00")
    plot = history_plot(history, summary, 30)
    assert pd.isna(plot.data.loc[2, "bikes"])
    assert plot.data.loc[1, "segment"] != plot.data.loc[3, "segment"]
    assert line_layers(plot)[0]._data.groupby("segment")["bikes"].apply(list).tolist() == [[10, 12], [13, 14]]
    assert "Missing scheduled dates break lines" in " ".join(plot.labels.caption.split())


@pytest.mark.parametrize("cutoff,value", [
    ("2026-09-24T08:00:00-04:00", None),
    ("2026-09-24T09:00:00-04:00", 10),
    ("2026-09-30T09:00:00-04:00", 10),
])
def test_same_hour_plot_renders_empty_single_and_constant_ranges(same_hour_chart, cutoff, value):
    observations, settings = same_hour_chart
    history, summary = station_hour_history(observations.assign(bikes=10), settings, "S01", "2026-09-24",
                                            cutoff[:10], 9, cutoff)
    plot = history_plot(history, summary, 30)
    assert summary["limits"] is None and summary["cl"] == value
    assert bool(limit_layers(plot)) == (value is not None)
    figure = plot.draw()
    figure.canvas.draw()
    plt.close(figure)
