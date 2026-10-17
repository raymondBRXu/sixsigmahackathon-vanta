"""Independent acceptance checks for the synthetic data, using only the stdlib."""

import csv
import hashlib
import importlib.util
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


SCRIPT = Path(__file__).with_name("generate_data.py")
SCENARIOS = ("normal", "disruption")
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
        cls.stations = json.loads((cls.output / "stations.json").read_text())
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


    def test_repeated_run_is_identical(self):
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.run_generator("--output-dir", str(self.output))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})


    def test_invalid_start_date_is_clear_error(self):
        result = self.run_generator("--start-date", "2026-08-23", "--output-dir", str(Path(self.temp.name) / "bad"), expect_success=False)
        self.assertIn("weekday", result.stderr)


    def test_alternate_calendar_handles_daylight_saving_change(self):
        output = Path(self.temp.name) / "dst"
        self.run_generator("--start-date", "2026-10-26", "--output-dir", str(output))
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


    def test_only_two_csvs_and_audit_reports(self):
        self.assertEqual(sorted(p.name for p in self.output.glob('*.csv')), ['disruption.csv', 'normal.csv'])
        report = json.loads((self.output / 'validation.json').read_text())
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['review_automatically_approved'])
        self.assertEqual(report['shared_baseline_rows'], 7500)
        self.assertTrue(report['shared_prechange_events_and_pending_rides'])
        self.assertTrue((self.output / 'demo_guide.md').is_file())
        self.assertEqual((self.output / 'README.md').read_bytes(), SCRIPT.with_name('README.v5.md').read_bytes())

    def test_data_only_snapshot_fallback_integrity_and_app_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'data'
            folder.mkdir()
            script = folder / 'generate_data.py'
            snapshot = folder / '_qc_snapshot.py'
            shutil.copy2(SCRIPT, script)
            shutil.copy2(SCRIPT.with_name('_qc_snapshot.py'), snapshot)
            spec = importlib.util.spec_from_file_location('isolated_publication_generator', script)
            generator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generator)
            self.assertEqual(Path(generator.load_qc().__file__).resolve(), snapshot.resolve())
            self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), generator.QC_SNAPSHOT_SHA256)
            original = snapshot.read_bytes()
            snapshot.write_bytes(original + b'\n# altered snapshot\n')
            with self.assertRaisesRegex(ValueError, 'integrity check'):
                generator.load_qc()
            (root / 'app').mkdir()
            app_detector = root / 'app' / 'qc.py'
            app_detector.write_bytes(original)
            self.assertEqual(Path(generator.load_qc().__file__).resolve(), app_detector.resolve())
            app_detector.unlink()
            snapshot.unlink()
            with self.assertRaisesRegex(ValueError, 'requires app/qc.py'):
                generator.load_qc()

    def test_normal_actual_detector_has_no_candidate_or_baseline_warning(self):
        qc = self.generator.load_qc()
        rows = self.rows['normal']
        by_series = defaultdict(list)
        for row in rows:
            parsed = datetime.fromisoformat(row['timestamp'])
            by_series[(row['station_id'], parsed.hour)].append({
                'bikes': int(row['bikes']), 'date': parsed.date().isoformat(), 'timestamp': row['timestamp']})
        self.assertEqual(len(by_series), 300)
        for key, points in by_series.items():
            with self.subTest(station_hour=key):
                self.assertTrue(all(6 <= p['bikes'] <= 24 for p in points))
                limits = qc.i_chart_limits([p['bikes'] for p in points[:25]])
                self.assertEqual((limits['n'], limits['pairs']), (25, 24))
                self.assertGreater(limits['sigma'], 0)
                self.assertEqual(qc.detect_rules(points[25:], limits), [])
                self.assertEqual(qc.baseline_diagnostics(points[:25], 30, limits)['warnings'], [])

    def test_operational_fixtures_use_real_dashboard_rules(self):
        qc = self.generator.load_qc()
        result = qc.build_dashboard(self.rows['disruption'], self.stations, self.settings,
                                    '2026-09-28T09:00:00-04:00', 'S01', 9)
        stations = {s['station_id']: s for s in result['operations']['stations']}
        actions = {a['station_id']: a for a in result['operations']['actions']}
        expected = {'S01': (0, 'empty', 'P1', 'add', 15), 'S06': (30, 'full', 'P1', 'remove', 15),
                    'S02': (3, 'low', 'P2', 'add', 12), 'S07': (27, 'high', 'P2', 'remove', 12)}
        for sid, (bikes, status, priority, direction, quantity) in expected.items():
            self.assertEqual((stations[sid]['bikes'], stations[sid]['status']), (bikes, status))
            self.assertEqual((actions[sid]['priority'], actions[sid]['direction'], actions[sid]['quantity']),
                             (priority, direction, quantity))
        for sid, bikes in [('S03', 6), ('S08', 24), ('S05', 15)]:
            self.assertEqual(stations[sid]['bikes'], bikes)
            self.assertNotIn(sid, actions)
        self.assertEqual(len(actions), len(result['operations']['actions']))
        self.assertEqual(result['operations']['kpis']['coverage'], 1.0)

    def test_planted_rules_are_causal_and_statistics_only_does_not_dispatch(self):
        qc = self.generator.load_qc()
        fixtures = [('S14', 12, '2026-10-07', '2026-10-06', 'eight_same_side'),
                    ('S17', 14, '2026-10-05', '2026-10-02', 'six_trend')]
        for sid, hour, trigger, before, rule in fixtures:
            with self.subTest(rule=rule):
                previous = qc.station_hour_analysis(self.rows['disruption'], self.stations, self.settings,
                              before + 'T%02d:00:00-04:00' % hour, sid, hour)
                self.assertFalse(any(e['rule'] == rule for e in previous['events']))
                current = qc.build_dashboard(self.rows['disruption'], self.stations, self.settings,
                              trigger + 'T%02d:00:00-04:00' % hour, sid, hour)
                analysis = current['analysis']
                self.assertTrue(analysis['baseline']['eligible'])
                self.assertEqual(analysis['status'], 'unreviewed')
                self.assertTrue(any(e['rule'] == rule and e['date'] == trigger for e in analysis['events']))
                self.assertTrue(all(e['kind'] == 'exploratory_pattern' for e in analysis['events']))
                self.assertNotIn(sid, {a['station_id'] for a in current['operations']['actions']})
                self.assertEqual(previous['limits'], analysis['limits'])
                truncated = [r for r in self.rows['disruption'] if instant(r['timestamp']) <= instant(before + 'T%02d:00:00-04:00' % hour)]
                self.assertEqual(previous, qc.station_hour_analysis(truncated, self.stations, self.settings,
                                 before + 'T%02d:00:00-04:00' % hour, sid, hour))

    def test_disruption_all_three_rules_and_mixed_operational_states(self):
        report = json.loads((self.output / 'validation.json').read_text())['scenarios']['disruption']
        self.assertTrue(all(report['candidate_rule_counts'].values()))
        self.assertGreater(report['statistics_only_events'], 0)
        self.assertEqual(report['eligible_strata'], 300)
        self.assertEqual(report['baseline_diagnostic_warnings'], 0)
        values = {int(r['bikes']) for r in self.rows['disruption']}
        self.assertTrue({0, 3, 5, 6, 15, 24, 25, 27, 30}.issubset(values))
        self.assertTrue(all(0 <= v <= 30 for v in values))
        by_time = defaultdict(list)
        for row in self.rows['disruption'][7500:]:
            by_time[row['timestamp']].append(int(row['bikes']))
        self.assertTrue(all(any(6 <= v <= 24 for v in snapshot) for snapshot in by_time.values()))

    def test_backups_preserve_old_edge_files_and_unrelated_files(self):
        output = Path(self.temp.name) / 'replace_old'
        output.mkdir()
        prior = {'normal.csv': b'oldnormal\n', 'disruption.csv': b'olddisruption\n',
                 'edge_cases.csv': b'oldedge\n', 'edge_cases_events.jsonl': b'{"old":true}\n',
                 'README.md': b'oldcodebook\n'}
        for name, content in prior.items():
            (output / name).write_bytes(content)
        (output / 'my_notes.txt').write_text('keep my notes')
        result = self.run_generator('--output-dir', str(output))
        self.assertIn('backed up:', result.stdout)
        backups = list((output.parent / '.dockwatch-data-backups').glob('replace_old-*'))
        self.assertEqual(len(backups), 1)
        for name, content in prior.items():
            self.assertEqual((backups[0] / name).read_bytes(), content)
        self.assertEqual(sorted(p.name for p in output.glob('*.csv')), ['disruption.csv', 'normal.csv'])
        self.assertFalse((output / 'edge_cases_events.jsonl').exists())
        self.assertEqual((output / 'my_notes.txt').read_text(), 'keep my notes')

    def test_unknown_csv_is_not_deleted_or_mixed(self):
        output = Path(self.temp.name) / 'unrelated_csv'
        output.mkdir()
        (output / 'research.csv').write_text('important\n')
        result = self.run_generator('--output-dir', str(output), expect_success=False)
        self.assertIn('unrelated CSVs', result.stderr)
        self.assertEqual((output / 'research.csv').read_text(), 'important\n')
        self.assertFalse((output / 'normal.csv').exists())

    def test_alternate_seed_is_reproducible_and_retains_contract(self):
        output = Path(self.temp.name) / 'seed10'
        self.run_generator('--seed', '10', '--output-dir', str(output))
        self.assertNotEqual((output / 'normal.csv').read_bytes(), (self.output / 'normal.csv').read_bytes())
        report = json.loads((output / 'validation.json').read_text())
        self.assertEqual(report['scenarios']['normal']['candidate_events'], 0)
        self.assertEqual(report['scenarios']['normal']['operational_warning_rows'], 0)
        self.assertEqual(report['scenarios']['normal']['eligible_strata'], 300)
        self.assertTrue(all(report['scenarios']['disruption']['candidate_rule_counts'].values()))
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        self.run_generator('--seed', '10', '--output-dir', str(output))
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_settings_exclude_planted_labels_and_review_approval(self):
        self.assertEqual(set(self.settings), {'schema_version', 'timezone', 'service_dates', 'baseline_dates',
                         'monitoring_dates', 'hours', 'station_ids', 'collection_mode'})
        self.assertTrue(self.metadata['synthetic'])
        self.assertTrue(self.metadata['not_detector_input'])
        self.assertEqual(self.metadata['configuration']['generator_version'], 5)
        self.assertIn('designed', self.metadata['provenance'])
        self.assertIn('fixture_selection_attempts_by_corridor', self.metadata)

    def test_commute_direction_night_intensity_and_cross_hour_rides(self):
        for scenario, events in self.events.items():
            homes = {'S01','S02','S03','S04','S05','S14','S17','S18'}
            academic = {'S06','S07','S08','S09','S10','S12','S11','S13'}
            morning_forward = morning_reverse = evening_forward = evening_reverse = 0
            nights = peaks = 0
            crossing_midnight = crossing_0700 = 0
            for event in events:
                if event['event'] != 'departure':
                    continue
                stamp = datetime.fromisoformat(event['timestamp']).astimezone(LOCAL)
                due = datetime.fromisoformat(event['arrival_due']).astimezone(LOCAL)
                if stamp.date() != due.date(): crossing_midnight += 1
                if stamp.hour == 6 and due.hour == 7: crossing_0700 += 1
                if stamp.hour < 6: nights += 1
                if stamp.weekday() < 5 and stamp.hour in (7, 8): peaks += 1
                if stamp.weekday() >= 5: continue
                source, dest = event['station_id'], event['destination_id']
                if 7 <= stamp.hour < 9:
                    morning_forward += source in homes and dest in academic
                    morning_reverse += source in academic and dest in homes
                if 15 <= stamp.hour < 19:
                    evening_forward += source in academic and dest in homes
                    evening_reverse += source in homes and dest in academic
            with self.subTest(scenario=scenario):
                self.assertGreater(morning_forward, morning_reverse)
                self.assertGreater(evening_forward, evening_reverse)
                self.assertGreater(peaks / (40 * 2), nights / (54 * 6))
                self.assertGreater(crossing_midnight, 0)
                self.assertGreater(crossing_0700, 0)
                seven = [int(r['bikes']) for r in self.rows[scenario][300:] if datetime.fromisoformat(r['timestamp']).hour == 7]
                self.assertGreater(len(set(seven)), 3)

    def test_replay_rejects_unlogged_stock_edit(self):
        rows = [(r['timestamp'], r['station_id'], int(r['bikes'])) for r in self.rows['normal']]
        rows[400] = (rows[400][0], rows[400][1], rows[400][2] + 1)
        with self.assertRaisesRegex(ValueError, 'replay disagrees'):
            self.generator.replay_and_validate(rows, self.events['normal'], self.metadata['snapshot_audit']['normal'])

    def test_off_hours_forward_riders_do_not_read_tomorrows_stock(self):
        generator = self.generator
        days = [datetime.fromisoformat(day).date() for day in self.settings['service_dates']]
        profiles, attempts = generator.design_normal_profiles(5300, days, generator.load_qc())
        exports = generator.snapshot_plans(profiles, days, 'normal', 5300, LOCAL)
        original = generator.all_hour_plans(exports, profiles)
        future = instant(days[1].isoformat() + 'T07:00:00-04:00')
        altered_exports = dict(exports)
        altered_exports[future] = [(15, 0, 0)] * 10
        altered = generator.all_hour_plans(altered_exports, profiles)
        self.assertEqual({t: v for t, v in original.items() if t < future},
                         {t: v for t, v in altered.items() if t < future})
        # Check every quiet hour, including each 07:00, against its previous
        # actual settled bike state. Only an independently planned -1/0/+1
        # rider increment may change it; no target-directed return is possible.
        service_dates = set(days)
        for profile in profiles:
            prior = None
            for stamp, plan in sorted(profile.items()):
                local = stamp.astimezone(LOCAL)
                if prior is not None and not (local.date() in service_dates and 8 <= local.hour <= 21):
                    settled = prior[0] + prior[1] * (1 if prior[2] else -1)
                    self.assertIn(plan[0] - settled, (-1, 0, 1))
                prior = plan


if __name__ == "__main__":
    unittest.main(verbosity=2)
