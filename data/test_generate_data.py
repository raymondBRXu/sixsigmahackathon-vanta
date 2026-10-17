"""Independent acceptance checks for the synthetic data, using only the stdlib."""

import csv
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


SCRIPT = Path(__file__).with_name("generate_data.py")
SCENARIOS = ("normal", "disruption", "edge_cases")
UTC = timezone.utc
LOCAL = ZoneInfo("America/New_York")


def instant(value):
    """Compare physical instants, including the two different DST 01:00 hours."""
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise AssertionError("Audit timestamps must include their UTC offset")
    return parsed.astimezone(UTC)


def read_events(path):
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay_events(case, events, snapshots=None, audit=None):
    """Independent bike ledger: uses only published events, never generator state.

    Every bike starts at its specified station. An unlogged reset or direct
    inventory adjustment therefore fails when the next CSV snapshot is compared.
    """
    station_ids = ["S%02d" % number for number in range(1, 21)]
    fleet = {"B%03d" % number for number in range(1, 301)}
    docked = {station: set() for station in station_ids}
    for number in range(1, 301):
        docked[station_ids[(number - 1) // 15]].add("B%03d" % number)
    moving = {}
    used_trips = set()
    previous_time = None
    previous_priority = None
    position = 0

    def apply(event):
        nonlocal previous_time, previous_priority
        moment = instant(event["timestamp"])
        kind = event["event"]
        case.assertIn(kind, {"departure", "arrival", "reroute"})
        priority = 1 if kind == "departure" else 0
        if previous_time is not None:
            case.assertGreaterEqual(moment, previous_time)
            if moment == previous_time:
                case.assertGreaterEqual(priority, previous_priority,
                                        "Arrivals/reroutes precede simultaneous departures")
        previous_time, previous_priority = moment, priority
        bike, trip, station = event["bike_id"], event["trip_id"], event["station_id"]
        case.assertIn(bike, fleet)
        case.assertIn(station, docked)
        case.assertTrue(trip)
        if kind == "departure":
            case.assertNotIn(trip, used_trips, "Trip IDs must identify unique journeys")
            used_trips.add(trip)
            case.assertIn(bike, docked[station], "Departure must own a bike at the origin")
            case.assertNotIn(bike, moving)
            destination, due = event["destination_id"], instant(event["arrival_due"])
            case.assertIn(destination, docked)
            case.assertNotEqual(destination, station)
            case.assertGreater(due, moment, "A ride cannot arrive instantaneously")
            case.assertTrue(event["flow"])
            docked[station].remove(bike)
            moving[bike] = {"trip": trip, "destination": destination, "due": due}
        else:
            case.assertIn(bike, moving, "Only an in-transit bike may arrive/reroute")
            journey = moving[bike]
            case.assertEqual(trip, journey["trip"])
            case.assertEqual(station, journey["destination"])
            case.assertEqual(moment, journey["due"], "Visit occurs at the latest scheduled due time")
            if kind == "arrival":
                case.assertLess(len(docked[station]), 30, "A full station cannot accept a bike")
                docked[station].add(bike)
                del moving[bike]
            else:
                case.assertEqual(len(docked[station]), 30, "Only an actually full destination triggers rerouting")
                destination, due = event["destination_id"], instant(event["arrival_due"])
                case.assertIn(destination, docked)
                case.assertNotEqual(destination, station)
                case.assertGreater(due, moment, "Rerouting adds positive riding time")
                moving[bike] = {"trip": trip, "destination": destination, "due": due}
        owners = [bike for bikes in docked.values() for bike in bikes] + list(moving)
        case.assertEqual(len(owners), 300)
        case.assertEqual(set(owners), fleet, "Every bike has exactly one owner/location")
        case.assertTrue(all(len(bikes) <= 30 for bikes in docked.values()))

    if snapshots is not None:
        case.assertEqual(set(snapshots), set(audit), "Every CSV snapshot needs one audit row")
        for moment, observed in sorted(snapshots.items()):
            while position < len(events) and instant(events[position]["timestamp"]) <= moment:
                apply(events[position])
                position += 1
            counts = {station: len(bikes) for station, bikes in docked.items()}
            case.assertTrue(all(journey["due"] > moment for journey in moving.values()),
                            "A snapshot cannot silently retain an overdue arrival")
            case.assertEqual(observed, counts, "CSV disagrees with independent event replay")
            case.assertEqual(audit[moment]["docked"], sum(counts.values()))
            case.assertEqual(audit[moment]["in_transit"], len(moving))
            case.assertEqual(sum(counts.values()) + len(moving), 300)
        case.assertEqual(position, len(events), "Log should end at the last exported snapshot")
    else:
        for event in events:
            apply(event)
    return {station: len(bikes) for station, bikes in docked.items()}, moving


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / "all"
        cls.run_generator("--output-dir", str(cls.output))
        cls.settings = json.loads((cls.output / "settings.json").read_text())
        cls.metadata = json.loads((cls.output / "generation_metadata.json").read_text())
        cls.rows = {}
        cls.events = {}
        for scenario in SCENARIOS:
            with (cls.output / (scenario + ".csv")).open(newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != ["timestamp", "station_id", "bikes"]:
                    raise AssertionError(reader.fieldnames)
                cls.rows[scenario] = list(reader)
            cls.events[scenario] = read_events(cls.output / (scenario + "_events.jsonl"))
        spec = importlib.util.spec_from_file_location("dockwatch_generator_under_test", SCRIPT)
        cls.generator = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.generator
        spec.loader.exec_module(cls.generator)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_generator(cls, *arguments, expect_success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True
        )
        if expect_success and result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        if not expect_success and result.returncode == 0:
            raise AssertionError("Expected a configuration error")
        return result

    def test_calendar_and_station_configuration(self):
        dates = self.settings["service_dates"]
        self.assertEqual((len(dates), dates[0], dates[-1]), (40, "2026-08-24", "2026-10-16"))
        self.assertTrue(all(datetime.fromisoformat(day).weekday() < 5 for day in dates))
        self.assertEqual(self.settings["baseline_dates"], dates[:25])
        self.assertEqual(self.settings["monitoring_dates"], dates[25:])
        self.assertEqual(self.settings["hours"], list(range(7, 22)))
        self.assertEqual(self.settings["timezone"], "America/New_York")
        stations = json.loads((self.output / "stations.json").read_text())
        self.assertEqual(len(stations), 20)
        self.assertEqual(len({station["station_id"] for station in stations}), 20)
        self.assertGreaterEqual(sum(station["area"].startswith("Cornell") for station in stations), 12)
        self.assertEqual(sum(station["type"] == "academic" for station in stations), 6)
        self.assertTrue(all(station["capacity"] == 30 for station in stations))
        for station in stations:
            self.assertEqual(set(station), {"station_id", "name", "area", "type", "latitude", "longitude", "capacity"})
            self.assertTrue(42.3 < station["latitude"] < 42.6)
            self.assertTrue(-76.6 < station["longitude"] < -76.3)

    def test_complete_bounded_snapshots_and_independent_fleet_replay(self):
        expected_ids = {"S%02d" % number for number in range(1, 21)}
        for scenario, rows in self.rows.items():
            with self.subTest(scenario=scenario):
                self.assertEqual(len(rows), 12000)
                snapshots = defaultdict(dict)
                previous = None
                for row in rows:
                    parsed = datetime.fromisoformat(row["timestamp"])
                    self.assertIsNotNone(parsed.utcoffset())
                    self.assertEqual(parsed.utcoffset().total_seconds(), -4 * 3600)
                    self.assertEqual((parsed.minute, parsed.second), (0, 0))
                    self.assertIn(parsed.date().isoformat(), self.settings["service_dates"])
                    self.assertIn(parsed.hour, range(7, 22))
                    count = int(row["bikes"])
                    self.assertEqual(str(count), row["bikes"])
                    self.assertTrue(0 <= count <= 30)
                    station = row["station_id"]
                    self.assertNotIn(station, snapshots[parsed.astimezone(UTC)])
                    snapshots[parsed.astimezone(UTC)][station] = count
                    key = (parsed.astimezone(UTC), station)
                    if previous is not None:
                        self.assertGreater(key, previous)
                    previous = key
                self.assertEqual(len(snapshots), 600)
                for moment, snapshot in snapshots.items():
                    self.assertEqual(set(snapshot), expected_ids)
                    self.assertLessEqual(sum(snapshot.values()), 300)
                self.assertEqual(set(snapshots[min(snapshots)].values()), {15})
                audit_rows = self.metadata["snapshot_audit"][scenario]
                audit = {instant(record["timestamp"]): record for record in audit_rows}
                self.assertEqual(len(audit), len(audit_rows), "No duplicate snapshot-audit timestamps")
                replay_events(self, self.events[scenario], snapshots, audit)
                if scenario != "edge_cases":
                    self.assertTrue(any(sum(values.values()) < 300 for values in snapshots.values()),
                                    "The default scenario must visibly include in-transit bikes")

    def test_night_and_weekend_rides_are_actual_events_not_resets(self):
        for scenario, events in self.events.items():
            with self.subTest(scenario=scenario):
                for kind in ("departure", "arrival"):
                    times = [instant(event["timestamp"]).astimezone(LOCAL)
                             for event in events if event["event"] == kind]
                    self.assertTrue(any(t.hour < 7 or t.hour >= 22 for t in times), kind)
                    self.assertTrue(any(t.weekday() >= 5 for t in times), kind)

    def test_shared_baseline_and_changed_monitoring(self):
        self.assertEqual(self.rows["normal"][:7500], self.rows["disruption"][:7500])
        self.assertNotEqual(self.rows["normal"][7500:], self.rows["disruption"][7500:])
        self.assertEqual(len(self.rows["normal"][7500:]), 4500)
        boundary = instant(self.settings["monitoring_dates"][0] + "T07:00:00-04:00")
        normal_history = [event for event in self.events["normal"] if instant(event["timestamp"]) < boundary]
        disruption_history = [event for event in self.events["disruption"] if instant(event["timestamp"]) < boundary]
        self.assertEqual(normal_history, disruption_history,
                         "Shared baseline includes latent bike ownership and ongoing trips")

    def test_edge_examples_and_constant_later_hour(self):
        values = {(row["timestamp"], row["station_id"]): int(row["bikes"]) for row in self.rows["edge_cases"]}
        day = self.settings["monitoring_dates"][0]
        balanced = [values[(day + "T09:00:00-04:00", "S%02d" % number)] for number in range(1, 21)]
        polarized = [values[(day + "T10:00:00-04:00", "S%02d" % number)] for number in range(1, 21)]
        self.assertEqual(balanced, [15] * 20)
        self.assertEqual(polarized, [0] * 10 + [30] * 10)
        thresholds = [values[(day + "T11:00:00-04:00", "S%02d" % number)] for number in range(1, 21)]
        self.assertEqual(thresholds, [6, 24, 5, 25, 0, 30] + [15] * 14)
        later_hour = [values[(day + "T12:00:00-04:00", "S20")] for day in self.settings["baseline_dates"]]
        self.assertEqual(later_hour, [15] * 25)
        self.assertTrue(all(int(row["bikes"]) == 15 for row in self.rows["edge_cases"][:7500]
                            if row["station_id"] == "S20"))
        boundary = instant(day + "T07:00:00-04:00")
        self.assertTrue(all(event["station_id"] != "S20" and event.get("destination_id") != "S20"
                            for event in self.events["edge_cases"]
                            if instant(event["timestamp"]) < boundary),
                        "The fixed S20 baseline must also be excluded from reroutes")
        edge_audit = {instant(record["timestamp"]): record for record in self.metadata["snapshot_audit"]["edge_cases"]}
        for hour in (9, 10, 11):
            record = edge_audit[instant(day + "T%02d:00:00-04:00" % hour)]
            self.assertEqual((record["docked"], record["in_transit"]), (300, 0))

    def test_separate_runs_match_all_byte_for_byte(self):
        output = Path(self.temp.name) / "separate"
        for scenario in reversed(SCENARIOS):
            self.run_generator("--scenario", scenario, "--output-dir", str(output))
        for filename in [name + suffix for name in SCENARIOS for suffix in (".csv", "_events.jsonl")] + ["stations.json", "settings.json", "generation_metadata.json"]:
            self.assertEqual((output / filename).read_bytes(), (self.output / filename).read_bytes(), filename)

    def test_repeated_run_is_identical(self):
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.run_generator("--output-dir", str(self.output))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_prevent_mixed_configuration(self):
        output = Path(self.temp.name) / "guard"
        self.run_generator("--scenario", "normal", "--output-dir", str(output))
        result = self.run_generator("--scenario", "disruption", "--seed", "10", "--output-dir", str(output), expect_success=False)
        self.assertIn("different configuration", result.stderr)
        self.assertFalse((output / "disruption.csv").exists())
        self.run_generator("--seed", "10", "--output-dir", str(output))
        self.assertNotEqual((output / "normal.csv").read_bytes(), (self.output / "normal.csv").read_bytes())

    def test_changed_station_anchors_cannot_mix_with_existing_csvs(self):
        output = Path(self.temp.name) / "anchor_guard"
        self.run_generator("--output-dir", str(output))
        altered = Path(self.temp.name) / "altered_generator"
        altered.mkdir()
        (altered / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
        anchors = json.loads(SCRIPT.with_name("station_anchors.json").read_text())
        anchors[0]["latitude"] += 0.001
        (altered / "station_anchors.json").write_text(json.dumps(anchors))
        result = subprocess.run(
            [sys.executable, str(altered / SCRIPT.name), "--scenario", "normal", "--output-dir", str(output)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different configuration", result.stderr)

    def test_invalid_start_date_is_clear_error(self):
        result = self.run_generator("--start-date", "2026-08-23", "--output-dir", str(Path(self.temp.name) / "bad"), expect_success=False)
        self.assertIn("weekday", result.stderr)

    def test_alternate_calendar_handles_daylight_saving_change(self):
        output = Path(self.temp.name) / "dst"
        self.run_generator("--scenario", "normal", "--start-date", "2026-10-26", "--output-dir", str(output))
        with (output / "normal.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["timestamp"], "2026-10-26T07:00:00-04:00")
        self.assertEqual(rows[5 * 300]["timestamp"], "2026-11-02T07:00:00-05:00")
        self.assertEqual(len(rows), 12000)
        events = read_events(output / "normal_events.jsonl")
        metadata = json.loads((output / "generation_metadata.json").read_text())
        snapshots = defaultdict(dict)
        for row in rows:
            snapshots[instant(row["timestamp"])][row["station_id"]] = int(row["bikes"])
        audit = {instant(row["timestamp"]): row for row in metadata["snapshot_audit"]["normal"]}
        replay_events(self, events, snapshots, audit)
        self.assertTrue(any(instant(e["timestamp"]).astimezone(LOCAL).utcoffset().total_seconds() == -5 * 3600
                            for e in events))

    def test_modified_sibling_is_not_silently_mixed(self):
        output = Path(self.temp.name) / "modified"
        self.run_generator("--scenario", "normal", "--output-dir", str(output))
        with (output / "normal.csv").open("a") as handle:
            handle.write("modified\n")
        result = self.run_generator("--scenario", "edge_cases", "--output-dir", str(output), expect_success=False)
        self.assertIn("recorded hash", result.stderr)
        self.assertFalse((output / "edge_cases.csv").exists())

    def test_modified_sibling_event_log_is_not_silently_mixed(self):
        output = Path(self.temp.name) / "modified_events"
        self.run_generator("--scenario", "normal", "--output-dir", str(output))
        with (output / "normal_events.jsonl").open("a") as handle:
            handle.write('{"tampered":true}\n')
        result = self.run_generator("--scenario", "edge_cases", "--output-dir", str(output), expect_success=False)
        self.assertIn("recorded hash", result.stderr)
        self.assertFalse((output / "edge_cases.csv").exists())

    def test_exported_hashes_match_actual_csvs_and_event_logs(self):
        for scenario in SCENARIOS:
            for filename, table in ((scenario + ".csv", "expected_csvs"),
                                    (scenario + "_events.jsonl", "expected_event_logs")):
                expected = self.metadata[table][filename]
                actual = hashlib.sha256((self.output / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected["sha256"], filename)

    def test_small_ride_crosses_midnight_without_teleporting(self):
        stations = json.loads((self.output / "stations.json").read_text())
        start = datetime(2026, 10, 16, 23, 50, tzinfo=LOCAL)
        simulator = self.generator.Simulator(stations, start, seed=5300)
        departure = start + timedelta(minutes=5)
        due = departure + timedelta(minutes=10)
        simulator.schedule_departure(departure, "S01", "S02", flow="test", duration_seconds=600)
        simulator.advance_to(departure - timedelta(seconds=1))
        self.assertEqual((simulator.snapshot()["S01"], simulator.snapshot()["S02"]), (15, 15))
        simulator.advance_to(departure)
        self.assertEqual((simulator.snapshot()["S01"], simulator.snapshot()["S02"]), (14, 15))
        self.assertEqual(len(simulator.in_transit), 1)
        simulator.advance_to(due - timedelta(seconds=1))
        self.assertEqual((simulator.snapshot()["S01"], simulator.snapshot()["S02"]), (14, 15))
        simulator.advance_to(due)
        self.assertEqual((simulator.snapshot()["S01"], simulator.snapshot()["S02"]), (14, 16))
        self.assertEqual(len(simulator.in_transit), 0)
        self.assertEqual([event["event"] for event in simulator.events], ["departure", "arrival"])
        self.assertEqual(instant(simulator.events[1]["timestamp"]).astimezone(LOCAL).date().isoformat(), "2026-10-17")
        counts, moving = replay_events(self, simulator.events)
        self.assertEqual(counts, simulator.snapshot())
        self.assertFalse(moving)

    def test_nonpositive_ride_time_is_rejected(self):
        stations = json.loads((self.output / "stations.json").read_text())
        start = datetime(2026, 10, 16, 10, 0, tzinfo=LOCAL)
        for duration in (0, -1):
            with self.subTest(duration=duration):
                simulator = self.generator.Simulator(stations, start, seed=5300)
                with self.assertRaises(ValueError):
                    simulator.schedule_departure(start, "S01", "S02", flow="test", duration_seconds=duration)

    def test_full_destination_reroutes_with_extra_time_and_same_bike(self):
        stations = json.loads((self.output / "stations.json").read_text())
        start = datetime(2026, 10, 16, 10, 0, tzinfo=LOCAL)
        simulator = self.generator.Simulator(stations, start, seed=5300)
        for _ in range(15):
            simulator.schedule_departure(start + timedelta(seconds=1), "S01", "S02", flow="test", duration_seconds=60)
        simulator.schedule_departure(start + timedelta(seconds=2), "S03", "S02", flow="test", duration_seconds=120)
        simulator.advance_to(start + timedelta(seconds=2))
        self.assertEqual(simulator.snapshot()["S02"], 15, "Destination still has space at departure")
        self.assertEqual(len(simulator.in_transit), 16)
        blocked_time = start + timedelta(seconds=122)
        simulator.advance_to(blocked_time)
        self.assertEqual(simulator.snapshot()["S02"], 30)
        self.assertEqual(simulator.snapshot()["S03"], 14)
        self.assertEqual(len(simulator.in_transit), 1)
        reroutes = [event for event in simulator.events if event["event"] == "reroute"]
        self.assertEqual(len(reroutes), 1)
        reroute = reroutes[0]
        self.assertEqual(reroute["station_id"], "S02")
        self.assertNotEqual(reroute["destination_id"], "S02")
        new_due = instant(reroute["arrival_due"])
        self.assertGreater(new_due, blocked_time.astimezone(UTC))
        before = simulator.snapshot()
        simulator.advance_to(new_due - timedelta(microseconds=1))
        self.assertEqual(simulator.snapshot(), before, "Rerouted bike remains in transit")
        simulator.advance_to(new_due)
        self.assertEqual(simulator.snapshot()["S02"], 30)
        self.assertEqual(simulator.snapshot()[reroute["destination_id"]], before[reroute["destination_id"]] + 1)
        arrival = simulator.events[-1]
        self.assertEqual((arrival["event"], arrival["bike_id"], arrival["trip_id"]),
                         ("arrival", reroute["bike_id"], reroute["trip_id"]))
        counts, moving = replay_events(self, simulator.events)
        self.assertEqual(counts, simulator.snapshot())
        self.assertFalse(moving)

    def test_settings_exclude_generation_only_labels(self):
        self.assertEqual(set(self.settings), {"schema_version", "timezone", "service_dates", "baseline_dates", "monitoring_dates", "hours", "station_ids", "collection_mode"})
        metadata = json.loads((self.output / "generation_metadata.json").read_text())
        self.assertTrue(metadata["synthetic"])
        self.assertEqual(metadata["configuration"]["seed"], 5300)
        self.assertTrue(metadata["edge_fixtures"])
        self.assertEqual(metadata["configuration"]["generator_version"], 4)

    def test_student_flow_audit(self):
        audits = self.metadata["transfer_audit"]
        for flow, result in audits["normal"]["baseline"].items():
            for key in ("planned_transfers", "successful_transfers"):
                self.assertEqual(result[key], audits["disruption"]["baseline"][flow][key])
        # Later arrivals/reroutes can differ after the shared departure history
        # branches, even when attributed back to a baseline journey in metadata.
        required_flows = {"background", "morning_to_class", "midday_exchange", "afternoon_return", "evening_return"}
        boundary = instant(self.settings["monitoring_dates"][0] + "T07:00:00-04:00")
        for scenario in SCENARIOS:
            for phase in ("baseline", "monitoring"):
                self.assertTrue(set(audits[scenario][phase]).issuperset(required_flows))
                actual = Counter(event["flow"] for event in self.events[scenario]
                                 if event["event"] == "departure" and
                                 ((instant(event["timestamp"]) < boundary) == (phase == "baseline")))
                self.assertTrue(set(actual).issubset(audits[scenario][phase]))
                for flow, result in audits[scenario][phase].items():
                    self.assertGreaterEqual(result["successful_transfers"], 0)
                    self.assertLessEqual(result["successful_transfers"], result["planned_transfers"])
                    self.assertEqual(result["successful_transfers"], actual[flow],
                                     (scenario, phase, flow, "Count actual departures, not intended attempts"))
        normal = audits["normal"]["monitoring"]["morning_to_class"]["planned_transfers"]
        abnormal = audits["disruption"]["monitoring"]["morning_to_class"]["planned_transfers"]
        self.assertGreater(abnormal, normal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
