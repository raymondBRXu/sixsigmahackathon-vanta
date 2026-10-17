# DockWatch demo walkthrough

Start with `./app/testme` from the repository root. These checkpoints use the
bundled seed-5300 data and America/New_York time. The default is **Normal
operations**, September 28 at 09:00.

## 1. Normal operations: a complete hourly decision

The opening snapshot shows:

| Metric | Expected value |
|---|---:|
| Two-way availability | 90% (18/20 stations) |
| Empty stations | 2 (S15, S16) |
| Full stations | 0 |
| Coverage | 100% (20/20) |
| Selected S01 bikes / free docks | 17 / 13 |
| S01 adjacent-hour net change | -1 |

Hover a map marker to read its ID, name, count, capacity, free docks, observation
age and suggested action. Double-click a marker to select its station in the
sidebar and detail panel; the page stays on Overview. S15/S16 suggest adding
15 bikes each. The sidebar selection controls Overview details; History opens
for whichever station card you choose.
The queue lists station IDs, readable names and target amounts; it does not
promise a feasible balanced route.

Press Play: one complete hourly snapshot advances every two seconds. Pan the map;
its view remains in place while colors, hover values, metrics and queue change.
Pause and step once. At September 28, 10:00, availability is 75%, empty count 2,
full count 3 and coverage 100%. The state is simulated, not live telemetry.

Open **View by Station**. All 20 station cards appear,
each with a fixed center line at 15 bikes and upper/lower lines at 24/6.
Play advances their eight-slot windows together; the newest reading enters on
the right and the oldest leaves. Pause and step backward to verify that each
window follows the shared clock. Card sizes and vertical scales stay fixed.
Click a chart body, or focus it and press **Enter** or **Space**, to show just
that station in a larger chart. Press Play to watch the same eight-slot window
update with fixed 15/24/6 lines. Choose **Back to all stations** or press
**Escape** to return to the grid.
Hover a point for its station, date, hour and count. Scrub to August 24, 07:00:
each station has only its first point. Step through eight more hours to see
the first point leave the window. Return to the desired clock position before
continuing. These lines are configured inventory references, separate from
the estimated limits in History.

Click **History** on S01's card. Playback pauses and a dialog opens with S01's
Individuals chart. The default hour is **07:00**, and the date range covers
**August 24 through October 16**, with all 40 service dates available regardless
of the playback clock or sidebar station. Select operating hour **09:00**
and use the date controls to select **September 22 through September 28**.

| Date-range result | Expected value |
|---|---:|
| Bikes at 09:00 on Sep 22, 23, 24, 25, 28 | 17, 23, 19, 15, 17 |
| Valid / planned readings | 5 / 5 |
| Valid moving-range pairs | 4 |
| CL | 18.200000 |
| Estimated LCL | 7.561702 |
| Estimated UCL | 28.838298 |

Each point is the selected station's actual snapshot at 09:00 on that date.
The range includes both endpoints. September 26–27 are not scheduled service
dates, so September 25 and 28 are consecutive observations for the moving range.
Changing the hour or date range recalculates the mean and estimated
limits. Missing scheduled readings remain gaps. These exploratory limits do not
establish a stable process or an automatic fault. The dialog contains this
Individuals chart, its selectors and summary.

Choose **10:00** with the same September 22–28 range: all five service dates
remain available even if the shared clock is still at September 28, 09:00. The
Individuals chart is independent of that playback clock.

Choose **07:00** and set both date endpoints to **August 24**. S01 has one
observed count of 15 and CL=15, but no adjacent variation from which to estimate
UCL/LCL. Close the dialog or press **Escape**: focus returns to S01's History
button, the original grid or enlarged chart remains, and playback stays paused.
Move the shared clock and reopen History: each opening resets to **07:00** and
the full configured service-date range. Repeat from an enlarged station chart
to confirm closing History returns to that enlarged chart.

## 2. Morning disruption: an operational contrast

Close History, open **Overview**, and select Morning disruption. At September 28, 09:00 the expected snapshot has
3 empty stations, 5 full stations, 60% two-way availability and 100% coverage.
The source has the same first 25 service days as normal but stronger morning
transfers in the last 15. This split describes scenario construction; it does not
set an application baseline or analysis gate. The app receives inventory
observations, not planted labels.

Interpret this as a synthetic scenario contrast, not evidence that a real
intervention improved customer outcomes or an automatic proof of SPC validity.

## 3. Edge cases: service is not average occupancy

On **Overview**, select Edge cases and start at the default September 28, 09:00.

| Time | Empty | Full | Two-way | Network occupancy |
|---|---:|---:|---:|---:|
| 09:00 | 0 | 0 | 100% | 50% |
| 10:00 | 10 | 10 | 0% | 50% |
| 11:00 | 1 | 1 | 90% | 50% |

At 09:00 all stations have 15 bikes. At 10:00 half are empty and half full.
The same total occupancy can represent completely different service availability.
At 11:00 S01/S02 hold 6/24 bikes (exact 20%/80%: no threshold action), while
S03/S04 hold 5/25 (add/remove 10). S05/S06 are empty/full (add/remove 15).

Open **View by Station**, click S20's **History**, keep 07:00 and set the date range to August 24 through
September 25. Its 25 selected-hour readings are all 15, so the chart shows those counts and
CL=15. Its moving ranges are zero, so no UCL/LCL can be estimated. Operational
rules still work.
Missing/invalid records are tested in software fixtures; this CSV is complete.

## Verification and presentation

```sh
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
npm test --prefix app/frontend
uv run --frozen --extra api python - <<'PY'
from dockwatch.data import load_bundle
from dockwatch.qc import snapshot_at, snapshot_metrics, individual_limits, station_hour_history
obs, stations, settings = load_bundle('data')
print(snapshot_metrics(snapshot_at(obs, stations, '2026-09-28T09:00:00-04:00')))
print(individual_limits([10, 12, 11, 13, 14]))
history, summary = station_hour_history(
    obs, settings, 'S01', '2026-09-22', '2026-09-28', 9,
    '2026-09-28T09:00:00-04:00',
)
print(summary)
PY
```

The arithmetic fixture produces CL=12, LCL=8.010638298, UCL=15.989361702.
The same-hour call reproduces the S01 table above. The suite also checks inclusive
endpoints, recalculation, station/hour/date isolation, missing readings and non-service-day
gaps, constant/single observations, unknown stations and invalid/duplicate
records. Missing observations remain missing, never zero.

A concise judge demonstration: normal snapshot and hover → double-click selection
→ station playback and enlargement → station History → disruption → balanced/polarized edge case.
Explain the supervisor's decision, the three measured inputs, the denominator and
the method's limitations. The public deployment and logged-out browser check are
still pending; follow app/README.md when publishing is authorized.
