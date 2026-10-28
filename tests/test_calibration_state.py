import unittest

from calibration_state import (
    CALIBRATION_RESET_MARKER_KEY,
    CALIBRATION_RESET_VERSION,
    reset_terminal_calibration_state,
)


class CalibrationStateTests(unittest.TestCase):
    def test_reset_clears_all_calibration_points_for_fresh_build(self):
        settings = {
            "points": [[1, 2]],
            "calc_points_profit_forge": [[3, 4]],
            "calc_points_metascalp": [[5, 6]],
            "calc_points_tigertrade": [[7, 8]],
            "calc_points_surf": [[9, 10]],
            "calc_points_vataga": [[11, 12]],
            "pf_glasses_points": {"1": [[1, 2]]},
            "metascalp_glasses_points": {"1": [[3, 4]]},
            "tiger_glasses_points": {"1": [[5, 6]]},
            "tiger_glasses_open_points": {"1": [7, 8]},
            "tiger_glasses_close_points": {"1": [9, 10]},
            "surf_glasses_points": {"1": [[11, 12]]},
            "surf_glasses_open_points": {"1": [13, 14]},
            "surf_glasses_accept_points": {"1": [15, 16]},
            "vataga_glasses_points": {"1": [[17, 18]]},
            "vataga_glasses_open_points": {"1": [19, 20]},
            "tiger_open_point": [1, 2],
            "tiger_close_point": [3, 4],
            "surf_open_point": [5, 6],
            "surf_accept_point": [7, 8],
            "vataga_open_point": [9, 10],
            "pf_glasses_count": 3,
            "pf_active_glass": 2,
            "pf_selected_glasses": [1, 2],
        }

        changed = reset_terminal_calibration_state(settings)

        self.assertTrue(changed)
        self.assertEqual(settings["points"], [])
        self.assertEqual(settings["calc_points_profit_forge"], [])
        self.assertEqual(settings["calc_points_metascalp"], [])
        self.assertEqual(settings["calc_points_tigertrade"], [])
        self.assertEqual(settings["calc_points_surf"], [])
        self.assertEqual(settings["calc_points_vataga"], [])
        self.assertEqual(settings["pf_glasses_points"], {})
        self.assertEqual(settings["metascalp_glasses_points"], {})
        self.assertEqual(settings["tiger_glasses_points"], {})
        self.assertEqual(settings["tiger_glasses_open_points"], {})
        self.assertEqual(settings["tiger_glasses_close_points"], {})
        self.assertEqual(settings["surf_glasses_points"], {})
        self.assertEqual(settings["surf_glasses_open_points"], {})
        self.assertEqual(settings["surf_glasses_accept_points"], {})
        self.assertEqual(settings["vataga_glasses_points"], {})
        self.assertEqual(settings["vataga_glasses_open_points"], {})
        self.assertIsNone(settings["tiger_open_point"])
        self.assertIsNone(settings["tiger_close_point"])
        self.assertIsNone(settings["surf_open_point"])
        self.assertIsNone(settings["surf_accept_point"])
        self.assertIsNone(settings["vataga_open_point"])
        self.assertEqual(settings["pf_glasses_count"], 1)
        self.assertEqual(settings["pf_active_glass"], 1)
        self.assertEqual(settings["pf_selected_glasses"], [1])
        self.assertFalse(settings["pf_show_preview_frames"])
        self.assertEqual(
            settings[CALIBRATION_RESET_MARKER_KEY],
            CALIBRATION_RESET_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
