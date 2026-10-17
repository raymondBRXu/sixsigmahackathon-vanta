#!/usr/bin/env python3
"""Generate DockWatch's two verified, fictional automatic-snapshot datasets.

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


SCENARIOS = ("normal", "disruption")
SCHEMA_VERSION = 1
GENERATOR_VERSION = 5
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


# Ten illustrative rider corridors connect the existing 20 anchors. These are
# intentionally designed teaching itineraries, not measured origin/destination data.
CORRIDORS = list(zip([0, 1, 2, 3, 4, 13, 16, 17, 18, 19], [5, 6, 7, 8, 9, 11, 10, 12, 14, 15]))
HOME_PROFILE = [17, 14, 11, 10, 11, 12, 11, 12, 13, 14, 15, 16, 17, 17, 17]
GENERATED_NAMES = [name + suffix for name in ("normal", "disruption", "edge_cases")
                   for suffix in (".csv", "_events.jsonl")] + [
    "stations.json", "settings.json", "generation_metadata.json", "validation.json", "demo_guide.md", "README.md"]


QC_SNAPSHOT_SHA256 = "e5e1b4824b41450ed10963f91ab27061ee774afe1682abd29841bbcec47b6384"


def load_qc():
    """Use app/qc.py, or its verified byte-identical data-only publication snapshot."""
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "app" / "qc.py"
    if not path.is_file():
        path = Path(__file__).with_name("_qc_snapshot.py")
        if not path.is_file():
            raise ValueError("Validation requires app/qc.py or the bundled data/_qc_snapshot.py; keep the complete data folder")
        if hashlib.sha256(path.read_bytes()).hexdigest() != QC_SNAPSHOT_SHA256:
            raise ValueError("The bundled app/qc.py snapshot failed its SHA256 integrity check; restore the published _qc_snapshot.py")
    spec = importlib.util.spec_from_file_location("dockwatch_generator_qc", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def points(values, days, hour):
    zone = ZoneInfo(TIMEZONE)
    return [{"bikes": value, "date": day.isoformat(),
             "timestamp": datetime.combine(day, time(hour), tzinfo=zone).isoformat()}
            for value, day in zip(values, days)]


def readings_for_plan(plan):
    home, pending, source = plan
    return (home - (pending if source == 0 else 0),
            30 - home - (pending if source == 1 else 0))


def design_normal_profiles(seed, days, qc):
    """Select finite synthetic itineraries with the explicitly requested behavior.

    This is disclosed fixture construction, not a claim that an unconstrained
    real system has zero false alarms. Night/weekend riding evolves forward from
    the previous actual state. A future morning inventory is never its target.
    """
    zone = ZoneInfo(TIMEZONE)
    start = utc(datetime.combine(days[0], time(7), tzinfo=zone))
    end = utc(datetime.combine(days[-1], time(21), tzinfo=zone))
    day_indices = {day: index for index, day in enumerate(days)}
    profiles, attempts = [], []
    for pair in range(len(CORRIDORS)):
        for attempt in range(10000):
            rng = random.Random(seed * 1000003 + pair * 137 + attempt * 7919)
            offsets = rng.choices([-2, -1, 0, 1, 2], weights=[1, 2, 3, 2, 1], k=SERVICE_DAYS)
            candidate = {}
            stamp, previous = start, (15, 0, 0)
            physically_valid = True
            while stamp <= end:
                local = stamp.astimezone(zone)
                day_index = day_indices.get(local.date())
                position = local.hour - 7
                if stamp == start:
                    plan = (15, 0, 0)
                elif day_index is not None and 8 <= local.hour <= 21:
                    base = HOME_PROFILE[position]
                    if pair >= 8:
                        base = 15 + round((base - 15) * 0.4)
                    home = base + offsets[day_index] + rng.choice([-1, 0, 0, 0, 1])
                    pending = int(rng.random() < (0.7 if position in (1, 2, 10, 11) else 0.35))
                    source = 0 if position < 8 else 1
                    plan = (home, pending, source)
                else:
                    # The preceding pending rider has really arrived before the
                    # next off-hours departure. Carry this net movement forward.
                    settled_home = previous[0] + previous[1] * (1 if previous[2] else -1)
                    night_rng = random.Random(seed * 1000003 + pair * 137 + attempt * 7919
                                              + int(stamp.timestamp()) // 3600 * 193)
                    weekend_day = local.weekday() >= 5 and 9 <= local.hour <= 20
                    # One sparse independent rider increment, never a pull
                    # toward 15 or a preselected tomorrow07 stock.
                    chance = 0.35 if weekend_day else 0.12
                    step = night_rng.choice((-1, 1)) if night_rng.random() < chance else 0
                    home = settled_home + step
                    pending_chance = 0.14 if weekend_day or local.hour in (6, 7, 22) else 0.04
                    pending = int(night_rng.random() < pending_chance)
                    source = night_rng.randrange(2)
                    plan = (home, pending, source)
                values = readings_for_plan(plan)
                if not all(6 <= value <= 24 for value in values):
                    physically_valid = False
                    break  # Reject this entire fixture, never clamp its stocks.
                candidate[stamp] = plan
                previous = plan
                stamp += timedelta(hours=1)
            if not physically_valid:
                continue
            accepted = True
            for hour in HOURS:
                for side in (0, 1):
                    values = [readings_for_plan(candidate[utc(datetime.combine(day, time(hour), tzinfo=zone))])[side]
                              for day in days]
                    baseline = points(values[:BASELINE_DAYS], days[:BASELINE_DAYS], hour)
                    limits = qc.i_chart_limits(values[:BASELINE_DAYS])
                    monitoring = points(values[BASELINE_DAYS:], days[BASELINE_DAYS:], hour)
                    if (not limits["sigma"] or qc.detect_rules(monitoring, limits)
                            or qc.baseline_diagnostics(baseline, CAPACITY, limits)["warnings"]):
                        accepted = False
                        break
                if not accepted:
                    break
            if accepted:
                profiles.append(candidate)
                attempts.append(attempt + 1)
                break
        else:
            raise ValueError("Could not construct a verified normal fixture for this seed; no files were written")
    return profiles, attempts

def snapshot_plans(profiles, days, scenario, seed, zone):
    plans = {}
    for day_index, day in enumerate(days):
        for position, hour in enumerate(HOURS):
            stamp = utc(datetime.combine(day, time(hour), tzinfo=zone))
            plan = [profiles[pair][stamp] for pair in range(10)]
            monitor = day_index - BASELINE_DAYS
            # The first monitoring 07:00 snapshot and all latent rides entering it
            # are shared; disruption begins with subsequent rider departures.
            if scenario == "disruption" and monitor >= 0 and hour >= 8:
                rng = random.Random(seed * 1000003 + monitor * 271 + hour * 8191)
                if hour in (8, 9, 10, 17, 18, 19):
                    # Vary which places and severities appear: not every station
                    # is red, and ordinary readings remain present throughout.
                    for pair in rng.sample(range(8), rng.randint(2, 4)):
                        low = rng.choice([0, 1, 3, 5, 6, 8])
                        home = low if hour < 12 else 30 - low
                        plan[pair] = (home, 0, 0 if hour < 12 else 1)
                if monitor == 0 and hour == 9:
                    plan[:5] = [(0, 0, 0), (3, 0, 0), (6, 0, 0), (5, 0, 0), (15, 0, 0)]
                # Statistics-only shift: safe inventory, eight points on the
                # same side of the frozen center, completed on monitoring day 8.
                if monitor < 8 and hour == 12:
                    plan[5] = (16 + monitor % 2, 0, 0)
                # Six distinct increasing points, completed on monitoring day 6.
                if monitor < 6 and hour == 14:
                    plan[6] = (10 + monitor, 0, 0)
            plans[utc(datetime.combine(day, time(hour), tzinfo=zone))] = plan
    return plans


def all_hour_plans(export_plans, profiles):
    """Use independently forward-simulated off-hours rider schedules unchanged."""
    result = {stamp: [profiles[pair][stamp] for pair in range(10)] for stamp in profiles[0]}
    result.update(export_plans)
    return result


def schedule_interval(simulator, plan, deadline, rng, phase):
    """Realize a planned rider itinerary; no inventory assignment or clipping.

    All earlier rides arrive normally in the first three minutes. Commuters then
    ride between corridor endpoints; a subset depart late and are still riding
    at the next hourly snapshot. Previously pending rides are never cancelled.
    """
    beginning = simulator.now
    simulator.advance_to(beginning + timedelta(minutes=4))
    if simulator.queue or simulator.in_transit:
        raise ValueError("Previous journeys did not finish; refusing to reset or clear them")
    local = deadline.astimezone(simulator.zone)
    if local.weekday() >= 5:
        flow = "synthetic_weekend_rider"
    elif 7 <= local.hour <= 10:
        flow = "synthetic_morning_commute"
    elif 16 <= local.hour <= 21:
        flow = "synthetic_evening_return"
    elif 7 < local.hour < 21:
        flow = "synthetic_daytime_rider"
    else:
        flow = "synthetic_overnight_rider"
    for pair, (first, second) in enumerate(CORRIDORS):
        home, pending, source = plan[pair]
        if not (0 <= home <= CAPACITY and pending in (0, 1)):
            raise ValueError("Invalid planned itinerary")
        counts = (len(simulator.docked[first]), len(simulator.docked[second]))
        if sum(counts) != 30:
            raise ValueError("A corridor lost bike ownership; refusing to repair inventories")
        difference = home - counts[0]
        origin, destination = (second, first) if difference > 0 else (first, second)
        transfer_finish = beginning
        for number in range(abs(difference)):
            depart = beginning + timedelta(seconds=300 + rng.randint(0, 45))
            duration = simulator.duration(origin, destination, rng)
            transfer_finish = max(transfer_finish, depart + timedelta(seconds=duration))
            simulator.schedule_departure(depart, simulator.ids[origin], simulator.ids[destination],
                                         flow, duration, phase)
        if pending:
            origin, destination = (first, second) if source == 0 else (second, first)
            duration = simulator.duration(origin, destination, rng)
            tail = rng.randint(120, 180)
            depart = deadline - timedelta(seconds=duration - tail)
            if depart <= transfer_finish:
                raise ValueError("Not enough time for positive-duration rides before this snapshot")
            simulator.schedule_departure(depart, simulator.ids[origin], simulator.ids[destination],
                                         flow + "_still_riding", duration, phase)
    simulator.advance_to(deadline)
    expected = {}
    for pair, (first, second) in enumerate(CORRIDORS):
        first_count, second_count = readings_for_plan(plan[pair])
        expected[simulator.ids[first]], expected[simulator.ids[second]] = first_count, second_count
    if simulator.snapshot() != expected:
        raise ValueError("Actual ride events failed to realize the itinerary; no CSV was written")


def generate_rows(scenario, seed, days, stations, zone, profiles=None):
    qc = load_qc()
    if profiles is None:
        profiles, _ = design_normal_profiles(seed, days, qc)
    export_plans = snapshot_plans(profiles, days, scenario, seed, zone)
    plans = all_hour_plans(export_plans, profiles)
    timestamps = sorted(plans)
    simulator = Simulator(stations, timestamps[0], seed)
    monitoring_start = utc(datetime.combine(days[BASELINE_DAYS], time(7), tzinfo=zone))
    rows, snapshot_audit = [], []
    for index, stamp in enumerate(timestamps):
        if index:
            rng = random.Random(seed * 1000003 + int(stamp.timestamp()) // 3600 * 9176)
            phase = "monitoring" if simulator.now >= monitoring_start else "baseline"
            schedule_interval(simulator, plans[stamp], stamp, rng, phase)
        if stamp in export_plans:
            timestamp = simulator.iso(stamp)
            counts = simulator.snapshot()
            rows.extend((timestamp, station_id, counts[station_id]) for station_id in simulator.ids)
            snapshot_audit.append({"timestamp": timestamp, "docked": sum(counts.values()),
                                   "in_transit": len(simulator.in_transit)})
    return rows, simulator.transfer_audit, simulator.events, snapshot_audit


def validate_rows(rows, days, stations, zone, snapshot_audit):
    expected_rows = len(days) * len(HOURS) * len(stations)
    if len(rows) != expected_rows or len(snapshot_audit) != len(days) * len(HOURS):
        raise ValueError("Wrong number of scheduled readings")
    offset = 0
    for day in days:
        for hour in HOURS:
            timestamp = datetime.combine(day, time(hour), tzinfo=zone).isoformat()
            snapshot = rows[offset:offset + 20]
            audit = snapshot_audit[offset // 20]
            offset += 20
            if [(r[0], r[1]) for r in snapshot] != [(timestamp, s["station_id"]) for s in stations]:
                raise ValueError("Incorrect timestamp, order, duplicate or missing station")
            counts = [r[2] for r in snapshot]
            if any(type(v) is not int or not 0 <= v <= CAPACITY for v in counts):
                raise ValueError("Inventory outside integer capacity bounds")
            if audit != {"timestamp": timestamp, "docked": sum(counts), "in_transit": FLEET - sum(counts)}:
                raise ValueError("Snapshot and fleet audit disagree")


def replay_and_validate(rows, events, snapshot_audit):
    """Independent event ledger audits every event and every exported snapshot."""
    docked = {"S%02d" % (i + 1): {"B%03d" % (i * 15 + j + 1) for j in range(15)} for i in range(20)}
    fleet = set().union(*docked.values())
    moving, trips = {}, set()
    position, previous, previous_priority = 0, None, None
    for offset in range(0, len(rows), 20):
        stamp = utc(datetime.fromisoformat(rows[offset][0]))
        while position < len(events) and utc(datetime.fromisoformat(events[position]["timestamp"])) <= stamp:
            event = events[position]
            position += 1
            moment = utc(datetime.fromisoformat(event["timestamp"]))
            kind, bike, station = event["event"], event["bike_id"], event["station_id"]
            priority = 1 if kind == "departure" else 0
            if previous is not None and (moment < previous or moment == previous and priority < previous_priority):
                raise ValueError("Event log is not chronological")
            previous, previous_priority = moment, priority
            if kind == "departure":
                due = utc(datetime.fromisoformat(event["arrival_due"]))
                if bike not in docked[station] or bike in moving or event["trip_id"] in trips or due <= moment:
                    raise ValueError("Invalid individual-bike departure")
                docked[station].remove(bike)
                trips.add(event["trip_id"])
                moving[bike] = (event["trip_id"], event["destination_id"], due)
            elif kind in ("arrival", "reroute"):
                if moving.get(bike) != (event["trip_id"], station, moment):
                    raise ValueError("Arrival does not match a pending ride")
                if kind == "arrival":
                    if len(docked[station]) >= CAPACITY:
                        raise ValueError("An arrival exceeded capacity")
                    docked[station].add(bike)
                    del moving[bike]
                else:
                    due = utc(datetime.fromisoformat(event["arrival_due"]))
                    if len(docked[station]) != CAPACITY or due <= moment:
                        raise ValueError("Invalid reroute")
                    moving[bike] = (event["trip_id"], event["destination_id"], due)
            else:
                raise ValueError("Unrecognized event type")
            owners = [bike for bikes in docked.values() for bike in bikes] + list(moving)
            if len(owners) != FLEET or set(owners) != fleet or any(len(v) > CAPACITY for v in docked.values()):
                raise ValueError("Individual-bike ownership or fleet conservation failed")
        if any(journey[2] <= stamp for journey in moving.values()):
            raise ValueError("An overdue ride was silently kept in transit")
        expected = {row[1]: row[2] for row in rows[offset:offset + 20]}
        if expected != {sid: len(bikes) for sid, bikes in docked.items()}:
            raise ValueError("Independent event replay disagrees with CSV")
        if snapshot_audit[offset // 20]["in_transit"] != len(moving):
            raise ValueError("Independent in-transit replay disagrees with audit")
    if position != len(events):
        raise ValueError("Event log extends beyond final snapshot")
    return {"events_checked": position, "snapshots_checked": len(rows) // 20,
            "individual_bikes": len(fleet), "conservation_at_every_event": True,
            "positive_duration_rides": True, "snapshots_match_event_replay": True,
            "pending_final_rides": len(moving)}


def assess_dataset(rows, days, stations, settings, qc):
    validated = qc.validate_rows([dict(zip(("timestamp", "station_id", "bikes"), row)) for row in rows], stations, settings)
    index = {(row["station_id"], row["timestamp"].hour, row["timestamp"].date().isoformat()): row["bikes"] for row in validated}
    strata, candidates, baseline_events, warnings = [], [], 0, 0
    for station in stations:
        for hour in HOURS:
            values = [index[(station["station_id"], hour, day.isoformat())] for day in days]
            limits = qc.i_chart_limits(values[:BASELINE_DAYS])
            diagnostics = qc.baseline_diagnostics(points(values[:BASELINE_DAYS], days[:BASELINE_DAYS], hour), CAPACITY, limits)
            events = qc.detect_rules(points(values[BASELINE_DAYS:], days[BASELINE_DAYS:], hour), limits)
            eligible = limits["n"] >= 20 and limits["pairs"] >= 15 and limits["sigma"] is not None and limits["sigma"] > 0
            strata.append({"station_id": station["station_id"], "hour": hour, "eligible": eligible,
                           "baseline_n": limits["n"], "adjacent_pairs": limits["pairs"],
                           "center": limits["center"], "lcl": limits["lcl"], "ucl": limits["ucl"],
                           "lag_one_correlation": diagnostics["lag_one_correlation"],
                           "diagnostic_warnings": diagnostics["warnings"], "candidate_events": len(events)})
            baseline_events += len(diagnostics["baseline_events"])
            warnings += len(diagnostics["warnings"])
            candidates.extend(dict(event, station_id=station["station_id"], hour=hour,
                                   status="exploratory", operational_warning=not 6 <= event["bikes"] <= 24)
                              for event in events)
    counts = [r[2] for r in rows]
    return {"rows": len(rows), "snapshots": len(rows) // 20, "coverage": 1.0,
            "min_bikes": min(counts), "max_bikes": max(counts),
            "operational_warning_rows": sum(not 6 <= v <= 24 for v in counts),
            "eligible_strata": sum(s["eligible"] for s in strata), "total_strata": len(strata),
            "baseline_rule_events": baseline_events, "baseline_diagnostic_warnings": warnings,
            "candidate_events": len(candidates), "candidate_rule_counts": {
                rule: sum(e["rule"] == rule for e in candidates)
                for rule in ("beyond_limit", "eight_same_side", "six_trend")},
            "statistics_only_events": sum(not e["operational_warning"] for e in candidates),
            "strata": strata, "events": candidates}


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


def make_demo_guide(assessments, days):
    report = assessments["disruption"]
    lines = ["# DockWatch v5 — verified synthetic demonstration", "",
             "Generated from actual CSV checks using app/qc.py. These are designed teaching fixtures, not measured demand.",
             "No baseline is automatically approved. Unreviewed patterns remain exploratory.", "",
             "## 1. Normal scenario", "",
             "Choose Normal on any exported date/hour. Every reading is in 6–24 inclusive; no operational warning.",
             "All 300 station/hour strata have 25 nonconstant baseline observations and zero baseline diagnostic warnings.",
             "All 4,500 monitoring readings produce zero point/8-side/6-trend candidate events.",
             "Before the reference period ends, baseline collection/review messages are expected workflow states.", "",
             "## 2. Operational contrast", "",
             "Choose Disruption, %s, 09:00 America/New_York." % days[BASELINE_DAYS].isoformat(), "",
             "| Station | Bikes | Expected behavior |", "|---|---:|---|",
             "| S01 | 0 | Empty, P1, consider adding 15 |", "| S06 | 30 | Full, P1, consider removing 15 |",
             "| S02 | 3 | Low, P2, consider adding 12 |", "| S07 | 27 | High, P2, consider removing 12 |",
             "| S03 | 6 | No low inventory warning at the exact threshold |",
             "| S08 | 24 | No high inventory warning at the exact threshold |",
             "| S04 | 5 | Low, P2 |", "| S09 | 25 | High, P2 |", "",
             "The map combines urgent, low/high and ordinary inventory states. Recommendations are reviewable quantities, not arranged dispatches.", "",
             "## 3. Cross-date statistical rules", "",
             "| Rule | Station | Hour | First trigger | Window | Bikes | Operational warning? |",
             "|---|---|---:|---|---|---:|---|"]
    expected = [("beyond_limit", "S01", 9), ("eight_same_side", "S14", 12), ("six_trend", "S17", 14)]
    for rule, sid, hour in expected:
        events = [event for event in report["events"] if event["rule"] == rule and event["station_id"] == sid and event["hour"] == hour]
        if not events:
            raise ValueError("Planned demonstration rule did not actually trigger: %s %s" % (rule, sid))
        event = min(events, key=lambda e: e["timestamp"])
        lines.append("| %s | %s | %02d:00 | %s | %s → %s | %s | %s |" %
                     (rule, sid, hour, event["date"], event["window_start"], event["window_end"], event["bikes"],
                      "Yes" if event["operational_warning"] else "No — company review only"))
    lines += ["", "Select the station and hour in Analysis. Step to the previous service date to see that an incomplete window is not yet flagged.",
              "A later event can overlap an earlier run. Do not call repeated sliding windows separate incidents.", "",
              "## 4. Physical continuity", "",
              "Docked bikes plus bikes still riding always total 300. Inventory persists through nights and weekends.",
              "Audit-only event logs identify every bike departure/arrival and must never be detector inputs.",
              "The final snapshot leaves ongoing rides in transit; they are not forced to finish.", ""]
    return "\n".join(lines).encode("utf-8")


def write_outputs(output, payloads):
    """Validate first; stage files; archive replaced generated outputs, never source."""
    import shutil
    import tempfile
    output = output.resolve()
    if output.exists():
        unknown_csvs = [path.name for path in output.glob("*.csv") if path.name not in GENERATED_NAMES]
        if unknown_csvs:
            raise ValueError("Output has unrelated CSVs (%s); choose a fresh --output-dir" % ", ".join(unknown_csvs))
    output.mkdir(parents=True, exist_ok=True)
    backup = None
    existing = [output / name for name in GENERATED_NAMES if (output / name).is_file()]
    if existing:
        backup_root = output.parent / ".dockwatch-data-backups"
        backup_root.mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=output.name + "-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-", dir=backup_root))
        for path in existing:
            shutil.copy2(path, backup / path.name)
    # Staging completes before replacement; previous files remain recoverable.
    with tempfile.TemporaryDirectory(prefix=".dockwatch-stage-", dir=output.parent) as staging:
        staged = Path(staging)
        for name, payload in payloads.items():
            (staged / name).write_bytes(payload)
        for name in payloads:
            (staged / name).replace(output / name)
        for name in ("edge_cases.csv", "edge_cases_events.jsonl"):
            path = output / name
            if path.exists():
                path.unlink()  # Its complete original is already in the backup.
    return backup


def generate(output, scenario="all", seed=5300, start=date(2026, 8, 24)):
    if scenario != "all":
        raise ValueError("Version 5 generates the matched pair together; use --scenario all")
    days = service_calendar(start)
    try:
        zone = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        raise ValueError("America/New_York timezone data is unavailable") from None
    stations, qc = station_configuration(), load_qc()
    profiles, selection_attempts = design_normal_profiles(seed, days, qc)
    settings = {"schema_version": SCHEMA_VERSION, "timezone": TIMEZONE,
                "service_dates": [day.isoformat() for day in days],
                "baseline_dates": [day.isoformat() for day in days[:BASELINE_DAYS]],
                "monitoring_dates": [day.isoformat() for day in days[BASELINE_DAYS:]],
                "hours": HOURS, "station_ids": [station["station_id"] for station in stations],
                "collection_mode": "automatic_complete_hourly_snapshots"}
    payloads, rows_by_scenario, events_by_scenario, snapshot_audits, transfer_audits, assessments, replay = {}, {}, {}, {}, {}, {}, {}
    for name in SCENARIOS:
        rows, audit, events, snapshots = generate_rows(name, seed, days, stations, zone, profiles)
        validate_rows(rows, days, stations, zone, snapshots)
        replay[name] = replay_and_validate(rows, events, snapshots)
        assessments[name] = assess_dataset(rows, days, stations, settings, qc)
        rows_by_scenario[name], events_by_scenario[name] = rows, events
        transfer_audits[name], snapshot_audits[name] = audit, snapshots
        payloads[name + ".csv"], payloads[name + "_events.jsonl"] = csv_bytes(rows), jsonl_bytes(events)
    baseline_rows = BASELINE_DAYS * len(HOURS) * len(stations)
    if rows_by_scenario["normal"][:baseline_rows] != rows_by_scenario["disruption"][:baseline_rows]:
        raise ValueError("Shared baseline rows differ")
    boundary = utc(datetime.combine(days[BASELINE_DAYS], time(7), tzinfo=zone))
    histories = {name: [event for event in events_by_scenario[name]
                        if utc(datetime.fromisoformat(event["timestamp"])) <= boundary] for name in SCENARIOS}
    if histories["normal"] != histories["disruption"]:
        raise ValueError("Pre-change rider history or pending rides differ")
    normal, disruption = assessments["normal"], assessments["disruption"]
    if (normal["operational_warning_rows"] or normal["candidate_events"] or normal["baseline_rule_events"]
            or normal["baseline_diagnostic_warnings"] or normal["eligible_strata"] != 300):
        raise ValueError("Normal scenario failed its zero-warning contract")
    if not all(disruption["candidate_rule_counts"].values()) or not disruption["statistics_only_events"]:
        raise ValueError("Disruption failed to demonstrate all three rules and a statistics-only event")
    if not {0, 3, 5, 6, 15, 24, 25, 27, 30}.issubset({row[2] for row in rows_by_scenario["disruption"]}):
        raise ValueError("Required operational boundary examples are missing")
    fixture_stamp = datetime.combine(days[BASELINE_DAYS], time(9), tzinfo=zone).isoformat()
    fixture = {row[1]: row[2] for row in rows_by_scenario["disruption"] if row[0] == fixture_stamp}
    expected_fixture = {"S01": 0, "S06": 30, "S02": 3, "S07": 27, "S03": 6, "S08": 24,
                        "S04": 5, "S09": 25, "S05": 15, "S10": 15}
    if any(fixture.get(sid) != value for sid, value in expected_fixture.items()):
        raise ValueError("Exact first-monitoring09:00 operational fixture failed")
    validation = {"generator_version": GENERATOR_VERSION, "status": "passed", "detector": "app/qc.py",
                  "review_automatically_approved": False, "shared_baseline_rows": baseline_rows,
                  "shared_prechange_events_and_pending_rides": True, "scenarios": assessments, "event_replay": replay,
                  "scope": "Finite designed synthetic fixture verification, not a real-process stability or independence certification"}
    metadata = {
        "synthetic": True, "not_detector_input": True,
        "configuration": {"generator_version": GENERATOR_VERSION, "seed": seed, "start_date": start.isoformat(),
                          "timezone": TIMEZONE, "hours": HOURS,
                          "stations_sha256": hashlib.sha256(json_bytes(stations)).hexdigest()},
        "provenance": "Entirely designed synthetic rider itineraries at real geographic landmark anchors; no observed customer demand or sensor records.",
        "calendar_assumption": "Forty fictional comparable weekdays, including holidays; not a real Cornell operating calendar.",
        "model": {
            "capacity_per_station": CAPACITY, "total_bikes": FLEET, "total_positions": CAPACITY * 20,
            "initial_allocation": "15 bikes per station at the first 07:00 only; no later reset, operator dispatch or nighttime rebalancing",
            "initial_bike_ids": "B001-B015 at S01, then successive blocks of fifteen through B286-B300 at S20",
            "corridors": [[stations[a]["station_id"], stations[b]["station_id"]] for a, b in CORRIDORS],
            "corridor_limitation": "Ten independent illustrative rider corridors; deliberately restricted OD patterns, not citywide routing or measured demand",
            "duration_seconds": "max(300, ceil(straight-line_km * 1.3 / 12 * 3600 + uniform_integer(180,480)))",
            "itinerary_construction": "Seeded finite hourly rider schedules, accepted using the unchanged app detector; actual individual departures and arrivals realize every snapshot, never CSV clipping or stock assignment",
            "normal_profile": "Main campus home-side designed full-stock profile08:00–21:00 (07:00 entry ignored; inherited from overnight rides) before late departures: " + str(HOME_PROFILE) + "; seeded day offsets and hourly jitter; no-alert fixture selection is explicitly intentional",
            "late_rides": "Some riders depart before an hourly reading and return 120–180 seconds after it; they are included in the in-transit fleet at that reading",
            "off_hours": "Sparse independently seeded overnight/weekend riders evolve forward from actual settled stocks; 07:00 inherits their result, never a preselected morning target or stock15 reset",
            "shared_history": "Same rider events and pending trips through first monitoring day07:00; changed schedules begin afterward",
            "sensors": "Accurate complete automatic readings; no missingness or sensor-failure simulation",
            "capacity_handling": "No departure from an empty station; every arrival checks capacity and reroutes with added positive riding time if full",
        },
        "fixture_selection_attempts_by_corridor": selection_attempts,
        "station_sources": [{"station_id": a["station_id"], "source_url": a["source_url"], "coordinate_note": a["coordinate_note"]}
                            for a in json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))],
        "transfer_audit": transfer_audits, "snapshot_audit": snapshot_audits,
        "expected_csvs": {name + ".csv": {"rows": len(rows_by_scenario[name]), "baseline_rows": baseline_rows,
                          "monitoring_rows": 4500, "complete_snapshots": 600, "coverage": 1.0,
                          "sha256": hashlib.sha256(payloads[name + ".csv"]).hexdigest()} for name in SCENARIOS},
        "expected_event_logs": {name + "_events.jsonl": {"events": len(events_by_scenario[name]),
                               "sha256": hashlib.sha256(payloads[name + "_events.jsonl"]).hexdigest()} for name in SCENARIOS},
        "final_in_transit": {name: snapshot_audits[name][-1]["in_transit"] for name in SCENARIOS},
        "limitations": ["Finite intentionally constructed teaching examples; zero normal alerts is not a general probability claim.",
                        "No real demand, calibrated routing, hills, causal claims or dispatcher intervention is modeled.",
                        "CSV snapshots do not reveal attempted rentals, failed trips or exact downtime.",
                        "The generator validates using app/qc.py but does not implement a second detector or approve any baseline.",
                        "Pattern selection uses complete synthetic candidate schedules offline; application scoring remains causal and uses no future observations."]}
    payloads["stations.json"], payloads["settings.json"] = json_bytes(stations), json_bytes(settings)
    payloads["generation_metadata.json"], payloads["validation.json"] = json_bytes(metadata), json_bytes(validation)
    payloads["demo_guide.md"] = make_demo_guide(assessments, days)
    codebook = Path(__file__).with_name("README.v5.md")
    if not codebook.is_file():
        raise ValueError("Missing data/README.v5.md codebook template; no outputs written")
    payloads["README.md"] = codebook.read_bytes()
    backup = write_outputs(Path(output), payloads)
    if backup:
        print("Previous generated files backed up: %s" % backup)
    return SCENARIOS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all",), default="all", help="Generate both matched scenarios together (default)")
    parser.add_argument("--seed", type=int, default=5300, help="Reproducible integer seed; default: 5300")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 8, 24), help="First fictional weekday; default: 2026-08-24")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent, help="Output directory; default: this script's directory")
    args = parser.parse_args(argv)
    try:
        selected = generate(args.output_dir, args.scenario, args.seed, args.start_date)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    for name in selected:
        print("%s: 12000 rows, 600 complete snapshots, docked + in-transit = 300" % (name + ".csv"))
    print("PASS: normal has zero inventory warnings and zero candidate statistical events across all 300 station/hour charts.")
    print("PASS: disruption demonstrates empty/full, low/high, exact thresholds and all three statistical rules.")
    print("PASS: all snapshots match independent bike-event replay; shared baseline and pending trips verified.")
    if not (Path(__file__).resolve().parents[1] / "app" / "qc.py").is_file():
        print("Validation used data/_qc_snapshot.py, the byte-identical app/qc.py publication snapshot (SHA256 %s)." % QC_SNAPSHOT_SHA256)
    print("Output: %s" % args.output_dir.resolve())
    print("Read demo_guide.md for verified dates/stations; validation.json contains detailed checks.")
    print("SYNTHETIC TEACHING FIXTURES. Baseline suitability still requires review; no GitHub files were pushed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
