#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for VTSAX and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import logging
from datetime import datetime
import csv
from enum import Enum

__version__ = "0.1"

# Logging Configuration
dt = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_name = f"{dt}_bearbuf_log.txt"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
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
PLOT_TITLE_FLOW_DRIFT = "Portfolio Over Time"

# historical data to be read
HISTORICAL_FILENAME = 'VTSAX_history.csv'

# ============================================================================
# Bear Buf UI Application
# ============================================================================
class BearBufUI:
    """
    Tkinter GUI for Bear Buf calculations
    """
    def __init__(self, root: tk.Tk):
        """
        Initialize the UI.

        Args:
            root: The root tkinter window
        """
        self.root = root
        self.root.title("Bear Buf Calculator")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.stock_date = []
        self.stock_value = []

        # Make root expandable
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # UI Components
        self.setup_ui()

    def setup_ui(self):
        """Set up the main UI components."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Create tabs
        self.control_frame = ttk.Frame(self.notebook)
        self.control_frame.rowconfigure(0, weight=1)
        self.control_frame.columnconfigure(0, weight=1)

        self.notebook.add(self.control_frame, text="Bear Buf Calculator")

        # Setup control tab
        self.setup_control_tab()

    def setup_control_tab(self):
        """Set up the control and monitoring tab."""
        # Create main container with vertical scrolling
        main_container = ttk.Frame(self.control_frame)
        main_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.control_frame.rowconfigure(0, weight=1)
        self.control_frame.columnconfigure(0, weight=1)

        main_container.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=0)  # left panel
        main_container.columnconfigure(1, weight=1)  # right panel expands

        # Left panel: Scrollable controls
        left_panel = ttk.Frame(main_container)
        left_panel.grid(row=0, column=0, sticky="ns", padx=5)

        left_panel.rowconfigure(0, weight=1)
        left_panel.columnconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_panel, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scrollbar.grid(row=0, column=1, sticky="ns")

        left_container = ttk.Frame(left_canvas)
        left_window = left_canvas.create_window((0, 0), window=left_container, anchor="nw")

        def _on_left_container_configure(event):
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

        # calculator frame for left panel
        calculator_frame = ttk.LabelFrame(left_container, text="Calculator", padding=10)
        calculator_frame.grid(row=0, column=0, sticky="ew", pady=5)
        calculator_frame.columnconfigure(0, weight=1)

        # Starting portfolio value entry
        portfolio_frame = ttk.LabelFrame(calculator_frame, padding=5)
        portfolio_frame.grid(row=0, column=0, sticky="ew", pady=5)
        portfolio_frame.columnconfigure(1, weight=1)

        ttk.Label(portfolio_frame, text="Starting Portfolio $").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.portfolio_start_val = tk.IntVar(value=2000000)
        self.portfolio_start_entry = ttk.Entry(
            portfolio_frame,
            textvariable=self.portfolio_start_val,
            width=10,
            justify=tk.RIGHT
        )
        self.portfolio_start_entry.grid(row=0, column=1, sticky="w", padx=5)

        # Weekly expenses entry
        weekly_expenses_frame = ttk.LabelFrame(calculator_frame, padding=5)
        weekly_expenses_frame.grid(row=1, column=0, sticky="ew", pady=5)
        weekly_expenses_frame.columnconfigure(1, weight=1)

        ttk.Label(weekly_expenses_frame, text="Weekly Expenses $").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.weekly_expenses_val = tk.IntVar(value=2000)
        self.weekly_expenses_entry = ttk.Entry(
            weekly_expenses_frame,
            textvariable=self.weekly_expenses_val,
            width=10,
            justify=tk.RIGHT
        )
        self.weekly_expenses_entry.grid(row=0, column=1, sticky="w", padx=5)

        # annual inflation rate entry
        annual_inflation_frame = ttk.LabelFrame(calculator_frame, padding=5)
        annual_inflation_frame.grid(row=2, column=0, sticky="ew", pady=5)
        annual_inflation_frame.columnconfigure(1, weight=1)

        ttk.Label(annual_inflation_frame, text="Annual Inflation Rate %").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.annual_inflation_rate_val = tk.IntVar(value=3)
        self.annual_inflation_rate_entry = ttk.Entry(
            annual_inflation_frame,
            textvariable=self.annual_inflation_rate_val,
            width=10,
            justify=tk.RIGHT
        )
        self.annual_inflation_rate_entry.grid(row=0, column=1, sticky="w", padx=5)

        # Interest rate entry
        annual_interest_rate_frame = ttk.LabelFrame(calculator_frame, padding=5)
        annual_interest_rate_frame.grid(row=3, column=0, sticky="ew", pady=5)
        annual_interest_rate_frame.columnconfigure(1, weight=1)

        ttk.Label(annual_interest_rate_frame, text="Annual Interest Rate %").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.annual_interest_rate_val = tk.IntVar(value=4)
        self.annual_interest_rate_entry = ttk.Entry(
            annual_interest_rate_frame,
            textvariable=self.annual_interest_rate_val,
            width=10,
            justify=tk.RIGHT
        )
        self.annual_interest_rate_entry.grid(row=0, column=1, sticky="w", padx=5)

        # run calculator button
        calculator_run_frame = ttk.Frame(calculator_frame)
        calculator_run_frame.grid(row=4, column=0, sticky="ew", pady=2)
        calculator_run_frame.columnconfigure(0, weight=1)

        self.calculator_run_button = ttk.Button(
            calculator_run_frame,
            text="Run Calculator",
            command=self.on_calculator_run,
            state=tk.NORMAL
        )
        self.calculator_run_button.grid(row=0, column=0, sticky="ew", padx=2)

        # Right panel: Scrollable Graphs
        right_panel = ttk.Frame(main_container)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=5)

        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)

        # Create canvas + vertical scrollbar for graph area
        graph_canvas = tk.Canvas(right_panel, highlightthickness=0)
        graph_scrollbar = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=graph_canvas.yview)
        graph_canvas.configure(yscrollcommand=graph_scrollbar.set)

        graph_canvas.grid(row=0, column=0, sticky="nsew")
        graph_scrollbar.grid(row=0, column=1, sticky="ns")

        # Inner frame that will contain all graph frames
        graph_container = ttk.Frame(graph_canvas)
        graph_container.columnconfigure(0, weight=1)
        graph_window = graph_canvas.create_window((0, 0), window=graph_container, anchor="nw")

        # Keep scrollregion updated
        def _on_graph_container_configure(event):
            graph_canvas.configure(scrollregion=graph_canvas.bbox("all"))

        # Keep inner frame width matched to canvas width
        def _on_graph_canvas_configure(event):
            graph_canvas.itemconfigure(graph_window, width=event.width)

        graph_container.bind("<Configure>", _on_graph_container_configure)
        graph_canvas.bind("<Configure>", _on_graph_canvas_configure)

        # Optional: mousewheel scrolling when cursor is over graph area
        def _on_mousewheel(event):
            graph_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_graph_mousewheel(_event):
            graph_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_graph_mousewheel(_event):
            graph_canvas.unbind_all("<MouseWheel>")

        graph_canvas.bind("<Enter>", _bind_graph_mousewheel)
        graph_canvas.bind("<Leave>", _unbind_graph_mousewheel)

        # Graph frame 1: Portfolio Value
        graph_frame_1 = ttk.LabelFrame(graph_container, text="Portfolio Over Time", padding=5)
        graph_frame_1.grid(row=0, column=0, sticky="nsew", pady=5)
        graph_frame_1.rowconfigure(0, weight=1)
        graph_frame_1.columnconfigure(0, weight=1)

        # Create matplotlib figure for portfolio value
        self.figure_portfolio = Figure(figsize=(8, 4), dpi=100)
        self.ax_portfolio = self.figure_portfolio.add_subplot(111)
        self.ax_portfolio.set_xlabel(PLOT_X_LABEL)
        self.ax_portfolio.set_ylabel(PLOT_Y_LABEL)
        self.ax_portfolio.set_title(PLOT_TITLE_FLOW)
        self.ax_portfolio.grid(True, alpha=0.3)

        # Embed matplotlib in tkinter
        self.canvas_portfolio = FigureCanvasTkAgg(self.figure_portfolio, master=graph_frame_1)
        self.canvas_portfolio.draw()
        self.canvas_portfolio.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def inflation_weekly_calc(self) -> float:
        annual = self.annual_inflation_rate_val.get() / 100
        weekly_inflation_rate = (1 + annual) ** (1 / 52) - 1
        return weekly_inflation_rate

    def update_plot(self):
        """Display the portfolio data"""
        try:
            x_label = f"Weeks from {self.stock_date[0]} to {self.stock_date[-1]}"

            # calculate the total number of shares at the beginning
            stock_num_start = self.portfolio_start_val.get() / float(self.stock_value[0])
            port_val_start = stock_num_start * float(self.stock_value[0])

            week_list = list(range(len(self.stock_date)))
            stock_val_list = [float(val) for val in self.stock_value]

            if len(week_list) != len(stock_val_list):
                str = f"Stock date and value lists are not the same length"
                logger.error(str)
                messagebox.showerror("Error", str)
                return

            # starting weekly expenses and portfolio value
            weekly_expense_val = self.weekly_expenses_val.get()

            weekly_port_val = port_val_start
            remaining_stock_num = stock_num_start

            port_val_list = []
            port_val_list.append(weekly_port_val)
            for week in week_list[1:]:
                expense_stock_num = weekly_expense_val / stock_val_list[week]
                remaining_stock_num -= expense_stock_num

                if remaining_stock_num < 0:
                    str = f"You broke in week {week}!"
                    logger.error(str)
                    messagebox.showerror("Error", str)
                    return

                weekly_port_val = remaining_stock_num * stock_val_list[week]
                port_val_list.append(weekly_port_val)

                # update expenses for inflation
                weekly_expense_val += weekly_expense_val * self.inflation_weekly_calc()

            if len(port_val_list) != len(week_list):
                str = f"port val list length: {len(port_val_list)}, week list length: {len(week_list)}"
                logger.error(str)
                messagebox.showerror("Error", str)
                return

            title = f"Portfolio start:{port_val_start:.2f} end:{port_val_list[-1]:.2f}"

            self.ax_portfolio.clear()
            self.ax_portfolio.plot(week_list, port_val_list, linestyle='-', linewidth=1, color='#1f77b4')
            self.ax_portfolio.set_xlabel(x_label)
            self.ax_portfolio.set_ylabel(PLOT_Y_LABEL)
            self.ax_portfolio.set_title(title)
            self.ax_portfolio.grid(True, alpha=0.3)

            self.figure_portfolio.tight_layout()
            self.canvas_portfolio.draw_idle()

            self.stock_date.clear()
            self.stock_value.clear()

        except Exception:
            logger.error("Unexpected plot update failure")

    def ui_var_disable(self, ui_var):
        ui_var.config(state=tk.DISABLED)

    def ui_var_enable(self, ui_var):
        ui_var.config(state=tk.NORMAL)

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
        except:
            self.history_clear()
            str = f"Error when reading historical data from {HISTORICAL_FILENAME}. "
            str += "Verify the file exists and try again."
            logger.error(str)
            messagebox.showerror("Error", str)

    def on_calculator_run(self):
        """Run the calculator and display results."""
        self.historical_data_read()

        if self.stock_date != [] and self.stock_value != []:
            self.update_plot()

    def cleanup(self):
        """Clean up resources."""
        self.disconnect_cleanup()

def main():
    """Main entry point for the  application."""
    root = tk.Tk()
    ui = BearBufUI(root)

    def on_closing():
        """Handle window closing."""
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
