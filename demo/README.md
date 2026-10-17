# DockWatch: current dashboard walkthrough

Run `./app/testme` from the repository root. These checkpoints use the published
v5 seed-5300 CSVs and the current React/Python eight-rule implementation, in
America/New_York. The default is **Normal operations**, September 28 at 09:00.

The preserved `data/demo_guide.md` and `data/validation.json` describe the
generator's historical three-rule detector with frozen reference limits. Its
baseline-review screens and exact statistical results do not describe this UI.
See [the integrated data codebook](../data/README.md) for the distinction.

## 1. Normal operations and live station charts

| Opening snapshot | Expected value |
|---|---:|
| Two-way availability | 100% (20/20 observed stations) |
| Empty / full stations | 0 / 0 |
| Coverage | 100% (20/20) |
| S01 bikes / free docks | 9 / 21 |
| S01 adjacent-hour net change | −4 |
| Action queue | No current inventory threshold actions |

Hover a map point for its inventory, free docks, reading age and action.
Double-click it to select station details without leaving Overview. The sidebar
holds the shared clock below Station. Play advances one scheduled hour every two
seconds; pause, step and scrub use that same time. Pan the map while playing:
its camera stays in place while observations update. At September 28, 10:00,
normal still has 100% availability, no empty/full stations and 100% coverage;
S01 has 10 bikes and adjacent-hour change +1.

Open **View by Station**. All 20 fixed-size cards appear, with the latest eight
scheduled slots and fixed inventory reference lines at 15, 24 and 6. Playback
adds a point on the right and drops the oldest slot. Pause and step backward to
check rewind. Click a chart body, or focus it and press Enter/Space, to enlarge
one station; playback continues. **Back to all stations** or Escape restores
the grid. Scrub to August 24, 07:00: each station has only its initial point.
Missing slots are not invented, and overnight points are not connected.

The model's fleet includes riders in transit. At the opening normal snapshot,
291 bikes are docked and 9 are riding; 291/600 dock occupancy is 48.5%, while
station two-way availability is 100%. These accounting values can be verified
from the complete CSV and event audit; they are not extra dashboard cards or
customer-success probabilities.

## 2. History arithmetic and interactive diagnosis

Open S01's **History**. Playback pauses; the dialog starts at **07:00** and
**August 24–October 16**, independently of the sidebar clock. Keep Diagnosis off,
select **09:00**, and narrow the dates to **September 22–September 28**.

| Same-hour result | Expected value |
|---|---:|
| Bikes on Sep 22, 23, 24, 25, 28 | 11, 12, 8, 11, 9 |
| Observed / planned readings | 5 / 5 |
| Moving-range pairs | 4 |
| CL | 10.200000 |
| Mean moving range | 2.500000 |
| Sigma estimate | 2.216312 |
| Estimated LCL / UCL | 3.551064 / 16.848936 |

Each point is one station's observed count at 09:00 on that date. Non-service
weekends do not break consecutive scheduled dates. Changing the hour or range
recalculates estimates. Hover, focus or tap a point to inspect its date and count.

Select **07:00**, then enable **Diagnosis**. It restores all 40 service dates and
locks both date sliders and selectors. Current normal S01 results are:

| Full-date diagnosis | Expected value |
|---|---:|
| Observed / planned; moving-range pairs | 40 / 40; 39 |
| CL | 17.550000 |
| Estimated LCL / UCL | 11.412520 / 23.687480 |
| Detected issue | T3, four of five beyond 1 sigma on one side |
| Unique red points / matching windows | 4 / 1 |

This T3 result is expected. The generation-time zero-candidate condition used
different rules and a different reference period; the current full-series
eight-rule diagnosis is not required to reproduce it. Normal still has no
operational stock warnings. Turn Diagnosis off to unlock dates.

For a constant-data example, keep Diagnosis off and select S01 **09:00,
August 24–27**: four readings are all 10, CL is 10 and estimated UCL/LCL are
unavailable because moving-range variation is zero. At **07:00, August 24 only**,
one reading of 15 gives CL 15 and no estimable limits. Closing History restores
focus and the underlying station view; playback remains paused. Reopening resets
the hour, full range and Diagnosis-off state.

## 3. Disruption: inventory alerts and boundary behavior

Close History, return to Overview, and select **Disruption**. Its September 28,
09:00 snapshot has **90% availability**, **one empty station**, **one full station**
and **100% coverage**. Docked inventory totals 296, with 4 bikes in transit.

| Station | Bikes | Current inventory state |
|---|---:|---|
| S01 | 0 | Empty; red alert; popup suggests adding 15 |
| S06 | 30 | Full; red alert; popup suggests removing 15 |
| S02 / S07 | 3 / 27 | Low / high; popup quantities +12 / −12 |
| S03 / S08 | 6 / 24 | Normal at the exact strict-threshold boundaries |
| S04 / S09 | 5 / 25 | Low / high |

The queue shows Station, Bikes and State, with no Move column. Hover or focus a
queue row, alert or map point to see the matching map halo and linked highlights.
Close S01's alert: its station remains empty in the queue and map, but the current
alert is dismissed. Rewind or change source to reset dismissals when repeating
the demonstration. Click S06's Full alert while playing: its enlarged live chart
opens at the same time and continues updating. The next reading at 10:00 has
S01=10 and S06=20, so both critical conditions resolve. All 20 stations then have
two-way availability, although some remain low/high.

In View by Station, open **S01 History**, select **09:00**, and enable Diagnosis:
full-series CL is **9.85**, LCL **3.848909**, UCL **15.851091**. Detected tabs are
T1, T2 and T4. T1 highlights two points in two windows; T2 highlights those same
two points in two windows; T4 highlights ten unique points in three overlapping
windows. Changing a tab updates red points and its explanation. Overlapping
matches are not independent incidents.

Two further examples distinguish stock warnings from temporal patterns:

- **S14, 12:00, Diagnosis on:** T4 highlights eight readings, September 28–October
  7, with values 16, 17, 16, 17, 16, 17, 16, 17. These are within 6–24. Other
  detected tabs are T1, T2, T3 and T7 under the current full-series estimates.
- **S17, 14:00, Diagnosis on:** T5 highlights six readings, September 28–October
  5, with values 10, 11, 12, 13, 14, 15. T3 is also detected. The trend does not
  itself establish a cause or require an immediate inventory action.

History reads the complete date series, even when playback is earlier. This is
retrospective exploration, not a simulation of prospective detection. No manual
baseline approval or frozen reference is required. The first 25 dates match
normal by construction; neither the contrast nor any matched pattern proves a
real-world intervention effect or a calibrated false-alarm rate.

## Verification and presentation

```sh
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
npm test --prefix app/frontend
uv run --frozen --extra api python - <<'PY'
from dockwatch.data import load_bundle
from dockwatch.qc import snapshot_at, snapshot_metrics, individual_limits, station_hour_history
obs, stations, settings = load_bundle('data', check_fleet=True)
print(snapshot_metrics(snapshot_at(obs, stations, '2026-09-28T09:00:00-04:00')))
print(individual_limits([10, 12, 11, 13, 14]))
_, summary = station_hour_history(obs, settings, 'S01', '2026-09-22', '2026-09-28',
                                  9, '2026-10-16T21:00:00-04:00')
print(summary)
PY
```

The independent arithmetic fixture remains CL=12, LCL=8.010638298 and
UCL=15.989361702. Input validation, missing observations, constant data, station/hour
isolation and eight-rule boundaries are covered in software tests, without
adding a third published scenario. Event replay separately checks positive ride
durations, dock capacity, continuous bike identity and total fleet conservation.

A short judge demonstration: normal snapshot → live station chart → same-hour
History arithmetic → Diagnosis and its limitation → disruption alerts and linked
map → stock boundary examples → noncritical-stock T4/T5 patterns. Explain the
supervisor's decision, three CSV inputs, denominators and assumptions. Remote
deployment and logged-out checks remain separate from local verification.
