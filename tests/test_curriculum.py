"""Tests for the curriculum graph loader and DAG operations."""
import unittest
from pathlib import Path

from eduverse.curriculum import Curriculum, CurriculumError
from eduverse.models import Tier, Topic

DATA = Path(__file__).resolve().parents[1] / "data" / "curriculum.yaml"


def tiny(topics):
    return Curriculum(topics, {"T0": Tier("T0", "Foundations")})


class TestRealCurriculum(unittest.TestCase):
    def setUp(self):
        self.c = Curriculum.load(DATA)

    def test_loads(self):
        self.assertGreater(len(self.c), 0)
        self.assertIn("T0.1", self.c)
        self.assertEqual(self.c["T0.1"].prerequisites, ())

    def test_acyclic(self):
        self.assertIsNone(self.c.find_cycle())

    def test_no_dangling_prerequisites(self):
        self.assertEqual(self.c.missing_prerequisites(), {})

    def test_topo_order_respects_prerequisites(self):
        order = self.c.topological_order()
        self.assertEqual(len(order), len(self.c))
        pos = {tid: i for i, tid in enumerate(order)}
        for t in self.c.topics.values():
            for p in t.prerequisites:
                self.assertLess(pos[p], pos[t.id])

    def test_topo_order_is_deterministic(self):
        self.assertEqual(self.c.topological_order(), self.c.topological_order())

    def test_available_frontier_starts_at_roots(self):
        # With nothing mastered, only prerequisite-free topics are available.
        avail = self.c.available_topics(mastered=set())
        self.assertIn("T0.1", avail)
        self.assertNotIn("T0.2", avail)  # depends on T0.1

    def test_available_unlocks_after_mastery(self):
        avail = self.c.available_topics(mastered={"T0.1"})
        self.assertIn("T0.2", avail)
        self.assertNotIn("T0.1", avail)  # already mastered, not re-offered


class TestSynthetic(unittest.TestCase):
    def test_cycle_detected(self):
        c = tiny([
            Topic("A", "T0", "A", ("B",)),
            Topic("B", "T0", "B", ("A",)),
        ])
        cycle = c.find_cycle()
        self.assertIsNotNone(cycle)
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)

    def test_cycle_breaks_topo_sort(self):
        c = tiny([
            Topic("A", "T0", "A", ("B",)),
            Topic("B", "T0", "B", ("A",)),
        ])
        with self.assertRaises(CurriculumError):
            c.topological_order()

    def test_dangling_prerequisite_reported(self):
        c = tiny([Topic("A", "T0", "A", ("Z",))])
        self.assertEqual(c.missing_prerequisites(), {"A": ["Z"]})

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(CurriculumError):
            tiny([Topic("A", "T0", "A"), Topic("A", "T0", "A2")])


if __name__ == "__main__":
    unittest.main()
