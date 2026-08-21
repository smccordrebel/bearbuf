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

from multisense_lab import (
    MultiSenseError,
    MultiSenseController,
    IMPEDANCE_SAMPLE_Q_MAX
)

__version__ = "1.0"

# ============================================================================
# Logging Configuration
# ============================================================================

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
        
        # Controller and async management
        self.controller = MultiSenseController()
        self.controller.set_disconnect_handler(self.on_controller_disconnect)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.async_thread: Optional[threading.Thread] = None
        self.connection_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Logging queue
        self.log_queue: queue.Queue = queue.Queue()
        self.setup_logging()
        self.log = logging.getLogger("multisense_lab")
        
        # Data storage for streaming data
        self.flow_imped_q = deque(maxlen=IMPEDANCE_SAMPLE_Q_MAX)
        self.flow_drift_imped_q = deque(maxlen=IMPEDANCE_SAMPLE_Q_MAX)
        self.pressure_imped_q = deque(maxlen=IMPEDANCE_SAMPLE_Q_MAX)
        self.patency_imped_q = deque(maxlen=IMPEDANCE_SAMPLE_Q_MAX)
        self.timestamp_imped_q = deque(maxlen=IMPEDANCE_SAMPLE_Q_MAX)

        # heater schedule queue
        self.schedule_q = queue.Queue(SCHEDULE_Q_MAX)

        # State tracking
        self.connect_state = ConnectState.DISCONNECTED
        self._connect_state_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._disconnect_lock = threading.Lock()
        self._disconnect_cleanup_done = False
        self._disconnect_call_active = False
        self.connect_device_address: Optional[str] = None

        # sensor streaming
        self.is_streaming = False

        # auto heater control
        self.is_auto_heater_on = False

        # heater/bubble generator schedule
        self.schedule_state = SchedState.IDLE
        self.is_heater_on = False
        self.is_bubble_gen_on = False
        
        # Heater schedule variables
        self.heater_duty_cycle_vars = []
        self.flow_time_on_vars = []
        self.flow_time_off_vars = []

        # Bubble generator schedule variables
        self.bubble_time_on_vars = []
        self.bubble_time_off_vars = []
        
        # UI Components
        self.setup_ui()
        self.disconnected_ui_update()
        
        # Start event loop thread
        self.start_async_loop()
        
        # Start logging update loop
        self.update_log_display()

        # Start the connection check loop
        self.connection_thread_start()

         # Start plot update loop
        self.update_plot()
    
    def setup_logging(self):
        """Configure logging to use queue handler."""
        self._multisense_lab_logger = logging.getLogger("multisense_lab")
        queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        queue_handler.setFormatter(formatter)
        self._multisense_lab_logger.addHandler(queue_handler)
        self._queue_handler = queue_handler
    
    def setup_ui(self):
        """Set up the main UI components."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.connection_frame = ttk.Frame(self.notebook)
        self.control_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.connection_frame, text="Bluetooth Connection")
        self.notebook.add(self.control_frame, text="Sensor Control")
        
        # Setup connection tab
        self.setup_connection_tab()
        
        # Setup control tab
        self.setup_control_tab()
    
    def setup_connection_tab(self):
        """Set up the Bluetooth connection tab."""
        # Title
        title_label = ttk.Label(
            self.connection_frame,
            text="Bluetooth Device Connection",
            font=("Arial", 14, "bold")
        )
        title_label.pack(pady=10)
        
        # Device list frame
        list_frame = ttk.LabelFrame(self.connection_frame, text="Available Devices", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbar for device list
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Device listbox
        self.device_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=15)
        self.device_listbox.pack(fill=tk.BOTH, expand=True)
        self.device_listbox.bind("<<ListboxSelect>>", self.on_device_selected)
        scrollbar.config(command=self.device_listbox.yview)
        
        # Button frame
        button_frame = ttk.Frame(self.connection_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Scan button
        self.scan_button = ttk.Button(
            button_frame,
            text="Scan for Devices",
            command=self.on_scan_devices
        )
        self.scan_button.pack(side=tk.LEFT, padx=5)
        
        # Connect button
        self.connect_button = ttk.Button(
            button_frame,
            text="Connect",
            command=self.on_connect_device,
            state=tk.DISABLED
        )
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        # Disconnect button
        self.disconnect_button = ttk.Button(
            button_frame,
            text="Disconnect",
            command=self.on_disconnect_device,
            state=tk.DISABLED
        )
        self.disconnect_button.pack(side=tk.LEFT, padx=5)
        
        # Connection status frame
        status_frame = ttk.LabelFrame(self.connection_frame, text="Connection Status", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = ttk.Label(
            status_frame,
            text="Status: Disconnected",
            font=("Arial", 11),
            foreground="red"
        )
        self.status_label.pack()
        
        # Logging output
        log_frame = ttk.LabelFrame(self.connection_frame, text="Logging Output", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            width=80,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for colored output
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("DEBUG", foreground="blue")
        self.log_text.tag_config("WARNING", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")
    
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

        # Sensor streaming frame
        streaming_frame = ttk.LabelFrame(left_container, text="Sensor Streaming", padding=10)
        streaming_frame.pack(fill=tk.X, pady=5)

        stream_button_frame = ttk.Frame(streaming_frame)
        stream_button_frame.pack(fill=tk.X, pady=2)

        self.stream_start_button = ttk.Button(
            stream_button_frame,
            text="Start Streaming",
            command=self.on_start_streaming,
            state=tk.DISABLED
        )
        self.stream_start_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.stream_stop_button = ttk.Button(
            stream_button_frame,
            text="Stop Streaming",
            command=self.on_stop_streaming,
            state=tk.DISABLED
        )
        self.stream_stop_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Impedance settle count frame
        settle_frame = ttk.LabelFrame(streaming_frame, padding=5)
        settle_frame.pack(fill=tk.X, pady=5)

        ttk.Label(settle_frame, text="BIOZ Settle Count").pack(side=tk.LEFT, padx=(0, 5))
        self.bioz_settle_count = tk.IntVar(value=4)
        self.settle_spinbox = ttk.Spinbox(
            settle_frame,
            from_=0,
            to=32,
            increment=2,
            textvariable=self.bioz_settle_count,
            width=5,
            justify=tk.CENTER
        )
        self.settle_spinbox.pack(side=tk.LEFT, padx=5)

        # Sensor streaming log output checkbox
        self.log_output_var = tk.BooleanVar(value=True)
        self.log_output_check = ttk.Checkbutton(
            streaming_frame,
            text="Log Output",
            variable=self.log_output_var
        )
        self.log_output_check.pack(side=tk.LEFT, fill=tk.X, pady=2)
        self.ui_var_disable(self.log_output_check)

        # Auto streaming output checkbox
        self.auto_stream_var = tk.BooleanVar(value=True)
        self.auto_stream_check = ttk.Checkbutton(
            streaming_frame,
            text="Auto Stream",
            variable=self.auto_stream_var
        )
        self.auto_stream_check.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=2)
        self.ui_var_disable(self.auto_stream_check)

        # Live plot options
        self.live_plot_label = tk.Label(streaming_frame, text="Live Plot")
        self.live_plot_label.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=2)

        live_plot_options = ["Flow", "Pressure", "Patency"]
        self.live_plot_var = tk.StringVar()
        self.live_plot_cb = ttk.Combobox(
            streaming_frame,
            textvariable=self.live_plot_var, 
            state="readonly", 
            values=live_plot_options, 
            width=8)
        self.live_plot_cb.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=2)
        self.live_plot_cb.current(0)  # default to Flow
        self.ui_var_disable(self.live_plot_cb)

        # Auto Heater Frame
        self.setup_auto_heater_frame(left_container)
        
        # Heater Schedule Frame
        self.setup_heater_sched_frame(left_container)

        # Bubble Generator Schedule Frame
        self.setup_bubble_gen_sched_frame(left_container)

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
        graph_frame_1 = ttk.LabelFrame(graph_container, text="Flow Impedance Over Time", padding=5)
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

        # Graph frame 2: Flow Drift Impedance
        graph_frame_2 = ttk.LabelFrame(graph_container, text="Flow Drift Impedance Over Time", padding=5)
        graph_frame_2.pack(fill=tk.BOTH, expand=True, pady=5)

        # Create matplotlib figure for flow drift impedance
        self.figure_drift = Figure(figsize=(8, 4), dpi=100)
        self.ax_drift = self.figure_drift.add_subplot(111)
        self.ax_drift.set_xlabel(PLOT_X_LABEL)
        self.ax_drift.set_ylabel(PLOT_Y_LABEL)
        self.ax_drift.set_title(PLOT_TITLE_FLOW_DRIFT)
        self.ax_drift.grid(True, alpha=0.3)

        # Embed matplotlib in tkinter
        self.canvas_drift = FigureCanvasTkAgg(self.figure_drift, master=graph_frame_2)
        self.canvas_drift.draw()
        self.canvas_drift.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Graph frame 3: Pressure Impedance
        graph_frame_3 = ttk.LabelFrame(graph_container, text="Pressure Impedance Over Time", padding=5)
        graph_frame_3.pack(fill=tk.BOTH, expand=True, pady=5)

        self.figure_pressure = Figure(figsize=(8, 4), dpi=100)
        self.ax_pressure = self.figure_pressure.add_subplot(111)
        self.ax_pressure.set_xlabel(PLOT_X_LABEL)
        self.ax_pressure.set_ylabel(PLOT_Y_LABEL)
        self.ax_pressure.set_title(PLOT_TITLE_PRESSURE)
        self.ax_pressure.grid(True, alpha=0.3)

        self.canvas_pressure = FigureCanvasTkAgg(self.figure_pressure, master=graph_frame_3)
        self.canvas_pressure.draw()
        self.canvas_pressure.get_tk_widget().pack(fill=tk.BOTH, expand=True)

         # Graph frame 4: Patency Impedance
        graph_frame_4 = ttk.LabelFrame(graph_container, text="Patency Impedance Over Time", padding=5)
        graph_frame_4.pack(fill=tk.BOTH, expand=True, pady=5)

        self.figure_patency = Figure(figsize=(8, 4), dpi=100)
        self.ax_patency = self.figure_patency.add_subplot(111)
        self.ax_patency.set_xlabel(PLOT_X_LABEL)
        self.ax_patency.set_ylabel(PLOT_Y_LABEL)
        self.ax_patency.set_title(PLOT_TITLE_PATENCY)
        self.ax_patency.grid(True, alpha=0.3)

        self.canvas_patency = FigureCanvasTkAgg(self.figure_patency, master=graph_frame_4)
        self.canvas_patency.draw()
        self.canvas_patency.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
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
        with self._disconnect_lock:
            if self._disconnect_cleanup_done:
                return
            self._disconnect_cleanup_done = True

        try:
            if self.streaming_on_get():
                self.stop_streaming()
                self.streaming_on_set(False)
        except Exception:
            self.log.error("Unexpected streaming cleanup failure during disconnect")

        try:
            if self.heater_on_get():
                self.heater_stop()
                self.heater_on_set(False)
        except Exception:
            self.log.error("Unexpected heater cleanup failure during disconnect")

        try:
            if self.bubble_gen_on_get():
                self.bubble_gen_stop()
                self.bubble_gen_on_set(False)
        except Exception:
            self.log.error("Unexpected bubble generator cleanup failure during disconnect")

        try:
            if self.is_auto_heater_on:
                self.stop_auto_heater()
                self.is_auto_heater_on = False
        except Exception:
            self.log.error("Unexpected auto heater cleanup failure during disconnect")

        try:
            self.clear_impedance_qs()
        except Exception:
            self.log.warning("Unexpected impedance queue cleanup failure during disconnect")

        state = self.schedule_state_get()
        if state != SchedState.IDLE:
            # post a stop to the scheduler queue
            try:
                self.schedule_q.put_nowait(SCHEDULE_STOP_ID)
            except queue.Full:
                self.log.warning("Scheduler queue full during disconnect")

            # set the scheduler state to idle
            try:
                self.schedule_state_set(SchedState.IDLE)
            except Exception:
                self.log.warning("Unexpected scheduler cleanup failure during disconnect")

    def _disconnect_call_acquire(self) -> bool:
        with self._disconnect_lock:
            if self._disconnect_call_active:
                return False
            self._disconnect_call_active = True
            return True

    def _disconnect_call_release(self) -> None:
        with self._disconnect_lock:
            self._disconnect_call_active = False

    def _disconnect_device_and_update_ui(self) -> None:
        if not self._disconnect_call_acquire():
            return
        try:
            self.run_async(self.controller.disconnect(), timed=TIMEOUT_DISCONNECT)
            # move to the disconnected state even if there is a failure
            try:
                self.root.after(0, lambda: self.connect_state_set(ConnectState.DISCONNECTED))
                self.root.after(0, self.on_disconnection)
            except Exception:
                self.log.warning("Unexpected UI update failure during disconnect")
        finally:
            self._disconnect_call_release()

    def on_disconnect_device(self):
        """Disconnect from the device."""

        if not self.connect_state_transition(ConnectState.CONNECTED, ConnectState.DISCONNECTING):
            return

        # before disconnecting, clean up
        self.disconnect_cleanup()

        threading.Thread(daemon=True, target=self._disconnect_device_and_update_ui).start()
    
    def on_disconnection(self):
        """Handle disconnection."""
        self.status_label.config(
            text="Status: Disconnected",
            foreground="red"
        )

    def clear_impedance_qs(self):
        """ Clear the queues used to shared impedance data"""
        self.flow_imped_q.clear()
        self.flow_drift_imped_q.clear()
        self.pressure_imped_q.clear()
        self.patency_imped_q.clear()
        self.timestamp_imped_q.clear()
        self.controller.impedance_q_clear()
    
    def disconnected_ui_update(self):
        """Reset connection-related UI to initial states."""
        def update():
            self.ui_var_enable(self.scan_button)

            if self.connect_device_address:
                self.ui_var_enable(self.connect_button)
            else:
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

            self.ui_var_disable(self.auto_stream_check)
            self.ui_var_disable(self.heater_sched_repeat_check)
            self.ui_var_disable(self.log_output_check)
            self.ui_var_disable(self.live_plot_cb)
            self.ui_var_disable(self.auto_heater_setpoint_spinbox)

            self.heater_on_set(False)
            self.bubble_gen_on_set(False)
        self.root.after(0, update)

    def on_start_streaming(self):
        """Start sensor streaming."""

        if self.streaming_on_get():
            return

        self.ui_var_disable(self.stream_start_button)

        def start_stream():
            self.start_streaming()
        threading.Thread(daemon=True, target=start_stream).start()

    def start_streaming(self) -> bool:
        """Call the controller to start streaming"""
        if self.streaming_on_get():
            return True

        self.clear_impedance_qs() # clear the old data
        ret = self.run_async(self.controller.sensor_stream_start(self.bioz_settle_count.get(),
                                                                 self.log_output_var.get()),
                                                                 timed=TIMEOUT_SENSOR_STREAM_START)
        if(ret):
            self.streaming_on_set(True)
        else:
            self.streaming_on_set(False)

        return ret
    
    def on_stop_streaming(self):
        """Stop sensor streaming."""

        if not self.streaming_on_get():
            self.log.info("Streaming is not started")
            return
        
        self.ui_var_disable(self.stream_stop_button)

        def stop_stream():
            self.stop_streaming()
        threading.Thread(daemon=True, target=stop_stream).start()

    def stop_streaming(self):
        """Call the controller to stop streaming"""
        if not self.streaming_on_get():
            return
        
        ret = self.run_async(self.controller.sensor_stream_stop(), timed=TIMEOUT_SENSOR_STREAM_STOP)
        if ret is False:
            self.log.warning("Sensor streaming may not have stopped cleanly")

        # regardless of success, set streaming to false
        self.streaming_on_set(False)

    def on_auto_heater_start(self):
        """
        Auto heater start. The heater is turned on/off based on the impedance
        set point for the flow sensor. 
        """
        if self.is_auto_heater_on:
            return
        
        if not self.auto_stream_var.get() or self.streaming_on_get():
            str = "Auto stream must be enabled and streaming must be stopped before starting Auto Heater"
            self.log.error(str)
            messagebox.showerror("Error", str)
            return

        if self.schedule_state_get() != SchedState.IDLE:
            str = "Scheduler must be idle before starting auto heater"
            self.log.error(str)
            messagebox.showerror("Error", str)
            return

        self.ui_var_disable(self.auto_heater_start_button)

        def auto_heater_start():
            self.start_auto_heater()
        threading.Thread(daemon=True, target=auto_heater_start).start()
            
    def start_auto_heater(self):
        """Call the controller to start streaming and enable auto heater"""
        if self.is_auto_heater_on:
            return

        self.is_auto_heater_on = True

        # start streaming to get impedance values, these are used to turn the heater on/off
        ret = self.start_streaming()
        if not ret:
            self.log.error("Streaming start failed")
            self.is_auto_heater_on = False
            self.schedule_ui_update(SchedState.IDLE)
        else:
            self.schedule_ui_update(SchedState.DISABLED)
        
    def on_auto_heater_stop(self):
        """
        Auto heater stop.
        """
        if not self.is_auto_heater_on:
            return
        
        self.ui_var_disable(self.auto_heater_stop_button)

        def auto_heater_stop():
            self.stop_auto_heater()
        threading.Thread(daemon=True, target=auto_heater_stop).start()

    def stop_auto_heater(self):
        """Stop auto heater"""
        if not self.is_auto_heater_on:
            return
        
        self.is_auto_heater_on = False

        # turn off streaming and heater
        if self.streaming_on_get():
            self.stop_streaming()

        if self.heater_on_get():
            self.heater_stop()

        # update UI elements
        self.schedule_ui_update(SchedState.IDLE)
        
    def auto_heater_evaluate(self, flow_imped: list):
        """Evaluate auto heater impedance values"""
        if self.is_auto_heater_on:
            imped_set_point = self.auto_heater_setpoint.get()

            # get the latest flow impedance value to evaluate
            imped_val = flow_imped[-1]

            if (imped_val > imped_set_point) and not self.heater_on_get():
                # run the heater at 100 duty cycle
                ret = self.heater_start(int(100))
                if not ret:
                    self.log.error("Unable to start the heater")
            elif (imped_val < imped_set_point) and self.heater_on_get():
                ret = self.heater_stop()
                if not ret:
                   self.log.error("Unable to stop the heater") 
            else:
                # leave the heater as is
                pass


    def clear_schedule_q(self):
        """Clear the queue used to share schedule information"""
        while True:
            try:
                self.schedule_q.get_nowait()
            except queue.Empty:
                break

    def heater_sched_read(self) -> list:
        rows_data = []
        for i in range(len(self.heater_duty_cycle_vars)):
            dc = self.heater_duty_cycle_vars[i].get()
            ton = self.flow_time_on_vars[i].get()
            toff = self.flow_time_off_vars[i].get()

            if dc == "":
                messagebox.showerror("Input error", f"Please select a duty cycle for Sched {i+1}.")
                return []
            if ton == "" or toff == "":
                messagebox.showerror("Input error", f"Please enter Time On and Time Off for Sched {i+1}.")
                return []
            try:
                dc_val = int(dc)
                ton_val = int(ton)
                toff_val = int(toff)
            except ValueError:
                messagebox.showerror("Input error", f"Time On and Time Off must be integers for Sched {i+1}.")
                return []
            if not (SCHEDULE_MIN_TIME <= ton_val <= SCHEDULE_MAX_TIME and 
                    SCHEDULE_MIN_TIME <= toff_val <= SCHEDULE_MAX_TIME):
                messagebox.showerror("Input error", f"Times must be between {SCHEDULE_MIN_TIME} and {SCHEDULE_MAX_TIME} seconds for Sched {i+1}.")
                return []
            rows_data.append((dc_val, ton_val, toff_val))

        return rows_data
            
    def on_heater_sched_start(self):
        self.on_schedule_start(SchedState.HEATER)

    def on_bubble_gen_sched_start(self):
        self.on_schedule_start(SchedState.BUBBLE_GEN)   

    def schedule_run(self, rows_data, state:SchedState, heater_repeat:bool):
        """Run a heater/bubble generator schedule"""
        repeat = True
        while repeat:
            for dc, ton, toff in rows_data:
                sched = SchedData(ton, toff, dc)
                ret = self.schedule_time_start(sched, state)
                if not ret:
                    break

            repeat = ret and heater_repeat

    def on_schedule_start(self, state:SchedState):
        """Start the heater/bubble generator schedule."""

        if self.schedule_state_get() != SchedState.IDLE:
            self.log.error("Scheduler is already active")
            return

        if self.auto_stream_var.get() and self.streaming_on_get():
            str = "Scheduler cannot control streaming unless streaming is stopped"
            self.log.error(str)
            messagebox.showerror("Error", str)
            return

        if self.is_auto_heater_on:
            self.log.error("Scheduler cannot run while auto heater is active")
            return

        # Collect all schedule rows values and validate
        if state == SchedState.HEATER:
            rows_data = self.heater_sched_read()
        elif state == SchedState.BUBBLE_GEN:
            rows_data = self.bubble_gen_sched_read()

        if rows_data == []:
            return

        no_time = True
        for row in rows_data:
            # check time on and time off
            if (row[1] > 0) or (row[2] > 0):
                no_time = False
                break

        # there is no time specified in the row data
        if no_time:
            return

        self.clear_schedule_q()

        def schedule_start():
            self.schedule_state_set(state)

            try:
                # if the schedule is controlling streaming, turn it on
                if self.auto_stream_var.get() and not self.streaming_on_get():
                    ret = self.start_streaming()
                else:
                    ret = True

                if not ret:
                    self.log.error("Streaming start failed")
                else:
                    heater_repeat = (state == SchedState.HEATER) and self.heater_sched_repeat_var.get()
                    self.schedule_run(rows_data, state, heater_repeat)
            except Exception:
                self.log.error("Unexpected schedule failure")
            finally:
                if self.auto_stream_var.get() and self.streaming_on_get():
                    self.stop_streaming()

                self.schedule_state_set(SchedState.IDLE)
        
        threading.Thread(daemon=True, target=schedule_start).start()

    def schedule_state_set(self, state:SchedState) -> None:
        """Set the schedule state"""
        with self._state_lock:
            if self.schedule_state == state:
                return
            self.schedule_state = state

        if self.connected():
            match state:
                case SchedState.HEATER:
                    self.schedule_ui_update(SchedState.HEATER)

                case SchedState.BUBBLE_GEN:
                    self.schedule_ui_update(SchedState.BUBBLE_GEN)

                case SchedState.DISABLED:
                    self.schedule_ui_update(SchedState.DISABLED)
    
                case SchedState.IDLE:
                    # if the heater or bubble generator are still on after the schedule stops,
                    # attempt to stop them
                    if(self.heater_on_get()):
                        self.heater_stop()

                    if(self.bubble_gen_on_get()):
                        self.bubble_gen_stop()

                    self.schedule_ui_update(SchedState.IDLE)

                case _:
                    self.log.error( f"Unknown Schedule State: {state}")
                    return

    def schedule_ui_update(self, state:SchedState):
        """update the scheduler UI elements based on the state"""
        match state:
            case SchedState.HEATER:
                # the heater schedule can be stopped at any time during the heater schedule, the bubble
                # generator schedule and auto heater are disabled
                self.root.after(0, lambda: self.ui_var_enable(self.heater_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_stop_button))

                #  disable the checkboxes
                self.root.after(0, lambda: self.ui_var_disable(self.log_output_check))
                self.root.after(0, lambda: self.ui_var_disable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_stream_check))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_repeat_check))

                # if the scheduler is controlling streaming, the streaming buttons are disabled
                if self.auto_stream_var.get():
                    self.root.after(0, lambda: self.ui_var_disable(self.stream_start_button))
                    self.root.after(0, lambda: self.ui_var_disable(self.stream_stop_button))

            case SchedState.BUBBLE_GEN:
                # the bubble schedule can be stopped at any time during the bubble schedule, the heater
                # generator schedule and auto heater are disabled
                self.root.after(0, lambda: self.ui_var_enable(self.bubble_gen_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_stop_button))

                # disable the checkboxes
                self.root.after(0, lambda: self.ui_var_disable(self.log_output_check))
                self.root.after(0, lambda: self.ui_var_disable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_stream_check))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_repeat_check))

                # if the scheduler is controlling streaming, the streaming buttons are disabled
                if self.auto_stream_var.get():
                    self.root.after(0, lambda: self.ui_var_disable(self.stream_start_button))
                    self.root.after(0, lambda: self.ui_var_disable(self.stream_stop_button))

            case SchedState.DISABLED:
                # the heater and bubble generator schedules are disabled when auto heater is active
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_stop_button))

                # enable auto heater stop
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_start_button))
                self.root.after(0, lambda: self.ui_var_enable(self.auto_heater_stop_button))

                # disable the checkboxes
                self.root.after(0, lambda: self.ui_var_disable(self.log_output_check))
                self.root.after(0, lambda: self.ui_var_disable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_stream_check))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_sched_repeat_check))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_setpoint_spinbox))

                # auto heater always controls streaming
                self.root.after(0, lambda: self.ui_var_disable(self.stream_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.stream_stop_button))

            case SchedState.IDLE:
                # the scheduler is inactive, enable the start buttons/checkboxes
                self.root.after(0, lambda: self.ui_var_enable(self.bubble_gen_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.bubble_gen_stop_button))
                self.root.after(0, lambda: self.ui_var_enable(self.heater_sched_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.heater_stop_button))
                self.root.after(0, lambda: self.ui_var_enable(self.auto_heater_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.auto_heater_stop_button))
                
                self.root.after(0, lambda: self.ui_var_enable(self.log_output_check))
                self.root.after(0, lambda: self.ui_var_enable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_enable(self.auto_stream_check))
                self.root.after(0, lambda: self.ui_var_enable(self.heater_sched_repeat_check))
                self.root.after(0, lambda: self.ui_var_enable(self.auto_heater_setpoint_spinbox))

                # if the scheduler was controlling streaming, update the buttons
                if self.auto_stream_var.get():
                    if not self.streaming_on_get():
                        self.root.after(0, lambda: self.ui_var_enable(self.stream_start_button))
                        self.root.after(0, lambda: self.ui_var_disable(self.stream_stop_button))

            case _:
                self.log.error( f"Unknown Schedule State: {state}")
                return
                    
    def schedule_state_get(self) -> SchedState:
        with self._state_lock:
            return self.schedule_state

    def heater_on_set(self, state:bool) -> None:
        """Set the heater on state"""
        with self._state_lock:
            if self.is_heater_on == state:
                return
            self.is_heater_on = state

        def update():
            if self.is_heater_on:
                self.heater_state_var.config(foreground="red", text="Heater State: ON")
            else:
                self.heater_state_var.config(foreground="black", text="Heater State: OFF")

        self.root.after(0, update)

    def heater_on_get(self) -> bool:
        """Return the heater on state"""
        with self._state_lock:
            return self.is_heater_on

    def heater_start(self, duty_cycle:int) -> bool:
        """Turn on the heater at the specified duty cycle"""
        if self.heater_on_get():
            return True
        else:
            ret = self.run_async(self.controller.heater_start(duty_cycle), timed=TIMEOUT_HEATER_START)
            if ret:
                self.heater_on_set(True)

            return ret

    def heater_stop(self) -> bool:
        """Turn off the heater"""
        if not self.heater_on_get():
            return True
        else:
            ret = self.run_async(self.controller.heater_stop(), timed=TIMEOUT_HEATER_STOP)
            # regardless of success, set the heater on to false
            self.heater_on_set(False)
            return ret
    
    def bubble_gen_start(self) -> bool:
        """Turn on the bubble generator"""
        if self.bubble_gen_on_get():
            return True
        else:
            ret = self.run_async(self.controller.bubble_gen_start(), timed=TIMEOUT_BUBBLE_GEN_START)
            if ret:
                self.bubble_gen_on_set(True)

            return ret

    def bubble_gen_stop(self) -> bool:
        """Turn off the bubble generator"""
        if not self.bubble_gen_on_get():
            return True
        else:
            ret = self.run_async(self.controller.bubble_gen_stop(), timed=TIMEOUT_BUBBLE_GEN_STOP)
            # regardless of success, set the bubble generator on to false
            self.bubble_gen_on_set(False)
            return ret

    def bubble_gen_on_set(self, state:bool) -> None:
        """Set the bubble generator on state"""
        with self._state_lock:
            if self.is_bubble_gen_on == state:
                return
            self.is_bubble_gen_on = state

        def update():
            if self.is_bubble_gen_on:
                self.bubble_gen_state_var.config(foreground="red", text="Bubble Generator State: ON")
            else:
                self.bubble_gen_state_var.config(foreground="black", text="Bubble Generator State: OFF")

        self.root.after(0, update)

    def bubble_gen_on_get(self) -> bool:
        """Return the bubble generator on state"""
        with self._state_lock:
            return self.is_bubble_gen_on

    def schedule_time_start(self, sched:SchedData, state:SchedState) -> bool:
        """
        Turn the heater or bubble generator on/off at the specified time periods.
        """
        ret = True
        if(sched.time_on > 0):
            ret = False
            if state == SchedState.HEATER:
                ret = self.heater_start(sched.duty_cycle)

            elif state == SchedState.BUBBLE_GEN:
                ret = self.bubble_gen_start()

            if ret:
                ret = self.schedule_wait(sched.time_on)

        if(ret and (sched.time_off > 0)):
            ret = False
            if state == SchedState.HEATER:
                ret = self.heater_stop()

            elif state == SchedState.BUBBLE_GEN:
                ret = self.bubble_gen_stop()

            if ret:
                ret = self.schedule_wait(sched.time_off)

        return ret
    
    def schedule_wait(self, time_sec) -> bool:
        """
        Wait for a timer to expire or for an event to arrive on the schedule queue

        @return True if the timer expires, False if a stop event is received
        """
        try:
            q_item = self.schedule_q.get(timeout=time_sec)
            if(q_item == SCHEDULE_STOP_ID):
                return False
            else:
                self.log.error(f"Unexpected event on the schedule queue: {q_item}")
                return False
        except queue.Empty:
            # we have timed out waiting on the queue
            return True
        except Exception:
            self.log.error("Unexpected scheduler wait failure")
            return False

    def on_heater_sched_stop(self):
        self.on_schedule_stop(SchedState.HEATER)

    def on_bubble_gen_sched_stop(self):
        self.on_schedule_stop(SchedState.BUBBLE_GEN)

    def on_schedule_stop(self, state:SchedState):
        """Stop the scheduler."""

        if state == SchedState.HEATER:
            self.ui_var_disable(self.heater_stop_button)

        elif state == SchedState.BUBBLE_GEN:
            self.ui_var_disable(self.bubble_gen_stop_button)

        else:
            return

        def schedule_stop():
            if state == SchedState.HEATER:
                self.heater_stop()
            elif state == SchedState.BUBBLE_GEN:
                self.bubble_gen_stop()

            # post a STOP to the scheduler q if it is active
            if self.schedule_state_get() != SchedState.IDLE:
                try:
                    self.schedule_q.put_nowait(SCHEDULE_STOP_ID)
                except queue.Full:
                    self.log.warning("Schedule stop signal could not be queued because the scheduler queue is full")

            self.heater_on_set(False)
            self.bubble_gen_on_set(False)
            self.schedule_state_set(SchedState.IDLE)

        threading.Thread(daemon=True, target=schedule_stop).start()

    def bubble_gen_sched_read(self):
        """Read the bubble generator schedule data"""
        rows_data = []
        for i in range(len(self.bubble_time_on_vars)):
            ton = self.bubble_time_on_vars[i].get()
            toff = self.bubble_time_off_vars[i].get()

            if ton == "" or toff == "":
                messagebox.showerror("Input error", f"Please enter Time On and Time Off for Sched {i+1}.")
                return []
            try:
                ton_val = int(ton)
                toff_val = int(toff)
            except ValueError:
                messagebox.showerror("Input error", f"Time On and Time Off must be integers for Sched {i+1}.")
                return []
            if not (SCHEDULE_MIN_TIME <= ton_val <= SCHEDULE_MAX_TIME and
                    SCHEDULE_MIN_TIME <= toff_val <= SCHEDULE_MAX_TIME):
                messagebox.showerror("Input error", f"Times must be between {SCHEDULE_MIN_TIME} and {SCHEDULE_MAX_TIME} seconds for Sched {i+1}.")
                return []

            # duty cycle is currently unused for bubble generator
            rows_data.append((0, ton_val, toff_val))

        return rows_data
    
    def connected(self) -> bool:
        if self.connect_state_get() == ConnectState.CONNECTED:
            return True
        else:
            return False

    def streaming_on_set(self, state:bool) -> None:
        """Set the streaming on state"""
        with self._state_lock:
            if self.is_streaming == state:
                return
            self.is_streaming = state
            # Copy all states under one lock acquisition so UI updates use a
            # consistent streaming/schedule snapshot.
            is_streaming = self.is_streaming
            schedule_state = self.schedule_state
            auto_heater_state = self.is_auto_heater_on

        # if auto heater is active or the schedule is active and controlling streaming, do not
        # update buttons
        if auto_heater_state or ((schedule_state != SchedState.IDLE) and self.auto_stream_var.get()):
            return

        if self.connected():
            if is_streaming:
                self.root.after(0, lambda: self.ui_var_disable(self.stream_start_button))
                self.root.after(0, lambda: self.ui_var_enable(self.stream_stop_button))
                self.root.after(0, lambda: self.ui_var_disable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_disable(self.log_output_check))

            else:
                self.root.after(0, lambda: self.ui_var_enable(self.stream_start_button))
                self.root.after(0, lambda: self.ui_var_disable(self.stream_stop_button))
                self.root.after(0, lambda: self.ui_var_enable(self.live_plot_cb))
                self.root.after(0, lambda: self.ui_var_enable(self.log_output_check))

    def streaming_on_get(self) -> bool:
        with self._state_lock:
            return self.is_streaming

    def cleanup(self):
        """Clean up resources."""
        self.disconnect_cleanup()

        self._shutdown_event.set()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.connection_thread and self.connection_thread.is_alive():
            self.connection_thread.join(timeout=2.0)
            if self.connection_thread.is_alive():
                self.log.warning("Connection check thread did not stop within 2.0s shutdown timeout")

        if self.async_thread and self.async_thread.is_alive():
            self.async_thread.join(timeout=2.0)
            if self.async_thread.is_alive():
                self.log.warning("Async event loop thread did not stop within 2.0s shutdown timeout")

        try:
            if getattr(self, "_queue_handler", None):
                self._multisense_lab_logger.removeHandler(self._queue_handler)
        except Exception:
            pass


def main():
    """Main entry point for the UI application."""
    root = tk.Tk()
    ui = BearBufUI(root)
    
    def on_closing():
        """Handle window closing."""
        ui.cleanup()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()