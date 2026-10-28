import math
import unittest

import main
from logic import calculate_position_adjustment


class PositionAdjustmentTests(unittest.TestCase):
    def test_fee_enabled_changes_required_size(self):
        no_fee = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=0,
            stop_entry_percent=1,
            stop_now_percent=1,
            fee_percent=0,
        )
        with_fee = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=0,
            stop_entry_percent=1,
            stop_now_percent=1,
            fee_percent=0.2,
        )

        self.assertEqual(no_fee["action"], "add")
        self.assertEqual(with_fee["action"], "add")
        self.assertGreater(no_fee["delta_abs"], with_fee["delta_abs"])

    def test_fee_disabled_means_no_fee_impact(self):
        zero_fee = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=250,
            stop_entry_percent=1,
            stop_now_percent=1,
            fee_percent=0,
        )
        with_fee = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=250,
            stop_entry_percent=1,
            stop_now_percent=1,
            fee_percent=0.5,
        )
        zero_fee_repeat = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=250,
            stop_entry_percent=1,
            stop_now_percent=1,
            fee_percent=0,
        )

        self.assertFalse(
            math.isclose(zero_fee["target_volume"], with_fee["target_volume"], rel_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(
                zero_fee["target_volume"],
                zero_fee_repeat["target_volume"],
                rel_tol=1e-9,
            )
        )

    def test_in_limit_when_position_was_opened_by_entry_stop_risk(self):
        # User scenario:
        # position was opened correctly by entry-stop risk,
        # then price moved and current-stop distance increased.
        # Must remain in-limit, not force reduction.
        deposit = 44
        risk_pct = 1
        stop_entry = 0.54
        current_volume = 72.1

        result = calculate_position_adjustment(
            deposit=deposit,
            target_risk_percent=risk_pct,
            current_volume=current_volume,
            stop_entry_percent=stop_entry,
            stop_now_percent=0.9,
            fee_percent=0.07,
            tolerance_cash=0.001,
        )

        self.assertEqual(result["action"], "in_limit")
        self.assertTrue(math.isclose(result["delta_abs"], 0.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(result["current_risk_cash"], 0.43981, rel_tol=1e-5))

    def test_add_uses_current_stop_distance(self):
        # Existing risk is measured by entry stop (1%),
        # additional size is measured by current stop distance (5%).
        result = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=100,
            stop_entry_percent=1,
            stop_now_percent=5,
            fee_percent=0,
        )

        self.assertEqual(result["action"], "add")
        # Existing risk = $1, target risk = $20, delta cash = $19,
        # add volume at 5% risk-per-volume => 380
        self.assertTrue(math.isclose(result["delta_abs"], 380.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(result["target_volume"], 480.0, rel_tol=1e-9))

    def test_reduce_uses_entry_stop_distance(self):
        result = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=1,
            current_volume=400,
            stop_entry_percent=5,
            stop_now_percent=5,
            fee_percent=0,
        )

        self.assertEqual(result["action"], "reduce")
        self.assertTrue(math.isclose(result["target_volume"], 200.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(result["delta_abs"], 200.0, rel_tol=1e-9))

    def test_in_limit_with_cash_tolerance(self):
        result = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=200.5,
            stop_entry_percent=10,
            stop_now_percent=5,
            fee_percent=0,
            tolerance_cash=0.1,
        )

        # target risk cash = $20, current risk cash = $20.05, diff = $0.05
        self.assertEqual(result["action"], "in_limit")
        self.assertTrue(math.isclose(result["delta_abs"], 0.0, rel_tol=1e-9))

    def test_short_and_long_are_symmetric_by_percent_distance(self):
        # stop percents are absolute distances; sign does not matter.
        long_like = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=500,
            stop_entry_percent=3,
            stop_now_percent=5,
            fee_percent=0,
        )
        short_like = calculate_position_adjustment(
            deposit=1000,
            target_risk_percent=2,
            current_volume=500,
            stop_entry_percent=-3,
            stop_now_percent=-5,
            fee_percent=0,
        )

        self.assertTrue(math.isclose(long_like["target_volume"], short_like["target_volume"], rel_tol=1e-9))
        self.assertEqual(long_like["action"], short_like["action"])

    def test_fee_settings_preserve_custom_maker_value(self):
        normalized = main.RiskVolumeApp._normalize_fee_settings({
            "fee_percent": 0.07,
            "fee_taker": 0.05,
            "fee_maker": 0.02,
        })

        self.assertEqual(normalized["fee_taker"], 0.05)
        self.assertEqual(normalized["fee_maker"], 0.02)
        self.assertEqual(normalized["fee_percent"], 0.07)


if __name__ == "__main__":
    unittest.main()
