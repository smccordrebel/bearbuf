#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for stocks and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import csv
import logging
import math
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox, ttk
from dataclasses import dataclass
from typing import Optional
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime

__version__ = "0.2"

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700
PLOT_X_LABEL = "Time (weeks)"
PLOT_Y_LABEL = "Portfolio Value"
PLOT_TITLE = "Portfolio"
CALM_WEEK_MAX = 500
BEAR_MARKET_LOOK_BACK_WEEKS = 10
BEAR_MARKET_DROP_THRESHOLD = 0.20


def configure_logging():
    """Set up file + console logging. Called from main(), not at import
    time, so importing this module elsewhere doesn't create a log file
    as a side effect."""
    dt = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_name = f"{dt}_bearbuf_log.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file_name),
            logging.StreamHandler()
        ]
    )


@dataclass
class CalcData:
    port_start: float
    weekly_exp: float
    inflation_annual: float
    interest_annual: float
    calm_weeks: int

@dataclass
class BearBuf:
    total: float
    recovery_week: int

@dataclass
class BearStart:
    start_date: str
    recovery_date: str
    start_week: int
    recovery_week: int

@dataclass
class WeeklyCalcData:
    expenses: float
    stock_price: float
    bear_active: bool
    bb_fund: BearBuf


class AnalysisError(Exception):
    """Raised when a historical-data analysis run cannot produce a result.
    The caller decides how to surface this (a dialog, a log line, or
    aborting an auto-run loop) rather than silently getting back None."""


# ============================================================================
# Bear Buf UI Application
# ============================================================================
class BearBufUI:
    """
    Tkinter GUI for Bear Buf calculations
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Bear Buf Calculator")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.input_file: Optional[str] = None
        self.stock_date = []
        self.stock_value = []
        self.results = {}

        # UI log widget reference
        self.log_text = None

        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.setup_ui()

    def setup_ui(self):
        """Set up the main UI components."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.control_frame = ttk.Frame(self.notebook)
        self.control_frame.rowconfigure(0, weight=1)
        self.control_frame.columnconfigure(0, weight=1)

        self.notebook.add(self.control_frame, text="Bear Buf Calculator")

        self.setup_control_tab()

    # ------------------------------------------------------------------
    # Shared scrollable-frame helper
    # ------------------------------------------------------------------
    def _make_scrollable_frame(self, parent, canvas_kwargs=None):
        """
        Build a vertically scrollable frame (canvas + scrollbar + inner
        container) with mousewheel support bound while the pointer is
        over it. Returns (outer_frame, inner_container) — add your
        widgets to inner_container.
        """
        canvas_kwargs = canvas_kwargs or {}
        outer = ttk.Frame(parent)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, highlightthickness=0, **canvas_kwargs)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas)
        inner.columnconfigure(0, weight=1)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        return outer, inner

    def setup_control_tab(self):
        """Set up the control and monitoring tab."""
        main_container = ttk.Frame(self.control_frame)
        main_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.control_frame.rowconfigure(0, weight=1)
        self.control_frame.columnconfigure(0, weight=1)

        # top row holds left/right panels; bottom row holds log output
        main_container.rowconfigure(0, weight=1)
        main_container.rowconfigure(1, weight=0)
        main_container.columnconfigure(0, weight=0)
        main_container.columnconfigure(1, weight=1)

        # ------------------------------------------------------------------
        # Left panel
        # ------------------------------------------------------------------
        left_panel, left_container = self._make_scrollable_frame(
            main_container, canvas_kwargs={"width": 320}
        )
        left_panel.grid(row=0, column=0, sticky="ns", padx=5)

        calculator_frame = ttk.LabelFrame(left_container, text="Calculator", padding=10)
        calculator_frame.grid(row=0, column=0, sticky="ew", pady=5)
        calculator_frame.columnconfigure(0, weight=1)

        file_input_frame = ttk.LabelFrame(calculator_frame, text="Input File", padding=8)
        file_input_frame.grid(row=0, column=0, sticky="ew", pady=5)
        file_input_frame.columnconfigure(0, weight=0)
        file_input_frame.columnconfigure(1, weight=1)

        self.file_input_button = ttk.Button(
            file_input_frame,
            text="Choose Input File",
            command=self.on_file_button,
            state=tk.NORMAL
        )
        self.file_input_button.grid(row=0, column=0, sticky="ew", padx=2)

        inputs_frame = ttk.LabelFrame(calculator_frame, text="Inputs", padding=8)
        inputs_frame.grid(row=1, column=0, sticky="ew", pady=5)
        inputs_frame.columnconfigure(0, weight=0)
        inputs_frame.columnconfigure(1, weight=1)

        ttk.Label(inputs_frame, text="Starting Portfolio $").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(inputs_frame, text="Weekly Expenses $").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(inputs_frame, text="Annual Inflation Rate %").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(inputs_frame, text="Annual Interest Rate %").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(inputs_frame, text="Bear Calm Weeks").grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=4
        )

        self.portfolio_start_val = tk.StringVar(value="2000000")
        self.weekly_expenses_val = tk.StringVar(value="2000")
        self.annual_inflation_rate_val = tk.StringVar(value="3")
        self.annual_interest_rate_val = tk.StringVar(value="1")
        self.bear_calm_weeks_val = tk.StringVar(value="26")

        vcmd_int = (self.root.register(self.validate_integer_entry), "%P")
        vcmd_float = (self.root.register(self.validate_float_entry), "%P")

        # NOTE: dollar fields now use the float validator so cents are
        # accepted (they were previously restricted to whole numbers by
        # the entry validator despite being parsed as floats).
        self.portfolio_start_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.portfolio_start_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_float
        )
        self.weekly_expenses_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.weekly_expenses_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_float
        )
        self.annual_inflation_rate_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.annual_inflation_rate_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_float
        )
        self.annual_interest_rate_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.annual_interest_rate_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_float
        )
        self.bear_calm_weeks_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.bear_calm_weeks_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_int
        )

        self.portfolio_start_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.weekly_expenses_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self.annual_inflation_rate_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self.annual_interest_rate_entry.grid(row=3, column=1, sticky="ew", pady=4)
        self.bear_calm_weeks_entry.grid(row=4, column=1, sticky="ew", pady=4)

        calculator_run_frame = ttk.Frame(calculator_frame)
        calculator_run_frame.grid(row=2, column=0, sticky="ew", pady=4)
        calculator_run_frame.columnconfigure(0, weight=1)

        self.calculator_run_button = ttk.Button(
            calculator_run_frame,
            text="Run Calculator",
            command=self.on_calculator_run,
            state=tk.NORMAL
        )
        self.calculator_run_button.grid(row=0, column=0, sticky="ew", padx=2)

        # auto run checkbox
        self.auto_run_var = tk.BooleanVar(value=False)
        self.auto_run_check = ttk.Checkbutton(
            calculator_run_frame,
            text="Auto Run",
            variable=self.auto_run_var
        )
        self.auto_run_check.grid(row=0, column=1, sticky="ew", padx=2)

        # ------------------------------------------------------------------
        # Right panel
        # ------------------------------------------------------------------
        right_panel, graph_container = self._make_scrollable_frame(main_container)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=5)

        graph_frame_1 = ttk.LabelFrame(
            graph_container,
            text="Portfolio Over Time",
            padding=5
        )
        graph_frame_1.grid(row=0, column=0, sticky="nsew", pady=5)
        graph_frame_1.rowconfigure(0, weight=1)
        graph_frame_1.columnconfigure(0, weight=1)

        self.figure_portfolio = Figure(figsize=(8, 4), dpi=100)
        self.ax_portfolio = self.figure_portfolio.add_subplot(111)
        self.ax_portfolio.set_xlabel(PLOT_X_LABEL)
        self.ax_portfolio.set_ylabel(PLOT_Y_LABEL)
        self.ax_portfolio.set_title(PLOT_TITLE)
        self.ax_portfolio.grid(True, alpha=0.3)

        self.canvas_portfolio = FigureCanvasTkAgg(
            self.figure_portfolio,
            master=graph_frame_1
        )
        self.canvas_portfolio.draw()
        self.canvas_portfolio.get_tk_widget().grid(
            row=0, column=0, sticky="nsew"
        )

        # ------------------------------------------------------------------
        # Bottom log output panel (spans left and right panels)
        # ------------------------------------------------------------------
        log_frame = ttk.LabelFrame(main_container, text="Log Output", padding=5)
        log_frame.grid(
            row=1, column=0, columnspan=2,
            sticky="nsew", padx=5, pady=(5, 0)
        )
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            state=tk.DISABLED
        )
        log_scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")

    def validate_integer_entry(self, proposed: str) -> bool:
        """Allow blank or non-negative integers."""
        if proposed == "":
            return True
        return proposed.isdigit()

    def validate_float_entry(self, proposed: str) -> bool:
        """Allow blank or non-negative float values."""
        if proposed == "":
            return True
        if proposed.count(".") > 1:
            return False
        if proposed == ".":
            return True
        try:
            value = float(proposed)
            return value >= 0
        except ValueError:
            return False

    def parse_positive_number(
        self,
        value: str,
        field_name: str,
        int_expected: bool = False,
        allow_zero: bool = False
    ) -> float:
        """Parse and validate a numeric field."""
        if value.strip() == "":
            raise ValueError(f"{field_name} is required.")

        try:
            if int_expected:
                number = int(value)
            else:
                number = float(value)

        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a valid number.") from exc

        if allow_zero:
            if number < 0:
                raise ValueError(f"{field_name} must be 0 or greater.")
        else:
            if number <= 0:
                raise ValueError(f"{field_name} must be greater than 0.")

        return number

    def validate_inputs(self):
        """Validate all user inputs and return parsed numeric values."""
        fields = (
            (self.portfolio_start_val.get(), "Starting Portfolio", False, False),
            (self.weekly_expenses_val.get(), "Weekly Expenses", False, False),
            (self.annual_inflation_rate_val.get(), "Annual Inflation Rate", False, True),
            (self.annual_interest_rate_val.get(), "Annual Interest Rate", False, True),
            (self.bear_calm_weeks_val.get(), "Bear Calm Weeks", True, True),
        )

        parsed_values = [
            self.parse_positive_number(value, field_name, int_expected, allow_zero=allow_zero)
            for value, field_name, int_expected, allow_zero in fields
        ]
        return tuple(parsed_values)

    def weekly_rate_from_annual(self, annual_rate: float) -> float:
        """Calculate a weekly rate from an annual rate"""
        rate = annual_rate / 100
        weekly_rate = (1 + rate) ** (1 / 52) - 1
        return weekly_rate

    def weekly_expense_stock_calc(self, weekly: WeeklyCalcData):
        """
        Determine how many stocks need to be sold to cover expenses. Utilize
        the bear buf if in a bear market.

        @attention bear buf funds are mutated in this method

        @return the number of stocks that need to be sold
        """
        exps = weekly.expenses

        if not weekly.bear_active:
            return exps / weekly.stock_price

        # if it is a bear market, try and use bear buf $$
        if weekly.bb_fund.total >= exps:
            # no stocks are needed to pay expenses
            weekly.bb_fund.total -= exps
            return 0

        elif weekly.bb_fund.total > 0:
            # use the remaining bear buf $$ and sell stocks for the rest
            exps -= weekly.bb_fund.total
            weekly.bb_fund.total = 0
            return exps / weekly.stock_price

        else:
            # no bear buf $$ left, sell stocks
            return exps / weekly.stock_price

    def append_log_output(self, level: str, msg: str):
        """Append log output to the UI log window."""
        if self.log_text is None:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} {level} - {msg}\n"

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def log_err(self, msg):
        """Log an error message"""
        logger.error(msg)
        self.append_log_output("ERROR", msg)
        messagebox.showerror("Error", msg)

    def log_msg(self, msg):
        """Log a message"""
        logger.info(msg)
        self.append_log_output("INFO", msg)

    def log_results(self):
        """Log all results of a portfolio analysis"""
        try:
            self.log_msg(f"Historical data range: {self.results['date_range']}")
            self.log_msg(f"Portfolio start value: {self.results['port_total_start']:.2f}")
            self.log_msg(f"Portfolio end value: {self.results['port_total_end']:.2f}")
            self.log_msg(f"Annual inflation rate: {self.results['inflation_annual']}")
            self.log_msg(f"Weekly inflation rate: {self.results['inflation_weekly']:.8f}")
            self.log_msg(f"Annual interest rate: {self.results['interest_annual']}")
            self.log_msg(f"Weekly interest rate: {self.results['interest_weekly']:.8f}")
            self.log_msg(f"Expense start: {self.results['expense_start']:.2f}")
            self.log_msg(f"Expense end: {self.results['expense_end']:.2f}")
            self.log_msg(f"Bear market dates: {self.results['bear_dates']}")
            self.log_msg(f"Bear recovery dates: {self.results['bear_recovery_dates']}")
            self.log_msg(f"Bear buf start: {self.results['bb_start']:.2f}")
            self.log_msg(f"Bear buf end: {self.results['bb_end']:.2f}\n\n")

        except Exception as e:
            self.log_err(f"{type(e).__name__}: {e}")

    def _find_bear_drop_start(self, stock_val_list, start, end):
        """
        Return the index where a bear market starts in the current analysis
        window, along with the index of the high value, or None if no start is found.
        """
        window_values = stock_val_list[start:end]
        high_val = max(window_values)
        if high_val <= 0:
            raise ValueError("Stock price <= 0!")

        high_index = start + window_values.index(high_val)

        drop_val = high_val * (1 - BEAR_MARKET_DROP_THRESHOLD)

        for bear_index in range(high_index, end):
            if stock_val_list[bear_index] <= drop_val:
                return bear_index, high_index

        return None, None

    def bear_recovery_calc(self, bear_start_index, high_index, stock_val_list):
        """
        Evaluate stock prices during a bear market to see if a recovery has
        been reached (stock price >= previous high immediately before the
        bear market).

        @return the index of the recovery week, or None if no recovery is
        found before the end of the data. (Previously this returned 0 as
        the "not found" sentinel; None is used instead so it can't be
        confused with a legitimate index if the search range ever changes.)
        """
        stock_val_high = stock_val_list[high_index]

        for week in range(bear_start_index + 1, len(stock_val_list)):
            if stock_val_list[week] >= stock_val_high:
                # recovery has been reached
                return week

        return None

    def bear_analyze(self,
                     stock_val_list,
                     stock_date_list,
                     bear_starts):
        """
        Analyze the stock prices and detect a bear market start:
        20% drop in price from recent 10 week highs. Calculate the
        recovery date (when the stock price matches the previous high
        for the period)
        """

        if any(value <= 0.0 for value in stock_val_list):
            self.log_err("Stock price <= 0!")
            return None

        start = 0
        end = start + BEAR_MARKET_LOOK_BACK_WEEKS
        while end < len(stock_val_list):
            try:
                bear_start_index, high_index = self._find_bear_drop_start(stock_val_list, start, end)
            except ValueError as exc:
                self.log_err(str(exc))
                return None

            if bear_start_index is not None:

                # find the week that the stock value recovers
                recovery_week_index = self.bear_recovery_calc(bear_start_index, high_index, stock_val_list)
                start_date = stock_date_list[bear_start_index]

                if recovery_week_index is None:
                    recovery_date = "No recovery"
                else:
                    recovery_date = stock_date_list[recovery_week_index]

                bear_start = BearStart(start_date,
                                       recovery_date,
                                       bear_start_index,
                                       recovery_week_index)

                bear_starts.append(bear_start)
                start = bear_start_index + 1
            else:
                start += 1

            end = start + BEAR_MARKET_LOOK_BACK_WEEKS

    def bear_buf_refresh(self, bb: BearBuf):
        """If there are remaining bear buf funds, refresh the bear calming funds"""
        if bb.bear_remaining > 0:
            if bb.total > 0.0:
                bb.calm_fund = bb.total / bb.bear_remaining
            else:
                bb.calm_fund = 0.0

            bb.bear_remaining -= 1
        else:
            bb.calm_fund = 0
            bb.bear_remaining = 0

    def check_for_bear_start(self, week_index, bb:BearBuf, bear_starts):
        """
        Check to see if the historical data from this week matches a bear market start.
        """
        for starts in bear_starts:
            if starts.start_week == week_index:
                bb.recovery_week = starts.recovery_week
                return True

        return False

    def check_for_bear_recovery(self, week_index, bb:BearBuf):
        """
        Check to see if the historical data from this week shows a recovery from a bear market
        """
        if bb.recovery_week is None:
            return False
        
        elif bb.recovery_week == week_index:
            return True
        
        else:
            return False
    
    def bear_buf_refresh(self,
                          bb:BearBuf, 
                          stock_val: float, 
                          remaining_stock_num: float, 
                          calm_weeks: int, 
                          expenses: float):
        
        """ Refresh the bear buf by selling stocks """

        if calm_weeks == 0:
            return remaining_stock_num

        # there may be remaining $$ in the previous bear buf
        amount = (calm_weeks * expenses) - bb.total
        stocks_needed = amount / stock_val

        # determine the total amount needed based on the current stock price
        if stocks_needed < remaining_stock_num:
            bb.total += amount
            return remaining_stock_num - stocks_needed
        else:
            return remaining_stock_num

    def analyze_historical_data(
        self,
        calc: CalcData,
        log_results=True
    ):
        """
        Calculate a portfolio value over time, by evaluating every week and
        subtracting expenses either through selling stocks or using bear
        calming funds during a bear market.

        @raise AnalysisError if the run cannot produce a result (e.g. the
        bear buf can't be funded, or an unexpected error occurs). Callers
        must handle this rather than assume a numeric return value.
        """
        try:
            # all calculator lists must match the stock value list length
            list_len = len(self.stock_value)

            # analyze the data for bear markets
            bear_starts = []
            self.bear_analyze(self.stock_value,
                              self.stock_date,
                              bear_starts)

             # a single bear buf == number of calm weeks * weekly expenses
            weekly_exp_start = calc.weekly_exp
            bear_buf_start = calc.calm_weeks * weekly_exp_start

            if bear_buf_start > calc.port_start:
                msg = (
                    "Not enough $$ in portfolio to fund the bear buf. "
                    f"Funds needed: calm weeks {calc.calm_weeks}, total {bear_buf_start}"
                )
                self.log_err(msg)
                raise AnalysisError(msg)

            # the bear buf is funded through the portfolio, deduct that money
            # before calculating the starting stock number
            stock_remaining = (calc.port_start - bear_buf_start) / self.stock_value[0]

            # initialize weekly processing variables
            weekly_expense_val = calc.weekly_exp
            weekly_port_val = calc.port_start
            inflation_weekly = self.weekly_rate_from_annual(calc.inflation_annual)
            interest_weekly = self.weekly_rate_from_annual(calc.interest_annual)
            port_val_weekly_list = [weekly_port_val]
            bear_active = False

            # the initial bear buf, once a bear start is encountered, the recovery week
            # is initiliazed
            bear_buf = BearBuf(total=bear_buf_start,
                               recovery_week=None)
    
            # for every week, determine how many stocks need to be sold for expenses
            for week in range(1, list_len):
                stock_val = self.stock_value[week]

                if not bear_active:
                    bear_active = self.check_for_bear_start(week, bear_buf, bear_starts)
                else:
                    if self.check_for_bear_recovery(week, bear_buf):

                        bear_active = False

                        # we have recovered, refresh the bear buf by selling stocks if there
                        # is enough money in the portfolio
                        stock_remaining = self.bear_buf_refresh(bear_buf, 
                                                stock_val,
                                                stock_remaining, 
                                                calc.calm_weeks,
                                                weekly_expense_val)

                weekly = WeeklyCalcData(expenses=weekly_expense_val,
                                        stock_price=stock_val,
                                        bear_active=bear_active,
                                        bb_fund=bear_buf)

                expense_stock_num = self.weekly_expense_stock_calc(weekly)

                if expense_stock_num <= stock_remaining:
                    # we have enough stock to pay for expenses
                    stock_remaining -= expense_stock_num
                else:
                    # we don't have enough stocks, dip into the bear buf if there
                    # is any money left
                    expense_stock_num -= stock_remaining
                    stock_remaining = 0

                    if bear_buf.total > 0.0:
                        needed = weekly_expense_val - (expense_stock_num * stock_val)

                        if bear_buf.total > needed:
                            bear_buf.total -= needed
                        else:
                            bear_buf.total = 0.0

                # add the weekly interest
                interest = bear_buf.total * interest_weekly
                bear_buf.total += interest

                # add the weekly portfolio value for this week
                weekly_port_val = (stock_remaining * stock_val) + bear_buf.total
                port_val_weekly_list.append(weekly_port_val)

                # add inflation to weekly expenses
                weekly_expense_val += (weekly_expense_val * inflation_weekly)

            if len(port_val_weekly_list) != list_len:
                msg = (
                    "Lists must be the same length: "
                    f"port val list length: {len(port_val_weekly_list)}, "
                    f"stock list length: {list_len}"
                )
                self.log_err(msg)
                raise AnalysisError(msg)

            if log_results:
                self.results["date_range"]       = f"{self.stock_date[0]} to {self.stock_date[-1]}"
                self.results["port_total_start"] = calc.port_start
                self.results["inflation_annual"] = calc.inflation_annual
                self.results["inflation_weekly"] = inflation_weekly
                self.results["interest_annual"]  = calc.interest_annual
                self.results["interest_weekly"]  = interest_weekly
                self.results["expense_start"]    = weekly_exp_start
                self.results["bb_start"]         = bear_buf_start
                self.results["bb_end"]           = bear_buf.total
                self.results["expense_end"]      = weekly_expense_val
                self.results["port_total_end"]   = port_val_weekly_list[-1]

                self.results["bear_dates"] = [
                    item.start_date for item in (bear_starts or []) if hasattr(item, "start_date")
                ]

                self.results["bear_recovery_dates"] = [
                    item.recovery_date for item in (bear_starts or []) if hasattr(item, "recovery_date")
                ]

                self.log_results()

                # display the data on the plot
                x_label = f"Weeks from {self.stock_date[0]} to {self.stock_date[-1]}"
                self.display_data(x_label, range(0, len(port_val_weekly_list)), port_val_weekly_list)

            return port_val_weekly_list[-1]

        except AnalysisError:
            raise
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self.log_err(msg)
            raise AnalysisError(msg) from e

    def display_data(self, x_label, week_list, port_val_weekly_list):
        """Display the portfolio analysis data on the graph"""
        title = (
            f"Portfolio start: {self.results['port_total_start']:.2f} "
            f"end: {self.results['port_total_end']:.2f}"
        )

        self.ax_portfolio.clear()
        self.ax_portfolio.plot(
            week_list,
            port_val_weekly_list,
            linestyle="-",
            linewidth=1,
            color="#1f77b4"
        )
        self.ax_portfolio.set_xlabel(x_label)
        self.ax_portfolio.set_ylabel(PLOT_Y_LABEL)
        self.ax_portfolio.set_title(title)
        self.ax_portfolio.grid(True, alpha=0.3)

        self.figure_portfolio.tight_layout()
        self.canvas_portfolio.draw_idle()

    def history_clear(self):
        """Clear history"""
        self.stock_date.clear()
        self.stock_value.clear()

    def historical_data_read(self):
        """Read the historical data. Raises on failure; does not
        swallow exceptions itself (see on_calculator_run)."""
        self.history_clear()

        if not self.input_file:
            raise ValueError("No input file chosen")

        try:
            with open(self.input_file, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    if len(row) < 2:
                        raise ValueError("Historical data row must have a date and value.")

                    date = row[0].strip()
                    stock_value = row[1].strip()
                    if not date:
                        raise ValueError("Historical data row date cannot be blank.")
                    if not stock_value:
                        raise ValueError("Historical data row value cannot be blank.")
                    parsed_value = float(stock_value)
                    if not math.isfinite(parsed_value):
                        raise ValueError("Historical data row value must be finite.")

                    self.stock_date.append(date)
                    self.stock_value.append(parsed_value)

        except Exception as exc:
            self.history_clear()
            logger.error("Historical data read failed for %s: %s", self.input_file, exc)
            raise ValueError(
                f"Error when reading historical data from {self.input_file}. "
                "Verify the file exists and contains valid date/value rows."
            ) from exc

    def on_file_button(self):
        """Choose the input that holds dates and stock prices"""
        file_path = self.input_file_get()
        if file_path:
            self.input_file = file_path
        else:
            self.log_err("No file selected")

    def input_file_get(self):
        """Display a dialogue for file input"""
        file_path = filedialog.askopenfilename(
                    title="Select a file",
                    filetypes=[("CSV Files", "*.csv")]
        )
        return file_path

    def on_calculator_run(self):
        """Run the calculator and display results."""
        try:
            (
                portfolio_start,
                weekly_expenses,
                inflation_annual,
                interest_annual,
                bear_calm_weeks
            ) = self.validate_inputs()
        except ValueError as exc:
            self.log_err(str(exc))
            return

        try:
            self.historical_data_read()
        except ValueError as exc:
            self.log_err(str(exc))
            return

        if not self.stock_date or not self.stock_value:
            return

        calc_data = CalcData(port_start=portfolio_start,
                             weekly_exp=weekly_expenses,
                             inflation_annual=inflation_annual,
                             interest_annual=interest_annual,
                             calm_weeks=bear_calm_weeks)

        if not self.auto_run_var.get():
            try:
                self.analyze_historical_data(calc_data, log_results=True)
            except AnalysisError:
                # already logged inside analyze_historical_data
                return
        else:
            self._run_auto_calibration(calc_data)

    def _run_auto_calibration(self, calc_data: CalcData):
        """
        Evaluate the portfolio with increasing bear-calming weeks to find
        the number of weeks that produces the largest final portfolio
        value. Extracted from on_calculator_run for readability and so
        the AnalysisError handling lives in one place.
        """
        calc_data.calm_weeks = 0
        port_end_previous = 0

        while calc_data.calm_weeks <= CALM_WEEK_MAX:
            try:
                port_end = self.analyze_historical_data(calc_data, log_results=False)
            except AnalysisError:
                # can't evaluate this many calm weeks (e.g. bear buf too
                # expensive) - stop calibrating and fall back to the last
                # good value
                if calc_data.calm_weeks > 0:
                    calc_data.calm_weeks -= 1
                break

            if port_end >= port_end_previous:
                port_end_previous = port_end
                calc_data.calm_weeks += 1
            else:
                if calc_data.calm_weeks > 0:
                    calc_data.calm_weeks -= 1
                break
        else:
            # loop finished without breaking - hit CALM_WEEK_MAX
            self.bear_calm_weeks_val.set(0)
            self.log_msg("Auto run stopped before finding optimal calming weeks.")
            return

        try:
            port_end = self.analyze_historical_data(calc_data, log_results=True)
        except AnalysisError:
            return

        self.bear_calm_weeks_val.set(calc_data.calm_weeks)
        msg = (
            f"Maximum portfolio of {port_end:.2f} found when bear calming "
            f"weeks are {calc_data.calm_weeks}"
        )
        self.log_msg(msg)


def main():
    """Main entry point for the application."""
    configure_logging()
    root = tk.Tk()
    BearBufUI(root)

    def on_closing():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()