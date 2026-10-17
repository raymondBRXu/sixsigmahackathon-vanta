# DockWatch · Team Vanta

A React dashboard and Python API for a synthetic Ithaca bikeshare network. Inspect current inventory, find empty/full stations, review manual inventory actions, and explore hourly history with Individuals charts.

**20 fictional stations · 300 bikes · hourly snapshots · three synthetic scenarios.** No live telemetry or automated dispatch. The React version preserves the final approved dashboard's content and statistical calculations.

## Run locally

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22+ within the frontend's engine range, and npm. The Python and JavaScript dependency versions are locked in `uv.lock` and `app/frontend/package-lock.json`.

```bash
./app/testme
```

Open **http://127.0.0.1:8000/**. The same process serves the React dashboard and API. API documentation is at **http://127.0.0.1:8000/api/docs**. Set `PORT=8001 ./app/testme` to use another port. The first run needs internet to install dependencies; street-map tiles also use the internet. Turn off **Street basemap** for a tile-free station view.

For frontend development, start the API and Vite in separate terminals:

```bash
uv sync --frozen --extra api
uv run --frozen --extra api uvicorn app.api:app --host 127.0.0.1 --port 8000
```

```bash
npm ci --prefix app/frontend
npm run dev --prefix app/frontend
```

Vite proxies `/api` and `/health` to port 8000. Production uses relative URLs, so both the page assets and API work beneath a Posit Connect content path.

## Dashboard workflow

1. Start with **Normal operations**, **S01**, Sep 28, 2026 at 09:00 EDT.
2. On **Operations**, play/pause the shared clock, step by one scheduled hour, or scrub the timeline. The network cards, map, action queue and selected-station details use the same instant.
3. Hover a map marker for inventory, free docks, reading age and action. **Double-click** a marker to select its station. The map camera stays put as readings update. The sidebar is an alternative station selector.
4. The action queue lists station IDs and names. Empty/full stations come first; low/high stock and reinspection follow. Suggested amounts target half capacity; they are not a balanced transport plan.
5. On **Analysis**, playback pauses. Select an inclusive time interval using the two range handles. The Individuals chart and its observed/CL/LCL/UCL cards use all scheduled hourly readings in that interval, through the shared clock.
6. The two lower plots show the shared clock's current day: the selected station's inventory and all stations' occupancy by elapsed hour. They are independent of the selected Individuals interval.
7. Upload your own observations or download the current snapshot from the sidebar/Operations controls.

The original baseline approval, same-hour SPC and automated alarm features are not part of this version. See [MVP](docs/MVP.md) and [verified demo checkpoints](demo/README.md).

## Inputs and interpretation

CSV columns are `timestamp`, `station_id`, `bikes`. Timestamps must include a UTC offset and fall on the configured hourly calendar. IDs must match `data/stations.json`; bike counts must be integers between zero and station capacity. Duplicate station/timestamp keys and invalid rows are rejected with row-level messages. Missing observations are absent rows, never inferred zeros. Uploads use the supplied station metadata and calendar, with no synthetic 300-bike-total requirement.

Uploads are temporary, limited to 5 MiB, and stored only in the Python process's memory (at most eight uploaded sources). Restarting the server or evicting an old upload requires uploading it again. Use one worker for this demonstration. Reloading the dashboard starts the default demo.

| Measure | Definition |
|---|---|
| Two-way availability | Current observed stations with `0 < bikes < capacity`, divided by observed stations |
| Empty/full proportions | Observed stations at zero/capacity, divided by observed stations |
| Coverage | Current observed stations divided by planned stations |
| Low/high stock | Strictly below 20% or above 80% occupancy |
| Suggested move | Half-capacity target minus current bikes for an actionable station |
| Hourly net change | Difference between consecutive one-hour readings in the same local service day |
| Individuals CL | Mean of valid counts in the selected interval |
| MR and sigma estimate | Mean absolute adjacent-hour difference, divided by `d2 = 1.128` |
| Estimated LCL/UCL | CL minus/plus three estimated sigma |

Moving ranges and lines exclude missing hours and overnight gaps. Limits are not clipped to physical capacity. Constant data, a single reading or no adjacent valid pair retain the observed values and mean but have no estimated UCL/LCL. Limits are exploratory: daily patterns and serial dependence can affect their interpretation. These charts do not establish stability, trigger alarms, measure failed customer attempts, give exact outage durations, or prove intervention effects.

The plain statistical functions and plot layering follow the course `sysen/functions/functions_process_control.py` approach, with the deterministic constant documented by [NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm). [Data codebook](data/README.md) explains every field, generator and assumption.

## Python library

Install the library alone without the web runtime:

```bash
python -m pip install .
```

```python
from dockwatch import individual_limits, load_bundle, snapshot_at, snapshot_metrics

print(individual_limits([10, 12, 11, 13, 14]))
observations, stations, settings = load_bundle("data")
state = snapshot_at(observations, stations, "2026-09-28T09:00:00-04:00")
print(snapshot_metrics(state))
```

`individual_limits(values, timestamps=None)` returns `cl`, `lcl`, `ucl`, `mr_mean`, `sigma`, `n`, and `pairs`. Optional timestamps restrict moving ranges to same-day adjacent hours. It raises `ValueError` when limits cannot be estimated.

`station_history(observations, settings, station_id, start_time, end_time)` returns an hourly DataFrame and a summary containing `limits` (nullable), `cl`, `n`, `planned`, `pairs`, and `reason`. Library callers choose their own cutoff; the HTTP API enforces `end <= cursor`.

`load_bundle(data_dir, source=None, check_fleet=False)` returns validated observations, stations and settings; the default CSV is `normal.csv`. Data files are explicit inputs, not bundled into the wheel. `snapshot_at` returns every configured station with exact-current counts and separately labeled last readings. `snapshot_metrics` returns the rates, counts and coverage above. `hourly_changes` adds `net_change` without bridging gaps.

## HTTP API

All endpoints are documented in `/api/docs`. Index parameters refer to the ordered `timestamps` array returned by `/api/config` (0 through 599 for the supplied calendar).

| Endpoint | Parameters / output |
|---|---|
| `GET /health` | Service health |
| `GET /api/config` | `source=normal`; scenario list, stations, timeline and source metadata |
| `GET /api/snapshot` | `source`, `cursor`; current station rows, metrics and sorted queue |
| `GET /api/analysis` | `source`, `cursor`, `station_id`, `start`, `end`; inclusive history and Individuals summary |
| `GET /api/charts/history.svg` | Same selection as analysis; original plotnine Individuals chart |
| `GET /api/charts/inventory.svg` | `source`, `cursor`, `station_id`; selected station today |
| `GET /api/charts/heatmap.svg` | `source`, `cursor`; all-station occupancy today |
| `GET /api/snapshot.csv` | `source`, `cursor`; downloadable current snapshot |
| `POST /api/uploads` | Multipart `file`; validates CSV and returns configuration with a temporary source ID |

Built-in source IDs are `normal`, `disruption`, `edge_cases`. Use the returned source ID for uploaded observations. Invalid selections return HTTP 422; unknown/expired sources return 404. Missing values serialize to JSON `null`.

## Verify

```bash
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
npm test --prefix app/frontend
npm run build --prefix app/frontend
uv build
```

Tests cover known-answer statistics, constant/insufficient data, missing and overnight gaps, input validation, API parity, clock cutoffs and frontend state transitions. The independent arithmetic fixture `[10,12,11,13,14]` gives CL 12, MR mean 1.5, LCL 8.010638298 and UCL 15.989361702.

## Package and deploy

```bash
./app/manifestme
```

This builds React, exports locked runtime requirements, copies only runtime code/data/assets into `build/connect`, generates a FastAPI manifest and verifies its checksums. `app/manifest.json` records that local bundle. React assets are served by FastAPI, so only one content item is needed.

When publisher environment variables `CONNECT_SERVER` and `CONNECT_API_KEY` are configured, an explicitly invoked `./app/deployme` publishes the verified bundle using the course's supplied Connect helper. Never put credentials in tracked files. The Connect server must provide a compatible Python 3.12 interpreter. Verify public access and the demo checkpoints after deployment; a local build is not a public deployment. No remote URL is claimed here.

## Project structure

- `app/frontend/`: React interface and interaction tests.
- `app/api.py`: HTTP adapter and static frontend hosting.
- `app/dockwatch/`: framework-free data/QC library and plotnine charts.
- `data/`: original synthetic observations, metadata, generator and codebook.
- `tests/`: statistical, plotting and API checks.
- `scripts/`: deployment bundle preparation and verification.

The FastAPI and React starters come from the repository's `demos/`; deployment publishing reuses its `connect-publish` helper. The previous Streamlit development remains archived in Git stash and is not a runtime dependency.
