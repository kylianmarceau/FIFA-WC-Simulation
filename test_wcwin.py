import tempfile
import unittest
from pathlib import Path

import wcwin


class PredictorTests(unittest.TestCase):
    def test_odds_conversion_and_devig(self):
        self.assertAlmostEqual(wcwin.american_to_probability(-150), 0.6)
        self.assertAlmostEqual(wcwin.american_to_probability(400), 0.2)
        probs = wcwin.devig_three_way(-120, 265, 370)
        self.assertAlmostEqual(sum(probs), 1.0)
        self.assertGreater(probs[0], probs[2])

    def test_fixture_inventory(self):
        teams = wcwin.all_teams()
        self.assertEqual(len(teams), 48)
        self.assertEqual(len(set(teams)), 48)
        self.assertEqual(len(wcwin.FIXTURES), 72)
        pair_keys = {frozenset((fixture.team_a, fixture.team_b)) for fixture in wcwin.FIXTURES}
        self.assertEqual(len(pair_keys), 72)
        self.assertEqual(len(wcwin.OBSERVED_RESULTS), 24)

    def test_full_path_has_all_matches_and_champion(self):
        ratings = wcwin.fit_strengths(iterations=80)
        projections, tables = wcwin.full_path(ratings)
        self.assertEqual(len(projections), 104)
        self.assertEqual(projections[0].note, "observed")
        self.assertEqual(projections[72].stage, "Round of 32")
        self.assertEqual(projections[-1].stage, "Final")
        self.assertNotEqual(projections[-1].winner, "Draw")
        self.assertIn(projections[-1].winner, wcwin.all_teams())
        self.assertEqual(set(tables), set(wcwin.GROUP_ORDER))

    def test_csv_writer_outputs_104_rows(self):
        ratings = wcwin.fit_strengths(iterations=40)
        projections, _ = wcwin.full_path(ratings)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "predictions.csv"
            wcwin.write_csv(path, projections)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 105)
        self.assertTrue(lines[0].startswith("match_no,stage,group"))

    def test_historical_code_aliases_and_probabilities(self):
        self.assertEqual(wcwin.historical_code("DEU"), "GER")
        ranks = {"GER": 1, "CRC": 50}
        probs = wcwin.historical_probabilities("DEU", "CRI", "WC-2006", ranks)
        self.assertAlmostEqual(sum(probs), 1.0)
        self.assertGreater(probs[0], probs[2])

    def test_summary_includes_calibration(self):
        ratings = wcwin.fit_strengths(iterations=20)
        projections, _ = wcwin.full_path(ratings)
        summary = wcwin.build_summary(ratings, projections, {"France": 0.2})
        self.assertIn("calibration", summary)
        self.assertEqual(summary["calibration"]["rank_log_scale"], wcwin.CALIBRATED_RANK_LOG_SCALE)


if __name__ == "__main__":
    unittest.main()
