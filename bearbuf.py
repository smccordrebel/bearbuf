#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for VTSAX and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import logging
from datetime import datetime

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

        # UI Components
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the main UI components."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.control_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.control_frame, text="Bear Buf Calculator")

        # Setup control tab
        self.setup_control_tab()

    def setup_control_tab(self):
        """Set up the control and monitoring tab."""
        # Create main container with vertical scrolling
        main_container = ttk.Frame(self.control_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel: Scrollable controls
        left_panel = ttk.Frame(main_container)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5)

        left_canvas = tk.Canvas(left_panel, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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
        calculator_frame.pack(fill=tk.X, pady=5)

        # read historical data
        historical_data_frame = ttk.Frame(calculator_frame)
        historical_data_frame.pack(fill=tk.X, pady=2)

        self.historical_data_button = ttk.Button(
            historical_data_frame,
            text="Read Historical Data",
            command=self.on_historical_data,
            state=tk.NORMAL
        )
        self.historical_data_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Starting portfolio value entry
        portfolio_frame = ttk.LabelFrame(calculator_frame, padding=5)
        portfolio_frame.pack(fill=tk.X, pady=5)

        ttk.Label(portfolio_frame, text="Starting Portfolio $").pack(side=tk.LEFT, padx=(0, 5))
        self.portfolio_start_val = tk.IntVar(value=2000000)
        self.portfolio_start_entry = ttk.Entry(
            portfolio_frame,
            textvariable=self.portfolio_start_val,
            width=10,
            justify=tk.RIGHT
        )
        self.portfolio_start_entry.pack(side=tk.LEFT, padx=5)

        # Weekly expenses entry
        weekly_expenses_frame = ttk.LabelFrame(calculator_frame, padding=5)
        weekly_expenses_frame.pack(fill=tk.X, pady=5)

        ttk.Label(weekly_expenses_frame, text="Weekly Expenses $").pack(side=tk.LEFT, padx=(0, 5))
        self.weekly_expenses_val = tk.IntVar(value=2000)
        self.weekly_expenses_entry = ttk.Entry(
            weekly_expenses_frame,
            textvariable=self.weekly_expenses_val,
            width=10,
            justify=tk.RIGHT
        )
        self.weekly_expenses_entry.pack(side=tk.LEFT, padx=5)

        # inflation rate entry
        inflation_rate_frame = ttk.LabelFrame(calculator_frame, padding=5)
        inflation_rate_frame.pack(fill=tk.X, pady=5)

        ttk.Label(inflation_rate_frame, text="Inflation Rate %").pack(side=tk.LEFT, padx=(0, 5))
        self.inflation_rate_val = tk.IntVar(value=3)
        self.inflation_rate_entry = ttk.Entry(
            inflation_rate_frame,
            textvariable=self.inflation_rate_val,
            width=10,
            justify=tk.RIGHT
        )
        self.inflation_rate_entry.pack(side=tk.LEFT, padx=5)

        # Interest rate entry
        interest_rate_frame = ttk.LabelFrame(calculator_frame, padding=5)
        interest_rate_frame.pack(fill=tk.X, pady=5)

        ttk.Label(interest_rate_frame, text="Interest Rate %").pack(side=tk.LEFT, padx=(0, 5))
        self.interest_rate_val = tk.IntVar(value=4)
        self.interest_rate_entry = ttk.Entry(
            interest_rate_frame,
            textvariable=self.interest_rate_val,
            width=10,
            justify=tk.RIGHT
        )
        self.interest_rate_entry.pack(side=tk.LEFT, padx=5)

        # run calculator button
        run_calculator_frame = ttk.Frame(calculator_frame)
        run_calculator_frame.pack(fill=tk.X, pady=2)

        self.run_calculator_button = ttk.Button(
            run_calculator_frame,
            text="Run Calculator",
            command=self.on_run_calculator,
            state=tk.NORMAL
        )
        self.run_calculator_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Right panel: Scrollable Graphs
        right_panel = ttk.Frame(main_container)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        # Create canvas + vertical scrollbar for graph area
        graph_canvas = tk.Canvas(right_panel, highlightthickness=0)
        graph_scrollbar = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=graph_canvas.yview)
        graph_canvas.configure(yscrollcommand=graph_scrollbar.set)

        graph_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        graph_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Inner frame that will contain all graph frames
        graph_container = ttk.Frame(graph_canvas)
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
        graph_frame_1.pack(fill=tk.BOTH, expand=True, pady=5)

        # Create matplotlib figure for portfolio value
        self.figure_flow = Figure(figsize=(8, 4), dpi=100)
        self.ax_flow = self.figure_flow.add_subplot(111)
        self.ax_flow.set_xlabel(PLOT_X_LABEL)
        self.ax_flow.set_ylabel(PLOT_Y_LABEL)
        self.ax_flow.set_title(PLOT_TITLE_FLOW)
        self.ax_flow.grid(True, alpha=0.3)

        # Embed matplotlib in tkinter
        self.canvas_flow = FigureCanvasTkAgg(self.figure_flow, master=graph_frame_1)
        self.canvas_flow.draw()
        self.canvas_flow.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def update_plot(self):
        """Display the portfolio data"""
        try:
            time_list = []
            flow_list = []

            # Update flow impedance plot - reuse existing lines
            if not hasattr(self, 'flow_line'):
                # First time: create the plot
                self.flow_line, = self.ax_flow.plot(time_list, flow_list, marker='o', linestyle='-', linewidth=1, color='#1f77b4')
                self.ax_flow.set_xlabel(PLOT_X_LABEL)
                self.ax_flow.set_ylabel(PLOT_Y_LABEL)
                self.ax_flow.set_title(PLOT_TITLE_FLOW)
                self.ax_flow.grid(True, alpha=0.3)
            else:
                # Subsequent updates: just update the data
                self.flow_line.set_data(time_list, flow_list)
                # Auto-scale axes to fit new data
                self.ax_flow.relim()
                self.ax_flow.autoscale_view()
            
            self.figure_flow.tight_layout()
            self.canvas_flow.draw_idle()

        except Exception:
            self.log.error("Unexpected plot update failure")

    def ui_var_disable(self, ui_var):
        ui_var.config(state=tk.DISABLED)
    
    def ui_var_enable(self, ui_var):
        ui_var.config(state=tk.NORMAL)
    
    def disconnect_cleanup(self):
        """Cleanup on a disconnection event"""
        pass

    def on_historical_data(self):
        """Start sensor streaming."""
        pass
    
    def on_run_calculator(self):
        """Stop sensor streaming."""
        pass


    def cleanup(self):
        """Clean up resources."""
        self.disconnect_cleanup()

def main():
    """Main entry point for the UI application."""
    root = tk.Tk()
    ui = BearBufUI(root)
    
    def on_closing():
        """Handle window closing."""
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()