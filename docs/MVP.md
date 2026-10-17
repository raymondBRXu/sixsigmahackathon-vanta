# DockWatch MVP

DockWatch helps a bikeshare supervisor inspect synthetic Ithaca station inventory and prioritize manual rebalancing. The React dashboard supports operations playback and same-hour inventory comparisons across dates. It uses the two published v5 datasets, Normal operations and Disruption, without changing their values.

## Overview and View by Station

- Normal operations is the default source; Disruption is the other built-in source. A validated CSV upload uses the configured station list and collection calendar. Operational boundary examples are in Disruption; degenerate and invalid inputs remain software tests.
- Default shared clock: September 28, 2026, 09:00 America/New_York, scheduled index 377 of 600. Default selected station: S01.
- Playback controls sit in the sidebar below Station. Playback advances one scheduled hourly snapshot every two seconds. Pause, backward/forward step and a time slider control the same clock. Scrubbing, stepping, changing source, opening History and map double-click selection pause playback.
- Four network cards: two-way availability, empty stations, full stations, observation coverage. Denominators are valid current observations, with coverage shown separately.
- Ithaca map shows all 20 stations with status colors, current counts, free docks, actions and latest-reading context. Hover reveals details. A marker double-click selects its station; a single click or background double-click does not. Camera position persists across updates. Street tiles can be disabled.
- Action queue shows Station, Bikes and State, sorted by priority then station ID. Empty/full stations precede low/high stock, then reinspection. Popup action quantities target half capacity and do not represent a balanced truck route; the queue has no Move column.
- A single horizontal row of red empty/full alerts replaces the map heading. Opening an alert shows that station's enlarged live chart while preserving time and playback. Closing an alert dismisses its current station/status episode; valid recovery permits a later new episode. Loading/missing data never reuse stale alerts or imply recovery. Source changes, rewinds and nonconsecutive seeks reset dismissals. Hover/focus links queue rows, alerts and map markers with a map halo.
- Selected station details show bikes, free docks and adjacent-hour net change. Missing current counts remain missing. Current snapshot is downloadable as CSV.
- The two navigation choices are **Overview** and **View by Station**. **View by Station** displays every configured station (20 in the supplied network), regardless of the sidebar selection. One API response provides all station histories for the current clock position. Each chart retains the latest eight scheduled hourly slots, drops the oldest as playback advances, and rewinds with the clock. Missing values remain gaps and no segment bridges an overnight break. Before eight slots exist, only available slots are shown.
- Station grid cards stay 336 × 275 pixels, with fixed 306 × 171 pixel SVGs, eight horizontal positions and a fixed 0–30 bike scale. The grid changes its column count to fit; small screens can scroll within the grid. Fixed inventory reference lines are center 15, upper 24 and lower 6; they are configured thresholds, not estimates of process variation. Points strictly outside 6–24 are highlighted without an automated alarm. Changing between Overview and View by Station preserves playback.
- Clicking a chart body, or focusing the chart and pressing **Enter** or **Space**, shows only that station as a larger chart on the same page. The shared clock keeps updating the eight-slot window and fixed reference lines. **Back to all stations** or **Escape** restores the fixed-size card grid.
- Each station card and enlarged chart has a separate **History** button. It opens the clicked station's historical chart without changing the underlying grid or enlarged view. The sidebar station selection continues to control Overview details.

## Station History

- **History** opens a modal dialog for the clicked station and current source, independently of the sidebar station. Opening it pauses playback. Closing it or pressing **Escape** restores focus to its History button and the original grid or enlarged chart, with playback still paused.
- The dialog reads the complete collection timeline, independently of the shared clock. Every opening resets the operating hour to **07:00** and the inclusive date range to every configured service date. An operating-hour selector and double-ended date slider select one scheduled count per service date for the clicked station/hour.
- Four cards: observed/planned readings, center line, LCL and UCL.
- Individuals chart: CL is the mean of observed readings. MR is the absolute difference of valid counts at the selected hour on consecutive scheduled service dates. Sigma estimate is mean(MR)/1.128; estimated limits are CL ± 3 sigma. Missing scheduled readings break chart lines and moving ranges. Non-service days are excluded by the collection calendar and do not break consecutive service-date pairs. Limits are not clipped to 0 or capacity.
- One observation, no adjacent pairs or constant moving ranges retain observations and CL when available, with an explanation instead of UCL/LCL.
- Diagnosis defaults off. Turning it on selects and locks the full date range and applies all eight course-image rules to the selected station/hour, using full-series CL and sigma. Missing slots break windows, ties break trends/alternation, and unavailable rules are distinguished from no matches. Turning it off unlocks dates; reopening History resets it.
- The interactive React SVG supports point hover/focus/tap. Detected-rule tabs select all contributing points in red and show a short explanation; other matched points have amber outlines. Overlapping windows do not duplicate point highlights. Python makes all rule decisions and React renders the returned results.
- There is no baseline approval, frozen monitoring reference or calibrated statistical alarm. Bounded counts, temporal dependence and the deliberately designed data limit interpretation. The legacy Plotnine history/inventory/heatmap SVG endpoints remain available to API callers.

## Data model and report compatibility

The fleet contains 300 bikes across docked and in-transit states, with 600 dock
positions. Positive-duration trips, rerouting and overnight movement preserve
continuous bike identities; there is no nightly reset or operator rebalancing.
The CSV measures docked inventory, so complete docked totals can be below 300.
Event logs independently verify conservation and are not chart/detection inputs.

The published data reports retain a historical three-rule detector that freezes
limits from the first 25 dates. Current History intentionally retains its
selected-range/eight-rule behavior. Thus a published zero-candidate result does
not promise zero matches here: normal S01 at 07:00 has a current T3 match.
The first 25/last 15 date labels describe data construction, not a current UI
approval gate. See the [data codebook](../data/README.md) and
[current demo checkpoints](../demo/README.md).

## Architecture and delivery

React/Vite owns interaction and layout. FastAPI validates HTTP input and calls the independently installable `dockwatch` library. Python owns data validation, inventory rules, statistics, pattern decisions, scheduled realtime windows and legacy Plotnine charts. React draws interactive History and lightweight realtime SVGs from supplied values and decisions. Built React assets and the two synthetic CSVs are packaged with FastAPI for a single-origin deployment.

Python 3.12 and `uv.lock`, Node version guidance and `package-lock.json` define reproducible environments. `app/testme`, `app/manifestme`, `app/deployme` and `app/README.md` retain the course's four-script delivery structure. All code comments are English. Public deployment and Git publication require actual configured services and are not implied by local success.

## Scope

No live telemetry, customer-attempt inference, exact outage-duration estimate, demand forecasting, route optimization, automated dispatch or causal improvement claim. Station locations and observations are synthetic. Availability means that a current observation has both a bike to borrow and a dock to return to.
