"""Tests for kips_table.py (run: python3 -m unittest -v in util/perf-opt)."""

import tempfile
import unittest
from pathlib import Path

import kips_table

TEMPLATE = """---------- Begin Simulation Statistics ----------
simSeconds                                   0.010000                       # Number of seconds simulated (Second)
hostInstRate                                 {rate}                       # Simulator instruction rate (inst/s) ((Count/Second))
simInsts                                     30000000                       # Number of instructions simulated (Count)
board.processor.start.core.numCycles         {cycles}                       # Number of cpu cycles simulated (Cycle)
---------- End Simulation Statistics   ----------
"""


def make_trial(root, name, per_ckpt):
    """per_ckpt: {checkpoint id: (hostInstRate, numCycles)}"""
    trial = Path(root) / name
    for cid, (rate, cycles) in per_ckpt.items():
        (trial / cid).mkdir(parents=True)
        (trial / cid / "stats.txt").write_text(
            TEMPLATE.format(rate=rate, cycles=cycles)
        )
    return trial


class KipsTest(unittest.TestCase):
    def test_reads_host_inst_rate_as_kips(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = make_trial(tmp, "t", {"c": (289332, 1)})
            self.assertAlmostEqual(
                kips_table.kips(t / "c" / "stats.txt"), 289.332
            )

    def test_missing_rate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "stats.txt"
            p.write_text("simInsts 1 # x\n")
            with self.assertRaises(ValueError):
                kips_table.kips(p)


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.a = make_trial(root, "base-a", {"c": (100000, 500)})
        self.b = make_trial(root, "base-b", {"c": (102000, 500)})

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, rate, cycles=500):
        t = make_trial(
            self.tmp.name, f"t{rate}-{cycles}", {"c": (rate, cycles)}
        )
        return kips_table.rows(t, [self.a, self.b], [self.a, self.b])

    def test_faster_row(self):
        (r,) = self.rows(110000)
        self.assertAlmostEqual(r["prev"], 101.0)
        self.assertAlmostEqual(r["new"], 110.0)
        self.assertAlmostEqual(r["change_pct"], 100 * (110 / 101 - 1))
        self.assertAlmostEqual(r["vs_base_pct"], 100 * (110 / 101 - 1))
        self.assertAlmostEqual(r["noise_pct"], 100 * 2 / 101)
        self.assertEqual(r["direction"], "faster")
        self.assertTrue(r["identical"])

    def test_gain_inside_noise_is_labelled(self):
        (r,) = self.rows(101500)
        self.assertEqual(r["direction"], "faster (within noise)")

    def test_slower_row(self):
        (r,) = self.rows(90000)
        self.assertEqual(r["direction"], "slower")

    def test_changed_stat_is_not_identical(self):
        (r,) = self.rows(110000, cycles=501)
        self.assertFalse(r["identical"])

    def test_identity_reference_can_differ_from_kips_baseline(self):
        ref = make_trial(self.tmp.name, "ident-ref", {"c": (100000, 501)})
        t = make_trial(self.tmp.name, "t-ident", {"c": (110000, 501)})
        (r,) = kips_table.rows(
            t, [self.a, self.b], [self.a, self.b], ident_dir=ref
        )
        self.assertTrue(r["identical"])
        self.assertAlmostEqual(r["vs_base_pct"], 100 * (110 / 101 - 1))


class PartialTrialTest(unittest.TestCase):
    def test_missing_checkpoint_is_listed_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ids = {f"c{i}": (100000, 500) for i in range(5)}
            a = make_trial(tmp, "base-a", ids)
            b = make_trial(tmp, "base-b", ids)
            # A trial where only 3 of the 5 checkpoints produced stats, all
            # faster and identical: it must not pass as "3/3".
            t = make_trial(
                tmp, "partial", {f"c{i}": (120000, 500) for i in range(3)}
            )
            table = kips_table.rows(t, [a, b], [a, b])
            self.assertEqual(
                [r["cid"] for r in table], ["c0", "c1", "c2", "c3", "c4"]
            )
            missing = [r for r in table if r["new"] is None]
            self.assertEqual(len(missing), 2)
            self.assertTrue(
                all(
                    r["direction"] == "MISSING" and not r["identical"]
                    for r in missing
                )
            )
            ok, reason = kips_table.verdict(table)
            self.assertFalse(ok)
            self.assertIn("missing on 2/5", reason)
            self.assertIn("| c3 | 100.0 | — |", kips_table.markdown(table))


def row(faster, identical=True):
    return {
        "cid": "x",
        "new": 2.0 if faster else 0.5,
        "prev": 1.0,
        "identical": identical,
    }


class VerdictTest(unittest.TestCase):
    def test_majority_faster_and_identical_is_accepted(self):
        ok, reason = kips_table.verdict(
            [row(1), row(1), row(1), row(0), row(0)]
        )
        self.assertTrue(ok)
        self.assertIn("faster on 3/5", reason)

    def test_minority_faster_is_rejected(self):
        ok, reason = kips_table.verdict(
            [row(1), row(1), row(0), row(0), row(0)]
        )
        self.assertFalse(ok)
        self.assertIn("faster on only 2/5", reason)

    def test_any_stats_difference_is_rejected(self):
        rows = [row(1), row(1), row(1), row(1), row(1, identical=False)]
        ok, reason = kips_table.verdict(rows)
        self.assertFalse(ok)
        self.assertIn("stats identical on only 4/5", reason)


class MarkdownTest(unittest.TestCase):
    def test_has_header_and_one_line_per_checkpoint(self):
        rows = [
            {
                "cid": "a.0.1",
                "prev": 100.0,
                "new": 110.0,
                "change_pct": 10.0,
                "direction": "faster",
                "vs_base_pct": 10.0,
                "noise_pct": 1.0,
                "identical": True,
            }
        ]
        md = kips_table.markdown(rows).splitlines()
        self.assertTrue(
            md[0].startswith("| Checkpoint | Previous KIPS | New KIPS")
        )
        self.assertEqual(len(md), 3)
        self.assertIn(
            "| a.0.1 | 100.0 | 110.0 | +10.00% | faster | +10.00% | 1.00% | yes |",
            md[2],
        )


if __name__ == "__main__":
    unittest.main()
