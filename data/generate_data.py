#!/usr/bin/env python3
"""Generate DockWatch's three complete, fictional automatic-snapshot datasets.

Python 3.9+; standard library only. Run this file with --help for options.
This is a conserving inventory simulator, not a customer-demand or SPC model.
"""

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
import random
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCENARIOS = ("normal", "disruption", "edge_cases")
SCHEMA_VERSION = 1
GENERATOR_VERSION = 4
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


def utc(instant):
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Simulation times must include a timezone")
    return instant.astimezone(timezone.utc)


class Simulator:
    """Individual-bike event simulator; no operator moves or inventory resets.

    Public test interface: schedule_departure(), advance_to(), snapshot(), events,
    and in_transit. Ties process arrivals before departures; snapshots follow both.
    """

    def __init__(self, stations, start, seed=5300):
        self.stations = stations
        self.ids = [station["station_id"] for station in stations]
        self.index = {station_id: index for index, station_id in enumerate(self.ids)}
        self.now = utc(start)
        self.zone = ZoneInfo(TIMEZONE)
        self.seed = seed
        self.docked = [{"B%03d" % (index * 15 + bike + 1) for bike in range(15)} for index in range(20)]
        self.in_transit = {}
        self.events = []
        self.queue = []
        self.sequence = 0
        self.trip_counter = 0
        self.transfer_audit = {}

    def iso(self, instant):
        return instant.astimezone(self.zone).isoformat()

    def snapshot(self):
        return {station_id: len(self.docked[index]) for index, station_id in enumerate(self.ids)}

    def duration(self, source, destination, rng):
        # Explicit assumptions, not a route/elevation or observed speed model.
        cycling_seconds = distance_km(self.stations[source], self.stations[destination]) * 1.3 / 12 * 3600
        return max(300, math.ceil(cycling_seconds + rng.randint(180, 480)))

    def _push(self, when, kind, payload):
        self.sequence += 1
        heapq.heappush(self.queue, (utc(when), 0 if kind == "arrival" else 1, self.sequence, kind, payload))

    def _audit(self, phase, flow):
        return self.transfer_audit.setdefault(phase, {}).setdefault(flow, {
            "planned_transfers": 0, "successful_transfers": 0, "arrivals": 0, "reroutes": 0,
        })

    def schedule_departure(self, when, source_id, destination_id, flow="test", duration_seconds=None,
                           phase="test", forbidden_ids=()):
        when = utc(when)
        if when < self.now:
            raise ValueError("Cannot schedule a departure in the past")
        source, destination = self.index[source_id], self.index[destination_id]
        if source == destination:
            raise ValueError("A ride needs different origin and destination stations")
        if source_id in forbidden_ids or destination_id in forbidden_ids:
            raise ValueError("A route includes an excluded fixture station")
        if duration_seconds is None:
            rng = random.Random(self.seed * 1000003 + int(when.timestamp()) + source * 31 + destination)
            duration_seconds = self.duration(source, destination, rng)
        if duration_seconds <= 0:
            raise ValueError("Ride duration must be positive")
        self._audit(phase, flow)["planned_transfers"] += 1
        self._push(when, "departure", {"source": source, "destination": destination,
                   "duration": duration_seconds, "flow": flow, "phase": phase,
                   "forbidden_ids": tuple(forbidden_ids)})

    def _depart(self, plan):
        source, destination = plan["source"], plan["destination"]
        if not self.docked[source]:
            return  # Unfulfilled synthetic plan, not an observed customer failure.
        bike_id = min(self.docked[source])
        self.docked[source].remove(bike_id)
        self.trip_counter += 1
        trip_id = "T%06d" % self.trip_counter
        due = self.now + timedelta(seconds=plan["duration"])
        trip = dict(plan, bike_id=bike_id, trip_id=trip_id, arrival_due=due, reroute_count=0)
        self.in_transit[bike_id] = trip
        self._audit(plan["phase"], plan["flow"])["successful_transfers"] += 1
        self.events.append({"event": "departure", "timestamp": self.iso(self.now), "bike_id": bike_id,
                            "trip_id": trip_id, "station_id": self.ids[source],
                            "destination_id": self.ids[destination], "arrival_due": self.iso(due), "flow": plan["flow"]})
        self._push(due, "arrival", bike_id)

    def _arrive(self, bike_id):
        trip = self.in_transit[bike_id]
        destination = trip["destination"]
        if len(self.docked[destination]) < self.stations[destination]["capacity"]:
            self.docked[destination].add(bike_id)
            del self.in_transit[bike_id]
            self._audit(trip["phase"], trip["flow"])["arrivals"] += 1
            self.events.append({"event": "arrival", "timestamp": self.iso(self.now), "bike_id": bike_id,
                                "trip_id": trip["trip_id"], "station_id": self.ids[destination]})
            return
        available = [index for index, station in enumerate(self.stations)
                     if len(self.docked[index]) < station["capacity"] and station["station_id"] not in trip["forbidden_ids"]]
        if not available:
            raise ValueError("No permissible free dock remains for a rerouted bike")
        alternative = min(available, key=lambda index: (distance_km(self.stations[destination], self.stations[index]), index))
        trip["reroute_count"] += 1
        rng = random.Random(self.seed * 1000003 + int(trip["trip_id"][1:]) * 7919 + trip["reroute_count"])
        due = self.now + timedelta(seconds=self.duration(destination, alternative, rng))
        trip["destination"], trip["arrival_due"] = alternative, due
        self._audit(trip["phase"], trip["flow"])["reroutes"] += 1
        self.events.append({"event": "reroute", "timestamp": self.iso(self.now), "bike_id": bike_id,
                            "trip_id": trip["trip_id"], "station_id": self.ids[destination],
                            "destination_id": self.ids[alternative], "arrival_due": self.iso(due)})
        self._push(due, "arrival", bike_id)

    def advance_to(self, when):
        when = utc(when)
        if when < self.now:
            raise ValueError("Cannot advance simulation backwards")
        while self.queue and self.queue[0][0] <= when:
            self.now, _, _, kind, payload = heapq.heappop(self.queue)
            if kind == "arrival":
                self._arrive(payload)
            else:
                self._depart(payload)
        self.now = when
        docked = sum(map(len, self.docked))
        if docked + len(self.in_transit) != FLEET:
            raise ValueError("Docked plus in-transit fleet conservation failed")


def candidate_flows(stations, excluded=()):
    usable = [index for index, station in enumerate(stations) if station["station_id"] not in excluded]
    homes = [index for index in usable if stations[index]["type"] == "residential"]
    academic = [index for index in usable if stations[index]["type"] == "academic"]
    hubs = [index for index in usable if stations[index]["type"] in ("mixed", "transport")]
    leisure = [index for index in usable if stations[index]["type"] in ("mixed", "recreation")]
    if not homes or not academic:
        raise ValueError("Station configuration requires residential and academic anchors")
    return {
        "background": transfer_pairs(stations, usable, usable),
        "morning_to_class": transfer_pairs(stations, homes, academic),
        "midday_exchange": transfer_pairs(stations, academic + hubs, academic + hubs),
        "afternoon_return": transfer_pairs(stations, academic, homes),
        "evening_return": transfer_pairs(stations, academic + hubs, homes),
        "weekend_outing": transfer_pairs(stations, homes + hubs, leisure),
        "weekend_return": transfer_pairs(stations, leisure + hubs, homes),
    }


def hourly_plans(local, abnormal, rng):
    """Synthetic attempt intensities for the hour starting at local time."""
    hour = local.hour
    if hour < 6:
        return [("background", rng.randint(0, 2))]
    if local.weekday() >= 5:
        if hour < 10 or hour >= 21:
            return [("background", rng.randint(1, 3))]
        flow = "weekend_outing" if hour < 17 else "weekend_return"
        return [("background", 4), (flow, rng.randint(2, 5))]
    if hour == 6:
        return [("background", 2), ("morning_to_class", rng.randint(4, 8))]
    if hour < 10:
        return [("background", 10), ("morning_to_class", (48 if abnormal else 16) + rng.randint(0, 6))]
    if hour < 14:
        return [("background", 6), ("midday_exchange", rng.randint(6, 10))]
    if hour < 17:
        return [("background", 6), ("afternoon_return", rng.randint(6, 10))]
    if hour < 21:
        return [("background", 10), ("evening_return", rng.randint(9, 13))]
    return [("background", 2), ("evening_return", rng.randint(2, 5))]


def schedule_fixture_rides(simulator, targets, deadline):
    """Artificial positive-duration rider schedules, not operator redistribution."""
    if simulator.in_transit or simulator.queue:
        raise ValueError("Fixture scheduling requires earlier rides to have settled; no queue may be cleared")
    counts = [len(bikes) for bikes in simulator.docked]
    if sum(targets) != FLEET or any(not 0 <= count <= CAPACITY for count in targets):
        raise ValueError("Invalid artificial fixture target")
    rng = random.Random(simulator.seed * 1000003 + int(simulator.now.timestamp()))
    ordinal = 0
    while counts != targets:
        source = next(index for index in range(20) if counts[index] > targets[index])
        destination = next(index for index in range(20) if counts[index] < targets[index])
        depart = simulator.now + timedelta(seconds=60 + ordinal % 240)
        duration = simulator.duration(source, destination, rng)
        if depart + timedelta(seconds=duration) >= utc(deadline):
            raise ValueError("A fixture ride cannot reach its target before the scheduled snapshot")
        simulator.schedule_departure(depart, simulator.ids[source], simulator.ids[destination],
                                     "edge_fixture_rider_schedule", duration, "monitoring")
        counts[source] -= 1
        counts[destination] += 1
        ordinal += 1


def generate_rows(scenario, seed, days, stations, zone):
    start = utc(datetime.combine(days[0], time(HOURS[0]), tzinfo=zone))
    end = utc(datetime.combine(days[-1], time(HOURS[-1]), tzinfo=zone))
    monitoring_start = utc(datetime.combine(days[BASELINE_DAYS], time(HOURS[0]), tzinfo=zone))
    fixture_day = days[BASELINE_DAYS]
    simulator = Simulator(stations, start, seed)
    candidates = candidate_flows(stations)
    constant_candidates = candidate_flows(stations, ("S20",))
    rows, snapshot_audit = [], []
    service_dates = set(days)
    cursor = start
    while cursor <= end:
        # UTC event arithmetic traverses every physical hour, including DST,
        # nights and weekends. Local time controls the hypothetical flow profile.
        simulator.advance_to(cursor)
        local = cursor.astimezone(zone)
        if local.date() in service_dates and local.hour in HOURS:
            timestamp = local.isoformat()
            counts = simulator.snapshot()
            rows.extend((timestamp, station_id, counts[station_id]) for station_id in simulator.ids)
            snapshot_audit.append({"timestamp": timestamp, "docked": sum(counts.values()),
                                   "in_transit": len(simulator.in_transit)})
        if cursor == end:
            break  # Pending rides remain in transit; no artificial final docking.
        fixture_pause = scenario == "edge_cases" and local.date() == fixture_day and local.hour < 12
        if fixture_pause:
            if local.hour == 7:
                schedule_fixture_rides(simulator, [15] * 20, cursor + timedelta(hours=2))
            elif local.hour == 9:
                schedule_fixture_rides(simulator, [0] * 10 + [30] * 10, cursor + timedelta(hours=1))
            elif local.hour == 10:
                schedule_fixture_rides(simulator, [6, 24, 5, 25, 0, 30] + [15] * 14, cursor + timedelta(hours=1))
        else:
            # No scenario-name seed: complete normal/disruption history is shared
            # before the first monitoring date at 07:00, including latent rides.
            rng = random.Random(seed * 1000003 + int(cursor.timestamp()) // 3600 * 9176)
            phase = "monitoring" if cursor >= monitoring_start else "baseline"
            abnormal = scenario == "disruption" and cursor >= monitoring_start
            excluded = ("S20",) if scenario == "edge_cases" and cursor < monitoring_start else ()
            flows = constant_candidates if excluded else candidates
            for flow, attempts in hourly_plans(local, abnormal, rng):
                pairs, weights = flows[flow]
                for _ in range(attempts):
                    source, destination = rng.choices(pairs, weights=weights, k=1)[0]
                    departure = cursor + timedelta(seconds=rng.randint(1, 3599))
                    duration = simulator.duration(source, destination, rng)
                    simulator.schedule_departure(departure, simulator.ids[source], simulator.ids[destination],
                                                 flow, duration, phase, excluded)
        cursor += timedelta(hours=1)
    return rows, simulator.transfer_audit, simulator.events, snapshot_audit


def validate_rows(rows, days, stations, zone, snapshot_audit):
    """Validate generation invariants, without implementing product statistics."""
    expected_rows = len(days) * len(HOURS) * len(stations)
    if len(rows) != expected_rows:
        raise ValueError("Expected %s rows" % expected_rows)
    if len(snapshot_audit) != len(days) * len(HOURS):
        raise ValueError("Expected one fleet audit for every scheduled snapshot")
    offset = 0
    snapshot_index = 0
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
            audit = snapshot_audit[snapshot_index]
            snapshot_index += 1
            if audit["timestamp"] != timestamp or audit["docked"] != sum(counts):
                raise ValueError("Snapshot audit disagrees with CSV inventory")
            if audit["docked"] + audit["in_transit"] != FLEET or audit["in_transit"] < 0:
                raise ValueError("Docked plus in-transit fleet conservation failed")


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["timestamp", "station_id", "bikes"])
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def jsonl_bytes(events):
    return "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events).encode("utf-8")


def configuration_guard(output, selected, configuration):
    """Never mix separately generated CSV/event pairs from different models."""
    siblings = [name for name in SCENARIOS if name not in selected and
                ((output / (name + ".csv")).exists() or (output / (name + "_events.jsonl")).exists())]
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
        for suffix, section in ((".csv", "expected_csvs"), ("_events.jsonl", "expected_event_logs")):
            filename = name + suffix
            if not (output / filename).exists():
                raise ValueError("Existing sibling dataset is missing its CSV or event log; regenerate --scenario all")
            expected = metadata.get(section, {}).get(filename, {}).get("sha256")
            actual = hashlib.sha256((output / filename).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("Existing sibling file does not match its recorded hash; use a new --output-dir or regenerate --scenario all")


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
    event_logs = {}
    snapshot_audits = {}
    for name in SCENARIOS:
        all_rows[name], transfer_audits[name], event_logs[name], snapshot_audits[name] = generate_rows(name, seed, days, stations, zone)
        validate_rows(all_rows[name], days, stations, zone, snapshot_audits[name])
        payloads[name + ".csv"] = csv_bytes(all_rows[name])
        payloads[name + "_events.jsonl"] = jsonl_bytes(event_logs[name])
    baseline_rows = BASELINE_DAYS * len(HOURS) * len(stations)
    if all_rows["normal"][:baseline_rows] != all_rows["disruption"][:baseline_rows]:
        raise ValueError("Normal/disruption baselines differ")
    monitoring_start = utc(datetime.combine(days[BASELINE_DAYS], time(HOURS[0]), tzinfo=zone))
    histories = {
        name: [event for event in event_logs[name] if utc(datetime.fromisoformat(event["timestamp"])) < monitoring_start]
        for name in ("normal", "disruption")
    }
    if histories["normal"] != histories["disruption"]:
        raise ValueError("Normal/disruption pre-monitoring event histories differ")
    for name in SCENARIOS:
        for suffix in (".csv", "_events.jsonl"):
            path = output / (name + suffix)
            if name not in selected and path.exists() and path.read_bytes() != payloads[name + suffix]:
                raise ValueError("Existing sibling file differs from the current generator output; use a new --output-dir or regenerate --scenario all")
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
            "initial_bike_ids": "B001-B015 at S01, B016-B030 at S02, continuing in blocks of 15 through B286-B300 at S20",
            "cross_date_continuity": "Individual bikes persist and rides continue across nights, weekends and service-date boundaries",
            "outside_observation_window": "Night/weekend rides are simulated continuously; CSV observations remain weekdays07:00-21:00",
            "transfer": "A departure removes one unique bike from its station into transit; only its later arrival returns it to a dock",
            "duration_seconds": "max(300, ceil(straight-line_km * 1.3 / 12km_per_hour * 3600 + uniform_integer(180,480))); explicit synthetic detour/speed/dwell assumptions, no real routes or hills",
            "distance_pair_weight": "1 / (1 + straight-line distance in km), at most 1",
            "weekday_07_to_10": "Each interval: 16..22 residential-to-academic plans plus10background; disruption monitoring uses48..54directed instead",
            "weekday_10_to_14": "Each interval: 6..10academic/mixed/transport exchange plans plus6background",
            "weekday_14_to_17": "Each interval: 6..10academic-to-residential plans plus6background",
            "weekday_17_to_21": "Each interval: 9..13academic/mixed/transport-to-residential plans plus10background",
            "weekday_21_to_24": "Each interval: 2..5return plans plus2background",
            "every_day_00_to_06": "Each interval: 0..2background plans",
            "weekday_06_to_07": "4..8residential-to-academic plans plus2background",
            "weekend_06_to_10_and_21_to_24": "Each interval: 1..3background plans",
            "weekend_10_to_21": "Each interval: 2..5outings(to17:00) or returns(after17:00) plus4background; no class surge",
            "departure_timing": "Uniform integer seconds1..3599 within each absolute UTC hour; local time selects the flow profile",
            "capacity_handling": "Empty sources skip synthetic plans; full destinations at arrival reroute to the nearest currently free permissible station with an additional positive ride duration, rechecked on arrival",
            "event_ties": "Arrivals and reroutes before departures; snapshot after all events at its timestamp",
            "edge_fixtures": "S20 excluded from every baseline route and reroute; first monitoring day00:00-12:00 random departures paused, prior rides must settle, then explicit positive-duration rider schedules target09/10/11fixtures; no queue clearing, teleportation or operator dispatch",
            "sensors": "All automatic readings accurate, complete and on the scheduled hour",
        },
        "transfer_audit": transfer_audits,
        "transfer_audit_scope": "Synthetic plans and actual departures/successful_transfers, arrivals and reroutes by departure phase/flow; edge rider schedules explicitly included; no true customer attempts or observed trips. Arrivals after the final export time remain pending.",
        "snapshot_audit": snapshot_audits,
        "expected_csvs": {
            name: {"rows": len(days) * len(HOURS) * len(stations), "baseline_rows": baseline_rows,
                   "monitoring_rows": (len(days) - BASELINE_DAYS) * len(HOURS) * len(stations),
                   "complete_snapshots": len(days) * len(HOURS), "coverage": 1.0,
                   "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in payloads.items() if name.endswith(".csv")
        },
        "expected_event_logs": {
            name + "_events.jsonl": {"events": len(events), "sha256": hashlib.sha256(payloads[name + "_events.jsonl"]).hexdigest()}
            for name, events in event_logs.items()
        },
        "final_in_transit": {name: audit[-1]["in_transit"] for name, audit in snapshot_audits.items()},
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
            "No operator dispatch or nightly rebalancing is simulated; night/weekend trips and travel times are hypothetical.",
            "Docked bikes alone need not total300 or imply50%network dock occupancy; docked plus in-transit always equals300.",
            "Rides pending at the final21:00 observation are censored, not forced to finish; their latest arrival_due is retained in the event logs.",
            "Normal means regular simulation, not guaranteed absence of inventory warnings or statistical signals.",
            "Disruption is an operational redistribution, not equipment failure; detection must be evaluated independently.",
            "No SPC implementation or baseline suitability approval is supplied by this generator.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    # All validation completes before writes; writing is confined to named outputs.
    for name in selected:
        (output / (name + ".csv")).write_bytes(payloads[name + ".csv"])
        (output / (name + "_events.jsonl")).write_bytes(payloads[name + "_events.jsonl"])
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
        print("%s: %s rows, %s complete snapshots, docked + in-transit = %s bikes" %
              (name + ".csv", SERVICE_DAYS * len(HOURS) * 20, SERVICE_DAYS * len(HOURS), FLEET))
    print("Shared files: stations.json, settings.json, generation_metadata.json")
    print("Output: %s" % args.output_dir.resolve())
    print("SYNTHETIC automatic readings; no missing rows or sensor failures. SPC analysis is not implemented here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
