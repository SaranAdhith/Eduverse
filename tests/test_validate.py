"""Tests for the cross-document consistency checker."""
import unittest
from pathlib import Path

from eduverse.bkt import load_params
from eduverse.curriculum import Curriculum
from eduverse.diagnostic import Blueprint
from eduverse.validate import check

DATA = Path(__file__).resolve().parents[1] / "data"


class TestBundledData(unittest.TestCase):
    def setUp(self):
        self.curriculum = Curriculum.load(DATA / "curriculum.yaml")
        self.blueprint = Blueprint.load(DATA / "diagnostic_blueprint.yaml")

    def test_no_errors(self):
        errors, _ = check(self.curriculum, self.blueprint)
        self.assertEqual(errors, [], f"unexpected validation errors: {errors}")

    def test_blueprint_sums_to_declared_total(self):
        self.assertEqual(self.blueprint.total_items(), self.blueprint.items_total)
        self.assertEqual(self.blueprint.total_items(), 25)

    def test_every_anchor_is_a_real_topic(self):
        for anchor in self.blueprint.all_anchors():
            self.assertIn(anchor, self.curriculum)

    def test_bkt_params_load_and_validate(self):
        params = load_params(DATA / "bkt_params.yaml")
        self.assertEqual(params.p_l0, 0.3)


if __name__ == "__main__":
    unittest.main()
