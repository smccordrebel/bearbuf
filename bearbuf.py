#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for VTSAX and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import csv
import logging
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox, ttk
from dataclasses import dataclass
from typing import Optional, TextIO
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
BEAR_CALM_WEEK_MAX = 52

@dataclass
class WeeklyCalcData:
    expenses: float
    stock_price: float
    bear_active: bool
    bear_calm_fund: float

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

        self.input_file: Optional[TextIO] = None
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

        self.portfolio_start_val = tk.StringVar(value="2000000")
        self.weekly_expenses_val = tk.StringVar(value="1800")
        self.annual_inflation_rate_val = tk.StringVar(value="3")
        self.annual_interest_rate_val = tk.StringVar(value="1")
        self.bear_calm_weeks_val = tk.StringVar(value="0")

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
            validatecommand=vcmd_float
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
        allow_zero: bool = False
    ) -> float:
        """Parse and validate a numeric field."""
        if value.strip() == "":
            raise ValueError(f"{field_name} is required.")

        try:
            number = float(value)
        except ValueError as exc:
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
        portfolio_start = self.parse_positive_number(
            self.portfolio_start_val.get(),
            "Starting Portfolio"
        )
        weekly_expenses = self.parse_positive_number(
            self.weekly_expenses_val.get(),
            "Weekly Expenses"
        )
        annual_inflation_rate = self.parse_positive_number(
            self.annual_inflation_rate_val.get(),
            "Annual Inflation Rate",
            allow_zero=True
        )
        annual_interest_rate = self.parse_positive_number(
            self.annual_interest_rate_val.get(),
            "Annual Interest Rate",
            allow_zero=True
        )
        bear_calm_weeks = self.parse_positive_number(
            self.bear_calm_weeks_val.get(),
            "Bear Calm Amount",
            allow_zero=True
        )

        return (
            portfolio_start,
            weekly_expenses,
            annual_inflation_rate,
            annual_interest_rate,
            bear_calm_weeks
        )

    def weekly_rate_from_annual(self, annual_rate: float) -> float:
        """Calculate a weekly rate from an annual rate"""
        rate = annual_rate / 100
        weekly_rate = (1 + rate) ** (1 / 52) - 1
        return weekly_rate
    
    def weekly_expense_stock_calc(self, calc:WeeklyCalcData):
        """
        Determine how many stocks need to be sold to cover expenses. Utilize
        the bear calming funds if in a bear market.

        @attention bear_calm_funds are mutated in this method

        @return the number of stocks that need to be sold
        """
        exps = calc.expenses

        if not calc.bear_active:
            return exps / calc.stock_price

        # if it is a bear market, try and use bear calming $$
        if calc.bear_calm_fund >= exps:
            # no stocks are needed to pay expenses
            calc.bear_calm_fund -= exps
            return 0
        
        elif calc.bear_calm_fund > 0:
            # use the remaining bear calming $$ and sell stocks for the rest
            exps -= calc.bear_calm_fund
            calc.bear_calm_fund = 0
            return exps / calc.stock_price

        else:
            # no bear calming $$ left, sell stocks
            return exps / calc.stock_price

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
                      

    def bear_start_analyze(self, stock_val_list, bear_start_list):
        """
        Analyze the stock prices and detect a bear market start:
            - 20% drop in price from recent 10 week highs.

        """
        BEAR_MARKET_LOOK_BACK_WEEKS=10

        # initialize the bear start list to all False
        bear_start_list[:] = [False] * len(bear_start_list)

        if any(value <= 0 for value in stock_val_list):
            self.log_err("Stock price <= 0!")
            return None

        bear_num = 0
        start = 0
        end = start + BEAR_MARKET_LOOK_BACK_WEEKS + 1
        while(end <= len(stock_val_list)):

            # find the high stock price in the look back period
            high_val = 0.0
            high_index = start
            for index in range(start, end):
                if (stock_val_list[index] > high_val):
                    high_val = stock_val_list[index]
                    high_index = index

            if high_val <= 0.0:
                self.log_err("Stock price <= 0!")
                return

            # compare stock values to the high price and detect a 20% drop
            bear_found = False
            drop_val = high_val - (high_val * 0.20)
            for index in range(high_index, end):
                if (stock_val_list[index] <= drop_val):
                    bear_start_list[index] = True
                    bear_found = True
                    bear_num += 1
                    start = index + 1
                    end = start + BEAR_MARKET_LOOK_BACK_WEEKS + 1
                    break

            if not bear_found:
                start += 1
                end = start + BEAR_MARKET_LOOK_BACK_WEEKS + 1

        return bear_num

    def stock_lists_get(self):
        # create lists of the weekly dates and weekly stock prices
        # that were read from the input file
        week_list = list(range(len(self.stock_date)))
        stock_val_list = [float(val) for val in self.stock_value]

        if any(value <= 0 for value in stock_val_list):
            self.log_err("Historical stock values must be greater than 0.")
            return [], []

        if len(week_list) != len(stock_val_list):
            self.log_err("Stock date and stock value lists are not the same length")
            return [], []

        return week_list, stock_val_list

    def bear_calm_funds_refresh(self, num_remaining, bear_buf, bear_calm):
        """If there are remaining bear buf funds, refresh the bear calming funds"""
        if num_remaining > 0:
            bear_calm = bear_buf / num_remaining
            num_remaining -= 1
        else:
            bear_calm = 0
            num_remaining = 0

        return num_remaining, bear_calm
    
    def analyze_historical_data(
        self,
        portfolio_start: float,
        weekly_expense_start: float,
        annual_inflation_rate: float,
        annual_interest_rate: float,
        bear_calm_weeks: float
    ):
        """
        Calculate a portfolio value over time, by evaluating every week and
        subtracting expenses either through selling stocks or if in a bear market
        using bear calm funds.
        """
        try:
            # create lists of the weekly dates and weekly stock prices
            week_list, stock_val_list = self.stock_lists_get()

            if not week_list or not stock_val_list:
                self.log_err("Invalid input data")
                return

            # a single bear calm fund == number of weeks * weekly expenses
            bear_calm_fund_start = bear_calm_weeks * weekly_expense_start

            # analyze the data for bear markets
            bear_start_list = [False] * len(stock_val_list)
            bear_market_num = self.bear_start_analyze(stock_val_list, bear_start_list)

            # calculate the total bear buf (bear_calm_funds * bear_market_num)
            bear_buf_start = bear_market_num * bear_calm_fund_start
            bear_buf_val = bear_buf_start

            if bear_buf_val > portfolio_start:
                self.log_err("Not enough $$ in portfolio to fund the bear buf")
                return

            # the bear buf is funded through the portfolio, deduct that money
            # before calculating the starting stock number
            stock_num_remaining = (portfolio_start - bear_buf_val) / stock_val_list[0]

            # initialize weekly processing variables
            weekly_expense_val = weekly_expense_start
            weekly_port_val = portfolio_start
            weekly_inflation_rate = self.weekly_rate_from_annual(annual_inflation_rate)
            weekly_interest_rate = self.weekly_rate_from_annual(annual_interest_rate)

            self.results["date_range"] = f"{self.stock_date[0]} to {self.stock_date[-1]}"
            self.results["port_total_start"] = portfolio_start
            self.results["inflation_annual"] = annual_inflation_rate
            self.results["inflation_weekly"] = weekly_inflation_rate
            self.results["interest_annual"] = annual_interest_rate
            self.results["interest_weekly"] = weekly_interest_rate
            self.results["expense_start"] = weekly_expense_start
            self.results["bear_calm"] = bear_calm_fund_start
            self.results["bear_num_total"] = bear_market_num

            # for every week, determine how many stocks need to be sold for expenses
            port_val_weekly_list = [weekly_port_val]
            bear_active = False
            bear_start_dates = []
            bear_remaining = bear_market_num
            bear_calm_fund = 0

            for week in week_list[1:]:
                # if a bear start is detected, expenses are paid from
                # the bear calm fund until it is depleted
                if not bear_active:
                    bear_active = bear_start_list[week]

                    if bear_active:
                        bear_start_dates.append(self.stock_date[week])
                        bear_remaining, bear_calm_fund = self.bear_calm_funds_refresh(bear_remaining,
                                                                                    bear_buf_val, 
                                                                                    bear_calm_fund)
                else:
                    # check to see if another bear market has triggered while 
                    # we are using bear calming funds
                    if bear_start_list[week]:
                        bear_start_dates.append(self.stock_date[week])
                        bear_remaining, bear_calm_fund = self.bear_calm_funds_refresh(bear_remaining,
                                                                                    bear_buf_val, 
                                                                                    bear_calm_fund)

                    if bear_calm_fund <= 0:
                        bear_calm_fund = 0
                        bear_active = False

                calc = WeeklyCalcData(expenses=weekly_expense_val,
                                      stock_price=stock_val_list[week],
                                      bear_active=bear_active,
                                      bear_calm_fund=bear_calm_fund)
                
                expense_stock_num = self.weekly_expense_stock_calc(calc)

                if expense_stock_num <= stock_num_remaining:
                    stock_num_remaining -= expense_stock_num
                elif stock_num_remaining > 0:
                    stock_num_remaining = 0

                # adjust the bear buf if bear calm funds were used
                if bear_calm_fund > calc.bear_calm_fund:
                    bear_buf_val -= (bear_calm_fund - calc.bear_calm_fund)

                bear_calm_fund = calc.bear_calm_fund
                interest = bear_buf_val * weekly_interest_rate 
                bear_buf_val += interest

                weekly_port_val = (stock_num_remaining * stock_val_list[week]) + bear_buf_val
                port_val_weekly_list.append(weekly_port_val)

                weekly_expense_val += (weekly_expense_val * weekly_inflation_rate)

            if len(port_val_weekly_list) != len(week_list):
                self.log_err((
                    f"Lists must be the same length: "
                    f"port val list length: {len(port_val_weekly_list)}, "
                    f"week list length: {len(week_list)}"
                ))
                return

            # log the results of the analysis
            if bear_start_dates != []:
                self.results["bear_dates"] = bear_start_dates
            else:
                self.results["bear_dates"] = "None"

            self.results["bb_start"] = bear_buf_start
            self.results["bb_end"] = bear_buf_val
            self.results["expense_end"] = weekly_expense_val
            self.results["port_total_end"] = port_val_weekly_list[-1]

            self.log_results()

            # display the data on the plot
            x_label = f"Weeks from {self.stock_date[0]} to {self.stock_date[-1]}"
            self.display_data(x_label, week_list, port_val_weekly_list)

            return self.results["port_total_end"]

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

                    # Validate the stock value before storing the CSV row.
                    float(row[1])
                    self.stock_date.append(row[0])
                    self.stock_value.append(row[1])

        except Exception:
            self.history_clear()
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
                annual_inflation_rate,
                annual_interest_rate,
                bear_calm_weeks
            ) = self.validate_inputs()
        except ValueError as exc:
            self.log_err(str(exc))
            return

        self.historical_data_read()

        if not self.stock_date or not self.stock_value:
            return

        port_end_previous = 0
        port_end = self.analyze_historical_data(
            portfolio_start=portfolio_start,
            weekly_expense_start=weekly_expenses,
            annual_inflation_rate=annual_inflation_rate,
            annual_interest_rate=annual_interest_rate,
            bear_calm_weeks=bear_calm_weeks)

        if self.auto_run_var.get():
            bear_calm_weeks = 1
            while ((bear_calm_weeks <= BEAR_CALM_WEEK_MAX) 
                   and (port_end > port_end_previous)):
                
                port_end_previous = port_end
                port_end = self.analyze_historical_data(
                    portfolio_start=portfolio_start,
                    weekly_expense_start=weekly_expenses,
                    annual_inflation_rate=annual_inflation_rate,
                    annual_interest_rate=annual_interest_rate,
                    bear_calm_weeks=bear_calm_weeks)

                bear_calm_weeks += 1

            if bear_calm_weeks > BEAR_CALM_WEEK_MAX:
                self.log_msg("Auto run stopped before finding maximum end portfolio")
            else:
                self.log_msg(f"Maximum portfolio of {port_end:.2f} found when bear calming weeks are {bear_calm_weeks}")

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
