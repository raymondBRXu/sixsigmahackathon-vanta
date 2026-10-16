#!/usr/bin/env python3
"""Generate DockWatch's three complete, fictional automatic-snapshot datasets.

Python 3.9+; standard library only. Run this file with --help for options.
This is a conserving inventory simulator, not a customer-demand or SPC model.
"""

import argparse
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import random
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCENARIOS = ("normal", "disruption", "edge_cases")
SCHEMA_VERSION = 1
GENERATOR_VERSION = 3
CAPACITY = 30
FLEET = 300
HOURS = list(range(7, 22))
TIMEZONE = "America/New_York"
SERVICE_DAYS = 40
BASELINE_DAYS = 25

ANCHOR_PATH = Path(__file__).with_name("station_anchors.json")


def station_configuration():
    """Read bundled official geographic anchors offline; return product fields."""
    anchors = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
    fields = ("station_id", "name", "area", "type", "latitude", "longitude", "capacity")
    stations = [{field: anchor[field] for field in fields} for anchor in anchors]
    if [station["station_id"] for station in stations] != ["S%02d" % index for index in range(1, 21)]:
        raise ValueError("Expected twenty ordered station anchors S01 through S20")
    if any(station["capacity"] != CAPACITY for station in stations):
        raise ValueError("All station capacities must remain 30")
    return stations


def service_calendar(start):
    """Forty fictional comparable weekdays, without holiday exclusions."""
    if start.weekday() >= 5:
        raise ValueError("--start-date must be a weekday (Monday through Friday)")
    days = []
    current = start
    while len(days) < SERVICE_DAYS:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def transfer(inventory, source, destination):
    """Move one bike instantaneously, if physically possible."""
    if source != destination and inventory[source] > 0 and inventory[destination] < CAPACITY:
        inventory[source] -= 1
        inventory[destination] += 1
        return True
    return False


def distance_km(first, second):
    """Straight-line great-circle separation, not road distance or travel time."""
    lat1, lat2 = math.radians(first["latitude"]), math.radians(second["latitude"])
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second["longitude"] - first["longitude"])
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, value)))


def transfer_pairs(stations, sources, destinations):
    """Nearby candidate pairs have more weight; no candidate exceeds weight 1."""
    pairs, weights = [], []
    for source in sources:
        for destination in destinations:
            if source != destination:
                pairs.append((source, destination))
                weights.append(1.0 / (1.0 + distance_km(stations[source], stations[destination])))
    return pairs, weights


def sampled_transfers(inventory, candidates, attempts, rng):
    """Count synthetic transfer attempts and successes, never customer attempts."""
    pairs, weights = candidates
    successful = 0
    for _ in range(attempts):
        source, destination = rng.choices(pairs, weights=weights, k=1)[0]
        successful += transfer(inventory, source, destination)
    return successful


def apply_fixture_station(inventory, station, target):
    """Set one edge-fixture count through real conserving one-bike transfers."""
    while inventory[station] != target:
        if inventory[station] > target:
            other = next(index for index in range(20) if index != station and inventory[index] < CAPACITY)
            transfer(inventory, station, other)
        else:
            other = next(index for index in range(20) if index != station and inventory[index] > 0)
            transfer(inventory, other, station)


def apply_fixture_vector(inventory, targets):
    """Plant an artificial software fixture; this is not an operator policy."""
    if sum(targets) != sum(inventory):
        raise ValueError("A fixture cannot add or remove fleet bikes")
    while inventory != targets:
        source = next(index for index in range(20) if inventory[index] > targets[index])
        destination = next(index for index in range(20) if inventory[index] < targets[index])
        transfer(inventory, source, destination)


def edge_adjustments(inventory, day_index, hour):
    # A constant later-hour baseline tests unsupported I-chart history while
    # every sensor continues reporting correctly. Monitoring is not forced flat.
    if day_index < BASELINE_DAYS:
        apply_fixture_station(inventory, 19, 15)
    if day_index == BASELINE_DAYS:
        if hour == 9:
            apply_fixture_vector(inventory, [15] * 20)
        elif hour == 10:
            apply_fixture_vector(inventory, [0] * 10 + [30] * 10)
        elif hour == 11:
            apply_fixture_vector(inventory, [6, 24, 5, 25, 0, 30] + [15] * 14)


def generate_rows(scenario, seed, days, stations, zone):
    homes = [index for index, station in enumerate(stations) if station["type"] == "residential"]
    academic = [index for index, station in enumerate(stations) if station["type"] == "academic"]
    hubs = [index for index, station in enumerate(stations) if station["type"] in ("mixed", "transport")]
    if not homes or not academic:
        raise ValueError("Station configuration requires residential and academic anchors")
    candidates = {
        "background": transfer_pairs(stations, range(len(stations)), range(len(stations))),
        "morning_to_class": transfer_pairs(stations, homes, academic),
        "midday_exchange": transfer_pairs(stations, academic + hubs, academic + hubs),
        "afternoon_return": transfer_pairs(stations, academic, homes),
        "evening_return": transfer_pairs(stations, academic + hubs, homes),
    }
    rows = []
    audit = {}
    inventory = [15] * 20  # One initial allocation, only at the first service date.
    for day_index, day in enumerate(days):
        # Date-indexed random streams are reproducible, but inventories carry
        # across dates and are NOT independent. No scenario-name seed is used.
        rng = random.Random(seed * 1000003 + day_index * 9176)
        for hour in HOURS:
            plans = []
            if hour > HOURS[0]:
                peak = hour in (8, 9, 10, 17, 18, 19)
                plans.append(("background", 10 if peak else 6))
                if hour in (8, 9, 10):
                    abnormal = scenario == "disruption" and day_index >= BASELINE_DAYS
                    plans.append(("morning_to_class", (48 if abnormal else 16) + rng.randint(0, 6)))
                elif hour in (11, 12, 13, 14):
                    plans.append(("midday_exchange", 6 + rng.randint(0, 4)))
                elif hour in (15, 16, 17):
                    plans.append(("afternoon_return", 6 + rng.randint(0, 4)))
                elif hour in (18, 19, 20, 21):
                    plans.append(("evening_return", 9 + rng.randint(0, 4)))
            phase = "baseline" if day_index < BASELINE_DAYS else "monitoring"
            for flow, attempts in plans:
                successful = sampled_transfers(inventory, candidates[flow], attempts, rng)
                totals = audit.setdefault(phase, {}).setdefault(flow, {"planned_transfers": 0, "successful_transfers": 0})
                totals["planned_transfers"] += attempts
                totals["successful_transfers"] += successful
            if scenario == "edge_cases" and hour > HOURS[0]:
                edge_adjustments(inventory, day_index, hour)
            timestamp = datetime.combine(day, time(hour), tzinfo=zone).isoformat()
            rows.extend((timestamp, station["station_id"], inventory[index]) for index, station in enumerate(stations))
    return rows, audit


def validate_rows(rows, days, stations, zone):
    """Validate generation invariants, without implementing product statistics."""
    expected_rows = len(days) * len(HOURS) * len(stations)
    if len(rows) != expected_rows:
        raise ValueError("Expected %s rows" % expected_rows)
    offset = 0
    for day in days:
        for hour in HOURS:
            timestamp = datetime.combine(day, time(hour), tzinfo=zone).isoformat()
            snapshot = rows[offset:offset + 20]
            offset += 20
            if [(row[0], row[1]) for row in snapshot] != [(timestamp, station["station_id"]) for station in stations]:
                raise ValueError("Incorrect timestamp, order, duplicate or missing station")
            counts = [row[2] for row in snapshot]
            if any(type(count) is not int or not 0 <= count <= CAPACITY for count in counts):
                raise ValueError("Inventory outside integer capacity bounds")
            if sum(counts) != FLEET:
                raise ValueError("Fleet conservation failed")


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["timestamp", "station_id", "bikes"])
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def configuration_guard(output, selected, configuration):
    """Never mix separately generated scenarios from different settings/seeds."""
    siblings = [name for name in SCENARIOS if name not in selected and (output / (name + ".csv")).exists()]
    if not siblings:
        return
    path = output / "generation_metadata.json"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        recorded = metadata["configuration"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Cannot verify existing sibling CSV configuration; use a new --output-dir or regenerate --scenario all") from None
    if recorded != configuration:
        raise ValueError("Existing sibling CSVs have a different configuration; use a new --output-dir or regenerate --scenario all")
    for name in siblings:
        filename = name + ".csv"
        expected = metadata.get("expected_csvs", {}).get(filename, {}).get("sha256")
        actual = hashlib.sha256((output / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Existing sibling CSV does not match its recorded hash; use a new --output-dir or regenerate --scenario all")


def generate(output, scenario="all", seed=5300, start=date(2026, 8, 24)):
    days = service_calendar(start)
    try:
        zone = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        raise ValueError("System timezone data for America/New_York is unavailable; run on a system with an IANA timezone database") from None
    stations = station_configuration()
    selected = SCENARIOS if scenario == "all" else (scenario,)
    configuration = {"generator_version": GENERATOR_VERSION, "seed": seed, "start_date": start.isoformat(), "timezone": TIMEZONE,
                     "stations_sha256": hashlib.sha256(json_bytes(stations)).hexdigest(), "hours": HOURS}
    configuration_guard(output, selected, configuration)
    settings = {
        "schema_version": SCHEMA_VERSION, "timezone": TIMEZONE,
        "service_dates": [day.isoformat() for day in days],
        "baseline_dates": [day.isoformat() for day in days[:BASELINE_DAYS]],
        "monitoring_dates": [day.isoformat() for day in days[BASELINE_DAYS:]],
        "hours": HOURS, "station_ids": [station["station_id"] for station in stations],
        "collection_mode": "automatic_complete_hourly_snapshots",
    }
    # Compute all expected hashes even for a single-scenario run, making
    # metadata independent of invocation order. Only selected CSVs are written.
    payloads = {}
    all_rows = {}
    transfer_audits = {}
    for name in SCENARIOS:
        all_rows[name], transfer_audits[name] = generate_rows(name, seed, days, stations, zone)
        validate_rows(all_rows[name], days, stations, zone)
        payloads[name + ".csv"] = csv_bytes(all_rows[name])
    baseline_rows = BASELINE_DAYS * len(HOURS) * len(stations)
    if all_rows["normal"][:baseline_rows] != all_rows["disruption"][:baseline_rows]:
        raise ValueError("Normal/disruption baselines differ")
    for name in SCENARIOS:
        path = output / (name + ".csv")
        if name not in selected and path.exists() and path.read_bytes() != payloads[name + ".csv"]:
            raise ValueError("Existing sibling CSV differs from the current generator output; use a new --output-dir or regenerate --scenario all")
    fixture_day = days[BASELINE_DAYS].isoformat()
    metadata = {
        "synthetic": True, "configuration": configuration,
        "not_detector_input": True,
        "provenance": "Inventories, bikeshare stations and flows are entirely simulated; geographic landmark anchors are real official-source coordinates. No real sensor readings, demand observations or trip records.",
        "geography": "Twelve anchors in Cornell core and eight surrounding anchors; official Cornell venue coordinates and TCAT GTFS20260922 transit coordinates. Geographic visual review and docking-site feasibility are separate; no existing bikeshare facilities are claimed.",
        "station_sources": [
            {"station_id": anchor["station_id"], "source_url": anchor["source_url"], "coordinate_note": anchor["coordinate_note"]}
            for anchor in json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
        ],
        "calendar_assumption": "All listed weekdays are fictional comparable service dates, including holidays; no real Cornell or Ithaca calendar is inferred.",
        "model": {
            "capacity_per_station": 30, "total_bikes": 300, "total_positions": 600,
            "initial_allocation": "15 bikes at every station only at 07:00 on the first service date; no daily reset or operator redistribution",
            "cross_date_continuity": "Each station's next planned date 07:00 inventory equals its previous planned date 21:00 inventory, including Friday-to-Monday",
            "outside_observation_window": "No movements are modeled outside 07:00-21:00 or on unlisted weekend days; inventory is held unchanged",
            "transfer": "Instantaneous single-bike movement, no in-transit inventory or travel times",
            "distance_pair_weight": "1 / (1 + straight-line distance in km), at most 1; not road distance, slope or travel time",
            "background_attempts": "10 at 08/09/10/17/18/19; 6 at other hours after 07; symmetric distance-weighted station pairs",
            "normal_morning_at_08_09_10": "16 + uniform integer 0..6 synthetic transfer attempts each hour, residential to academic",
            "disruption_monitoring_morning_at_08_09_10": "48 + uniform integer 0..6 synthetic transfer attempts each hour, residential to academic",
            "midday_at_11_12_13_14": "6 + uniform integer 0..4 attempts each hour among academic/mixed/transport stations",
            "afternoon_at_15_16_17": "6 + uniform integer 0..4 attempts each hour, academic to residential",
            "evening_at_18_19_20_21": "9 + uniform integer 0..4 attempts each hour, academic/mixed/transport to residential, including library return",
            "capacity_handling": "Transfers require a bike at the source and a free position at the destination",
            "edge_adjustments": "Artificial software fixtures during daytime hours only, not operator dispatch or a claimed natural commuting process",
            "sensors": "All automatic readings accurate, complete and on the scheduled hour",
        },
        "transfer_audit": transfer_audits,
        "transfer_audit_scope": "Synthetic planned/successful movements aggregated by scenario and phase; excludes the initial allocation and artificial edge-fixture adjustments; never customer attempts or observed trips",
        "expected_csvs": {
            name: {"rows": len(days) * len(HOURS) * len(stations), "baseline_rows": baseline_rows,
                   "monitoring_rows": (len(days) - BASELINE_DAYS) * len(HOURS) * len(stations),
                   "complete_snapshots": len(days) * len(HOURS), "coverage": 1.0,
                   "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in payloads.items()
        },
        "edge_fixtures": [
            {"case": "constant later-hour baseline", "station_id": "S20", "dates": settings["baseline_dates"], "hours": HOURS, "bikes": 15},
            {"case": "balanced network", "date": fixture_day, "hour": 9, "bikes_by_station_order": [15] * 20},
            {"case": "polarized network", "date": fixture_day, "hour": 10, "bikes_by_station_order": [0] * 10 + [30] * 10},
            {"case": "exact and near stock thresholds; empty/full", "date": fixture_day, "hour": 11,
             "bikes_by_station_order": [6, 24, 5, 25, 0, 30] + [15] * 14},
        ],
        "limitations": [
            "No missing readings, sensor failures, closures or unusable bikes/docks in any scenario.",
            "Inventory persists across service dates; same-hour sequences may have serial dependence, drift or boundary concentration and require independent suitability review.",
            "No operator dispatch, nightly rebalancing, overnight trips or weekend trips are simulated.",
            "Normal means regular simulation, not guaranteed absence of inventory warnings or statistical signals.",
            "Disruption is an operational redistribution, not equipment failure; detection must be evaluated independently.",
            "No SPC implementation or baseline suitability approval is supplied by this generator.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    # All validation completes before writes; writing is confined to named outputs.
    for name in selected:
        (output / (name + ".csv")).write_bytes(payloads[name + ".csv"])
    for filename, value in (("stations.json", stations), ("settings.json", settings), ("generation_metadata.json", metadata)):
        (output / filename).write_bytes(json_bytes(value))
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all",) + SCENARIOS, default="all", help="CSV(s) to write; default: all")
    parser.add_argument("--seed", type=int, default=5300, help="Reproducible integer seed; default: 5300")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 8, 24), help="First fictional weekday in YYYY-MM-DD; default: 2026-08-24")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent, help="Output directory; default: this script's directory")
    args = parser.parse_args(argv)
    try:
        selected = generate(args.output_dir, args.scenario, args.seed, args.start_date)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    for name in selected:
        print("%s: %s rows, %s complete snapshots, %s bikes per snapshot" %
              (name + ".csv", SERVICE_DAYS * len(HOURS) * 20, SERVICE_DAYS * len(HOURS), FLEET))
    print("Shared files: stations.json, settings.json, generation_metadata.json")
    print("Output: %s" % args.output_dir.resolve())
    print("SYNTHETIC automatic readings; no missing rows or sensor failures. SPC analysis is not implemented here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
