import unittest

from main import RiskVolumeApp


class FakeTable:
    def __init__(self, values):
        self._items = []
        for v in values:
            class FakeCell:
                def __init__(self, text):
                    self._text = text
                def text(self):
                    return self._text
                def setText(self, text):
                    self._text = text
            self._items.append(FakeCell(v))

    def item(self, row, col):
        if row < 0 or row >= len(self._items) or col != 2:
            return None
        return self._items[row]


class ManualDistributionPersistenceTests(unittest.TestCase):
    def test_get_manual_distribution_keeps_nonzero_fallback_when_snapshot_has_blank_rows(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [10, 20, 30, 40, 50],
            "scalp_manual_multipliers_pos": [10, 0, 0, 0, 0],
            "cells_reversed": False,
            "pos_mode_enabled": False,
        }

        self.assertEqual(app._get_manual_distribution_values(), [10, 20, 30, 40, 50])

    def test_capture_current_distribution_preserves_prior_values_for_blank_cells(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [10, 20, 30, 40, 50],
            "scalp_manual_multipliers_pos": [10, 20, 30, 40, 50],
            "cells_reversed": False,
            "pos_mode_enabled": False,
        }
        app.cells_table = FakeTable(["10", "", "30", "", "50"])

        app._capture_current_manual_distribution(pos_mode=False)

        self.assertEqual(
            app.settings["scalp_manual_multipliers"],
            [10, 20, 30, 40, 50],
        )

    def test_persist_manual_percent_snapshot_keeps_prior_values_for_empty_cells(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [10, 20, 30, 40, 50],
            "scalp_manual_multipliers_pos": [10, 20, 30, 40, 50],
            "cells_reversed": False,
            "pos_mode_enabled": False,
        }
        app.cells_table = FakeTable(["10", "", "30", "", "50"])
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()

        app._persist_manual_percent_snapshot(pos_mode=False)

        self.assertEqual(
            app.settings["scalp_manual_multipliers"],
            [10, 20, 30, 40, 50],
        )

    def test_startup_restore_does_not_save_zero_snapshot_over_manual_values(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [10, 20, 30, 40, 50],
            "scalp_manual_multipliers_pos": [10, 20, 30, 40, 50],
            "cells_reversed": False,
            "pos_mode_enabled": False,
            "scalp_distribution_type": 2,
        }
        app._startup_restore_suppressed = True

        class FakeCell:
            def __init__(self):
                self.text_value = ""
            def text(self):
                return self.text_value
            def setText(self, value):
                self.text_value = value

        class FakeItemChanged:
            def disconnect(self, *args, **kwargs):
                pass
            def connect(self, *args, **kwargs):
                pass

        app.cells_table = type("Table", (), {"itemChanged": FakeItemChanged(), "item": lambda self, row, col: FakeCell()})()
        app.cb_distribution = type(
            "Cb",
            (),
            {"currentIndex": lambda self: 2, "blockSignals": lambda self, value: None, "setCurrentIndex": lambda self, value: None},
        )()
        app.save_cell_settings = lambda: (_ for _ in ()).throw(RuntimeError("startup restore should not persist zero snapshot"))
        app._apply_manual_active_row_flags = lambda: None
        app._update_selected_rows_visuals = lambda: None
        app.update_cell_volumes = lambda: None
        app._get_active_rows_for_table = lambda: set(range(5))
        app.on_table_item_changed = lambda *args, **kwargs: None

        try:
            app._restore_distribution_state(False)
        except RuntimeError as exc:
            self.fail(f"startup restore unexpectedly persisted settings: {exc}")

    def test_manual_row_toggle_preserves_previous_percentage_when_reenabled(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [50, 0, 0, 0, 0],
            "scalp_manual_multipliers_pos": [50, 0, 0, 0, 0],
            "cells_reversed": False,
            "pos_mode_enabled": False,
        }

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell(""), Cell(""), Cell(""), Cell(""), Cell("")]
        app.cells_table = type("Table", (), {"item": lambda self, row, col: rows[row] if col == 2 else None})()
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app._apply_manual_active_row_flags = lambda: None
        app.on_table_item_changed = lambda *args, **kwargs: None

        app._restore_manual_distribution_for_active_rows({0})

        self.assertEqual(rows[0].text(), "50")

    def test_position_mode_keeps_special_100_fallback_only_in_pos_mode(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [0, 0, 0, 0, 0],
            "scalp_manual_multipliers_pos": [0, 0, 0, 0, 0],
            "cells_reversed": False,
            "pos_mode_enabled": True,
        }
        app.pos_adjust_delta = 40.0

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell(""), Cell(""), Cell(""), Cell(""), Cell("")]

        class FakeSignal:
            def connect(self, *args, **kwargs):
                pass
            def disconnect(self, *args, **kwargs):
                pass

        class FakeTable:
            def __init__(self):
                self.itemChanged = FakeSignal()
            def item(self, row, col):
                return rows[row] if col == 2 else None

        app.cells_table = FakeTable()
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app._apply_manual_active_row_flags = lambda: None
        app.on_table_item_changed = lambda *args, **kwargs: None
        app._get_active_rows_for_table = lambda: [0]
        app._update_selected_rows_visuals = lambda: None
        app.update_cell_volumes = lambda: None
        app.save_cell_settings = lambda: None
        app._update_status_text = lambda: None

        app.apply_position_adjustment_to_cell()

        self.assertEqual(rows[0].text(), "100")

    def test_distribution_type_and_manual_values_are_stored_per_mode(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [100, 50, 25, 10, 0],
            "scalp_manual_multipliers_pos": [75, 25, 0, 0, 0],
            "scalp_distribution_type": 0,
            "scalp_distribution_type_pos": 1,
            "cells_reversed": False,
            "pos_mode_enabled": True,
        }
        app.position_target_row_active = None
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app.inp_min_order = type("Inp", (), {"text": lambda self: "6"})()
        app.lbl_cells_count = type("Lbl", (), {"text": lambda self: "5"})()
        app._set_terminal_cells_count = lambda value: None
        app.save_settings = lambda: None

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell("10"), Cell("20"), Cell(""), Cell(""), Cell("")]
        app.cells_table = type("Table", (), {"item": lambda self, row, col: rows[row] if col == 2 else None})()

        app.save_cell_settings()

        self.assertEqual(app.settings["scalp_distribution_type_pos"], 2)
        self.assertEqual(app.settings["scalp_distribution_type"], 0)
        self.assertEqual(app.settings["scalp_manual_multipliers_pos"], [10, 20, 0, 0, 0])
        self.assertEqual(app.settings["scalp_manual_multipliers"], [100, 50, 25, 10, 0])

    def test_manual_row_toggle_does_not_double_reverse_percent_values_when_reversed_order_is_active(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [50, 40, 30, 20, 10],
            "scalp_manual_multipliers_pos": [50, 40, 30, 20, 10],
            "scalp_distribution_type": 2,
            "cells_reversed": True,
            "pos_mode_enabled": False,
        }
        app.position_target_row_active = None
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app._apply_manual_active_row_flags = lambda: None
        app.on_table_item_changed = lambda *args, **kwargs: None

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell("50"), Cell("40"), Cell("30"), Cell("20"), Cell("10")]
        app.cells_table = type(
            "Table",
            (),
            {
                "item": lambda self, row, col: rows[row] if col == 2 else None,
                "itemChanged": type("Signal", (), {"disconnect": lambda self, *a, **k: None, "connect": lambda self, *a, **k: None})(),
            },
        )()

        app._restore_manual_distribution_for_active_rows({0, 1, 2, 4})

        self.assertEqual(rows[0].text(), "50")
        self.assertEqual(rows[1].text(), "40")
        self.assertEqual(rows[2].text(), "30")
        self.assertEqual(rows[4].text(), "10")

    def test_manual_snapshot_is_preserved_when_switching_from_equal_to_manual(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [100, 60, 33, 15, 5],
            "scalp_manual_multipliers_pos": [0, 0, 0, 0, 0],
            "scalp_distribution_type": 0,
            "scalp_distribution_type_pos": 0,
            "cells_reversed": False,
            "pos_mode_enabled": False,
        }
        app.position_target_row_active = None
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 0})()
        app.inp_min_order = type("Inp", (), {"text": lambda self: "6"})()
        app.lbl_cells_count = type("Lbl", (), {"text": lambda self: "5"})()
        app._set_terminal_cells_count = lambda value: None
        app.save_settings = lambda: None

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell("20"), Cell("20"), Cell("20"), Cell("20"), Cell("20")]
        app.cells_table = type("Table", (), {"item": lambda self, row, col: rows[row] if col == 2 else None})()

        app.save_cell_settings()

        self.assertEqual(app.settings["scalp_manual_multipliers"], [100, 60, 33, 15, 5])
        self.assertEqual(app.settings["scalp_distribution_type"], 0)

    def test_manual_toggle_keeps_original_row_values_when_reverse_display_is_active(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "scalp_manual_multipliers": [10, 20, 30, 40, 50],
            "scalp_manual_multipliers_pos": [10, 20, 30, 40, 50],
            "scalp_distribution_type": 2,
            "cells_reversed": True,
            "pos_mode_enabled": False,
        }
        app.position_target_row_active = None
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app.inp_min_order = type("Inp", (), {"text": lambda self: "6"})()
        app.lbl_cells_count = type("Lbl", (), {"text": lambda self: "5"})()
        app._set_terminal_cells_count = lambda value: None
        app.save_settings = lambda: None

        class Cell:
            def __init__(self, text=""):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell("50"), Cell("40"), Cell("30"), Cell(""), Cell("10")]
        app.cells_table = type("Table", (), {"item": lambda self, row, col: rows[row] if col == 2 else None})()

        app.save_cell_settings()

        self.assertEqual(app.settings["scalp_manual_multipliers"], [50, 40, 30, 40, 10])

    def test_toggle_cells_order_reverses_percent_values_with_rows_per_mode(self):
        app = RiskVolumeApp.__new__(RiskVolumeApp)
        app.settings = {
            "cells_reversed": False,
            "cells_reversed_pos": False,
            "pos_mode_enabled": False,
        }
        app.cb_distribution = type("Cb", (), {"currentIndex": lambda self: 2})()
        app.lbl_cells_count = type("Lbl", (), {"text": lambda self: "5"})()
        app.update_cell_volumes = lambda: None
        app.save_cell_settings = lambda: None
        app._update_selected_rows_visuals = lambda: None
        app._apply_manual_active_row_flags = lambda: None
        app.on_table_item_changed = lambda *args, **kwargs: None

        class Cell:
            def __init__(self, text="0"):
                self._text = text
            def text(self):
                return self._text
            def setText(self, value):
                self._text = str(value)

        rows = [Cell("100"), Cell("80"), Cell("60"), Cell("40"), Cell("20")]
        app.cells_table = type(
            "Table",
            (),
            {
                "item": lambda self, row, col: rows[row] if col == 2 else None,
                "itemChanged": type("Signal", (), {"disconnect": lambda self, *a, **k: None, "connect": lambda self, *a, **k: None})(),
            },
        )()

        app.toggle_cells_order()
        self.assertTrue(app.settings["cells_reversed"])
        self.assertFalse(app.settings["cells_reversed_pos"])
        self.assertEqual([row.text() for row in rows], ["20", "40", "60", "80", "100"])

        app.settings["pos_mode_enabled"] = True
        app.toggle_cells_order()
        self.assertTrue(app.settings["cells_reversed"])
        self.assertTrue(app.settings["cells_reversed_pos"])
        self.assertEqual([row.text() for row in rows], ["100", "80", "60", "40", "20"])

        app.settings["pos_mode_enabled"] = False
        app.toggle_cells_order()
        self.assertFalse(app.settings["cells_reversed"])
        self.assertTrue(app.settings["cells_reversed_pos"])
        self.assertEqual([row.text() for row in rows], ["20", "40", "60", "80", "100"])


if __name__ == "__main__":
    unittest.main()
