# DockWatch MVP — React migration

DockWatch helps a bikeshare supervisor inspect synthetic Ithaca station inventory and prioritize manual rebalancing. This React implementation preserves the final approved dashboard behavior. It uses the existing three datasets without changing their values.

## Operations

- Normal operations is the default source. Morning disruption and Edge cases are selectable. A validated CSV upload uses the configured station list and collection calendar.
- Default shared clock: September 28, 2026, 09:00 America/New_York, scheduled index 377 of 600. Default selected station: S01.
- Playback advances one scheduled hourly snapshot every two seconds. Pause, backward/forward step and a time slider control the same clock. Scrubbing, stepping, changing source or workspace, and map double-click selection pause playback.
- Four network cards: two-way availability, empty stations, full stations, observation coverage. Denominators are valid current observations, with coverage shown separately.
- Ithaca map shows all 20 stations with status colors, current counts, free docks, actions and latest-reading context. Hover reveals details. A marker double-click selects its station; a single click or background double-click does not. Camera position persists across updates. Street tiles can be disabled.
- Action queue includes station IDs and names, sorted by priority then station ID. Empty/full stations precede low/high stock, then reinspection. Moves target half capacity and do not represent a balanced truck route.
- Selected station details show bikes, free docks and adjacent-hour net change. Missing current counts remain missing. Current snapshot is downloadable as CSV.

## Analysis

- Shares the Operations station, source and clock. Playback is paused and Play is disabled here; the clock can still be scrubbed or stepped.
- A double-ended slider selects an inclusive interval ending no later than the shared clock. It includes all scheduled hourly readings for the selected station. Switching stations or workspaces preserves the interval; moving the clock backward clamps its endpoints. Changing source resets it to 0 through the default clock.
- Four cards: observed/planned readings, center line, LCL and UCL.
- Individuals chart: CL is the mean of observed readings. MR is the absolute difference of consecutive valid, one-hour-separated readings within the same local service day. Sigma estimate is mean(MR)/1.128; estimated limits are CL ± 3 sigma. Missing slots and overnight gaps break chart lines and moving ranges. Limits are not clipped to 0 or capacity.
- One observation, no adjacent pairs or constant moving ranges retain observations and CL when available, with an explanation instead of UCL/LCL.
- No baseline approval, same-hour-across-days filter, automated alarm, crossing count or baseline diagnostic plots.
- Two context charts retain their original behavior: selected station inventory today, and all-station hourly occupancy today. Both use the shared clock's date and elapsed hours, independently of the Individuals interval.
- Plotnine renders the same chart functions to SVG; React displays these figures. Statistical interpretation remains with the user. Intraday patterns and serial dependence can affect exploratory limits.

## Architecture and delivery

React/Vite owns interaction and layout. FastAPI validates HTTP input and calls the independently installable `dockwatch` library. Python owns data validation, inventory rules, statistics and plotnine charts. Built React assets and synthetic data are packaged with FastAPI for a single-origin deployment.

Python 3.12 and `uv.lock`, Node version guidance and `package-lock.json` define reproducible environments. `app/testme`, `app/manifestme`, `app/deployme` and `app/README.md` retain the course's four-script delivery structure. All code comments are English. Public deployment and Git publication require actual configured services and are not implied by local success.

## Scope

No live telemetry, customer-attempt inference, exact outage-duration estimate, demand forecasting, route optimization, automated dispatch or causal improvement claim. Station locations and observations are synthetic. Availability means that a current observation has both a bike to borrow and a dock to return to.
