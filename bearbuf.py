#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for VTSAX and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import csv
import logging
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

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
PLOT_TITLE_FLOW = "Portfolio"

HISTORICAL_FILENAME = "VTSAX_history.csv"


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

        self.stock_date = []
        self.stock_value = []

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

        main_container.rowconfigure(0, weight=1)
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

        inputs_frame = ttk.LabelFrame(calculator_frame, text="Inputs", padding=8)
        inputs_frame.grid(row=0, column=0, sticky="ew", pady=5)
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
        self.weekly_expenses_val = tk.StringVar(value="1600")
        self.annual_inflation_rate_val = tk.StringVar(value="3")
        self.annual_interest_rate_val = tk.StringVar(value="4")
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
        calculator_run_frame.grid(row=1, column=0, sticky="ew", pady=4)
        calculator_run_frame.columnconfigure(0, weight=1)

        self.calculator_run_button = ttk.Button(
            calculator_run_frame,
            text="Run Calculator",
            command=self.on_calculator_run,
            state=tk.NORMAL
        )
        self.calculator_run_button.grid(row=0, column=0, sticky="ew", padx=2)

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
        self.ax_portfolio.set_title(PLOT_TITLE_FLOW)
        self.ax_portfolio.grid(True, alpha=0.3)

        self.canvas_portfolio = FigureCanvasTkAgg(
            self.figure_portfolio,
            master=graph_frame_1
        )
        self.canvas_portfolio.draw()
        self.canvas_portfolio.get_tk_widget().grid(
            row=0, column=0, sticky="nsew"
        )

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

    def inflation_weekly_calc(self, annual_inflation_rate: float) -> float:
        """Calculation the weekly inflation rate"""
        annual = annual_inflation_rate / 100
        weekly_inflation_rate = (1 + annual) ** (1 / 52) - 1
        return weekly_inflation_rate

    def weekly_expense_stock_calc(self, expenses, stock_price, bear_start, bear_calm_amount):
        """
        Determine how many stocks need to be sold to cover expenses. Utilize
        the bear calming savings if in a bear market.

        @return the number of stocks that need to be sold
        """
        exps = expenses

        if not bear_start:
            return exps / stock_price

         # if it is a bear market, try and use bear calming $$
        if bear_calm_amount >= exps:
            # no stocks are needed to pay expenses
            bear_calm_amount -= exps
            return 0
        
        elif bear_calm_amount > 0:
            # use the remaining bear calming $$ and sell stocks
            # for the rest
            exps -= bear_calm_amount
            bear_calm_amount = 0
            return exps / stock_price

        else:
            # no bear calming $$ left, sell stocks
            return exps / stock_price


    def log_err(self, msg):
        """Log an error message"""
        logger.error(msg)
        messagebox.showerror("Error", msg)

    def log_msg(self, msg):
        """Log a message"""
        logger.info(msg)

    def bear_start_analyze(self, stock_val_list, bear_start_list):
        """
        Analyze the stock prices and detect a bear market start:
            20% drop in price from recent 10 week highs.

        """
        BEAR_MARKET_LOOK_BACK_WEEKS=10

        # initialize the bear start list to False
        bear_start_list[:] = [False] * len(bear_start_list)

        if len(stock_val_list) < BEAR_MARKET_LOOK_BACK_WEEKS:
            return
        
        start = 0
        end = start + BEAR_MARKET_LOOK_BACK_WEEKS
        while(end < len(stock_val_list)):

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
                    start = index + 1
                    end = start + BEAR_MARKET_LOOK_BACK_WEEKS
                    break

            if not bear_found:
                start += 1
                end = start + BEAR_MARKET_LOOK_BACK_WEEKS

    def analyze_historical_data(
        self,
        portfolio_start: float,
        weekly_expenses_start: float,
        annual_inflation_rate: float,
        bear_calm_weeks: float
    ):
        """Anaylze the portfolio and expenses over time and plot the data"""
        try:
            first_stock_price = float(self.stock_value[0])
            if first_stock_price <= 0:
                self.log_err("Historical starting stock value must be greater than 0.")
                return

            stock_num_start = portfolio_start / first_stock_price
            port_val_start = stock_num_start * first_stock_price

            week_list = list(range(len(self.stock_date)))
            stock_val_list = [float(val) for val in self.stock_value]

            if len(week_list) != len(stock_val_list):
                self.log_err("Stock date and value lists are not the same length")
                return

            # analyze the data for bear markets
            bear_start_list = [False] * len(stock_val_list)
            self.bear_start_analyze(stock_val_list, bear_start_list)

            weekly_expense_val = weekly_expenses_start
            weekly_port_val = port_val_start
            remaining_stock_num = stock_num_start
            weekly_inflation_rate = self.inflation_weekly_calc(annual_inflation_rate)
            bear_calm_amount = self.bear_calm_calc(bear_calm_weeks, weekly_expenses_start)

            # for every week in the history, determine how many stocks
            # need to be sold for expenses
            port_val_weekly_list = [weekly_port_val]
            bear_active = False
            bear_starts = 0
            for week in week_list[1:]:
                if stock_val_list[week] <= 0:
                    self.log_err(f"Historical stock value at week {week} must be greater than 0.")
                    return

                # if a bear start is detected, expenses are paid from
                # the bear calm bucket until it is depleted
                if not bear_active:
                    bear_active = bear_start_list[week]

                    # @test 
                    if bear_active:
                        bear_starts += 1
                else:
                    if bear_calm_amount <= 0:
                        bear_active = False
                        # refresh the bear calm amount if available
                        bear_calm_amount = self.bear_calm_calc(bear_calm_weeks, weekly_expenses_start)

                expense_stock_num = self.weekly_expense_stock_calc(weekly_expense_val, 
                                                                   stock_val_list[week], 
                                                                   bear_active,
                                                                   bear_calm_amount)
                remaining_stock_num -= expense_stock_num

                if remaining_stock_num < 0:
                    remaining_stock_num = 0
                    self.log_err(f"You started spending on {self.stock_date[0]}. You broke on {self.stock_date[week]} :(")
                    return

                weekly_port_val = remaining_stock_num * stock_val_list[week]
                port_val_weekly_list.append(weekly_port_val)

                weekly_expense_val += weekly_expense_val * weekly_inflation_rate

            if len(port_val_weekly_list) != len(week_list):
                self.log_err((
                    f"Lists must be the same length: "
                    f"port val list length: {len(port_val_weekly_list)}, "
                    f"week list length: {len(week_list)}"
                ))
                return

            # display the data on the plot
            x_label = f"Weeks from {self.stock_date[0]} to {self.stock_date[-1]}"
            self.display_data(x_label, week_list, port_val_weekly_list)

            # log the results of the analysis
            self.log_results()

            self.history_clear()

        except Exception as e:
            self.log_err(f"{type(e).__name__}: {e}")

    def bear_calm_calc(self, weeks, expenses):
        """Determine the bear calm amount"""
        return weeks * expenses

    def log_results(self):
        pass

    def display_data(self, x_label, week_list, port_val_weekly_list):
        """Display the portfolio analysis data on the graph"""
        title = (
            f"Portfolio start: {port_val_weekly_list[0]:.2f} "
            f"end: {port_val_weekly_list[-1]:.2f}"
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

    def disconnect_cleanup(self):
        """Cleanup on a disconnection event"""
        pass

    def history_clear(self):
        """Clear history"""
        self.stock_date.clear()
        self.stock_value.clear()

    def historical_data_read(self):
        """Read the historical data"""
        try:
            self.history_clear()

            with open(HISTORICAL_FILENAME, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        self.stock_date.append(row[0])
                        self.stock_value.append(row[1])

        except Exception:
            self.history_clear()
            self.log_err((
                f"Error when reading historical data from {HISTORICAL_FILENAME}. "
                "Verify the file exists and try again."
            ))

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

        # annual_interest_rate parsed and validated for future use
        _ = annual_interest_rate

        self.analyze_historical_data(
            portfolio_start=portfolio_start,
            weekly_expenses_start=weekly_expenses,
            annual_inflation_rate=annual_inflation_rate,
            bear_calm_weeks=bear_calm_weeks
        )

    def cleanup(self):
        """Clean up resources."""
        self.disconnect_cleanup()


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
