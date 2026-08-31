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

__version__ = "0.1"

# Logging Configuration
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

@dataclass
class WeeklyCalcData:
    expenses: float
    stock_price: float
    bear_active: bool
    calm_fund: float

@dataclass
class CalcData:
    port_start: float
    weekly_exp: float
    inflation_annual: float
    interest_annual: float
    calm_weeks: int
    bear_num: int

@dataclass
class BearBuf:
    total: float
    calm_fund: float
    bear_remaining: int

@dataclass
class BearStart:
    start_date: str
    start_week: int
    recovery_week: int

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
        left_panel = ttk.Frame(main_container)
        left_panel.grid(row=0, column=0, sticky="ns", padx=5)

        left_panel.rowconfigure(0, weight=1)
        left_panel.columnconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_panel, highlightthickness=0, width=320)
        left_scrollbar = ttk.Scrollbar(
            left_panel,
            orient=tk.VERTICAL,
            command=left_canvas.yview
        )
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scrollbar.grid(row=0, column=1, sticky="ns")

        left_container = ttk.Frame(left_canvas)
        left_window = left_canvas.create_window(
            (0, 0),
            window=left_container,
            anchor="nw"
        )

        def _on_left_container_configure(_event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _on_left_canvas_configure(event):
            left_canvas.itemconfigure(left_window, width=event.width)

        left_container.bind("<Configure>", _on_left_container_configure)
        left_canvas.bind("<Configure>", _on_left_canvas_configure)

        def _on_left_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_left_mousewheel(_event):
            left_canvas.bind_all("<MouseWheel>", _on_left_mousewheel)

        def _unbind_left_mousewheel(_event):
            left_canvas.unbind_all("<MouseWheel>")

        left_canvas.bind("<Enter>", _bind_left_mousewheel)
        left_canvas.bind("<Leave>", _unbind_left_mousewheel)

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
        ttk.Label(inputs_frame, text="Bear Market Number").grid(
            row=5, column=0, sticky="w", padx=(0, 10), pady=4
        )

        self.portfolio_start_val = tk.StringVar(value="2000000")
        self.weekly_expenses_val = tk.StringVar(value="2000")
        self.annual_inflation_rate_val = tk.StringVar(value="3")
        self.annual_interest_rate_val = tk.StringVar(value="1")
        self.bear_calm_weeks_val = tk.StringVar(value="26")
        self.bear_market_num_val = tk.StringVar(value="0")

        vcmd_int = (self.root.register(self.validate_integer_entry), "%P")
        vcmd_float = (self.root.register(self.validate_float_entry), "%P")

        self.portfolio_start_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.portfolio_start_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_int
        )
        self.weekly_expenses_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.weekly_expenses_val,
            width=14,
            justify=tk.RIGHT,
            validate="key",
            validatecommand=vcmd_int
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
        self.bear_market_num_entry = ttk.Entry(
            inputs_frame,
            textvariable=self.bear_market_num_val,
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
        self.bear_market_num_entry.grid(row=5, column=1, sticky="ew", pady=4)

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
        right_panel = ttk.Frame(main_container)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=5)

        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)

        graph_canvas = tk.Canvas(right_panel, highlightthickness=0)
        graph_scrollbar = ttk.Scrollbar(
            right_panel,
            orient=tk.VERTICAL,
            command=graph_canvas.yview
        )
        graph_canvas.configure(yscrollcommand=graph_scrollbar.set)

        graph_canvas.grid(row=0, column=0, sticky="nsew")
        graph_scrollbar.grid(row=0, column=1, sticky="ns")

        graph_container = ttk.Frame(graph_canvas)
        graph_container.columnconfigure(0, weight=1)
        graph_window = graph_canvas.create_window(
            (0, 0),
            window=graph_container,
            anchor="nw"
        )

        def _on_graph_container_configure(_event):
            graph_canvas.configure(scrollregion=graph_canvas.bbox("all"))

        def _on_graph_canvas_configure(event):
            graph_canvas.itemconfigure(graph_window, width=event.width)

        graph_container.bind("<Configure>", _on_graph_container_configure)
        graph_canvas.bind("<Configure>", _on_graph_canvas_configure)

        def _on_graph_mousewheel(event):
            graph_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_graph_mousewheel(_event):
            graph_canvas.bind_all("<MouseWheel>", _on_graph_mousewheel)

        def _unbind_graph_mousewheel(_event):
            graph_canvas.unbind_all("<MouseWheel>")

        graph_canvas.bind("<Enter>", _bind_graph_mousewheel)
        graph_canvas.bind("<Leave>", _unbind_graph_mousewheel)

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
            # integer or float?
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
            (self.bear_calm_weeks_val.get(), "Bear Calm Amount",True, True),
            (self.bear_market_num_val.get(), "Bear Market Num", True, True),
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
    
    def weekly_expense_stock_calc(self, weekly:WeeklyCalcData):
        """
        Determine how many stocks need to be sold to cover expenses. Utilize
        the bear calming funds if in a bear market.

        @attention bear_calm_funds are mutated in this method

        @return the number of stocks that need to be sold
        """
        exps = weekly.expenses

        if not weekly.bear_active:
            return exps / weekly.stock_price

        # if it is a bear market, try and use bear calming $$
        if weekly.calm_fund >= exps:
            # no stocks are needed to pay expenses
            weekly.calm_fund -= exps
            return 0
        
        elif weekly.calm_fund > 0:
            # use the remaining bear calming $$ and sell stocks for the rest
            exps -= weekly.calm_fund
            weekly.calm_fund = 0
            return exps / weekly.stock_price

        else:
            # no bear calming $$ left, sell stocks
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
            self.log_msg(f"Bear markets: {self.results['bear_num_total']}")
            self.log_msg(f"Bear market dates: {self.results['bear_dates']}")
            self.log_msg(f"Bear calm amount: {self.results['bear_calm']:.2f}")
            self.log_msg(f"Bear buf start: {self.results['bb_start']:.2f}")
            self.log_msg(f"Bear buf end: {self.results['bb_end']:.2f}\n\n")

        except Exception as e:
            self.log_err(f"{type(e).__name__}: {e}")
                      

    def _find_bear_drop_start(self, stock_val_list, start, end):
        """
        Return the index where a bear market starts in the current analysis
        window, or None if no start is found.
        """
        window_values = stock_val_list[start:end]
        high_val = max(window_values)
        if high_val <= 0:
            raise ValueError("Stock price <= 0!")
        
        high_index = start + window_values.index(high_val)
        
        drop_val = high_val * (1 - BEAR_MARKET_DROP_THRESHOLD)

        for index in range(high_index, end):
            if stock_val_list[index] <= drop_val:
                return index

        return None

    def bear_recovery_calc(self, high_index, stock_val_list):
        """
        Evaluate stock prices during a bear market to see if a recovery has been
        reached (stock price >= previous high immediately before the bear market)
        """
        stock_val_high = stock_val_list[high_index]

        for week in range(high_index + 1, len(stock_val_list)):
            if stock_val_list[week] >= stock_val_high:
                # recovery has been reached
                return week
            
        return 0
            

    def bear_analyze(self, 
                     stock_val_list, 
                     stock_date_list, 
                     bear_start_list, 
                     bear_starts):
        """
        Analyze the stock prices and detect a bear market start: 
        20% drop in price from recent 10 week highs. Calculate the 
        recovery date (when the stock price matches the previous high
        for the period)

        """
        # initialize the bear start list to all False
        bear_start_list[:] = [False] * len(stock_val_list)

        if any(value <= 0.0 for value in stock_val_list):
            self.log_err("Stock price <= 0!")
            return None

        bear_num = 0
        start = 0
        end = start + BEAR_MARKET_LOOK_BACK_WEEKS
        while end <= len(stock_val_list):
            try:
                bear_start_index = self._find_bear_drop_start(stock_val_list, start, end)
            except ValueError as exc:
                self.log_err(str(exc))
                return None
            
            if bear_start_index is not None:

                if bear_start_index <= start:
                    msg = "Invalid index in bear start calculations"
                    self.log_err(msg)
                    return None

                # find the week that the stock value recovers from the high before the
                # bear started
                high_index = bear_start_index - 1
                recovery_week_index = self.bear_recovery_calc(high_index, stock_val_list)

                bear_start = BearStart(stock_date_list[bear_start_index],
                                       bear_start_index,
                                       recovery_week_index)

                bear_start_list[bear_start_index] = True
                bear_starts.append(bear_start)
                bear_num += 1
                start = bear_start_index + 1
            else:
                start += 1

            end = start + BEAR_MARKET_LOOK_BACK_WEEKS

        return bear_num

    def stock_lists_get(self):
        """Return weekly index and stock-value lists for analysis."""
        if len(self.stock_date) != len(self.stock_value):
            self.log_err("Stock date and stock value lists are not the same length")
            return [], []

        # create lists of the weekly dates and weekly stock prices
        # that were read from the input file
        week_list = list(range(len(self.stock_date)))
        try:
            stock_val_list = [float(val) for val in self.stock_value]
        except (TypeError, ValueError):
            self.log_err("Historical stock values must be valid numbers.")
            return [], []

        if any(value <= 0 for value in stock_val_list):
            self.log_err("Historical stock values must be greater than 0.")
            return [], []

        return week_list, stock_val_list

    def bear_calm_funds_refresh(self, bb:BearBuf):
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

    def analyze_historical_data(
        self,
        calc: CalcData,
        log_results=True
    ):
        """
        Calculate a portfolio value over time, by evaluating every week and
        subtracting expenses either through selling stocks or using bear calming
        funds during a bear market
        """
        try:
            # all calculator lists must match the stock value list length
            list_len = len(self.stock_value)

            # a single bear calm fund == number of weeks * weekly expenses
            weekly_exp_start = calc.weekly_exp
            calm_fund_start = calc.calm_weeks * weekly_exp_start

            # analyze the data for bear markets
            bear_start_list = []
            bear_starts = []
            self.bear_analyze(self.stock_value, 
                              self.stock_date, 
                              bear_start_list, 
                              bear_starts)

            # calculate the total bear buf (bear calm funds * bear num chosen on UI)
            bear_buf_start = calc.bear_num * calm_fund_start

            if bear_buf_start > calc.port_start:
                msg = f"Not enough $$ in portfolio to fund the bear buf. "
                msg += f"Funds needed: calm weeks {calc.calm_weeks}, total {bear_buf_start}"
                self.log_err(msg)
                return

            # the bear buf is funded through the portfolio, deduct that money
            # before calculating the starting stock number
            stock_num_remaining = (calc.port_start - bear_buf_start) / self.stock_value[0]

            # initialize weekly processing variables
            weekly_expense_val = calc.weekly_exp
            weekly_port_val = calc.port_start
            inflation_weekly = self.weekly_rate_from_annual(calc.inflation_annual)
            interest_weekly = self.weekly_rate_from_annual(calc.interest_annual)
            port_val_weekly_list = [weekly_port_val]
            bear_active = False

            bear_buf = BearBuf(total=bear_buf_start,
                               calm_fund=0.0,
                               bear_remaining=calc.bear_num)
    
            # for every week, determine how many stocks need to be sold for expenses
            for week in range(1, list_len):
                stock_price = self.stock_value[week]

                # if a bear start is detected, expenses are paid from the bear calm fund
                # if it is available
                if bear_start_list[week]:
                    bear_active = True
                    self.bear_calm_funds_refresh(bear_buf)

                if not (bear_buf.calm_fund > 0.0):
                    bear_active = False

                weekly = WeeklyCalcData(expenses=weekly_expense_val,
                                        stock_price=stock_price,
                                        bear_active=bear_active,
                                        calm_fund=bear_buf.calm_fund)
                
                expense_stock_num = self.weekly_expense_stock_calc(weekly)

                if expense_stock_num <= stock_num_remaining:
                    stock_num_remaining -= expense_stock_num
                elif stock_num_remaining > 0:
                    stock_num_remaining = 0

                # adjust the bear buf total if bear calm funds were used
                if bear_buf.calm_fund > weekly.calm_fund:
                    bear_buf.total -= (bear_buf.calm_fund - weekly.calm_fund)

                bear_buf.calm_fund = weekly.calm_fund

                # add the weekly interest
                interest = bear_buf.total * interest_weekly
                bear_buf.total += interest

                # add the weekly portfolio value for this week
                weekly_port_val = (stock_num_remaining * self.stock_value[week]) + bear_buf.total
                port_val_weekly_list.append(weekly_port_val)

                # add inflation to weekly expenses
                weekly_expense_val += (weekly_expense_val * inflation_weekly)

            if len(port_val_weekly_list) != list_len:
                msg = "Lists must be the same length: "
                msg += f"port val list length: {len(port_val_weekly_list)}, "
                msg += f"stock list length: {list_len}"
                self.log_err(msg)
                return

            if log_results:
                # log the results of the analysis
                self.results["date_range"]       = f"{self.stock_date[0]} to {self.stock_date[-1]}"
                self.results["port_total_start"] = calc.port_start
                self.results["inflation_annual"] = calc.inflation_annual
                self.results["inflation_weekly"] = inflation_weekly
                self.results["interest_annual"]  = calc.interest_annual
                self.results["interest_weekly"]  = interest_weekly
                self.results["expense_start"]    = weekly_exp_start
                self.results["bear_calm"]        = calm_fund_start
                self.results["bear_num_total"]   = calc.bear_num
                self.results["bb_start"]         = bear_buf_start
                self.results["bb_end"]           = bear_buf.total
                self.results["expense_end"]      = weekly_expense_val
                self.results["port_total_end"]   = port_val_weekly_list[-1]

                self.results["bear_dates"] = [
                    item.start_date for item in (bear_starts or []) if hasattr(item, "start_date")
                ]
                  
                self.log_results()

                # display the data on the plot
                x_label = f"Weeks from {self.stock_date[0]} to {self.stock_date[-1]}"
                self.display_data(x_label, range(0, len(port_val_weekly_list)), port_val_weekly_list)

            # return the final portfolio ending value
            return port_val_weekly_list[-1]

        except Exception as e:
            self.log_err(f"{type(e).__name__}: {e}")

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
        """Read the historical data"""
        try:
            self.history_clear()

            if not self.input_file:
                self.log_err("No input file chosen")
                return

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
            self.log_err((
                f"Error when reading historical data from {self.input_file}. "
                "Verify the file exists and contains valid date/value rows."
            ))

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
                bear_calm_weeks,
                bear_market_num
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
                             calm_weeks=bear_calm_weeks,
                             bear_num=bear_market_num)


        if not self.auto_run_var.get():
            # run a single pass and display the results on the plot
            self.analyze_historical_data(calc_data, log_results=True)

        else:
            # evaluate the portfolio with different bear calming weeks to 
            # determine the largest final portfolio
            calc_data.calm_weeks = 0
            port_end_previous = 0
            port_end = 1

            while (calc_data.calm_weeks <= CALM_WEEK_MAX):

                port_end = self.analyze_historical_data(calc_data, log_results=False)

                if port_end >= port_end_previous:
                    port_end_previous = port_end
                    calc_data.calm_weeks += 1
                else:
                    # use the previous # of calm weeks, it resulted in a higher ending portfolio
                    if calc_data.calm_weeks > 0:
                        calc_data.calm_weeks -= 1

                    break

            if calc_data.calm_weeks > CALM_WEEK_MAX:
                msg = "Auto run stopped before finding optimal calming weeks."
                self.log_msg(msg)
            else:
                port_end = self.analyze_historical_data(calc_data, log_results=True)
                msg = f"Maximum portfolio of {port_end:.2f}"
                msg += f" found when bear calming weeks are {calc_data.calm_weeks}"
                msg += f" total weeks {calc_data.calm_weeks * calc_data.bear_num}"
                self.log_msg(msg)

def main():
    """Main entry point for the application."""
    root = tk.Tk()
    BearBufUI(root)

    def on_closing():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
