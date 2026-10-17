# DockWatch v5 — verified synthetic demonstration

Generated from actual CSV checks using app/qc.py. These are designed teaching fixtures, not measured demand.
No baseline is automatically approved. Unreviewed patterns remain exploratory.

## 1. Normal scenario

Choose Normal on any exported date/hour. Every reading is in 6–24 inclusive; no operational warning.
All 300 station/hour strata have 25 nonconstant baseline observations and zero baseline diagnostic warnings.
All 4,500 monitoring readings produce zero point/8-side/6-trend candidate events.
Before the reference period ends, baseline collection/review messages are expected workflow states.

## 2. Operational contrast

Choose Disruption, 2026-09-28, 09:00 America/New_York.

| Station | Bikes | Expected behavior |
|---|---:|---|
| S01 | 0 | Empty, P1, consider adding 15 |
| S06 | 30 | Full, P1, consider removing 15 |
| S02 | 3 | Low, P2, consider adding 12 |
| S07 | 27 | High, P2, consider removing 12 |
| S03 | 6 | No low inventory warning at the exact threshold |
| S08 | 24 | No high inventory warning at the exact threshold |
| S04 | 5 | Low, P2 |
| S09 | 25 | High, P2 |

The map combines urgent, low/high and ordinary inventory states. Recommendations are reviewable quantities, not arranged dispatches.

## 3. Cross-date statistical rules

| Rule | Station | Hour | First trigger | Window | Bikes | Operational warning? |
|---|---|---:|---|---|---:|---|
| beyond_limit | S01 | 09:00 | 2026-09-28 | 2026-09-28 → 2026-09-28 | 0 | Yes |
| eight_same_side | S14 | 12:00 | 2026-10-07 | 2026-09-28 → 2026-10-07 | 17 | No — company review only |
| six_trend | S17 | 14:00 | 2026-10-05 | 2026-09-28 → 2026-10-05 | 15 | No — company review only |

Select the station and hour in Analysis. Step to the previous service date to see that an incomplete window is not yet flagged.
A later event can overlap an earlier run. Do not call repeated sliding windows separate incidents.

## 4. Physical continuity

Docked bikes plus bikes still riding always total 300. Inventory persists through nights and weekends.
Audit-only event logs identify every bike departure/arrival and must never be detector inputs.
The final snapshot leaves ongoing rides in transit; they are not forced to finish.
