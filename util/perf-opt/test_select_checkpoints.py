"""Tests for select_checkpoints.py (run: python3 -m unittest -v in util/perf-opt)."""

import unittest

import select_checkpoints as sc

ROWS = [
    {
        "benchmark": f"7{i:02d}.b_r",
        "inv": i % 3,
        "simpoint": i % 5,
        "weight": 0.1,
    }
    for i in range(40)
]


class SelectTest(unittest.TestCase):
    def test_same_seed_same_draw(self):
        self.assertEqual(sc.select(ROWS, 7, 5, 3), sc.select(ROWS, 7, 5, 3))

    def test_sizes_and_disjoint_sets(self):
        test, train = sc.select(ROWS, 7, 5, 3)
        self.assertEqual((len(test), len(train)), (5, 3))
        ids = [sc.checkpoint_id(r) for r in test + train]
        self.assertEqual(len(ids), len(set(ids)))

    def test_paths_follow_archive_layout(self):
        e = sc.entry(
            {
                "benchmark": "708.sqlite_r",
                "inv": 0,
                "simpoint": 3,
                "weight": 0.5,
            },
            "test",
        )
        self.assertEqual(e["id"], "708.sqlite_r.0.3")
        self.assertTrue(
            e["remote"].endswith("/ckpts/708.sqlite_r/0/cpt.708.sqlite_r.0.3")
        )
        self.assertTrue(
            e["local"].endswith(
                "/fs_ckpts/708.sqlite_r/0/cpt.708.sqlite_r.0.3"
            )
        )


if __name__ == "__main__":
    unittest.main()
