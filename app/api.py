"""FastAPI delivery for DockWatch's shared data and statistical library.

The React build is served beside the API so deployment needs one Python process.
Uploads are temporary in-memory demo sources, not a shared observation database.
"""

from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from dockwatch.data import load_observations, load_settings, load_stations, planned_timestamps
from dockwatch.plots import history_plot, inventory_plot, occupancy_heatmap
from dockwatch.qc import (
    REALTIME_WINDOW_SIZE, hourly_changes, realtime_history, snapshot_at, snapshot_metrics,
    station_history, station_hour_history,
)


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data" if (APP_DIR / "data").is_dir() else APP_DIR.parent / "data"
SCENARIOS = [
    {"id": "normal", "label": "Normal operations", "filename": "normal.csv"},
    {"id": "disruption", "label": "Morning disruption", "filename": "disruption.csv"},
    {"id": "edge_cases", "label": "Edge cases", "filename": "edge_cases.csv"},
]
SCENARIO_BY_ID = {scenario["id"]: scenario for scenario in SCENARIOS}
STATIONS = load_stations(DATA_DIR / "stations.json")
SETTINGS = load_settings(DATA_DIR / "settings.json", STATIONS)
PLAN = planned_timestamps(SETTINGS)
NAMES = STATIONS.set_index("station_id")["name"].str.replace(" — simulated station", "", regex=False)
DEMO_DATE = SETTINGS["service_dates"][min(25, len(SETTINGS["service_dates"]) - 1)]
DEFAULT_CURSOR = int(PLAN.get_indexer([
    pd.Timestamp(f"{DEMO_DATE} 09:00", tz=SETTINGS["timezone"])
], method="nearest")[0])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_SOURCES = 8
UPLOADS = OrderedDict()
SOURCE_LOCK = RLock()
PLOT_LOCK = RLock()
# Operational inventory references are fixed policy values, not estimated I-chart limits.
REALTIME_REFERENCE_LINES = {"center": 15, "upper": 24, "lower": 6}

app = FastAPI(
    title="DockWatch API",
    description="Synthetic bikeshare inventory and exploratory Individuals analysis.",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


def _records(frame):
    """Convert pandas scalars to JSON values without losing local UTC offsets."""
    def scalar(value):
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return value.item() if isinstance(value, np.generic) else value

    return [{key: scalar(value) for key, value in row.items()} for row in frame.to_dict("records")]


@lru_cache(maxsize=3)
def _builtin(source):
    observations = load_observations(
        DATA_DIR / SCENARIO_BY_ID[source]["filename"], STATIONS, SETTINGS, check_fleet=True
    )
    return hourly_changes(observations)


def _source(source):
    if source in SCENARIO_BY_ID:
        return _builtin(source), SCENARIO_BY_ID[source]["filename"]
    with SOURCE_LOCK:
        entry = UPLOADS.get(source)
        if entry is not None:
            return entry
    raise HTTPException(404, "Unknown or expired source. Choose a demo or upload the CSV again.")


def _timestamp(cursor):
    if not 0 <= cursor < len(PLAN):
        raise HTTPException(422, f"cursor must be between 0 and {len(PLAN) - 1}.")
    return PLAN[cursor]


def _station(station_id):
    selected = STATIONS.loc[STATIONS["station_id"].eq(station_id)]
    if selected.empty:
        raise HTTPException(422, "Select a configured station_id.")
    return selected.iloc[0]


def _interval(cursor, start, end):
    now = _timestamp(cursor)
    end = cursor if end is None else end
    if not 0 <= start <= end <= cursor:
        raise HTTPException(422, "The interval must satisfy 0 <= start <= end <= cursor.")
    return now, PLAN[start], PLAN[end]


def _snapshot(source, cursor):
    observations, _ = _source(source)
    now = _timestamp(cursor)
    snapshot = snapshot_at(observations, STATIONS, now)
    changes = observations.loc[observations["timestamp"].eq(now), ["station_id", "net_change"]]
    snapshot = snapshot.merge(changes, on="station_id", how="left")
    snapshot["display_name"] = snapshot["station_id"].map(NAMES)
    return now, snapshot


def _history_selection(observations, station_id, cursor, start, end, hour, start_date, end_date):
    """Resolve the legacy hourly interval or the selected-hour date series."""
    now = _timestamp(cursor)
    if hour is None:
        if start_date is not None or end_date is not None:
            raise HTTPException(422, "Select an hour when using start_date or end_date.")
        _, first, last = _interval(cursor, start, end)
        history, summary = station_history(observations, SETTINGS, station_id, first, last)
        selection = {"start": first.isoformat(), "end": last.isoformat()}
    else:
        first = SETTINGS["service_dates"][0] if start_date is None else start_date
        last = now.date().isoformat() if end_date is None else end_date
        try:
            history, summary = station_hour_history(observations, SETTINGS, station_id, first, last, hour, now)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        selection = {"hour": hour, "start_date": first, "end_date": last}
    return {**selection, "timestamp": now.isoformat()}, history, summary


def _config(source):
    observations, label = _source(source)
    stations = STATIONS.assign(display_name=STATIONS["station_id"].map(NAMES))
    return {
        "scenarios": SCENARIOS,
        "stations": _records(stations),
        "timestamps": [timestamp.isoformat() for timestamp in PLAN],
        "default_cursor": DEFAULT_CURSOR,
        "timezone": SETTINGS["timezone"],
        "hours": SETTINGS["hours"],
        "service_dates": SETTINGS["service_dates"],
        "source": {"id": source, "label": label, "observations": len(observations)},
    }


@app.get("/health", include_in_schema=False)
@app.get("/api/health")
def health():
    """Report that the Python service is running."""
    return {"status": "ok"}


@app.get("/api/config")
def config(source: str = "normal"):
    """Return the fixed collection calendar, stations and selected source."""
    return _config(source)


@app.get("/api/snapshot")
def snapshot(source: str = "normal", cursor: int = Query(DEFAULT_CURSOR, ge=0)):
    """Return the current network state and ordered inventory action queue."""
    now, frame = _snapshot(source, cursor)
    queue = frame.loc[frame["priority"].lt(4)].sort_values(["priority", "station_id"])
    return {
        "timestamp": now.isoformat(),
        "metrics": snapshot_metrics(frame),
        "stations": _records(frame),
        "queue": _records(queue),
    }


@app.get("/api/analysis")
def analysis(
    source: str = "normal", cursor: int = Query(DEFAULT_CURSOR, ge=0),
    station_id: str = "S01", start: int = Query(0, ge=0), end: int | None = Query(None, ge=0),
    hour: int | None = Query(None, ge=0, le=23), start_date: str | None = None, end_date: str | None = None,
):
    """Analyze one hour across dates, or all hours with the legacy start/end indexes."""
    observations, _ = _source(source)
    station = _station(station_id)
    selection, history, summary = _history_selection(
        observations, station_id, cursor, start, end, hour, start_date, end_date
    )
    return {
        "station_id": station_id, "capacity": int(station["capacity"]),
        **selection,
        "summary": summary, "history": _records(history),
    }


@app.get("/api/realtime")
def realtime(source: str = "normal", cursor: int = Query(DEFAULT_CURSOR, ge=0)):
    """Return all station histories in one fixed eight-slot scheduled window."""
    observations, _ = _source(source)
    now = _timestamp(cursor)
    history = realtime_history(observations, SETTINGS, now)
    station_histories = {
        station_id: _records(frame[["timestamp", "bikes"]])
        for station_id, frame in history.groupby("station_id", sort=False)
    }
    return {
        "timestamp": now.isoformat(),
        "window_size": REALTIME_WINDOW_SIZE,
        "timestamps": [stamp.isoformat() for stamp in history["timestamp"].drop_duplicates()],
        "reference_lines": REALTIME_REFERENCE_LINES,
        "stations": [
            {"station_id": station.station_id, "display_name": NAMES[station.station_id],
             "capacity": int(station.capacity), "history": station_histories.get(station.station_id, [])}
            for station in STATIONS.itertuples(index=False)
        ],
    }


def _render_chart(chart, observations, station_id, cursor, start, end, hour, start_date, end_date):
    now = _timestamp(cursor)
    capacity = int(_station(station_id)["capacity"])
    if chart == "history":
        _, history, summary = _history_selection(
            observations, station_id, cursor, start, end, hour, start_date, end_date
        )
    else:
        _interval(cursor, start, end)
    with PLOT_LOCK:
        if chart == "history":
            plot = history_plot(history, summary, capacity)
        elif chart == "inventory":
            plot = inventory_plot(observations, station_id, now, capacity, SETTINGS["hours"])
        else:
            plot = occupancy_heatmap(observations, STATIONS, now, SETTINGS)
        figure = plot.draw()
        try:
            figure.set_size_inches(12 if chart == "history" else 7.5, 5)
            output = BytesIO()
            figure.savefig(output, format="svg", bbox_inches="tight")
            return output.getvalue()
        finally:
            plt.close(figure)


@lru_cache(maxsize=48)
def _builtin_chart(chart, source, station_id, cursor, start, end, hour, start_date, end_date):
    return _render_chart(chart, _builtin(source), station_id, cursor, start, end, hour, start_date, end_date)


@app.get("/api/charts/{chart}.svg", response_class=Response)
def chart_svg(
    chart: Literal["history", "inventory", "heatmap"], source: str = "normal",
    cursor: int = Query(DEFAULT_CURSOR, ge=0), station_id: str = "S01",
    start: int = Query(0, ge=0), end: int | None = Query(None, ge=0),
    hour: int | None = Query(None, ge=0, le=23), start_date: str | None = None, end_date: str | None = None,
):
    """Render the same plotnine views used by the original dashboard."""
    observations, _ = _source(source)
    _station(station_id)
    if source in SCENARIO_BY_ID:
        content = _builtin_chart(chart, source, station_id, cursor, start, end, hour, start_date, end_date)
    else:
        content = _render_chart(chart, observations, station_id, cursor, start, end, hour, start_date, end_date)
    return Response(content, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/snapshot.csv", response_class=Response)
def snapshot_csv(source: str = "normal", cursor: int = Query(DEFAULT_CURSOR, ge=0)):
    """Download the original full snapshot table, with missing counts left blank."""
    observations, _ = _source(source)
    now = _timestamp(cursor)
    content = snapshot_at(observations, STATIONS, now).to_csv(index=False)
    return Response(content, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="dockwatch-{now:%Y%m%d-%H%M}.csv"',
        "Cache-Control": "no-store",
    })


@app.post("/api/uploads", status_code=201)
async def upload(file: UploadFile):
    """Validate a CSV against the supplied station list and collection calendar."""
    try:
        payload = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "CSV must be no larger than 5 MiB.")
    try:
        observations = load_observations(BytesIO(payload), STATIONS, SETTINGS)
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as error:
        raise HTTPException(422, str(error)) from error
    source = "upload-" + uuid4().hex
    label = Path(file.filename or "Uploaded CSV").name
    with SOURCE_LOCK:
        UPLOADS[source] = (hourly_changes(observations), label)
        while len(UPLOADS) > MAX_UPLOAD_SOURCES:
            UPLOADS.popitem(last=False)
    return _config(source)


FRONTEND_DIR = APP_DIR / "frontend" / "dist"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="dashboard")
