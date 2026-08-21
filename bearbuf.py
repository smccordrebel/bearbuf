#!/usr/bin/env python3

"""
Bearbuf Calculator UI Module.

Look at the historical data for VTSAX and analyze bear starts and how
to utilize a portfolio of stocks/bonds/cash.
"""

import asyncio
import concurrent.futures
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from collections import deque
from typing import Optional
from enum import Enum
import logging
import queue
import threading
from datetime import datetime

from multisense_lab import (
    MultiSenseError,
    MultiSenseController,
    IMPEDANCE_SAMPLE_Q_MAX
)

__version__ = "0.1"

# ============================================================================
# Logging Configuration
# ============================================================================
# Logging Configuration
dt = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_name = f"{dt}_bearbuf_log.txt"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
                logging.FileHandler(log_file_name),
                logging.StreamHandler()
             ]
)
logger = logging.getLogger(__name__)

class QueueHandler(logging.Handler):
    """Custom logging handler that puts log records into a queue."""
    
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to the queue."""
        try:
            msg = self.format(record)
            self.log_queue.put((record.levelname, msg))
        except Exception:
            self.handleError(record)


# ============================================================================
# Constants
# ============================================================================
BT_DEVICE_NAME="MultiSense"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700
LOG_UPDATE_INTERVAL_MS = 100
PLOT_UPDATE_INTERVAL_MS = 180
HEARTBEAT_INTERVAL_SEC = 10.0
PLOT_X_LABEL = "Time (Min)"
PLOT_Y_LABEL = "Impedance (Ω)"
PLOT_TITLE_FLOW = "Flow Impedance"
PLOT_TITLE_FLOW_DRIFT = "Flow Drift Impedance"
PLOT_TITLE_PRESSURE = "Pressure Impedance"
PLOT_TITLE_PATENCY = "Patency Impedance"
IMPEDANCE_MIN_VAL = 0
IMPEDANCE_MAX_VAL = 65535
SCHEDULE_ROWS = 4
SCHEDULE_MIN_TIME = 0
SCHEDULE_MAX_TIME = 28800 # 8 hours of seconds
SCHEDULE_Q_MAX = 10
SCHEDULE_STOP_ID = 1

class ConnectState(Enum):
    DISCONNECTED = 1
    SCANNING = 2
    CONNECTING = 3
    CONNECTED = 4
    DISCONNECTING = 5

class SchedState(Enum):
    IDLE = 0
    HEATER = 1
    BUBBLE_GEN = 2
    DISABLED = 3

# Async call timeouts
TIMEOUT_SCAN = 15.0
TIMEOUT_CONNECT= 40.0
TIMEOUT_DISCONNECT = 5.0
TIMEOUT_SENSOR_STREAM_START = 5.0
TIMEOUT_SENSOR_STREAM_STOP = 5.0
TIMEOUT_HEATER_START = 5.0
TIMEOUT_HEATER_STOP = 5.0
TIMEOUT_BUBBLE_GEN_STOP = 5.0
TIMEOUT_BUBBLE_GEN_START = 5.0
TIMEOUT_HEARTBEAT_VERIFY = 5.0

# ============================================================================
# Validation Functions
# ============================================================================

def validate_schedule_time(action, index, value_if_allowed,
                     prior_value, text, validation_type, trigger_type, widget_name):
    """Validation callback: allow empty (for editing) or integers 0-SCHEDULE_MAX_TIME."""
    if action == '1':  # insert
        if value_if_allowed == "":
            return True
        if not value_if_allowed.isdigit():
            return False
        try:
            v = int(value_if_allowed)
        except ValueError:
            return False
        return SCHEDULE_MIN_TIME <= v <= SCHEDULE_MAX_TIME
    return True  # deletion or other actions allowed

def validate_impedance_val(action, index, value_if_allowed,
                     prior_value, text, validation_type, trigger_type, widget_name):
    """Validation callback: allow empty (for editing) or integers 0-IMPEDANCE_MAX_VAL."""
    if action == '1':  # insert
        if value_if_allowed == "":
            return True
        if not value_if_allowed.isdigit():
            return False
        try:
            v = int(value_if_allowed)
        except ValueError:
            return False
        return IMPEDANCE_MIN_VAL <= v <= IMPEDANCE_MAX_VAL
    return True  # deletion or other actions allowed

class SchedData:
    def __init__(self, time_on, time_off, duty_cycle=100):
        self.duty_cycle = duty_cycle
        self.time_on = time_on
        self.time_off = time_off

# ============================================================================
# MultiSense UI Application
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

        # read historical data
        calculator_frame = ttk.LabelFrame(left_container, text="Calculator", padding=10)
        calculator_frame.pack(fill=tk.X, pady=5)

        stream_button_frame = ttk.Frame(calculator_frame)
        stream_button_frame.pack(fill=tk.X, pady=2)

        self.stream_start_button = ttk.Button(
            stream_button_frame,
            text="Read Historical Data",
            command=self.on_start_streaming,
            state=tk.NORMAL
        )
        self.stream_start_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.stream_stop_button = ttk.Button(
            stream_button_frame,
            text="Run Calculator",
            command=self.on_stop_streaming,
            state=tk.NORMAL
        )
        self.stream_stop_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Impedance settle count frame
        settle_frame = ttk.LabelFrame(calculator_frame, padding=5)
        settle_frame.pack(fill=tk.X, pady=5)

        ttk.Label(settle_frame, text="Starting Portfolio").pack(side=tk.LEFT, padx=(0, 5))
        self.bioz_settle_count = tk.IntVar(value=2000000)
        self.settle_spinbox = ttk.Entry(
            settle_frame,
            textvariable=self.bioz_settle_count,
            width=10,
            justify=tk.RIGHT
        )
        self.settle_spinbox.pack(side=tk.LEFT, padx=5)

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

        # Graph frame 1: Flow Impedance
        graph_frame_1 = ttk.LabelFrame(graph_container, text="Portfolio Over Time", padding=5)
        graph_frame_1.pack(fill=tk.BOTH, expand=True, pady=5)

        # Create matplotlib figure for flow impedance
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
    
    def setup_auto_heater_frame(self, left_panel):
        """Set up the auto heater frame"""
        auto_heater_frame = ttk.LabelFrame(left_panel, text="Auto Heater", padding=10)
        auto_heater_frame.pack(fill=tk.X, pady=5)

        # Validation registration
        vcmd = (self.root.register(validate_impedance_val),
                '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')

        # Impedance set point input
        ttk.Label(auto_heater_frame, text="Flow Impedance Set Point").grid(row=0, column=0, padx=(0, 8), pady=4, sticky="W")

        self.auto_heater_setpoint = tk.IntVar(value=0)
        self.auto_heater_setpoint_spinbox = ttk.Spinbox(
            auto_heater_frame,
            from_=0,
            to=65535,
            textvariable=self.auto_heater_setpoint,
            validate="key",
            validatecommand=vcmd,
            width=10,
            justify=tk.CENTER
        )
        self.auto_heater_setpoint_spinbox.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="W")

        # Auto heater buttons
        auto_heater_button_frame = ttk.Frame(auto_heater_frame)
        auto_heater_button_frame.grid(row=1, column=0, columnspan=2, sticky="EW", pady=(6, 0))

        self.auto_heater_start_button = ttk.Button(
            auto_heater_button_frame,
            text="Auto Heater Start",
            command=self.on_auto_heater_start,
            state=tk.DISABLED
        )
        self.auto_heater_start_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.auto_heater_stop_button = ttk.Button(
            auto_heater_button_frame,
            text="Auto Heater Stop",
            command=self.on_auto_heater_stop,
            state=tk.DISABLED
        )
        self.auto_heater_stop_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)


    def setup_heater_sched_frame(self, parent):
        """Set up the Heater Schedule frame."""
        heater_sched_frame = ttk.LabelFrame(parent, text="Heater Schedule", padding=10)
        heater_sched_frame.pack(fill=tk.X, pady=5)
        
        # Validation registration
        vcmd = (self.root.register(validate_schedule_time),
                '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')
        
        # Duty cycle options
        duty_options = ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100"]
        
        # Header labels
        ttk.Label(heater_sched_frame, text="").grid(row=0, column=0, padx=6, pady=4)  # spacer for schedule label column
        ttk.Label(heater_sched_frame, text="Duty Cycle (%)").grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(heater_sched_frame, text="Time On (sec)").grid(row=0, column=3, padx=6, pady=4)
        ttk.Label(heater_sched_frame, text="Time Off (sec)").grid(row=0, column=5, padx=6, pady=4)
        
        # Create rows with Duty Cycle, Time On, Time Off on the same row for each
        for r in range(SCHEDULE_ROWS):
            row_idx = r + 1  # start at grid row 1 (row 0 is header)
            
            # Schedule label (e.g., "Sched 1:")
            ttk.Label(heater_sched_frame, text=f"Sched {row_idx}:").grid(row=row_idx, column=0, sticky="W", padx=(0, 6))
            
            # Duty cycle
            dc_var = tk.StringVar()
            dc_cb = ttk.Combobox(heater_sched_frame, textvariable=dc_var, state="readonly",
                                 values=duty_options, width=8)
            dc_cb.grid(row=row_idx, column=1, sticky="W", padx=(0, 12))
            dc_cb.current(9)  # default to 100%
            self.heater_duty_cycle_vars.append(dc_var)
            
            # Time On
            ton_var = tk.StringVar(value="0")
            ton_entry = ttk.Entry(heater_sched_frame, textvariable=ton_var, validate="key",
                                  validatecommand=vcmd, width=8)
            # spacer column to align with header
            ttk.Label(heater_sched_frame, text="").grid(row=row_idx, column=2)
            ton_entry.grid(row=row_idx, column=3, sticky="W", padx=(0, 12))
            self.flow_time_on_vars.append(ton_var)
            
            # Time Off
            toff_var = tk.StringVar(value="0")
            toff_entry = ttk.Entry(heater_sched_frame, textvariable=toff_var, validate="key",
                                   validatecommand=vcmd, width=8)
            # spacer column to align with header
            ttk.Label(heater_sched_frame, text="").grid(row=row_idx, column=4)
            toff_entry.grid(row=row_idx, column=5, sticky="W")
            self.flow_time_off_vars.append(toff_var)
        
        # Button frame for Heater Schedule Start and Heater Stop buttons
        button_frame = ttk.Frame(heater_sched_frame)
        button_frame.grid(row=SCHEDULE_ROWS + 2, column=0, columnspan=6, pady=(10, 0), sticky="EW")
        
        self.heater_sched_start_button = ttk.Button(
            button_frame,
            text="Heater Schedule Start",
            command=self.on_heater_sched_start,
            state=tk.DISABLED
        )
        self.heater_sched_start_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        self.heater_stop_button = ttk.Button(
            button_frame,
            text="Heater Schedule Stop",
            command=self.on_heater_sched_stop,
            state=tk.DISABLED
        )
        self.heater_stop_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Button frame Heater state
        heater_state_frame = ttk.Frame(heater_sched_frame)
        heater_state_frame.grid(row=SCHEDULE_ROWS + 4, column=0, columnspan=6, pady=(10, 0), sticky="EW")

        # Heater state indicator
        self.heater_state_var = ttk.Label(
            heater_state_frame,
            text="Heater State: Off"
        )
        self.heater_on_set(False)
        self.heater_state_var.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Heater schedule repeat checkbox
        self.heater_sched_repeat_var = tk.BooleanVar(value=False)
        self.heater_sched_repeat_check = ttk.Checkbutton(
            heater_state_frame,
            text="Heater Schedule Repeat",
            variable=self.heater_sched_repeat_var
        )
        self.heater_sched_repeat_check.pack(side=tk.RIGHT, fill=tk.X, padx=20, pady=2)
        self.ui_var_disable(self.heater_sched_repeat_check)
        
        # Configure column weights for spacing
        for i in range(6):
            heater_sched_frame.columnconfigure(i, weight=0)

    def setup_bubble_gen_sched_frame(self, parent):
        """Set up the Bubble Generator Schedule frame."""
        bubble_gen_sched_frame = ttk.LabelFrame(parent, text="Bubble Generator Schedule", padding=10)
        bubble_gen_sched_frame.pack(fill=tk.X, pady=5)

        # Validation registration
        vcmd = (self.root.register(validate_schedule_time),
                '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')

        # Header labels (no Duty Cycle column)
        ttk.Label(bubble_gen_sched_frame, text="").grid(row=0, column=0, padx=6, pady=4)
        ttk.Label(bubble_gen_sched_frame, text="Time On (sec)").grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(bubble_gen_sched_frame, text="Time Off (sec)").grid(row=0, column=3, padx=6, pady=4)

        # Create rows with Time On and Time Off
        for r in range(SCHEDULE_ROWS):
            row_idx = r + 1

            ttk.Label(bubble_gen_sched_frame, text=f"Sched {row_idx}:").grid(
                row=row_idx, column=0, sticky="W", padx=(0, 6))

            # Time On
            ton_var = tk.StringVar(value="0")
            ton_entry = ttk.Entry(bubble_gen_sched_frame, textvariable=ton_var, validate="key",
                                  validatecommand=vcmd, width=8)
            ton_entry.grid(row=row_idx, column=1, sticky="W", padx=(0, 12))
            self.bubble_time_on_vars.append(ton_var)

            # Time Off
            toff_var = tk.StringVar(value="0")
            toff_entry = ttk.Entry(bubble_gen_sched_frame, textvariable=toff_var, validate="key",
                                   validatecommand=vcmd, width=8)
            ttk.Label(bubble_gen_sched_frame, text="").grid(row=row_idx, column=2)
            toff_entry.grid(row=row_idx, column=3, sticky="W")
            self.bubble_time_off_vars.append(toff_var)

        # Button frame for Bubble Generator Schedule Start and Stop buttons
        button_frame = ttk.Frame(bubble_gen_sched_frame)
        button_frame.grid(row=SCHEDULE_ROWS + 1, column=0, columnspan=4, pady=(10, 0), sticky="EW")

        self.bubble_gen_sched_start_button = ttk.Button(
            button_frame,
            text="Bubble Schedule Start",
            command=self.on_bubble_gen_sched_start,
            state=tk.DISABLED
        )
        self.bubble_gen_sched_start_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.bubble_gen_stop_button = ttk.Button(
            button_frame,
            text="Bubble Schedule Stop",
            command=self.on_bubble_gen_sched_stop,
            state=tk.DISABLED
        )
        self.bubble_gen_stop_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Bubble Generator state indicator
        bubble_gen_state_frame = ttk.Frame(bubble_gen_sched_frame)
        bubble_gen_state_frame.grid(
            row=SCHEDULE_ROWS + 3, column=0, columnspan=4, pady=(10, 0), sticky="EW")

        self.bubble_gen_state_var = ttk.Label(
            bubble_gen_state_frame,
            text="Bubble Generator State: Off"
        )
        self.bubble_gen_state_var.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Configure column weights for spacing
        for i in range(4):
            bubble_gen_sched_frame.columnconfigure(i, weight=0)

    def start_async_loop(self):
        """Start the async event loop in a separate thread."""
        def run_loop():
            try:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                self.loop.run_forever()
            except Exception:
                self.log.error("Async event loop stopped unexpectedly")

        self.async_thread = threading.Thread(daemon=True, target=run_loop)
        self.async_thread.start()

    def run_async(self, coro, timed=5.0):
        """
        Run a coroutine in the async event loop with detailed error handling.
        
        Args:
            coro: The coroutine to run
            timed: Timeout in seconds (added to buffer for overhead)
        
        Returns:
            Result on success, False on failure, None if event loop unavailable
        """
        if not self.loop:
            self.log.error("Event loop not running")
            return None
        
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        timeout_with_buffer = timed + 10.0
        
        try:
            return future.result(timeout=timeout_with_buffer)
        except concurrent.futures.TimeoutError:
            future.cancel()
            self.log.error(f"Operation timed out after {timed}s")
            return False
        except concurrent.futures.CancelledError:
            self.log.warning("Async operation was cancelled")
            return False
        except MultiSenseError as e:
            self.log.error(str(e))
            return False
        except Exception:
            self.log.error("Unexpected async operation failure")
            return False

    def update_log_display(self):
        """Update the log display with messages from the queue."""
        try:
            while True:
                levelname, message = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"{message}\n", levelname)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        
        self.root.after(LOG_UPDATE_INTERVAL_MS, self.update_log_display)
    
    async def connection_check_loop(self):
        """Loop to check the BLE connection when it is active"""
        while not self._shutdown_event.is_set():
            self.connection_heartbeat()
            elapsed = 0.0
            sleep_step = 0.2
            while (elapsed < HEARTBEAT_INTERVAL_SEC) and (not self._shutdown_event.is_set()):
                wait_time = min(sleep_step, HEARTBEAT_INTERVAL_SEC - elapsed)
                await asyncio.sleep(wait_time)
                elapsed += wait_time

    def connection_thread_start(self):
        """Create and start the connection check thread"""
        def runner():
            asyncio.run(self.connection_check_loop())

        thread = threading.Thread(target=runner, name="Connection Check Thread", daemon=True)
        thread.start()
        self.connection_thread = thread
        return thread
    
    def connection_heartbeat(self):
        """When a connection is established, must send a periodic heartbeat"""
        if self.connected():
            ret = self.run_async(self.controller.heartbeat_verify(),
                                 timed=TIMEOUT_HEARTBEAT_VERIFY)

            if not ret:
                if not self.connect_state_transition(ConnectState.CONNECTED, ConnectState.DISCONNECTING):
                    with self._connect_state_lock:
                        state_name = self.connect_state.name
                    self.log.warning(f"Skipping heartbeat disconnect cleanup; state is {state_name}")
                    return
                
                # the connection is compromised
                self.disconnect_cleanup()
                self._disconnect_device_and_update_ui()

    def on_controller_disconnect(self):
        """Handle BLE disconnect callback from backend controller."""
        self.root.after(0, self._on_controller_disconnect_ui_thread)

    def _on_controller_disconnect_ui_thread(self):
        """Handle disconnect on UI thread."""
        if not self.connect_state_transition(ConnectState.CONNECTED, ConnectState.DISCONNECTING):
            return
        try:
            # this is an unexpected disconnect
            self.log.error("BLE Connection Lost")
            self.disconnect_cleanup()
        except Exception:
            self.log.error("Unexpected cleanup failure after backend disconnect callback")
        self.connect_state_set(ConnectState.DISCONNECTED)
        self.on_disconnection()

    def update_plot(self):
        """Update the impedance plots."""
        try:
            # Collect all new items from queue
            new_items = False
            while True:
                try:
                    q_item = self.controller.impedance_q.get_nowait()
                    self.flow_imped_q.append(q_item.flow_imped)
                    self.flow_drift_imped_q.append(q_item.flow_drift_imped)
                    self.pressure_imped_q.append(q_item.pressure_imped)
                    self.patency_imped_q.append(q_item.patency_imped)
                    # convert milliseconds to minutes
                    self.timestamp_imped_q.append(((q_item.timestamp)/1000)/60)
                    new_items = True
                except queue.Empty:
                    break
            
            if new_items:
                live_plot = self.live_plot_var.get()
                time_list = list(self.timestamp_imped_q)

                if live_plot == "Flow":
                    flow_list = list(self.flow_imped_q)
                    flow_drift_list = list(self.flow_drift_imped_q)

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
                    
                    # Update flow drift impedance plot - reuse existing lines
                    if not hasattr(self, 'drift_line'):
                        # First time: create the plot
                        self.drift_line, = self.ax_drift.plot(time_list, flow_drift_list, marker='o', linestyle='-', linewidth=1, color='#ff7f0e')
                        self.ax_drift.set_xlabel(PLOT_X_LABEL)
                        self.ax_drift.set_ylabel(PLOT_Y_LABEL)
                        self.ax_drift.set_title(PLOT_TITLE_FLOW_DRIFT)
                        self.ax_drift.grid(True, alpha=0.3)
                    else:
                        # Subsequent updates: just update the data
                        self.drift_line.set_data(time_list, flow_drift_list)
                        # Auto-scale axes to fit new data
                        self.ax_drift.relim()
                        self.ax_drift.autoscale_view()
                    
                    self.figure_drift.tight_layout()
                    self.canvas_drift.draw_idle()

                elif live_plot == "Pressure":
                    pressure_list = list(self.pressure_imped_q)

                    # Update pressure impedance plot — reuse existing lines
                    if not hasattr(self, 'pressure_line'):
                        # First time: create the plot
                        self.pressure_line, = self.ax_pressure.plot(time_list, pressure_list, marker='o', linestyle='-', linewidth=1, color='#2ca02c')
                        self.ax_pressure.set_xlabel(PLOT_X_LABEL)
                        self.ax_pressure.set_ylabel(PLOT_Y_LABEL)
                        self.ax_pressure.set_title(PLOT_TITLE_PRESSURE)
                        self.ax_pressure.grid(True, alpha=0.3)
                    else:
                        # Subsequent updates: just update the data
                        self.pressure_line.set_data(time_list, pressure_list)
                        # Auto-scale axes to fit new data
                        self.ax_pressure.relim()
                        self.ax_pressure.autoscale_view()

                    self.figure_pressure.tight_layout()
                    self.canvas_pressure.draw_idle()

                elif live_plot == "Patency":
                    patency_list = list(self.patency_imped_q)

                    # Update patency impedance plot — reuse existing lines
                    if not hasattr(self, 'patency_line'):
                        # First time: create the plot
                        self.patency_line, = self.ax_patency.plot(
                            time_list, patency_list, marker='o', linestyle='-', linewidth=1, color='#9467bd'
                        )
                        self.ax_patency.set_xlabel(PLOT_X_LABEL)
                        self.ax_patency.set_ylabel(PLOT_Y_LABEL)
                        self.ax_patency.set_title(PLOT_TITLE_PATENCY)
                        self.ax_patency.grid(True, alpha=0.3)
                    else:
                        # Subsequent updates: just update the data
                        self.patency_line.set_data(time_list, patency_list)
                        # Auto-scale axes to fit new data
                        self.ax_patency.relim()
                        self.ax_patency.autoscale_view()

                    self.figure_patency.tight_layout()
                    self.canvas_patency.draw_idle()
                else:
                    self.log.debug("Unknown live plot value")

                # evaluate auto heater with impedance values of flow
                self.root.after(0, lambda: self.auto_heater_evaluate(self.flow_imped_q))

        except Exception:
            self.log.error("Unexpected plot update failure")
        
        self.root.after(PLOT_UPDATE_INTERVAL_MS, self.update_plot)

    def ui_var_disable(self, ui_var):
        ui_var.config(state=tk.DISABLED)
    
    def ui_var_enable(self, ui_var):
        ui_var.config(state=tk.NORMAL)

    def button_enable(self, button):
        button.config(state=tk.NORMAL)

    def ui_disable_all(self):
        """Disable all UI widgets"""
        def update():
            self.ui_var_disable(self.scan_button)
            self.ui_var_disable(self.connect_button)
            self.ui_var_disable(self.disconnect_button)
            self.ui_var_disable(self.stream_start_button)
            self.ui_var_disable(self.stream_stop_button)
            self.ui_var_disable(self.heater_sched_start_button)
            self.ui_var_disable(self.heater_stop_button)
            self.ui_var_disable(self.bubble_gen_sched_start_button)
            self.ui_var_disable(self.bubble_gen_stop_button)
            self.ui_var_disable(self.auto_heater_start_button)
            self.ui_var_disable(self.auto_heater_stop_button)

            self.ui_var_disable(self.log_output_check)
            self.ui_var_disable(self.auto_stream_check)
            self.ui_var_disable(self.heater_sched_repeat_check)
            self.ui_var_disable(self.auto_heater_setpoint_spinbox)
            self.ui_var_disable(self.live_plot_cb)

        self.root.after(0, update)

    def ui_state_update(self, state:ConnectState):
        """Update the UI states based on the connection state"""
        match state:
            case ConnectState.SCANNING | ConnectState.CONNECTING | ConnectState.DISCONNECTING:
                # all buttons/checkboxes are temporarily disabled during these states
                self.ui_disable_all()
            case ConnectState.CONNECTED:
                self.connected_ui_update()

            case ConnectState.DISCONNECTED:
                self.disconnected_ui_update()

            case _:
                self.log.error(f"Unknown connection state: {state}")
                return

    def connect_state_set(self, state:ConnectState):
        """Update the connection state"""
        if state in ConnectState:
            if state == ConnectState.CONNECTED:
                with self._disconnect_lock:
                    self._disconnect_cleanup_done = False
                    self._disconnect_call_active = False
            with self._connect_state_lock:
                self.connect_state = state
            self.ui_state_update(state)
        else:
            self.log.error(f"Unknown connection state: {state}")

    def connect_state_get(self) -> ConnectState:
        with self._connect_state_lock:
            return self.connect_state

    def connect_state_transition(self, expected_state: ConnectState, next_state: ConnectState) -> bool:
        """Atomically transition connect state when current state matches expected."""
        with self._connect_state_lock:
            if self.connect_state != expected_state:
                return False
            self.connect_state = next_state
        self.ui_state_update(next_state)
        return True

    def on_scan_devices(self):
        """Scan for available Bluetooth devices."""

        self.log.info("Puppy is cute")
        if (self.connect_state_get() != ConnectState.DISCONNECTED):
            return

        self.connect_state_set(ConnectState.SCANNING)

        self.connect_device_address = None
        self.device_listbox.delete(0, tk.END)
        self.device_listbox.insert(tk.END, "Scanning...")
        
        def scan():
            devices = []
            result = self.run_async(self.controller.scan_devices(timeout=TIMEOUT_SCAN),
                                     timed=TIMEOUT_SCAN)
            # run_async can return None (loop unavailable) or False (timeout/error);
            # only treat a real list as a successful scan.
            if isinstance(result, list):
                devices = result
                self.root.after(0, lambda: self.display_devices(devices))
            else:
                self.root.after(0, lambda: self.device_listbox.delete(0, tk.END))

            self.root.after(0, lambda: self.connect_state_set(ConnectState.DISCONNECTED))
        
        threading.Thread(daemon=True, target=scan).start()
    
    def display_devices(self, devices):
        """Display discovered MultiSense devices in the listbox."""
        self.device_listbox.delete(0, tk.END)

        matching_devices = [
            f"{device.name} ({device.address})"
            for device in devices
            if device.name == BT_DEVICE_NAME
        ]

        if matching_devices:
            for device_info in matching_devices:
                self.device_listbox.insert(tk.END, device_info)
        else:
            self.device_listbox.insert(tk.END, "No MultiSense devices found")

    
    def on_device_selected(self, event):
        """Handle device selection from listbox."""
        selection = self.device_listbox.curselection()
        if not selection:
            return
        
        device_info = self.device_listbox.get(selection[0])

        # Extract MAC address from "Name (Address)" format
        self.connect_device_address = device_info.split('(')[-1].rstrip(')')

        # only enable the connect button if in the proper state
        if(self.connect_state_get() == ConnectState.DISCONNECTED):
            self.ui_var_enable(self.connect_button)
    
    def on_connect_device(self):
        """Connect to the selected device."""

        if (self.connect_state_get() != ConnectState.DISCONNECTED):
            return
        
        if not self.connect_device_address:
            messagebox.showerror("Error", "No device selected")
            return
        
        self.connect_state_set(ConnectState.CONNECTING)
        
        def connect():
            success = self.run_async(self.controller.connect(self.connect_device_address, TIMEOUT_CONNECT),
                                     timed=TIMEOUT_CONNECT)

            if(success):
                self.root.after(0, lambda: self.connect_state_set(ConnectState.CONNECTED))
            else:
                self.root.after(0, lambda: self.connect_state_set(ConnectState.DISCONNECTED))

            self.root.after(0, lambda: self.on_connection_result(success))

        
        threading.Thread(daemon=True, target=connect).start()

    def connected_ui_update(self):
        """ Update the UI states when a BLE connection is established"""
        def update():
            self.ui_var_disable(self.scan_button)
            self.ui_var_disable(self.connect_button)
            self.ui_var_enable(self.disconnect_button)
            self.ui_var_enable(self.stream_start_button)
            self.ui_var_enable(self.heater_sched_start_button)
            self.ui_var_enable(self.bubble_gen_sched_start_button)
            self.ui_var_enable(self.auto_heater_start_button)
            self.ui_var_enable(self.log_output_check)
            self.ui_var_enable(self.live_plot_cb)
            self.ui_var_enable(self.auto_stream_check)
            self.ui_var_enable(self.heater_sched_repeat_check)
            self.ui_var_enable(self.auto_heater_setpoint_spinbox)
        self.root.after(0, update)

    def on_connection_result(self, success: bool):
        """Handle connection result."""
        if success:
            self.status_label.config(
                text=f"Status: Connected to {self.connect_device_address}",
                foreground="green"
            )
    
    def disconnect_cleanup(self):
        """Cleanup on a disconnection event"""
        pass

    def on_start_streaming(self):
        """Start sensor streaming."""
        pass
    
    def on_stop_streaming(self):
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