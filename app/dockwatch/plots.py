"""Plotnine views of validated observations and exploratory interval estimates.

The line, point, center-line and control-band layering follows the course's
sysen/functions/functions_process_control.py::ggxbar. This module does not call
that helper: DockWatch's core supplies interval-based Individuals estimates.
"""

from textwrap import fill

import pandas as pd
from plotnine import (
    aes, annotate, element_blank, element_line, element_rect,
    element_text, geom_hline, geom_line, geom_point,
    geom_tile, ggplot, labs, scale_fill_gradient,
    scale_linetype_manual, scale_x_continuous, scale_y_continuous, theme,
    theme_minimal,
)


GREEN = "#146c5b"
INK = "#18332f"
RED = "#c34b50"
PALE = "#dcefe8"
MISSING = "#d9dfdb"


def _theme():
    return theme_minimal(base_size=11) + theme(
        text=element_text(color=INK),
        plot_title=element_text(weight="bold", size=14),
        plot_subtitle=element_text(size=10, color="#62746e"),
        plot_caption=element_text(size=9, color="#62746e", ha="left"),
        plot_background=element_rect(fill="#ffffff", color="none"),
        panel_background=element_rect(fill="#fcfdfb", color="none"),
        panel_grid_minor=element_blank(),
        panel_grid_major=element_line(color="#e8eeea", size=0.4),
        legend_position="bottom",
    )


def _segmented(frame, same_hour=False):
    data = frame.copy().reset_index(drop=True)
    breaks = data["bikes"].isna()
    if not same_hour:
        previous = data["timestamp"].shift()
        adjacent = data["timestamp"].sub(previous).dt.total_seconds().eq(3600)
        same_day = data["timestamp"].dt.date.eq(previous.dt.date)
        breaks |= ~adjacent | ~same_day
    data["segment"] = breaks.cumsum()
    return data


def _line_data(data):
    valid = data[data["bikes"].notna()].copy()
    return valid[valid.groupby("segment")["segment"].transform("size").ge(2)]


def _date_axis(data, date_only=False):
    step = max(1, len(data) // 6)
    positions = list(range(0, len(data), step))
    if len(data) and len(data) - 1 not in positions:
        if len(positions) > 1 and len(data) - 1 - positions[-1] < max(2, step / 2):
            positions.pop()
        positions.append(len(data) - 1)
    date_format = "%b %d" if date_only else "%b %d\n%H:%M"
    labels = [pd.Timestamp(data.iloc[position]["timestamp"]).strftime(date_format) for position in positions]
    return scale_x_continuous(breaks=positions, labels=labels)


def inventory_plot(observations, station_id, as_of_time, capacity, planned_hours=range(7, 22)):
    """Show the selected day's elapsed scheduled hours; missing slots break lines."""
    now = pd.Timestamp(as_of_time).tz_convert(observations["timestamp"].dt.tz)
    stamps = pd.DatetimeIndex([
        pd.Timestamp(f"{now.date()} {hour:02}:00", tz=now.tz) for hour in planned_hours
    ])
    stamps = stamps[stamps <= now]
    selected = observations.loc[
        observations["station_id"].eq(station_id) & observations["timestamp"].le(now)
    ].set_index("timestamp")["bikes"]
    data = pd.DataFrame({"timestamp": stamps, "bikes": selected.reindex(stamps).to_numpy()})
    data["hour"] = data["timestamp"].dt.hour
    data = _segmented(data)
    valid = data[data["bikes"].notna()]
    extremes = valid[valid["bikes"].eq(0) | valid["bikes"].eq(capacity)]
    return (
        ggplot(data, aes("hour", "bikes"))
        + geom_line(data=_line_data(data), mapping=aes(group="segment"), color=GREEN, size=0.9)
        + geom_point(data=valid, color=GREEN, size=2.5)
        + geom_point(data=extremes, color=RED, size=3)
        + scale_x_continuous(breaks=data["hour"].tolist(), labels=[f"{hour:02}" for hour in data["hour"]])
        + scale_y_continuous(limits=(0, capacity), breaks=[0, capacity // 2, capacity])
        + labs(title="Today's inventory", x="Local hour (HH:00)", y="Bikes",
               subtitle=f"{station_id} · {now:%b %d} · {len(valid)}/{len(data)} scheduled readings observed",
               caption=fill("Red points mark empty/full readings. Gaps are missing observations; counts do not measure trips.", width=90))
        + _theme()
    )


def occupancy_heatmap(observations, stations, as_of_time, settings):
    """Show today's elapsed station/hour cells, with gray for missing observations."""
    now = pd.Timestamp(as_of_time).tz_convert(settings["timezone"])
    date = str(now.date())
    hours = [hour for hour in settings["hours"]
             if date in settings["service_dates"]
             and pd.Timestamp(f"{date} {hour:02}:00", tz=now.tz) <= now]
    data = pd.MultiIndex.from_product([settings["station_ids"], hours], names=["station_id", "hour"]).to_frame(index=False)
    selected = observations.loc[
        observations["timestamp"].dt.date.eq(now.date()) & observations["timestamp"].le(now)
    ].copy()
    selected["hour"] = selected["timestamp"].dt.hour
    data = data.merge(selected[["station_id", "hour", "bikes"]], on=["station_id", "hour"], how="left")
    data = data.merge(stations[["station_id", "capacity"]], on="station_id", how="left")
    data["occupancy"] = data["bikes"] / data["capacity"]
    data["station_id"] = pd.Categorical(data["station_id"], categories=list(reversed(settings["station_ids"])), ordered=True)
    count = int(data["bikes"].notna().sum())
    return (
        ggplot(data, aes("hour", "station_id", fill="occupancy"))
        + geom_tile(color="white", size=0.3)
        + scale_fill_gradient(low="#eff7ec", high=GREEN, limits=(0, 1), na_value=MISSING,
                              breaks=[0, 0.5, 1], labels=["0%", "50%", "100%"])
        + scale_x_continuous(breaks=hours, labels=[f"{hour:02}" for hour in hours])
        + labs(title="Station inventory across today's hours", x="Local hour (HH:00)", y="Station", fill="Occupancy",
               subtitle=f"{now:%b %d} · {count}/{len(data)} planned readings available through {now:%H:%M}",
               caption=fill("Gray cells are missing. Future hours are not displayed. Occupancy is bikes divided by capacity.", width=90))
        + _theme()
        + theme(panel_grid_major=element_blank())
    )


def history_plot(history, summary, capacity):
    """Plot a scheduled series, its mean and estimated Individuals limits.

    ``summary.hour`` selects the same-hour date view. Its input is reindexed to
    every elapsed service-date slot by ``station_hour_history``.
    """
    data = history.copy().reset_index(drop=True)
    data["position"] = range(len(data))
    same_hour = summary.get("hour") is not None
    data = _segmented(data, same_hour=same_hour)
    valid = data[data["bikes"].notna()]
    limits = summary["limits"]
    plot = ggplot(data, aes("position", "bikes"))
    if limits:
        plot += annotate("rect", xmin=-0.5, xmax=max(len(data) - 0.5, 0.5),
                         ymin=limits["lcl"], ymax=limits["ucl"], fill=PALE, alpha=0.5)
    plot += geom_line(data=_line_data(data), mapping=aes(group="segment"), color=INK, size=0.7)
    plot += geom_point(data=valid, color=GREEN, size=2.3)
    if summary["cl"] is not None:
        levels = [summary["cl"]]
        labels = [f"CL = {summary['cl']:.2f}"]
        linetypes = {labels[0]: "solid"}
        if limits:
            levels.extend([limits["lcl"], limits["ucl"]])
            labels.extend([f"Estimated LCL = {limits['lcl']:.2f}", f"Estimated UCL = {limits['ucl']:.2f}"])
            linetypes.update({label: "dashed" for label in labels[1:]})
        limit_data = pd.DataFrame({"level": levels, "kind": labels})
        plot += geom_hline(data=limit_data, mapping=aes(yintercept="level", linetype="kind"),
                           color=GREEN, size=0.65, inherit_aes=False)
        plot += scale_linetype_manual(values=linetypes, breaks=labels, name="")
    lower = min(0, limits["lcl"]) if limits else 0
    upper = max(capacity, limits["ucl"]) if limits else capacity
    if same_hour:
        subtitle = (f"{summary['hour']:02}:00 · {summary['n']}/{summary['planned']} daily readings observed · "
                    f"{summary['pairs']} consecutive service-date pairs")
        x_label = "Scheduled service date"
        caption = ("Exploratory limits at a fixed hour; autocorrelation is not tested. "
                   "Missing scheduled dates break lines. Limits are not stock targets.")
    else:
        subtitle = (f"{summary['n']}/{summary['planned']} hourly readings observed · "
                    f"{summary['pairs']} adjacent-hour pairs")
        x_label = "Scheduled observations (local date and hour)"
        caption = ("Exploratory limits; intraday patterns and autocorrelation are not tested. "
                   "Missing hours and overnight gaps break lines. Limits are not stock targets.")
    if summary["reason"]:
        subtitle += f" · {summary['reason']}"
    return (
        plot
        + _date_axis(data, date_only=same_hour)
        + scale_y_continuous(limits=(lower - 0.5, upper + 0.5))
        + labs(title="Individuals chart", x=x_label, y="Bikes",
               subtitle=fill(subtitle, width=90),
               caption=fill(caption, width=90))
        + _theme()
        + theme(legend_title=element_blank())
    )
