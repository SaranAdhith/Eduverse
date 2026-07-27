"""Tests for the BKT update rule (DOC_00 section 4)."""
import unittest

from eduverse.bkt import is_mastered, posterior, update
from eduverse.models import BKTParams

PARAMS = BKTParams(p_l0=0.3, p_transit=0.15, p_guess=0.25, p_slip=0.1)


class TestPosterior(unittest.TestCase):
    def test_correct_raises_belief(self):
        # Worked example: p_l=0.3 -> 0.3*0.9 / (0.3*0.9 + 0.7*0.25) = 0.27/0.445
        self.assertAlmostEqual(posterior(0.3, PARAMS, True), 0.27 / 0.445, places=10)
        self.assertGreater(posterior(0.3, PARAMS, True), 0.3)

    def test_incorrect_lowers_belief(self):
        # p_l=0.3 -> 0.3*0.1 / (0.3*0.1 + 0.7*0.75) = 0.03/0.555
        self.assertAlmostEqual(posterior(0.3, PARAMS, False), 0.03 / 0.555, places=10)
        self.assertLess(posterior(0.3, PARAMS, False), 0.3)

    def test_bounds(self):
        for p in (0.0, 0.5, 1.0):
            for correct in (True, False):
                self.assertGreaterEqual(posterior(p, PARAMS, correct), 0.0)
                self.assertLessEqual(posterior(p, PARAMS, correct), 1.0)

    def test_certain_beliefs_are_stable(self):
        self.assertAlmostEqual(posterior(1.0, PARAMS, True), 1.0)
        self.assertAlmostEqual(posterior(0.0, PARAMS, False), 0.0)

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            posterior(1.5, PARAMS, True)


class TestUpdate(unittest.TestCase):
    def test_learning_step_adds_transit_mass(self):
        post = posterior(0.3, PARAMS, True)
        expected = post + (1 - post) * PARAMS.p_transit
        self.assertAlmostEqual(update(0.3, PARAMS, True), expected, places=10)

    def test_update_is_monotone_in_correctness(self):
        self.assertGreater(update(0.4, PARAMS, True), update(0.4, PARAMS, False))

    def test_repeated_correct_converges_to_mastery(self):
        p = PARAMS.p_l0
        for _ in range(10):
            p = update(p, PARAMS, True)
        self.assertTrue(is_mastered(p, PARAMS))


class TestParamValidation(unittest.TestCase):
    def test_guess_plus_slip_must_be_under_one(self):
        with self.assertRaises(ValueError):
            BKTParams(p_l0=0.3, p_transit=0.15, p_guess=0.6, p_slip=0.5)

    def test_param_range(self):
        with self.assertRaises(ValueError):
            BKTParams(p_l0=1.2, p_transit=0.15, p_guess=0.25, p_slip=0.1)


if __name__ == "__main__":
    unittest.main()
