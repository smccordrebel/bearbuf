import importlib
import io
import sys
import types
import unittest
from unittest.mock import Mock, patch


def install_gui_stubs():
    tkinter = types.ModuleType("tkinter")
    tkinter.Tk = type("Tk", (), {})
    tkinter.Canvas = type("Canvas", (), {})
    tkinter.VERTICAL = "vertical"

    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Notebook", "Frame", "Scrollbar", "Label", "Entry", "Button"):
        setattr(ttk, name, type(name, (), {}))

    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.showerror = Mock()

    tkinter.ttk = ttk
    tkinter.messagebox = messagebox

    backend_tkagg = types.ModuleType("matplotlib.backends.backend_tkagg")
    backend_tkagg.FigureCanvasTkAgg = type("FigureCanvasTkAgg", (), {})

    figure_module = types.ModuleType("matplotlib.figure")
    figure_module.Figure = type("Figure", (), {})

    sys.modules["tkinter"] = tkinter
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["matplotlib.backends.backend_tkagg"] = backend_tkagg
    sys.modules["matplotlib.figure"] = figure_module


install_gui_stubs()
if "bearbuf" in sys.modules:
    del sys.modules["bearbuf"]
bearbuf = importlib.import_module("bearbuf")


def make_ui():
    ui = object.__new__(bearbuf.BearBufUI)
    ui.stock_date = []
    ui.stock_value = []
    ui.results = {}
    ui.log_err = Mock()
    return ui


class TestInputValidation(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()

    def test_validate_integer_entry_accepts_blank_and_digits(self):
        self.assertTrue(self.ui.validate_integer_entry(""))
        self.assertTrue(self.ui.validate_integer_entry("0"))
        self.assertTrue(self.ui.validate_integer_entry("123"))

    def test_validate_integer_entry_rejects_invalid_values(self):
        self.assertFalse(self.ui.validate_integer_entry("-1"))
        self.assertFalse(self.ui.validate_integer_entry("12.3"))
        self.assertFalse(self.ui.validate_integer_entry("abc"))

    def test_validate_float_entry_accepts_valid_values(self):
        self.assertTrue(self.ui.validate_float_entry(""))
        self.assertTrue(self.ui.validate_float_entry("."))
        self.assertTrue(self.ui.validate_float_entry("0"))
        self.assertTrue(self.ui.validate_float_entry("123.45"))

    def test_validate_float_entry_rejects_invalid_values(self):
        self.assertFalse(self.ui.validate_float_entry("-0.1"))
        self.assertFalse(self.ui.validate_float_entry("1.2.3"))
        self.assertFalse(self.ui.validate_float_entry("abc"))

    def test_parse_positive_number_accepts_positive_and_zero_when_allowed(self):
        self.assertEqual(
            self.ui.parse_positive_number("12.5", "Field"),
            12.5
        )
        self.assertEqual(
            self.ui.parse_positive_number("0", "Field", allow_zero=True),
            0
        )

    def test_parse_positive_number_rejects_missing_invalid_and_negative_values(self):
        with self.assertRaisesRegex(ValueError, "Field is required."):
            self.ui.parse_positive_number("  ", "Field")

        with self.assertRaisesRegex(ValueError, "Field must be a valid number."):
            self.ui.parse_positive_number("abc", "Field")

        with self.assertRaisesRegex(ValueError, "Field must be greater than 0."):
            self.ui.parse_positive_number("0", "Field")

        with self.assertRaisesRegex(ValueError, "Field must be 0 or greater."):
            self.ui.parse_positive_number("-1", "Field", allow_zero=True)


class TestRateCalculations(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()

    def test_weekly_rate_from_annual_handles_core_rates(self):
        self.assertEqual(self.ui.weekly_rate_from_annual(0), 0)
        self.assertAlmostEqual(
            self.ui.weekly_rate_from_annual(100),
            (2 ** (1 / 52)) - 1
        )
        self.assertAlmostEqual(
            self.ui.weekly_rate_from_annual(500),
            (6 ** (1 / 52)) - 1
        )


class TestBearMarketDetection(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()

    def test_bear_start_analyze_detects_twenty_percent_drop(self):
        prices = [10] * 10 + [8]
        bears = [False] * len(prices)

        bear_num = self.ui.bear_start_analyze(prices, bears)

        self.assertEqual(bear_num, 1)
        self.assertEqual(bears, [False] * 10 + [True])

    def test_bear_start_analyze_returns_zero_for_stable_prices(self):
        prices = [10, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11]
        bears = [True] * len(prices)

        bear_num = self.ui.bear_start_analyze(prices, bears)

        self.assertEqual(bear_num, 0)
        self.assertEqual(bears, [False] * len(prices))

    def test_bear_start_analyze_detects_multiple_bear_markets(self):
        prices = [10] * 10 + [8] + [12] * 9 + [9.5, 9.5]
        bears = [False] * len(prices)

        bear_num = self.ui.bear_start_analyze(prices, bears)

        self.assertEqual(bear_num, 2)
        self.assertTrue(bears[10])
        self.assertTrue(bears[20])

    def test_bear_start_analyze_errors_for_non_positive_prices(self):
        prices = [10] * 9 + [0, 8]
        bears = [False] * len(prices)

        bear_num = self.ui.bear_start_analyze(prices, bears)

        self.assertIsNone(bear_num)
        self.ui.log_err.assert_called_once_with("Stock price <= 0!")
        self.assertEqual(bears, [False] * len(prices))

    def test_bear_start_analyze_handles_small_datasets(self):
        prices = [10, 9.5, 9]
        bears = [True] * len(prices)

        bear_num = self.ui.bear_start_analyze(prices, bears)

        self.assertEqual(bear_num, 0)
        self.assertEqual(bears, [False] * len(prices))


class TestWeeklyExpenseCalculation(unittest.TestCase):
    def test_weekly_expense_stock_calc_without_bear_market(self):
        ui = make_ui()
        weekly = bearbuf.WeeklyExpenses(100, 20, False, 500)

        self.assertEqual(ui.weekly_expense_stock_calc(weekly), 5)
        self.assertEqual(weekly.bear_calm_fund, 500)

    def test_weekly_expense_stock_calc_uses_calm_fund_when_sufficient(self):
        ui = make_ui()
        weekly = bearbuf.WeeklyExpenses(100, 20, True, 150)

        self.assertEqual(ui.weekly_expense_stock_calc(weekly), 0)
        self.assertEqual(weekly.bear_calm_fund, 50)

    def test_weekly_expense_stock_calc_uses_partial_calm_fund(self):
        ui = make_ui()
        weekly = bearbuf.WeeklyExpenses(100, 20, True, 40)

        self.assertEqual(ui.weekly_expense_stock_calc(weekly), 3)
        self.assertEqual(weekly.bear_calm_fund, 0)

    def test_weekly_expense_stock_calc_sells_stock_when_calm_fund_depleted(self):
        ui = make_ui()
        weekly = bearbuf.WeeklyExpenses(100, 20, True, 0)

        self.assertEqual(ui.weekly_expense_stock_calc(weekly), 5)
        self.assertEqual(weekly.bear_calm_fund, 0)


class TestStockListProcessing(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()

    def test_stock_lists_get_returns_week_and_value_lists_for_valid_data(self):
        self.ui.stock_date = ["2024-01-01", "2024-01-08"]
        self.ui.stock_value = ["100", "101.5"]

        weeks, values = self.ui.stock_lists_get()

        self.assertEqual(weeks, [0, 1])
        self.assertEqual(values, [100.0, 101.5])
        self.ui.log_err.assert_not_called()

    def test_stock_lists_get_errors_for_non_positive_prices(self):
        self.ui.stock_date = ["2024-01-01", "2024-01-08"]
        self.ui.stock_value = ["100", "0"]

        weeks, values = self.ui.stock_lists_get()

        self.assertEqual((weeks, values), ([], []))
        self.ui.log_err.assert_called_once_with(
            "Historical stock values must be greater than 0."
        )

    def test_stock_lists_get_errors_for_mismatched_lengths(self):
        self.ui.stock_date = ["2024-01-01", "2024-01-08"]
        self.ui.stock_value = ["100"]

        weeks, values = self.ui.stock_lists_get()

        self.assertEqual((weeks, values), ([], []))
        self.ui.log_err.assert_called_once_with(
            "Stock date and stock value lists are not the same length"
        )


class TestHistoricalDataRead(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()

    def test_historical_data_read_loads_valid_csv(self):
        csv_data = "2024-01-01,100\n2024-01-08,101.5\n"

        with patch("builtins.open", return_value=io.StringIO(csv_data)):
            self.ui.historical_data_read()

        self.assertEqual(self.ui.stock_date, ["2024-01-01", "2024-01-08"])
        self.assertEqual(self.ui.stock_value, ["100", "101.5"])
        self.ui.log_err.assert_not_called()

    def test_historical_data_read_handles_missing_file(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            self.ui.historical_data_read()

        self.assertEqual(self.ui.stock_date, [])
        self.assertEqual(self.ui.stock_value, [])
        self.ui.log_err.assert_called_once()

    def test_historical_data_read_handles_malformed_csv(self):
        csv_data = "2024-01-01,100\n2024-01-08,not-a-number\n"

        with patch("builtins.open", return_value=io.StringIO(csv_data)):
            self.ui.historical_data_read()

        self.assertEqual(self.ui.stock_date, [])
        self.assertEqual(self.ui.stock_value, [])
        self.ui.log_err.assert_called_once()


if __name__ == "__main__":
    unittest.main()
