"""Tests for stats_gate.py (run: python3 -m unittest -v in util/perf-opt)."""

import tempfile
import unittest
from pathlib import Path

import stats_gate

BASE = """
---------- Begin Simulation Statistics ----------
simSeconds                                   0.010000                       # Number of seconds simulated (Second)
simFreq                                  1000000000000                       # The number of ticks per simulated second ((Tick/Second))
hostSeconds                                    172.81                       # Real time elapsed on the host (Second)
hostInstRate                                   289332                       # Simulator instruction rate (inst/s) ((Count/Second))
simInsts                                     30000000                       # Number of instructions simulated (Count)
board.processor.start.core.numCycles         20000000                       # Number of cpu cycles simulated (Cycle)
board.processor.start.core.branchPred.lookups   123                       # Number of BP lookups (Count)

---------- End Simulation Statistics   ----------
"""


def write(tmp, name, text):
    path = Path(tmp) / name
    path.write_text(text)
    return path


class LoadTest(unittest.TestCase):
    def test_ignores_host_simfreq_separators_and_blanks(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = stats_gate.load(write(tmp, "s.txt", BASE))
        self.assertEqual(
            set(stats),
            {
                "simSeconds",
                "simInsts",
                "board.processor.start.core.numCycles",
                "board.processor.start.core.branchPred.lookups",
            },
        )


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = stats_gate.load(write(self.tmp.name, "b.txt", BASE))

    def tearDown(self):
        self.tmp.cleanup()

    def cand(self, text):
        return stats_gate.load(write(self.tmp.name, "c.txt", text))

    def test_identical_when_only_host_stats_differ(self):
        text = BASE.replace("172.81", "99.00").replace("289332", "512000")
        self.assertEqual(stats_gate.diff(self.base, self.cand(text)), [])

    def test_changed_value_is_reported(self):
        text = BASE.replace("20000000", "20000001")
        bad = stats_gate.diff(self.base, self.cand(text))
        self.assertEqual(len(bad), 1)
        self.assertIn("DIFFERS board.processor.start.core.numCycles", bad[0])

    def test_missing_stat_is_reported(self):
        text = "\n".join(
            l for l in BASE.splitlines() if not l.startswith("simInsts")
        )
        self.assertEqual(
            stats_gate.diff(self.base, self.cand(text)), ["MISSING simInsts"]
        )

    def test_new_zero_stat_is_allowed_new_nonzero_is_not(self):
        zero = BASE.replace(
            "\n\n---------- End",
            "\nboard.newStat                 0                       # new (Count)\n\n---------- End",
        )
        self.assertEqual(stats_gate.diff(self.base, self.cand(zero)), [])
        nonzero = zero.replace(
            "board.newStat                 0",
            "board.newStat                 7",
        )
        bad = stats_gate.diff(self.base, self.cand(nonzero))
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("NEW NONZERO board.newStat"))

    def test_excluded_stat_is_skipped(self):
        text = BASE.replace("   123", "   124")
        exclude = frozenset({"board.processor.start.core.branchPred.lookups"})
        self.assertEqual(
            stats_gate.diff(self.base, self.cand(text), exclude), []
        )


class DifferingNamesTest(unittest.TestCase):
    def test_lists_changed_added_and_removed_names(self):
        a = {"x": "x 1", "y": "y 2", "z": "z 3"}
        b = {"x": "x 1", "y": "y 5", "w": "w 0"}
        self.assertEqual(stats_gate.differing_names(a, b), {"y", "z", "w"})


class ExclusionFileTest(unittest.TestCase):
    def test_reads_first_token_skips_comments_and_blanks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ex.txt", "# header\n\nstat.a  why\nstat.b\n")
            self.assertEqual(
                stats_gate.load_exclusions(path),
                frozenset({"stat.a", "stat.b"}),
            )

    def test_missing_file_means_no_exclusions(self):
        self.assertEqual(stats_gate.load_exclusions(None), frozenset())
        self.assertEqual(
            stats_gate.load_exclusions("/nonexistent/x.txt"), frozenset()
        )


class TrialCheckpointsTest(unittest.TestCase):
    def test_lists_subdirs_that_hold_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("b.1.0", "a.0.2"):
                (Path(tmp) / name).mkdir()
                (Path(tmp) / name / "stats.txt").write_text(BASE)
            (Path(tmp) / "no-stats").mkdir()
            self.assertEqual(
                stats_gate.trial_checkpoints(tmp), ["a.0.2", "b.1.0"]
            )


class GateTest(unittest.TestCase):
    def make(self, root, name, ids):
        d = Path(root) / name
        for cid in ids:
            (d / cid).mkdir(parents=True)
            (d / cid / "stats.txt").write_text(BASE)
        return d

    def test_missing_or_empty_base_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cand = self.make(tmp, "cand", ["a.0.1"])
            self.assertFalse(
                stats_gate.gate(Path(tmp) / "typo", cand, frozenset())
            )
            (Path(tmp) / "empty").mkdir()
            self.assertFalse(
                stats_gate.gate(Path(tmp) / "empty", cand, frozenset())
            )

    def test_checkpoint_only_in_candidate_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self.make(tmp, "base", ["a.0.1"])
            cand = self.make(tmp, "cand", ["a.0.1", "b.0.2"])
            self.assertFalse(stats_gate.gate(base, cand, frozenset()))

    def test_matching_trials_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self.make(tmp, "base", ["a.0.1", "b.0.2"])
            cand = self.make(tmp, "cand", ["a.0.1", "b.0.2"])
            self.assertTrue(stats_gate.gate(base, cand, frozenset()))


if __name__ == "__main__":
    unittest.main()
