import csv
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import importlib.util
import tkinter as tk
import webbrowser
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox, filedialog, simpledialog

APP_TITLE = "NEW VERSION 2026 (SHUBHVASTRA)"
REFERENCES = ["AGENT", "DIRECT", "CHAIN STORE", "EXPORTER"]
CSV_HEADERS = [
    "Party ID", "Party Name", "Phone Number", "Address", "City", "State",
    "Party GST Number", "Reference", "Transport Details", "Transport GST Number", "Agent Name"
]
REQUIRED_CSV_FIELDS = [
    "Party Name", "Phone Number", "Address", "City", "State", "Party GST Number",
    "Reference", "Transport Details", "Transport GST Number"
]
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "party_reporting.db"


def ensure_reportlab_installed():
    """Ensure ReportLab is available in the exact interpreter running this app.

    Try the common install routes in order and retain a diagnostic log so that
    PDF errors show the actual pip failure instead of a generic message.
    """
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        pass

    logs = []
    py = sys.executable

    # Some Python installations do not have pip bootstrapped yet.
    try:
        r = subprocess.run(
            [py, "-m", "ensurepip", "--upgrade"], capture_output=True,
            text=True, timeout=120
        )
        logs.append("ensurepip: " + ((r.stderr or r.stdout or "no output").strip()[-1200:]))
    except Exception as exc:
        logs.append("ensurepip: " + repr(exc))

    install_commands = [
        [py, "-m", "pip", "install", "--upgrade", "--user", "reportlab>=4.2,<5"],
        [py, "-m", "pip", "install", "--upgrade", "reportlab>=4.2,<5"],
    ]
    for cmd in install_commands:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
            logs.append("command: " + " ".join(cmd[1:]) + "\n" + (r.stderr or r.stdout or "no output").strip()[-1800:])
            importlib.invalidate_caches()
            try:
                import reportlab  # noqa: F401
                return True
            except Exception:
                if r.returncode == 0:
                    logs.append("pip reported success, but reportlab still cannot import")
        except Exception as exc:
            logs.append("install exception: " + repr(exc))

    try:
        (BASE_DIR / "pdf_install_error.log").write_text(
            "Python: " + py + "\n\n" + "\n\n".join(logs), encoding="utf-8"
        )
    except Exception:
        pass
    return False


class PartyReportingApp(tk.Tk):
    AUTO_BACKUP_INTERVAL_MS = 5 * 60 * 1000
    AUTO_BACKUP_KEEP_COUNT = 288  # approximately 24 hours at 5-minute intervals

    def __init__(self):
        super().__init__()
        self.title("NEW VERSION 2026 (SHUBHVASTRA) | Order Management")
        self.geometry("1360x820")
        self.minsize(1050, 680)
        self.configure(bg="#f3f5f8")

        self.conn = self.open_database(DB_PATH)
        self.create_tables()

        self.selected_party_id = None
        self.selected_agent_id = None
        self.agent_id_by_name = {}
        self.agent_phone_by_name = {}
        self.agent_name_by_id = {}
        self.party_vars = {}
        self.party_widgets = {}
        self.party_form_mode = "new"
        self.last_viewed_party_id = None

        self.setup_style()
        self.build_header()
        self.build_notebook()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Create a restore point at startup, then keep backing up every five minutes.
        self.create_automatic_backup()
        self.schedule_automatic_backup()

    @staticmethod
    def open_database(path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    phone_number TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS parties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    party_name TEXT NOT NULL COLLATE NOCASE,
                    phone_number TEXT NOT NULL,
                    address TEXT NOT NULL,
                    city TEXT NOT NULL,
                    state TEXT NOT NULL,
                    gst_number TEXT NOT NULL,
                    reference TEXT NOT NULL CHECK(reference IN ('AGENT','DIRECT','CHAIN STORE','EXPORTER')),
                    transport_details TEXT NOT NULL,
                    transport_gst_number TEXT NOT NULL,
                    agent_id INTEGER NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE RESTRICT
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_parties_name ON parties(party_name)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_parties_reference ON parties(reference)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_parties_agent ON parties(agent_id)")
            # Order-management tables are added without changing existing Party/Agent records.
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_no INTEGER NOT NULL UNIQUE,
                    order_date TEXT NOT NULL,
                    party_id INTEGER NOT NULL,
                    packaging TEXT NOT NULL DEFAULT '[]',
                    narration TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(party_id) REFERENCES parties(id) ON DELETE RESTRICT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    sr_no INTEGER NOT NULL,
                    particulars TEXT NOT NULL,
                    piece_rate REAL NOT NULL DEFAULT 0,
                    discount REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS order_item_sizes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_item_id INTEGER NOT NULL,
                    size_code TEXT NOT NULL,
                    ordered_qty INTEGER NOT NULL CHECK(ordered_qty > 0),
                    UNIQUE(order_item_id, size_code),
                    FOREIGN KEY(order_item_id) REFERENCES order_items(id) ON DELETE CASCADE
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS order_dispatches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_size_id INTEGER NOT NULL,
                    dispatched_size TEXT NOT NULL,
                    qty INTEGER NOT NULL CHECK(qty > 0),
                    dispatch_date TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    invoice_number TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(order_size_id) REFERENCES order_item_sizes(id) ON DELETE RESTRICT
                )
            """)
            # Migrate databases created by earlier versions without losing dispatch records.
            order_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(orders)")}
            if "cancelled" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
            size_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(order_item_sizes)")}
            if "cancelled" not in size_columns:
                self.conn.execute("ALTER TABLE order_item_sizes ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
            dispatch_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(order_dispatches)")}
            if "invoice_number" not in dispatch_columns:
                self.conn.execute("ALTER TABLE order_dispatches ADD COLUMN invoice_number TEXT NOT NULL DEFAULT ''")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_party ON orders(party_id, order_date)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_number ON orders(order_no)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_order_item_sizes_item ON order_item_sizes(order_item_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_order_dispatch_size ON order_dispatches(order_size_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatch_date ON order_dispatches(dispatch_date)")

    def setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f5f8")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f3f5f8", foreground="#243247", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#ffffff", foreground="#17365d", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", font=("Segoe UI", 9), padding=(8, 5))
        style.configure("PartyDetail.TEntry", font=("Segoe UI", 8), padding=(3, 2))
        style.configure("Primary.TButton", background="#1769aa", foreground="#ffffff", padding=(10, 6))
        style.map("Primary.TButton", background=[("active", "#12568c")], foreground=[("active", "#ffffff")])
        style.configure("Danger.TButton", background="#a93226", foreground="#ffffff", padding=(8, 5))
        style.map("Danger.TButton", background=[("active", "#85251c")])
        style.configure("TNotebook", background="#f3f5f8", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(17, 9))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#17365d")])
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26, background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#e7edf5", foreground="#17365d", padding=6)
        style.map("Treeview", background=[("selected", "#cfe4fb")], foreground=[("selected", "#162b44")])
        style.configure("KPI.TLabel", background="#ffffff", foreground="#17365d", font=("Segoe UI", 16, "bold"))
        style.configure("KPIName.TLabel", background="#ffffff", foreground="#65758b", font=("Segoe UI", 9))

    def build_header(self):
        header = tk.Frame(self, bg="#17365d", height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="NEW VERSION 2026  |  SHUBHVASTRA", bg="#17365d", fg="#ffffff",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(10, 0))
        tk.Label(header, text="Order Management • Party Master • Dispatch • Manufacturing Reports",
                 bg="#17365d", fg="#d9e6f5", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=23, pady=(5, 0))

    def build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=12)
        self.dashboard_tab = ttk.Frame(self.notebook, padding=10)
        self.party_tab = ttk.Frame(self.notebook, padding=10)
        self.order_tab = ttk.Frame(self.notebook, padding=8)
        self.pending_tab = ttk.Frame(self.notebook, padding=8)
        self.reports_tab = ttk.Frame(self.notebook, padding=8)
        self.utilities_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.dashboard_tab, text="  Party List  ")
        self.notebook.add(self.party_tab, text="  Party Details  ")
        self.notebook.add(self.order_tab, text="  Order Form  ")
        self.notebook.add(self.pending_tab, text="  Pending Orders  ")
        self.notebook.add(self.reports_tab, text="  Order Reports  ")
        self.notebook.add(self.utilities_tab, text="  Utilities  ")

        self.utilities_notebook = ttk.Notebook(self.utilities_tab)
        self.utilities_notebook.pack(fill="both", expand=True)
        self.agent_tab = ttk.Frame(self.utilities_notebook, padding=10)
        self.backup_tab = ttk.Frame(self.utilities_notebook, padding=10)
        self.utilities_notebook.add(self.agent_tab, text="  Agent Master  ")
        self.utilities_notebook.add(self.backup_tab, text="  Backup / Restore  ")

        self.build_dashboard_tab()
        self.build_party_tab()
        self.build_order_form_tab()
        self.build_pending_orders_tab()
        self.build_order_reports_tab()
        self.build_agent_tab()
        self.build_backup_tab()

    def make_card(self, parent, title=None):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=10)
        if title:
            ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def create_tree(self, parent, columns, headings, widths, show="headings"):
        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=columns, show=show, selectmode="browse")
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], minwidth=55, anchor="w", stretch=True)
        ybar = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.tag_configure("row_even", background="#ffffff")
        tree.tag_configure("row_odd", background="#f2f6fb")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        # Some Windows/Tk combinations do not scroll Treeviews with the wheel by default.
        tree.bind("<MouseWheel>", lambda event, widget=tree: self.scroll_tree_with_wheel(event, widget), add="+")
        tree.bind("<Button-4>", lambda event, widget=tree: self.scroll_tree_with_wheel(event, widget), add="+")
        tree.bind("<Button-5>", lambda event, widget=tree: self.scroll_tree_with_wheel(event, widget), add="+")
        return tree

    def build_dashboard_tab(self):
        kpis = ttk.Frame(self.dashboard_tab)
        kpis.pack(fill="x", pady=(0, 10))
        self.kpi_parties = tk.StringVar(value="0")
        self.kpi_agents = tk.StringVar(value="0")
        self.kpi_agent_linked = tk.StringVar(value="0")
        for col, (name, var) in enumerate([
            ("TOTAL PARTIES", self.kpi_parties),
            ("TOTAL AGENTS", self.kpi_agents),
            ("PARTIES LINKED TO AGENTS", self.kpi_agent_linked),
        ]):
            card = ttk.Frame(kpis, style="Card.TFrame", padding=(14, 10))
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
            ttk.Label(card, text=name, style="KPIName.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=var, style="KPI.TLabel").pack(anchor="w", pady=(3, 0))
            kpis.columnconfigure(col, weight=1)

        order_kpis = ttk.Frame(self.dashboard_tab)
        order_kpis.pack(fill="x", pady=(0, 10))
        self.order_kpi_vars = {key: tk.StringVar(value="0") for key in ("bills", "orders", "pending", "partial", "dispatched", "pending_pieces", "dispatched_pieces")}
        order_kpi_labels = [("TOTAL BILLS", "bills"), ("TOTAL ORDERS", "orders"), ("PENDING ORDERS", "pending"),
                            ("PARTIALLY DISPATCHED", "partial"), ("FULLY DISPATCHED", "dispatched"),
                            ("PENDING PIECES", "pending_pieces"), ("DISPATCHED PIECES", "dispatched_pieces")]
        for col, (label, key) in enumerate(order_kpi_labels):
            card = ttk.Frame(order_kpis, style="Card.TFrame", padding=(10, 8))
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 0))
            ttk.Label(card, text=label, style="KPIName.TLabel", wraplength=120).pack(anchor="w")
            ttk.Label(card, textvariable=self.order_kpi_vars[key], style="KPI.TLabel").pack(anchor="w", pady=(3, 0))
            order_kpis.columnconfigure(col, weight=1)

        listing = self.make_card(self.dashboard_tab, "PARTY LIST")
        listing.pack(fill="both", expand=True)
        toolbar = ttk.Frame(listing, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Search:").pack(side="left")
        self.dashboard_search_var = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self.dashboard_search_var, width=29)
        search.pack(side="left", padx=(6, 10), ipady=3)
        search.bind("<KeyRelease>", lambda _e: self.refresh_dashboard())
        ttk.Label(toolbar, text="Reference:").pack(side="left")
        self.dashboard_filter_var = tk.StringVar(value="ALL")
        f = ttk.Combobox(toolbar, textvariable=self.dashboard_filter_var, values=["ALL"] + REFERENCES, state="readonly", width=13)
        f.pack(side="left", padx=(6, 12))
        f.bind("<<ComboboxSelected>>", lambda _e: self.refresh_dashboard())
        ttk.Button(toolbar, text="+ Add Party", style="Primary.TButton", command=self.new_party).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="View Selected", command=self.view_selected_party).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Delete Selected", style="Danger.TButton", command=self.delete_party).pack(side="left", padx=5)

        # Party ID stays internal as the Treeview item ID, not as a visible column.
        columns = ("party_name", "phone", "address", "city", "state", "gst", "reference", "agent", "transport", "transport_gst")
        headings = {"party_name":"Party Name", "phone":"Phone Number", "address":"Address", "city":"City", "state":"State",
                    "gst":"Party GST Number", "reference":"Reference", "agent":"Agent Name", "transport":"Transport Details", "transport_gst":"Transport GST Number"}
        widths = {"party_name":175, "phone":120, "address":240, "city":100, "state":100, "gst":160,
                  "reference":115, "agent":160, "transport":190, "transport_gst":170}
        self.party_tree = self.create_tree(listing, columns, headings, widths)
        # Subtle alternating row colors improve readability without reducing contrast.
        self.party_tree.tag_configure("row_even", background="#ffffff")
        self.party_tree.tag_configure("row_odd", background="#f2f6fb")
        # A single click opens the Party Details screen in view-only mode.
        self.party_tree.bind("<ButtonRelease-1>", self.on_dashboard_row_click)
        self.party_tree.bind("<Return>", lambda _e: self.view_selected_party())
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.dashboard_tab, textvariable=self.status_var, foreground="#65758b").pack(anchor="w", pady=(5, 0))

    def build_party_tab(self):
        form = self.make_card(self.party_tab, "PARTY DETAILS  •  all fields marked * are required")
        form.pack(fill="x", pady=(0, 10))
        keys = ["party_name", "phone_number", "address", "city", "state", "gst_number", "reference", "transport_details", "transport_gst_number", "agent", "agent_phone"]
        self.party_vars = {key: tk.StringVar() for key in keys}

        fields_frame = ttk.Frame(form, style="Card.TFrame")
        fields_frame.pack(fill="x")
        fields = [
            ("Party Name", "party_name", "entry"),
            ("Phone Number *", "phone_number", "entry"),
            ("Address *", "address", "entry"),
            ("City *", "city", "entry"),
            ("State *", "state", "entry"),
            ("Party GST Number *", "gst_number", "entry"),
            ("Reference *", "reference", "reference"),
            ("Transport Details *", "transport_details", "entry"),
            ("Transport GST Number *", "transport_gst_number", "entry"),
        ]
        for i, (label, key, kind) in enumerate(fields):
            row, col = divmod(i, 3)
            cell = ttk.Frame(fields_frame, style="Card.TFrame")
            cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 12, 8), pady=5)
            ttk.Label(cell, text=label).pack(anchor="w", pady=(0, 3))
            if kind == "reference":
                widget = ttk.Combobox(cell, textvariable=self.party_vars[key], values=REFERENCES, state="readonly")
                widget.bind("<<ComboboxSelected>>", self.on_reference_change)
            else:
                widget = ttk.Entry(cell, textvariable=self.party_vars[key])
            widget.pack(fill="x", ipady=4)
            self.party_widgets[key] = widget
            fields_frame.columnconfigure(col, weight=1)

        # This entire section is hidden unless Reference = AGENT.
        self.agent_detail_frame = ttk.Frame(form, style="Card.TFrame", padding=(0, 8, 0, 2))
        agent_cell = ttk.Frame(self.agent_detail_frame, style="Card.TFrame")
        agent_cell.pack(side="left", fill="x", expand=True, padx=(0, 12))
        ttk.Label(agent_cell, text="Agent Name * (only for AGENT reference)").pack(anchor="w", pady=(0, 3))
        self.party_widgets["agent"] = ttk.Combobox(agent_cell, textvariable=self.party_vars["agent"], state="readonly")
        self.party_widgets["agent"].pack(fill="x", ipady=4)
        self.party_widgets["agent"].bind("<<ComboboxSelected>>", self.on_agent_selected)
        phone_cell = ttk.Frame(self.agent_detail_frame, style="Card.TFrame")
        phone_cell.pack(side="left", fill="x", expand=True)
        ttk.Label(phone_cell, text="Agent Phone Number (automatic)").pack(anchor="w", pady=(0, 3))
        self.party_widgets["agent_phone"] = ttk.Entry(phone_cell, textvariable=self.party_vars["agent_phone"], state="readonly")
        self.party_widgets["agent_phone"].pack(fill="x", ipady=4)
        self.agent_detail_frame.pack_forget()

        self.party_form_status_var = tk.StringVar(value="NEW PARTY — Enter details, then save")
        ttk.Label(form, textvariable=self.party_form_status_var, background="#ffffff",
                  foreground="#1769aa", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 6))

        actions = ttk.Frame(form, style="Card.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        self.save_new_party_button = ttk.Button(actions, text="Save New Party", style="Primary.TButton", command=self.save_party)
        self.clear_party_button = ttk.Button(actions, text="Clear Form", command=self.clear_party_form)
        self.edit_party_button = ttk.Button(actions, text="Edit", style="Primary.TButton", command=self.start_edit_party)
        self.save_changes_button = ttk.Button(actions, text="Save Changes", style="Primary.TButton", command=self.update_party)
        self.cancel_party_button = ttk.Button(actions, text="Cancel", command=self.cancel_party_changes)
        self.delete_detail_party_button = ttk.Button(actions, text="Delete Party", style="Danger.TButton", command=self.delete_party)
        self.back_to_list_button = ttk.Button(actions, text="Back to Party List", command=self.back_to_party_list)
        for button in (self.save_new_party_button, self.clear_party_button, self.edit_party_button,
                       self.save_changes_button, self.cancel_party_button, self.delete_detail_party_button,
                       self.back_to_list_button):
            button.pack_forget()
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=9)
        ttk.Button(actions, text="Download Sample CSV", command=self.download_sample_csv).pack(side="left", padx=5)
        ttk.Button(actions, text="Import CSV", command=self.import_party_csv).pack(side="left", padx=5)
        ttk.Button(actions, text="Export CSV", command=self.export_party_csv).pack(side="left", padx=5)
        ttk.Label(form, text="CSV import only adds new rows or updates rows whose Party ID is supplied. Existing parties are never cleared. Agent Master entries must be added manually.",
                  background="#ffffff", foreground="#65758b", wraplength=1250).pack(anchor="w", pady=(9, 0))
        self.set_party_form_mode("new")

    # ------------------------------------------------------------------
    # ORDER FORM
    # ------------------------------------------------------------------
    SIZE_OPTIONS = ["M (38)", "L (40)", "XL (42)", "XXL (44)"]
    PACKAGING_OPTIONS = ["Chain Bag", "Sherwani Packing", "Box Packing"]

    def make_scrollable(self, parent):
        """Create a vertically scrollable frame with consistent mouse-wheel support."""
        outer = ttk.Frame(parent)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg="#f3f5f8", highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        if not hasattr(self, "_scroll_canvases"):
            self._scroll_canvases = []
        self._scroll_canvases.append(canvas)
        if not getattr(self, "_scroll_wheel_bound", False):
            def wheel(event):
                # Walk up the widget-parent chain; this also works when the pointer is
                # over an Entry, Checkbutton, or nested frame inside the scrollable page.
                target = None
                widget = getattr(event, "widget", None)
                while widget is not None:
                    for candidate in reversed(self._scroll_canvases):
                        if widget == candidate:
                            target = candidate
                            break
                    if target is not None:
                        break
                    widget = getattr(widget, "master", None)
                if target is not None:
                    delta = getattr(event, "delta", 0) or 0
                    if delta:
                        # Ensure small high-resolution wheel deltas still move at least one unit.
                        steps = max(1, int(round(abs(delta) / 120.0)))
                        target.yview_scroll(-steps if delta > 0 else steps, "units")
                        return "break"
                    number = getattr(event, "num", None)
                    if number == 4:
                        target.yview_scroll(-3, "units")
                        return "break"
                    if number == 5:
                        target.yview_scroll(3, "units")
                        return "break"
                return None
            self.bind_all("<MouseWheel>", wheel, add="+")
            self.bind_all("<Button-4>", wheel, add="+")
            self.bind_all("<Button-5>", wheel, add="+")
            self._scroll_wheel_bound = True
        return canvas, content

    @staticmethod
    def scroll_tree_with_wheel(event, tree):
        """Scroll report/list Treeviews in predictable row increments."""
        delta = getattr(event, "delta", 0) or 0
        if delta:
            steps = max(1, int(round(abs(delta) / 120.0)))
            tree.yview_scroll(-steps if delta > 0 else steps, "units")
            return "break"
        number = getattr(event, "num", None)
        if number == 4:
            tree.yview_scroll(-3, "units")
            return "break"
        if number == 5:
            tree.yview_scroll(3, "units")
            return "break"
        return None

    @staticmethod
    def parse_date_value(value):
        """Accept ISO or common day-first dates and always return a real date."""
        text = str(value or "").strip()
        if not text:
            raise ValueError("Date is required.")
        # Explicit handling ensures a short year like 26 becomes 2026.
        import re
        match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", text)
        if match:
            day, month, year_text = match.groups()
            year = int(year_text)
            if len(year_text) == 2:
                year += 2000
            return date(year, int(month), int(day))
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
        raise ValueError("Use DD-MM-YYYY or YYYY-MM-DD, for example 20-04-2026.")

    @staticmethod
    def show_date(value):
        if not value:
            return ""
        try:
            if isinstance(value, date):
                dt = value
            else:
                dt = PartyReportingApp.parse_date_value(value)
            return dt.strftime("%d-%m-%Y")
        except (ValueError, TypeError):
            return str(value)

    def next_order_number(self):
        current = self.conn.execute("SELECT MAX(order_no) FROM orders").fetchone()[0]
        return 1101 if current is None else int(current) + 1

    def build_order_form_tab(self):
        self.order_canvas, self.order_content = self.make_scrollable(self.order_tab)
        header = self.make_card(self.order_content, "ORDER FORM")
        header.pack(fill="x", pady=(0, 9))

        top = ttk.Frame(header, style="Card.TFrame")
        top.pack(fill="x")
        self.order_number_var = tk.StringVar(value="1101")
        self.order_date_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
        ttk.Label(top, text="Order Number").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.order_number_entry = ttk.Entry(top, textvariable=self.order_number_var, width=14)
        self.order_number_entry.grid(row=1, column=0, sticky="ew", padx=(0, 14))
        ttk.Label(top, text="Order Date").grid(row=0, column=1, sticky="w", padx=(0, 6), pady=4)
        self.order_date_entry = ttk.Entry(top, textvariable=self.order_date_var, width=18)
        self.order_date_entry.grid(row=1, column=1, sticky="ew", padx=(0, 16))
        self.order_date_entry.bind("<FocusOut>", self.normalize_order_date)
        ttk.Label(top, text="Party Name").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        self.order_party_var = tk.StringVar()
        self.order_party_combo = ttk.Combobox(top, textvariable=self.order_party_var, state="normal", width=48)
        self.order_party_combo.grid(row=1, column=2, sticky="ew", padx=(0, 6))
        self.order_party_combo.bind("<KeyRelease>", self.on_order_party_keyrelease)
        self.order_party_combo.bind("<<ComboboxSelected>>", self.on_order_party_selected)
        top.columnconfigure(2, weight=1)

        details = self.make_card(self.order_content, "PARTY DETAILS")
        details.pack(fill="x", pady=(0, 9))
        details_grid = ttk.Frame(details, style="Card.TFrame")
        details_grid.pack(fill="x")
        self.order_party_detail_vars = {key: tk.StringVar(value="—") for key in ("phone", "address", "city_state", "gst", "transport", "transport_gst")}
        party_detail_fields = [
            ("Phone Number", "phone"), ("Address", "address"), ("City / State", "city_state"),
            ("Party GST Number", "gst"), ("Transport Details", "transport"), ("Transport GST / ID", "transport_gst")
        ]
        for i, (label, key) in enumerate(party_detail_fields):
            r, c = divmod(i, 3)
            cell = ttk.Frame(details_grid, style="Card.TFrame")
            cell.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 12, 7), pady=4)
            ttk.Label(cell, text=label).pack(anchor="w", pady=(0, 3))
            ttk.Entry(cell, textvariable=self.order_party_detail_vars[key], state="readonly", style="PartyDetail.TEntry").pack(fill="x", ipady=1)
            details_grid.columnconfigure(c, weight=1)

        items_card = self.make_card(self.order_content, "Item Details")
        items_card.pack(fill="x", pady=(0, 9))
        hint = ttk.Label(items_card, text="", background="#ffffff", foreground="#65758b")
        hint.pack(anchor="w", pady=(0, 6))
        self.order_items_header = ttk.Frame(items_card, style="Card.TFrame")
        self.order_items_header.pack(fill="x")
        headers = [("Sr.", 0), ("Particulars", 1), ("M (38) + Qty", 2), ("L (40) + Qty", 3),
                   ("XL (42) + Qty", 4), ("XXL (44) + Qty", 5), ("Piece Rate", 6), ("Discount", 7), ("Amount", 8)]
        for label, col in headers:
            ttk.Label(self.order_items_header, text=label, background="#e7edf5", foreground="#17365d",
                      font=("Segoe UI", 9, "bold"), anchor="center", padding=5).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
        for col, weight in enumerate((0, 3, 2, 2, 2, 2, 1, 1, 1)):
            self.order_items_header.columnconfigure(col, weight=weight, minsize=42 if col == 0 else 70)
        self.order_items_container = ttk.Frame(items_card, style="Card.TFrame")
        self.order_items_container.pack(fill="x")
        self.order_item_rows = []
        self.order_form_locked = False
        self.current_order_id = None
        for _ in range(5):
            self.add_order_item_row()
        row_buttons = ttk.Frame(items_card, style="Card.TFrame")
        row_buttons.pack(fill="x", pady=(8, 0))
        self.add_item_row_button = ttk.Button(row_buttons, text="+ Add Item Row (max 200)", command=self.add_order_item_row)
        self.add_item_row_button.pack(side="left", padx=(0, 7))
        self.remove_item_row_button = ttk.Button(row_buttons, text="Remove Last Row", command=self.remove_order_item_row)
        self.remove_item_row_button.pack(side="left")

        bottom = ttk.Frame(self.order_content)
        bottom.pack(fill="x")
        packaging_card = self.make_card(bottom, "PACKAGING — Select one or more")
        packaging_card.pack(fill="x", pady=(0, 8))
        self.packaging_vars = {name: tk.BooleanVar(value=False) for name in self.PACKAGING_OPTIONS}
        packaging_row = ttk.Frame(packaging_card, style="Card.TFrame")
        packaging_row.pack(fill="x")
        self.packaging_checks = []
        for name in self.PACKAGING_OPTIONS:
            cb = ttk.Checkbutton(packaging_row, text=name, variable=self.packaging_vars[name])
            cb.pack(side="left", padx=(0, 20), pady=3)
            self.packaging_checks.append(cb)

        narration_card = self.make_card(bottom, "Additional Order Details")
        narration_card.pack(fill="x", pady=(0, 8))
        self.order_narration = tk.Text(narration_card, height=3, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1)
        self.order_narration.pack(fill="x")

        actions = self.make_card(bottom, "ORDER ACTIONS")
        actions.pack(fill="x", pady=(0, 8))
        self.order_status_var = tk.StringVar(value="New order — enter the details and save.")
        ttk.Label(actions, textvariable=self.order_status_var, background="#ffffff", foreground="#65758b").pack(anchor="w", pady=(0, 8))
        action_row = ttk.Frame(actions, style="Card.TFrame")
        action_row.pack(fill="x")
        # Keep only the three requested actions on the Order Form itself.
        self.save_order_button = ttk.Button(action_row, text="Save Order", style="Primary.TButton", command=self.save_order)
        self.save_order_button.pack(side="left", padx=(0, 7))
        self.delete_order_button = ttk.Button(action_row, text="Delete Order", style="Danger.TButton", command=self.prompt_delete_order)
        self.delete_order_button.pack(side="left", padx=7)
        self.order_list_button = ttk.Button(action_row, text="Order List", command=self.open_order_list)
        self.order_list_button.pack(side="left", padx=7)
        ttk.Button(action_row, text="Create Order CSV", command=self.create_order_import_template).pack(side="left", padx=7)
        ttk.Button(action_row, text="Import Order CSV", command=self.import_order_csv).pack(side="left", padx=7)
        # PDF/print and new-order commands remain available through the list/workflow, not as extra form buttons.
        self.save_order_pdf_button = ttk.Button(action_row, text="Save PDF", command=self.save_order_pdf)
        self.print_order_button = ttk.Button(action_row, text="Print Order", command=self.print_order_pdf)
        self.new_order_button = ttk.Button(action_row, text="New Order", command=self.start_new_order)
        self.load_edit_order_button = ttk.Button(action_row, text="Find / Edit Order", command=self.prompt_load_order_for_edit)
        self.current_order_id = None
        self.order_editing = False
        self.order_form_locked = False
        self.order_party_id_by_display = {}
        self.order_party_rows_by_display = {}
        self.refresh_order_party_lookup()
        self.initialize_order_form()

    def refresh_order_party_lookup(self):
        if not hasattr(self, "order_party_combo"):
            return
        rows = self.conn.execute("SELECT * FROM parties ORDER BY party_name COLLATE NOCASE, city COLLATE NOCASE, id").fetchall()
        values, id_map, row_map = [], {}, {}
        counts = {}
        for row in rows:
            base = f"{row['party_name']} — {row['city']} — {row['phone_number']}"
            counts[base] = counts.get(base, 0) + 1
            display = base if counts[base] == 1 else f"{base} ({counts[base]})"
            values.append(display)
            id_map[display] = int(row["id"])
            row_map[display] = row
        self.order_party_id_by_display = id_map
        self.order_party_rows_by_display = row_map
        current = self.order_party_var.get() if hasattr(self, "order_party_var") else ""
        self.order_party_combo.configure(values=values)
        if current and current not in id_map:
            self.order_party_var.set("")
            self.clear_order_party_details()

    def clear_order_party_details(self):
        for var in self.order_party_detail_vars.values():
            var.set("—")

    def on_order_party_keyrelease(self, event=None):
        if self.order_form_locked or not hasattr(self, "order_party_combo"):
            return
        if event and event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R"):
            return
        query = self.order_party_var.get().strip().casefold()
        displays = list(self.order_party_id_by_display)
        matches = [name for name in displays if query in name.casefold()] if query else displays
        self.order_party_combo.configure(values=matches)
        exact = self.order_party_id_by_display.get(self.order_party_var.get().strip())
        if exact is None:
            self.clear_order_party_details()
        if query and matches and self.focus_get() == self.order_party_combo:
            try:
                self.order_party_combo.event_generate("<Down>")
            except tk.TclError:
                pass

    def on_order_party_selected(self, _event=None):
        display = self.order_party_var.get().strip()
        row = self.order_party_rows_by_display.get(display)
        if not row:
            self.clear_order_party_details()
            return
        self.order_party_detail_vars["phone"].set(row["phone_number"] or "—")
        self.order_party_detail_vars["address"].set(row["address"] or "—")
        self.order_party_detail_vars["city_state"].set(f"{row['city'] or ''}, {row['state'] or ''}".strip(", ") or "—")
        self.order_party_detail_vars["gst"].set(row["gst_number"] or "—")
        self.order_party_detail_vars["transport"].set(row["transport_details"] or "—")
        self.order_party_detail_vars["transport_gst"].set(row["transport_gst_number"] or "—")

    def normalize_order_date(self, _event=None):
        try:
            self.order_date_var.set(self.parse_date_value(self.order_date_var.get()).strftime("%d-%m-%Y"))
        except ValueError:
            # Keep the user's input visible; validation displays the message on Save.
            return

    def add_order_item_row(self):
        if getattr(self, "order_form_locked", False):
            return
        if len(getattr(self, "order_item_rows", [])) >= 200:
            messagebox.showwarning("Maximum Rows", "Order Formમાં વધુમાં વધુ 200 item rows જ ઉમેરી શકાય.", parent=self)
            return
        sr = len(self.order_item_rows) + 1
        frame = ttk.Frame(self.order_items_container, style="Card.TFrame", padding=(0, 2))
        frame.pack(fill="x")
        sr_label = ttk.Label(frame, text=str(sr), anchor="center")
        sr_label.grid(row=0, column=0, sticky="nsew", padx=1, pady=3)
        particulars_var = tk.StringVar()
        particulars_entry = ttk.Entry(frame, textvariable=particulars_var)
        particulars_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=3, ipady=3)
        size_vars, qty_vars, size_checks, qty_entries = {}, {}, {}, {}
        for idx, size in enumerate(self.SIZE_OPTIONS, start=2):
            cell = ttk.Frame(frame, style="Card.TFrame")
            cell.grid(row=0, column=idx, sticky="ew", padx=1, pady=3)
            selected = tk.BooleanVar(value=False)
            qty_var = tk.StringVar(value="")
            check = ttk.Checkbutton(cell, text=size, variable=selected,
                                    command=lambda r_index=sr-1, sz=size: self.on_order_size_toggle_by_index(r_index, sz))
            check.pack(side="left", padx=(1, 3))
            entry = ttk.Entry(cell, textvariable=qty_var, width=4, state="disabled", justify="center")
            entry.pack(side="left", fill="x", expand=True, ipady=3)
            size_vars[size] = selected
            qty_vars[size] = qty_var
            size_checks[size] = check
            qty_entries[size] = entry
        rate_var, discount_var, amount_var = tk.StringVar(value=""), tk.StringVar(value="0"), tk.StringVar(value="0.00")
        rate_entry = ttk.Entry(frame, textvariable=rate_var, width=10, justify="right")
        rate_entry.grid(row=0, column=6, sticky="ew", padx=2, pady=3, ipady=3)
        discount_entry = ttk.Entry(frame, textvariable=discount_var, width=10, justify="right")
        discount_entry.grid(row=0, column=7, sticky="ew", padx=2, pady=3, ipady=3)
        amount_label = ttk.Label(frame, textvariable=amount_var, anchor="e", width=12, font=("Segoe UI", 9, "bold"))
        amount_label.grid(row=0, column=8, sticky="ew", padx=3, pady=3)
        weights = (0, 3, 2, 2, 2, 2, 1, 1, 1)
        for col, weight in enumerate(weights):
            frame.columnconfigure(col, weight=weight, minsize=42 if col == 0 else 70)
        row = {
            "index": sr-1, "frame": frame, "sr_label": sr_label,
            "particulars_var": particulars_var, "particulars_entry": particulars_entry,
            "size_vars": size_vars, "qty_vars": qty_vars, "size_checks": size_checks,
            "qty_entries": qty_entries, "rate_var": rate_var, "discount_var": discount_var,
            "rate_entry": rate_entry, "discount_entry": discount_entry, "amount_var": amount_var,
            "amount_label": amount_label
        }
        self.order_item_rows.append(row)
        for var in [rate_var, discount_var] + list(qty_vars.values()) + list(size_vars.values()):
            var.trace_add("write", lambda *_args, r=row: self.update_order_row_amount(r))
        self.update_order_row_amount(row)
        if self.order_form_locked:
            self.set_order_form_locked(True)

    def on_order_size_toggle_by_index(self, index, size):
        if index >= len(self.order_item_rows):
            return
        self.on_order_size_toggle(self.order_item_rows[index], size)

    def on_order_size_toggle(self, row, size):
        if self.order_form_locked:
            return
        selected = row["size_vars"][size].get()
        entry = row["qty_entries"][size]
        if selected:
            if not row["qty_vars"][size].get().strip() or row["qty_vars"][size].get().strip() == "0":
                row["qty_vars"][size].set("1")
            entry.configure(state="normal")
            entry.focus_set()
        else:
            row["qty_vars"][size].set("")
            entry.configure(state="disabled")
        self.update_order_row_amount(row)

    @staticmethod
    def to_float(value, label):
        text = str(value or "").strip().replace(",", "")
        if not text:
            return 0.0
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"{label} must be a valid number.")
        if number < 0:
            raise ValueError(f"{label} cannot be negative.")
        return number

    def update_order_row_amount(self, row):
        try:
            rate = self.to_float(row["rate_var"].get(), "Piece Rate")
            discount = self.to_float(row["discount_var"].get(), "Discount")
            total_qty = 0
            for size in self.SIZE_OPTIONS:
                if row["size_vars"][size].get():
                    q_text = row["qty_vars"][size].get().strip()
                    if q_text:
                        total_qty += max(0, int(q_text))
            amount = max(0.0, total_qty * rate - discount)
            row["amount_var"].set(f"{amount:,.2f}")
        except (ValueError, TypeError):
            row["amount_var"].set("—")

    def remove_order_item_row(self):
        if self.order_form_locked:
            return
        if len(self.order_item_rows) <= 1:
            messagebox.showinfo("Item Row", "ઓછામાં ઓછી એક item row રાખવી જરૂરી છે.", parent=self)
            return
        row = self.order_item_rows.pop()
        row["frame"].destroy()
        for index, entry in enumerate(self.order_item_rows, start=1):
            entry["index"] = index - 1
            entry["sr_label"].configure(text=str(index))
        self.order_canvas.configure(scrollregion=self.order_canvas.bbox("all"))

    def reset_order_item_rows(self):
        while len(self.order_item_rows) > 5:
            row = self.order_item_rows.pop()
            row["frame"].destroy()
        while len(self.order_item_rows) < 5:
            self.add_order_item_row()
        for index, row in enumerate(self.order_item_rows, start=1):
            row["index"] = index - 1
            row["sr_label"].configure(text=str(index))
            row["particulars_var"].set("")
            row["rate_var"].set("")
            row["discount_var"].set("0")
            for size in self.SIZE_OPTIONS:
                row["size_vars"][size].set(False)
                row["qty_vars"][size].set("")
                row["qty_entries"][size].configure(state="disabled")
            self.update_order_row_amount(row)

    def initialize_order_form(self):
        self.current_order_id = None
        self.order_editing = False
        self.order_form_locked = False
        self.order_number_var.set(str(self.next_order_number()))
        self.save_order_button.configure(text="Save Order")
        self.order_date_var.set(datetime.now().strftime("%d-%m-%Y"))
        self.order_party_var.set("")
        self.clear_order_party_details()
        for var in self.packaging_vars.values():
            var.set(False)
        self.order_narration.configure(state="normal")
        self.order_narration.delete("1.0", "end")
        self.reset_order_item_rows()
        self.set_order_form_locked(False)
        self.order_status_var.set("New order — enter the details and save.")

    def start_new_order(self):
        if self.current_order_id is None and self.order_draft_has_content():
            if not messagebox.askyesno("Discard Current Order", "Current order details are not saved. Start a new order and discard them?", parent=self):
                return
        self.initialize_order_form()
        self.notebook.select(self.order_tab)

    def order_draft_has_content(self):
        if self.order_party_var.get().strip() or self.order_narration.get("1.0", "end").strip():
            return True
        if any(v.get() for v in self.packaging_vars.values()):
            return True
        for row in self.order_item_rows:
            if row["particulars_var"].get().strip() or row["rate_var"].get().strip() or any(v.get() for v in row["size_vars"].values()):
                return True
        return False

    def set_order_form_locked(self, locked):
        self.order_form_locked = locked
        state = "disabled" if locked else "normal"
        self.order_date_entry.configure(state=state)
        self.order_number_entry.configure(state="normal" if not locked else "disabled")
        self.order_party_combo.configure(state="disabled" if locked else "normal")
        self.add_item_row_button.configure(state="disabled" if locked else "normal")
        self.remove_item_row_button.configure(state="disabled" if locked else "normal")
        self.save_order_button.configure(state="disabled" if locked else "normal")
        for cb in self.packaging_checks:
            cb.configure(state="disabled" if locked else "normal")
        self.order_narration.configure(state="disabled" if locked else "normal")
        for row in self.order_item_rows:
            row["particulars_entry"].configure(state=state)
            row["rate_entry"].configure(state=state)
            row["discount_entry"].configure(state=state)
            for size in self.SIZE_OPTIONS:
                row["size_checks"][size].configure(state="disabled" if locked else "normal")
                enabled = not locked and row["size_vars"][size].get()
                row["qty_entries"][size].configure(state="normal" if enabled else "disabled")

    def collect_order_form(self, show_messages=True):
        try:
            order_date = self.parse_date_value(self.order_date_var.get())
        except ValueError as exc:
            if show_messages:
                messagebox.showwarning("Invalid Order Date", str(exc), parent=self)
                self.order_date_entry.focus_set()
            return None
        display = self.order_party_var.get().strip()
        party_id = self.order_party_id_by_display.get(display)
        if not party_id:
            if show_messages:
                messagebox.showwarning("Select Party", "Party Name dropdownમાંથી સાચી Party select કરો.", parent=self)
                self.order_party_combo.focus_set()
            return None
        items, errors = [], []
        for idx, row in enumerate(self.order_item_rows, start=1):
            particulars = row["particulars_var"].get().strip()
            selected_sizes = [size for size in self.SIZE_OPTIONS if row["size_vars"][size].get()]
            has_any = bool(particulars or row["rate_var"].get().strip() or selected_sizes)
            if not has_any:
                continue
            if not particulars:
                errors.append(f"Sr. No. {idx}: Particulars is required.")
                continue
            if not selected_sizes:
                errors.append(f"Sr. No. {idx}: Select at least one size.")
                continue
            try:
                rate = self.to_float(row["rate_var"].get(), f"Sr. No. {idx} Piece Rate")
                if not row["rate_var"].get().strip():
                    errors.append(f"Sr. No. {idx}: Piece Rate is required.")
                    continue
                discount = self.to_float(row["discount_var"].get(), f"Sr. No. {idx} Discount")
            except ValueError as exc:
                errors.append(f"Sr. No. {idx}: {exc}")
                continue
            sizes, total_qty = [], 0
            for size in selected_sizes:
                qty_text = row["qty_vars"][size].get().strip()
                try:
                    qty = int(qty_text)
                    if qty <= 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"Sr. No. {idx}: Quantity for {size} must be a whole number greater than 0.")
                    continue
                sizes.append({"size_code": size, "qty": qty})
                total_qty += qty
            if len(sizes) != len(selected_sizes):
                continue
            gross = total_qty * rate
            if discount > gross:
                errors.append(f"Sr. No. {idx}: Discount cannot exceed line gross amount ({gross:.2f}).")
                continue
            items.append({"sr_no": len(items) + 1, "particulars": particulars, "piece_rate": rate,
                          "discount": discount, "sizes": sizes, "total_qty": total_qty,
                          "gross": gross, "amount": gross - discount})
        if errors:
            if show_messages:
                messagebox.showwarning("Check Item Details", "Please correct these details:\n\n" + "\n".join(errors[:15]), parent=self)
            return None
        if not items:
            if show_messages:
                messagebox.showwarning("No Items", "Order Formમાં ઓછામાં ઓછી એક complete item row ઉમેરો.", parent=self)
            return None
        packaging = [name for name in self.PACKAGING_OPTIONS if self.packaging_vars[name].get()]
        narration = self.order_narration.get("1.0", "end").strip()
        return {"order_date": order_date.isoformat(), "party_id": party_id, "packaging": packaging,
                "narration": narration, "items": items}

    def save_order(self, show_success=True, reset_after_save=True):
        data = self.collect_order_form()
        if data is None:
            return False
        try:
            try:
                order_no = int(str(self.order_number_var.get()).strip())
                if order_no <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid Order Number", "Order Numberમાં positive whole number દાખલ કરો.", parent=self)
                self.order_number_entry.focus_set()
                return False
            duplicate = self.conn.execute("SELECT id FROM orders WHERE order_no=? AND id<>COALESCE(?, -1)", (order_no, self.current_order_id)).fetchone()
            if duplicate:
                messagebox.showwarning("Duplicate Order Number", f"Order No. {order_no} પહેલેથી ઉપયોગમાં છે. બીજો નંબર દાખલ કરો.", parent=self)
                self.order_number_entry.focus_set()
                return False
            if self.current_order_id is not None and self.order_editing:
                dispatch_count = self.conn.execute("""SELECT COUNT(*) FROM order_dispatches d
                    JOIN order_item_sizes s ON s.id=d.order_size_id
                    JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=?""", (self.current_order_id,)).fetchone()[0]
                if dispatch_count:
                    messagebox.showwarning("Order Has Dispatches", "આ orderમાં dispatch history છે, તેથી તેની item lines edit કરી શકાતી નથી. Dispatch history સુરક્ષિત રાખવા edit અટકાવ્યું છે.", parent=self)
                    return False
                with self.conn:
                    self.conn.execute("UPDATE orders SET order_no=?, order_date=?, party_id=?, packaging=?, narration=? WHERE id=?",
                        (order_no, data["order_date"], data["party_id"], json.dumps(data["packaging"], ensure_ascii=False), data["narration"], self.current_order_id))
                    old_items = self.conn.execute("SELECT id FROM order_items WHERE order_id=?", (self.current_order_id,)).fetchall()
                    for old in old_items:
                        self.conn.execute("DELETE FROM order_item_sizes WHERE order_item_id=?", (old["id"],))
                    self.conn.execute("DELETE FROM order_items WHERE order_id=?", (self.current_order_id,))
                    for item in data["items"]:
                        cur = self.conn.execute("INSERT INTO order_items(order_id, sr_no, particulars, piece_rate, discount) VALUES(?,?,?,?,?)",
                            (self.current_order_id, item["sr_no"], item["particulars"], item["piece_rate"], item["discount"]))
                        for size in item["sizes"]:
                            self.conn.execute("INSERT INTO order_item_sizes(order_item_id, size_code, ordered_qty) VALUES(?,?,?)", (cur.lastrowid, size["size_code"], size["qty"]))
                self.order_editing = False
                self.order_number_var.set(str(order_no))
                self.order_date_var.set(self.show_date(data["order_date"]))
                self.set_order_form_locked(True)
                self.order_status_var.set(f"UPDATED — Order No. {order_no}.")
                self.save_order_button.configure(text="Save Order")
                self.refresh_all()
                if show_success:
                    messagebox.showinfo("Order Updated", f"Order No. {order_no} updated successfully.", parent=self)
                return True
            if self.current_order_id is not None and not self.order_editing:
                if show_success:
                    messagebox.showinfo("Order Already Saved", f"Order No. {self.order_number_var.get()} is already saved. Use New Order to create another order.", parent=self)
                return True
            with self.conn:
                cur = self.conn.execute("INSERT INTO orders(order_no, order_date, party_id, packaging, narration) VALUES(?,?,?,?,?)",
                    (order_no, data["order_date"], data["party_id"], json.dumps(data["packaging"], ensure_ascii=False), data["narration"]))
                order_id = cur.lastrowid
                for item in data["items"]:
                    item_cur = self.conn.execute("INSERT INTO order_items(order_id, sr_no, particulars, piece_rate, discount) VALUES(?,?,?,?,?)",
                        (order_id, item["sr_no"], item["particulars"], item["piece_rate"], item["discount"]))
                    for size in item["sizes"]:
                        self.conn.execute("INSERT INTO order_item_sizes(order_item_id, size_code, ordered_qty) VALUES(?,?,?)", (item_cur.lastrowid, size["size_code"], size["qty"]))
            self.current_order_id = int(order_id)
            self.order_number_var.set(str(order_no))
            self.order_date_var.set(self.show_date(data["order_date"]))
            self.set_order_form_locked(True)
            self.order_status_var.set(f"SAVED — Order No. {order_no}.")
            self.refresh_all()
            if show_success:
                messagebox.showinfo("Order Saved", f"Order No. {order_no} saved successfully.", parent=self)
            if reset_after_save:
                self.initialize_order_form()
            return True
        except sqlite3.Error as exc:
            messagebox.showerror("Save Order Failed", f"Could not save Order Form.\n\n{exc}", parent=self)
            return False

    # ------------------------------------------------------------------
    # ORDER / DISPATCH CSV IMPORT TEMPLATES
    # ------------------------------------------------------------------
    ORDER_IMPORT_HEADERS = [
        "Order Number", "Order Date", "Party Name", "Party City", "Party Phone",
        "Particulars", "M Qty", "L Qty", "XL Qty", "XXL Qty", "Piece Rate",
        "Discount", "Packaging", "Additional Order Details"
    ]
    DISPATCH_IMPORT_HEADERS = [
        "Order Number", "Party Name", "Particulars", "Order Size", "Dispatch Qty",
        "Dispatch Date", "Invoice Number", "Details"
    ]

    def _create_csv_template(self, headers, filename, title):
        path = filedialog.asksaveasfilename(parent=self, title=title, defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")], initialfile=filename)
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                csv.writer(handle).writerow(headers)
            messagebox.showinfo("CSV Template Created", f"CSV template saved:\n{path}\n\nExcelમાં rows ભરો અને પછી Import CSV પસંદ કરો. Header names બદલશો નહીં.", parent=self)
        except OSError as exc:
            messagebox.showerror("CSV Template Failed", f"CSV template બનાવી શકાઈ નથી.\n\n{exc}", parent=self)

    def create_order_import_template(self):
        self._create_csv_template(self.ORDER_IMPORT_HEADERS, "order_import_template.csv", "Create Order Import CSV Template")

    def create_dispatch_import_template(self):
        self._create_csv_template(self.DISPATCH_IMPORT_HEADERS, "dispatch_import_template.csv", "Create Pending-to-Dispatched CSV Template")

    @staticmethod
    def _csv_int(value, label, allow_blank=False):
        text = str(value or "").strip()
        if not text and allow_blank:
            return None
        try:
            number = int(text)
            return number
        except (ValueError, TypeError):
            raise ValueError(f"{label}: whole number દાખલ કરો.")

    @staticmethod
    def _csv_float(value, label, default=None):
        text = str(value or "").strip()
        if not text and default is not None:
            return float(default)
        try:
            return float(text)
        except (ValueError, TypeError):
            raise ValueError(f"{label}: valid number દાખલ કરો.")

    def import_order_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import Orders from CSV", filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValueError("CSV fileમાં header row નથી.")
                headers = {self.normalize_header(h): h for h in reader.fieldnames}
                required = ["order number", "order date", "party name", "party city", "party phone", "particulars", "m qty", "l qty", "xl qty", "xxl qty", "piece rate", "discount", "packaging", "additional order details"]
                missing = [h for h in required if h not in headers]
                if missing:
                    raise ValueError("આ columns missing છે: " + ", ".join(missing) + "\nOrder CSV template બનાવો અને તે જ header રાખો.")
                records = list(reader)
            if not records:
                raise ValueError("CSVમાં data rows નથી.")
            grouped = {}
            for line_no, raw in enumerate(records, start=2):
                get = lambda name: str(raw.get(headers[name], "") or "").strip()
                if not any(str(v or "").strip() for v in raw.values()):
                    continue
                order_no = self._csv_int(get("order number"), f"Row {line_no} Order Number")
                if order_no <= 0:
                    raise ValueError(f"Row {line_no}: Order Number positive હોવો જોઈએ.")
                try:
                    order_date = self.parse_date_value(get("order date")).isoformat()
                except ValueError as exc:
                    raise ValueError(f"Row {line_no} Order Date: {exc}")
                party_name, city, phone = get("party name"), get("party city"), get("party phone")
                if not party_name:
                    raise ValueError(f"Row {line_no}: Party Name જરૂરી છે.")
                party_rows = self.conn.execute("SELECT id, party_name, city, phone_number FROM parties WHERE party_name=? COLLATE NOCASE ORDER BY id", (party_name,)).fetchall()
                party_rows = [r for r in party_rows if (not city or r["city"].strip().casefold()==city.casefold()) and (not phone or r["phone_number"].strip()==phone)]
                if len(party_rows) != 1:
                    raise ValueError(f"Row {line_no}: Party '{party_name}' માટે unique match મળ્યો નથી. Party Name, Party City અને Party Phone ચેક કરો.")
                particulars = get("particulars")
                if not particulars:
                    raise ValueError(f"Row {line_no}: Particulars જરૂરી છે.")
                quantities=[]
                for size_label, key in zip(self.SIZE_OPTIONS, ("m qty","l qty","xl qty","xxl qty")):
                    qty_text=get(key)
                    qty=0 if not qty_text else self._csv_int(qty_text, f"Row {line_no} {key}")
                    if qty < 0:
                        raise ValueError(f"Row {line_no}: {key} negative ન હોઈ શકે.")
                    if qty:
                        quantities.append({"size_code":size_label,"qty":qty})
                if not quantities:
                    raise ValueError(f"Row {line_no}: ઓછામાં ઓછી એક size quantity આપો.")
                rate=self._csv_float(get("piece rate"),f"Row {line_no} Piece Rate")
                discount=self._csv_float(get("discount"),f"Row {line_no} Discount",0)
                if rate < 0 or discount < 0 or discount > sum(x["qty"] for x in quantities)*rate:
                    raise ValueError(f"Row {line_no}: Piece Rate/Discount ચેક કરો.")
                packaging=[x.strip() for x in get("packaging").split(";") if x.strip()]
                invalid_pack=[x for x in packaging if x not in self.PACKAGING_OPTIONS]
                if invalid_pack:
                    raise ValueError(f"Row {line_no}: Packaging values semicolonથી અલગ કરો; માન્ય values: {', '.join(self.PACKAGING_OPTIONS)}")
                item={"particulars":particulars,"piece_rate":rate,"discount":discount,"sizes":quantities}
                if order_no not in grouped:
                    grouped[order_no]={"order_date":order_date,"party_id":int(party_rows[0]["id"]),"packaging":packaging,"narration":get("additional order details"),"items":[]}
                group=grouped[order_no]
                if group["order_date"]!=order_date or group["party_id"]!=int(party_rows[0]["id"]):
                    raise ValueError(f"Row {line_no}: same Order Numberની rowsમાં Order Date/Party સરખાં હોવા જોઈએ.")
                if group["packaging"]!=packaging or group["narration"]!=get("additional order details"):
                    raise ValueError(f"Row {line_no}: same Order Numberની rowsમાં Packaging અને Additional Order Details સરખાં હોવા જોઈએ.")
                group["items"].append(item)
            if not grouped:
                raise ValueError("CSVમાં import કરવા માટે કોઈ valid rows નથી.")
            existing=[]
            for order_no in grouped:
                if self.conn.execute("SELECT 1 FROM orders WHERE order_no=?",(order_no,)).fetchone(): existing.append(order_no)
            if existing:
                raise ValueError("આ Order Number પહેલેથી છે: " + ", ".join(map(str,existing)) + ". CSV import રોકવામાં આવ્યો છે; કોઈ data save થયો નથી.")
            with self.conn:
                for order_no, data in grouped.items():
                    cur=self.conn.execute("INSERT INTO orders(order_no,order_date,party_id,packaging,narration) VALUES(?,?,?,?,?)",(order_no,data["order_date"],data["party_id"],json.dumps(data["packaging"],ensure_ascii=False),data["narration"]))
                    for sr,item in enumerate(data["items"],start=1):
                        item_cur=self.conn.execute("INSERT INTO order_items(order_id,sr_no,particulars,piece_rate,discount) VALUES(?,?,?,?,?)",(cur.lastrowid,sr,item["particulars"],item["piece_rate"],item["discount"]))
                        for size in item["sizes"]:
                            self.conn.execute("INSERT INTO order_item_sizes(order_item_id,size_code,ordered_qty) VALUES(?,?,?)",(item_cur.lastrowid,size["size_code"],size["qty"]))
            self.refresh_all()
            messagebox.showinfo("Order CSV Import Complete", f"{len(grouped)} Order(s) import થયા.\nCSVની item rows grouped by Order Number કરવામાં આવી છે.", parent=self)
        except (OSError, csv.Error, sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Order CSV Import Failed", f"Import પહેલાં validation કરવામાં આવ્યું; error હોય તો data save કરાયું નથી.\n\n{exc}", parent=self)

    def import_dispatch_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import Pending-to-Dispatched CSV", filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as handle:
                reader=csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValueError("CSV fileમાં header row નથી.")
                headers={self.normalize_header(h):h for h in reader.fieldnames}
                required=["order number","party name","particulars","order size","dispatch qty","dispatch date","invoice number","details"]
                missing=[h for h in required if h not in headers]
                if missing: raise ValueError("આ columns missing છે: "+", ".join(missing)+"\nDispatch CSV template બનાવો.")
                records=list(reader)
            if not records: raise ValueError("CSVમાં data rows નથી.")
            pending=[]
            for line_no,raw in enumerate(records,start=2):
                get=lambda name: str(raw.get(headers[name],"") or "").strip()
                if not any(str(v or "").strip() for v in raw.values()): continue
                order_no=self._csv_int(get("order number"),f"Row {line_no} Order Number")
                party_name=get("party name"); particulars=get("particulars"); size_text=get("order size").upper().strip()
                aliases={"M":"M (38)","M (38)":"M (38)","L":"L (40)","L (40)":"L (40)","XL":"XL (42)","XL (42)":"XL (42)","XXL":"XXL (44)","XXL (44)":"XXL (44)"}
                if size_text not in aliases: raise ValueError(f"Row {line_no}: Order Size M, L, XL, XXL અથવા M (38) વગેરે હોવો જોઈએ.")
                size_code=aliases[size_text]
                qty=self._csv_int(get("dispatch qty"),f"Row {line_no} Dispatch Qty")
                if qty<=0: raise ValueError(f"Row {line_no}: Dispatch Qty 0 કરતાં વધુ હોવી જોઈએ.")
                try: dispatch_date=(self.parse_date_value(get("dispatch date")).isoformat() if get("dispatch date") else date.today().isoformat())
                except ValueError as exc: raise ValueError(f"Row {line_no} Dispatch Date: {exc}")
                matches=self.conn.execute("""SELECT s.id AS size_id,s.ordered_qty,s.cancelled,i.particulars,o.id AS order_id,p.party_name
                    FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id
                    JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.order_no=? AND p.party_name=? COLLATE NOCASE
                    AND i.particulars=? COLLATE NOCASE AND s.size_code=? AND o.cancelled=0 AND s.cancelled=0""",(order_no,party_name,particulars,size_code)).fetchall()
                if len(matches)!=1: raise ValueError(f"Row {line_no}: Order {order_no} / Party '{party_name}' / Item '{particulars}' / Size '{size_code}' માટે unique pending order row મળી નથી.")
                match=matches[0]
                already=self.conn.execute("SELECT COALESCE(SUM(qty),0) FROM order_dispatches WHERE order_size_id=?",(match["size_id"],)).fetchone()[0]
                remaining=int(match["ordered_qty"])-int(already or 0)
                used=sum(x["qty"] for x in pending if x["size_id"]==int(match["size_id"]))
                if qty+used>remaining: raise ValueError(f"Row {line_no}: Dispatch Qty {qty} ઉપલબ્ધ pending qty {remaining-used} કરતાં વધુ છે.")
                pending.append({"size_id":int(match["size_id"]),"qty":qty,"date":dispatch_date,"invoice":get("invoice number"),"details":get("details"),"line":line_no})
            if not pending: raise ValueError("CSVમાં import કરવા માટે કોઈ valid dispatch rows નથી.")
            if not messagebox.askyesno("Confirm Dispatch CSV Import",f"{len(pending)} dispatch row(s) save કરવી છે?\nઆથી selected quantities Dispatched ગણાશે અને Pending quantity ઘટશે.",parent=self): return
            with self.conn:
                for row in pending:
                    size_row=self.conn.execute("SELECT size_code FROM order_item_sizes WHERE id=?",(row["size_id"],)).fetchone()
                    self.conn.execute("INSERT INTO order_dispatches(order_size_id,dispatched_size,qty,dispatch_date,details,invoice_number) VALUES(?,?,?,?,?,?)",(row["size_id"],size_row["size_code"],row["qty"],row["date"],row["details"],row["invoice"]))
            self.refresh_all()
            self.refresh_pending_rows()
            self.refresh_dispatched_tree()
            self.refresh_order_reports()
            messagebox.showinfo("Dispatch CSV Import Complete",f"{len(pending)} dispatch row(s) import થયા.\nPending/Dispatched report refresh કરી દીધો છે.",parent=self)
        except (OSError,csv.Error,sqlite3.Error,ValueError) as exc:
            messagebox.showerror("Dispatch CSV Import Failed",f"Validation errorને કારણે dispatch data save કરાયું નથી.\n\n{exc}",parent=self)

    def open_order_list(self):
        win = tk.Toplevel(self)
        win.title("Shubhvastra — Saved Order List")
        win.geometry("900x560")
        win.transient(self)
        win.grab_set()
        outer = ttk.Frame(win, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="SAVED ORDER FORM DETAILS", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        cols = ("order_no", "order_date", "party", "city", "state", "items")
        tree = ttk.Treeview(outer, columns=cols, show="headings", selectmode="browse")
        for col, label, width in [("order_no", "Order Number", 110), ("order_date", "Order Date", 110), ("party", "Party Name", 250), ("city", "City", 120), ("state", "State", 120), ("items", "Item Rows", 90)]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")
        ybar = ttk.Scrollbar(outer, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ybar.set)
        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        rows = self.conn.execute("""SELECT o.id, o.order_no, o.order_date, p.party_name, p.city, p.state,
            (SELECT COUNT(*) FROM order_items i WHERE i.order_id=o.id) AS item_count
            FROM orders o JOIN parties p ON p.id=o.party_id ORDER BY o.order_date DESC, o.order_no DESC""").fetchall()
        for row in rows:
            tree.insert("", "end", iid=str(row["id"]), values=(row["order_no"], self.show_date(row["order_date"]), row["party_name"], row["city"], row["state"], row["item_count"]))
        actions = ttk.Frame(win, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        def selected_order_id():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Select Order", "Listમાંથી Order પસંદ કરો.", parent=win)
                return None
            return int(selected[0])
        def edit_selected():
            oid = selected_order_id()
            if oid is None:
                return
            order = self.conn.execute("SELECT order_no FROM orders WHERE id=?", (oid,)).fetchone()
            if order is None:
                return
            dispatch_count = self.conn.execute("""SELECT COUNT(*) FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=?""", (oid,)).fetchone()[0]
            if dispatch_count:
                messagebox.showwarning("Order Has Dispatches", "આ orderમાં dispatch history છે, તેથી તેને edit કરી શકાતો નથી.", parent=win)
                return
            win.destroy()
            self.load_order_into_form(oid)
        def download_selected_pdf():
            oid = selected_order_id()
            if oid is None:
                return
            order = self.conn.execute("SELECT order_no FROM orders WHERE id=?", (oid,)).fetchone()
            if order is None:
                messagebox.showerror("Order Not Found", "પસંદ કરેલો order databaseમાં મળ્યો નથી.", parent=win)
                return
            path = filedialog.asksaveasfilename(
                parent=win, title="Download Order PDF", defaultextension=".pdf",
                filetypes=[("PDF document", "*.pdf")], initialfile=f"Order_{order['order_no']}.pdf"
            )
            if not path:
                return
            try:
                self.create_order_pdf(oid, path)  # PDF is formatted on A4 by create_order_pdf.
                messagebox.showinfo("PDF Downloaded", f"Order No. {order['order_no']}ની PDF save થઈ ગઈ છે:\n{path}", parent=win)
            except Exception as exc:
                messagebox.showerror("PDF Download Failed", f"Order PDF બનાવી શકાઈ નથી.\n\n{exc}", parent=win)

        ttk.Button(actions, text="Find / Edit Order", style="Primary.TButton", command=edit_selected).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="PDF Download", command=download_selected_pdf).pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=win.destroy).pack(side="right")
        tree.bind("<Double-1>", lambda _e: edit_selected())

    def prompt_load_order_for_edit(self):
        order_no = simpledialog.askinteger("Find / Edit Order", "Edit કરવા Order Number દાખલ કરો:", parent=self, minvalue=1)
        if order_no is None:
            return
        order = self.conn.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
        if not order:
            messagebox.showinfo("Order Not Found", f"Order No. {order_no} મળ્યો નથી.", parent=self)
            return
        dispatch_count = self.conn.execute("""SELECT COUNT(*) FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=?""", (order["id"],)).fetchone()[0]
        if dispatch_count:
            messagebox.showwarning("Order Has Dispatches", "આ orderમાં dispatch history છે. Dispatch record સુરક્ષિત રાખવા માટે હાલ આ order edit કરી શકાતો નથી.", parent=self)
            return
        if self.order_draft_has_content() and self.current_order_id is None:
            if not messagebox.askyesno("Load Order", "હાલના unsaved formને બદલીને પસંદ કરેલો order ખોલવો છે?", parent=self):
                return
        self.load_order_into_form(order["id"])

    def load_order_into_form(self, order_id):
        order = self.conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            messagebox.showerror("Order Not Found", "Saved order databaseમાં મળ્યો નથી.", parent=self)
            return
        self.current_order_id = int(order_id)
        self.order_editing = True
        self.order_form_locked = False
        self.order_number_var.set(str(order["order_no"]))
        self.order_date_var.set(self.show_date(order["order_date"]))
        party = self.conn.execute("SELECT * FROM parties WHERE id=?", (order["party_id"],)).fetchone()
        if party:
            for display, pid in self.order_party_id_by_display.items():
                if pid == party["id"]:
                    self.order_party_var.set(display)
                    self.on_order_party_selected()
                    break
        self.reset_order_item_rows()
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY sr_no,id", (order_id,)).fetchall()
        while len(self.order_item_rows) < max(5, len(items)):
            self.add_order_item_row()
        for idx, item in enumerate(items):
            row = self.order_item_rows[idx]
            row["particulars_var"].set(item["particulars"] or "")
            row["rate_var"].set(str(item["piece_rate"] or 0))
            row["discount_var"].set(str(item["discount"] or 0))
            sizes = self.conn.execute("SELECT size_code, ordered_qty FROM order_item_sizes WHERE order_item_id=?", (item["id"],)).fetchall()
            for size in self.SIZE_OPTIONS:
                match = next((x for x in sizes if x["size_code"] == size), None)
                row["size_vars"][size].set(bool(match))
                row["qty_vars"][size].set(str(match["ordered_qty"]) if match else "")
                row["qty_entries"][size].configure(state="normal" if match else "disabled")
            self.update_order_row_amount(row)
        try:
            packaging = json.loads(order["packaging"] or "[]")
        except Exception:
            packaging = []
        for name, var in self.packaging_vars.items():
            var.set(name in packaging)
        self.order_narration.configure(state="normal")
        self.order_narration.delete("1.0", "end")
        self.order_narration.insert("1.0", order["narration"] or "")
        self.set_order_form_locked(False)
        self.save_order_button.configure(text="Update Order")
        self.order_status_var.set(f"EDITING — Order No. {order['order_no']}. Save કરવા Update Order દબાવો.")
        self.notebook.select(self.order_tab)

    def prompt_delete_order(self):
        order_no = simpledialog.askinteger("Delete Order", "Delete કરવા Order Number દાખલ કરો:", parent=self, minvalue=1)
        if order_no is None:
            return
        order = self.conn.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
        if not order:
            messagebox.showinfo("Order Not Found", f"Order No. {order_no} મળ્યો નથી.", parent=self)
            return
        dispatch_count = self.conn.execute("""SELECT COUNT(*) FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=?""", (order["id"],)).fetchone()[0]
        if dispatch_count:
            messagebox.showwarning("Cannot Delete", "આ orderમાં dispatch history છે. Dispatch recordsની સુરક્ષા માટે delete અટકાવ્યું છે.", parent=self)
            return
        if not messagebox.askyesno("Confirm Delete", f"Order No. {order_no} અને તેની item details કાયમ માટે delete કરવી છે? આ action undo થઈ શકશે નહીં.", icon="warning", parent=self):
            return
        try:
            with self.conn:
                self.conn.execute("DELETE FROM order_item_sizes WHERE order_item_id IN (SELECT id FROM order_items WHERE order_id=?)", (order["id"],))
                self.conn.execute("DELETE FROM order_items WHERE order_id=?", (order["id"],))
                self.conn.execute("DELETE FROM orders WHERE id=?", (order["id"],))
            if self.current_order_id == order["id"]:
                self.initialize_order_form()
            self.refresh_all()
            messagebox.showinfo("Order Deleted", f"Order No. {order_no} delete થયો.", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Delete Failed", f"Order delete થઈ શક્યો નથી.\n\n{exc}", parent=self)

    @staticmethod
    def _pdf_safe_text(value):
        from xml.sax.saxutils import escape
        return escape(str(value or "")).replace("\n", "<br/>")

    def create_order_pdf(self, order_id, path):
        if not ensure_reportlab_installed():
            raise RuntimeError("PDF library (ReportLab) could not be installed. Connect to the internet and run install_pdf_library.bat (Windows) or ./install_pdf_library.command (Mac). The detailed reason is saved in pdf_install_error.log.")
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image as PDFImage
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError as exc:
            raise RuntimeError("PDF library is missing or could not be imported. Run install_pdf_library.bat (Windows) or ./install_pdf_library.command (Mac), then restart the software. See pdf_install_error.log for details.") from exc

        # Use a Windows Indic-capable font when present; fall back to DejaVu/Helvetica.
        regular_font, bold_font = "Helvetica", "Helvetica-Bold"
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        font_pairs = [
            (windir / "Fonts" / "Nirmala.ttf", windir / "Fonts" / "NirmalaB.ttf"),
            (windir / "Fonts" / "arial.ttf", windir / "Fonts" / "arialbd.ttf"),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        ]
        for regular_path, bold_path in font_pairs:
            if regular_path.exists():
                try:
                    if "PartyUnicode" not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont("PartyUnicode", str(regular_path)))
                    regular_font = "PartyUnicode"
                    if bold_path.exists():
                        if "PartyUnicodeBold" not in pdfmetrics.getRegisteredFontNames():
                            pdfmetrics.registerFont(TTFont("PartyUnicodeBold", str(bold_path)))
                        bold_font = "PartyUnicodeBold"
                    else:
                        bold_font = regular_font
                    pdfmetrics.registerFontFamily(regular_font, normal=regular_font, bold=bold_font, italic=regular_font, boldItalic=bold_font)
                    break
                except Exception:
                    regular_font, bold_font = "Helvetica", "Helvetica-Bold"

        order = self.conn.execute("""
            SELECT o.*, p.party_name, p.phone_number, p.address, p.city, p.state, p.gst_number,
                   p.transport_details, p.transport_gst_number
            FROM orders o JOIN parties p ON p.id=o.party_id WHERE o.id=?
        """, (order_id,)).fetchone()
        if not order:
            raise ValueError("Saved order not found in database.")
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY sr_no, id", (order_id,)).fetchall()
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="CompanyHead", parent=styles["Title"], fontName=bold_font, fontSize=15, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#17365d"), spaceAfter=2))
        styles.add(ParagraphStyle(name="SubHead", parent=styles["Normal"], fontName=bold_font, fontSize=9, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#40536b"), spaceAfter=6))
        styles.add(ParagraphStyle(name="CellSmall", parent=styles["Normal"], fontName=regular_font, fontSize=8, leading=10, spaceAfter=0))
        styles.add(ParagraphStyle(name="CellSmallRight", parent=styles["CellSmall"], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name="SectionPDF", parent=styles["Heading3"], fontName=bold_font, fontSize=9, leading=11, textColor=colors.HexColor("#17365d"), spaceBefore=5, spaceAfter=4))
        doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=13*mm, leftMargin=13*mm, topMargin=12*mm, bottomMargin=15*mm, title=f"Order Form {order['order_no']}")
        # Branded A4 header: Trishiv Enterprise LLP logo and contact details on the left,
        # Shubhvastra logo at the upper-right. Assets live beside app.py for both Windows/Mac.
        app_dir = Path(__file__).resolve().parent
        trishiv_logo_path = app_dir / "trishiv_logo.jpg"
        shubhvastra_logo_path = app_dir / "shubhvastra_logo.png"
        address_style = ParagraphStyle(name="CompanyAddressPDF", parent=styles["Normal"], fontName=regular_font,
                                       fontSize=8, leading=10, alignment=TA_LEFT, textColor=colors.HexColor("#222222"), spaceAfter=1)
        trishiv_block = []
        if trishiv_logo_path.exists():
            trishiv_block.append(PDFImage(str(trishiv_logo_path), width=31*mm, height=31*mm, kind="proportional"))
            trishiv_block.append(Spacer(1, 2))
        trishiv_block.append(Paragraph("<b>Address:</b> 2005 New Sardar Traders Market (NSTM), Puna Kumbhariya Road, Surat 395010", address_style))
        trishiv_block.append(Paragraph("<b>Phone Number:</b> 9537510757 (Bhavik), 9099444455 (Nimesh)", address_style))
        shubhvastra_block = []
        if shubhvastra_logo_path.exists():
            shubhvastra_block.append(PDFImage(str(shubhvastra_logo_path), width=53*mm, height=22*mm, kind="proportional"))
        header_table = Table([[trishiv_block, shubhvastra_block]], colWidths=[119*mm, 65*mm], hAlign="LEFT")
        header_table.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ALIGN", (0,0), (0,0), "LEFT"), ("ALIGN", (1,0), (1,0), "RIGHT"),
            ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ]))
        story = [header_table, Spacer(1, 5),
                 Paragraph("ORDER FORM", ParagraphStyle(name="OrderTitle", parent=styles["Heading2"], alignment=TA_CENTER, fontSize=12, textColor=colors.HexColor("#17365d"))),
                 Spacer(1, 4)]
        order_meta = [
            [Paragraph(f"<b>Order Number:</b> {order['order_no']}", styles["CellSmall"]), Paragraph(f"<b>Order Date:</b> {self.show_date(order['order_date'])}", styles["CellSmallRight"])],
            [Paragraph(f"<b>Party:</b> {self._pdf_safe_text(order['party_name'])}", styles["CellSmall"]), Paragraph(f"<b>Phone:</b> {self._pdf_safe_text(order['phone_number'])}", styles["CellSmallRight"])],
            [Paragraph(f"<b>Address:</b> {self._pdf_safe_text(order['address'])}, {self._pdf_safe_text(order['city'])}, {self._pdf_safe_text(order['state'])}", styles["CellSmall"]), Paragraph(f"<b>Party GST:</b> {self._pdf_safe_text(order['gst_number'])}", styles["CellSmallRight"])],
            [Paragraph(f"<b>Transport:</b> {self._pdf_safe_text(order['transport_details'])}", styles["CellSmall"]), Paragraph(f"<b>Transport GST / ID:</b> {self._pdf_safe_text(order['transport_gst_number'])}", styles["CellSmallRight"])],
        ]
        meta_table = Table(order_meta, colWidths=[100*mm, 80*mm])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f2f6fb")), ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#c9d5e3")),
            ("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#d8e1ec")), ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5)
        ]))
        story.extend([meta_table, Spacer(1, 8), Paragraph("ITEM DETAILS", styles["SectionPDF"])])
        # Compact A4 item table: one row per product, with a separate quantity column for each size.
        # Size labels appear only in the header; quantities are shown below each size heading.
        # Explicit white paragraph text is required: ReportLab Paragraph styles override
        # the table cell TEXTCOLOR, so keep the size/Qty labels white on the navy header.
        size_header_style = ParagraphStyle(
            name="SizeHeaderWhite", parent=styles["CellSmall"], fontName=bold_font,
            fontSize=7.2, leading=8.5, alignment=TA_CENTER,
            textColor=colors.white, spaceAfter=0
        )
        size_headers = [Paragraph("<b>M (38)</b><br/>Qty", size_header_style),
                        Paragraph("<b>L (40)</b><br/>Qty", size_header_style),
                        Paragraph("<b>XL (42)</b><br/>Qty", size_header_style),
                        Paragraph("<b>XXL (44)</b><br/>Qty", size_header_style)]
        table_rows = [["Sr.", "Particulars", *size_headers, "Piece Rate", "Discount", "Amount"]]
        gross_total = discount_total = net_total = total_qty = 0
        for item in items:
            sizes = self.conn.execute("SELECT size_code, ordered_qty FROM order_item_sizes WHERE order_item_id=?", (item["id"],)).fetchall()
            qty_by_size = {str(sz["size_code"]): int(sz["ordered_qty"] or 0) for sz in sizes}
            line_qty = sum(qty_by_size.values())
            item_discount = float(item["discount"] or 0)
            gross = line_qty * float(item["piece_rate"] or 0)
            net = gross - item_discount
            table_rows.append([
                str(item["sr_no"]),
                Paragraph(self._pdf_safe_text(item["particulars"]), styles["CellSmall"]),
                *[str(qty_by_size.get(size, "—") if qty_by_size.get(size, 0) else "—") for size in self.SIZE_OPTIONS],
                f"{float(item['piece_rate'] or 0):,.2f}", f"{item_discount:,.2f}", f"{net:,.2f}"
            ])
            gross_total += gross
            discount_total += item_discount
            net_total += net
            total_qty += line_qty
        item_table = Table(table_rows, repeatRows=1, colWidths=[8*mm, 48*mm, 14*mm, 14*mm, 14*mm, 14*mm, 22*mm, 22*mm, 28*mm])
        item_table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365d")), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),bold_font), ("FONTSIZE",(0,0),(-1,0),7.2),
            ("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#000000")), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("ALIGN",(0,0),(-1,-1),"CENTER"), ("ALIGN",(6,1),(-1,-1),"RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f2f6fb")]),
            ("LEFTPADDING",(0,0),(-1,-1),3), ("RIGHTPADDING",(0,0),(-1,-1),3),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)
        ]))
        story.extend([item_table, Spacer(1, 6)])
        totals = Table([
            [Paragraph(f"<b>Total Pieces:</b> {total_qty}", styles["CellSmall"]), Paragraph(f"<b>Gross:</b> {gross_total:,.2f}", styles["CellSmallRight"])],
            [Paragraph(f"<b>Total Discount:</b> {discount_total:,.2f}", styles["CellSmall"]), Paragraph(f"<b>Net Total:</b> {net_total:,.2f}", styles["CellSmallRight"])],
        ], colWidths=[90*mm, 90*mm])
        totals.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#eaf1f8")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#c9d5e3")),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#d8e1ec")),("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6), ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(totals)
        try:
            packaging = json.loads(order["packaging"] or "[]")
            if not isinstance(packaging, list):
                packaging = [str(packaging)] if packaging else []
        except (ValueError, TypeError):
            packaging = [str(order["packaging"])] if order["packaging"] else []
        story.extend([Spacer(1, 7), Paragraph(f"<b>Packaging:</b> {self._pdf_safe_text(', '.join(packaging) if packaging else '—')}", styles["CellSmall"])])
        if (order["narration"] or "").strip():
            story.extend([Spacer(1, 5), Paragraph("Additional Order Details", styles["SectionPDF"]), Paragraph(self._pdf_safe_text(order["narration"]), styles["CellSmall"])])

        def footer(canvas, _doc):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#c9d5e3"))
            canvas.line(13*mm, 10*mm, A4[0]-13*mm, 10*mm)
            canvas.setFont(regular_font, 7)
            canvas.setFillColor(colors.HexColor("#65758b"))
            canvas.drawString(13*mm, 6*mm, f"Order No. {order['order_no']} — TRISHIV ENTERPRISE LLP / SHUBHVASTRA")
            canvas.drawRightString(A4[0]-13*mm, 6*mm, f"Page {canvas.getPageNumber()}")
            canvas.restoreState()
        doc.build(story, onFirstPage=footer, onLaterPages=footer)

    def save_order_pdf(self):
        was_new_order = self.current_order_id is None
        if not self.save_order(show_success=False, reset_after_save=False):
            return
        order_id = self.current_order_id
        order_no = self.order_number_var.get()
        path = filedialog.asksaveasfilename(parent=self, title="Save Order PDF", defaultextension=".pdf",
                                            filetypes=[("PDF document", "*.pdf")], initialfile=f"Order_{order_no}.pdf")
        if not path:
            return
        try:
            self.create_order_pdf(order_id, path)
            messagebox.showinfo("PDF Saved", f"Order PDF saved successfully:\n{path}", parent=self)
            if was_new_order:
                self.initialize_order_form()
        except Exception as exc:
            messagebox.showerror("PDF Failed", f"Could not create order PDF.\n\n{exc}", parent=self)

    def print_order_pdf(self):
        was_new_order = self.current_order_id is None
        if not self.save_order(show_success=False, reset_after_save=False):
            return
        order_id = self.current_order_id
        order_no = self.order_number_var.get()
        try:
            print_dir = Path(os.getenv("TEMP") or os.getenv("TMP") or str(BASE_DIR)) / "PartyReportingPrints"
            print_dir.mkdir(parents=True, exist_ok=True)
            path = print_dir / f"Order_{order_no}.pdf"
            self.create_order_pdf(order_id, path)
            if os.name == "nt":
                os.startfile(str(path), "print")
            else:
                webbrowser.open(path.resolve().as_uri())
            messagebox.showinfo("Print Order", f"Order No. {order_no} PDF તૈયાર છે અને print command મોકલવાનો પ્રયાસ કર્યો છે.\n\nફાઇલ: {path}\n\nPrinter/printing dialog તમારા computer પર આધારિત હોઈ શકે છે.", parent=self)
            if was_new_order:
                self.initialize_order_form()
        except Exception as exc:
            messagebox.showerror("Print Failed", f"Could not print order.\n\n{exc}", parent=self)

    # ------------------------------------------------------------------
    # PENDING AND DISPATCHED ORDERS
    # ------------------------------------------------------------------
    def build_pending_orders_tab(self):
        self.pending_notebook = ttk.Notebook(self.pending_tab)
        self.pending_notebook.pack(fill="both", expand=True)
        self.pending_work_tab = ttk.Frame(self.pending_notebook, padding=6)
        self.dispatched_orders_tab = ttk.Frame(self.pending_notebook, padding=8)
        self.pending_notebook.add(self.pending_work_tab, text="  Pending to Dispatch  ")
        self.pending_notebook.add(self.dispatched_orders_tab, text="  Dispatched Orders  ")

        self.pending_canvas, self.pending_content = self.make_scrollable(self.pending_work_tab)
        party_card = self.make_card(self.pending_content, "PENDING ORDERS — SELECT A PARTY")
        party_card.pack(fill="x", pady=(0, 8))
        party_fields = ttk.Frame(party_card, style="Card.TFrame")
        party_fields.pack(fill="x")
        ttk.Label(party_fields, text="Party Name (type to search and select)", background="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.pending_party_var = tk.StringVar()
        self.pending_party_combo = ttk.Combobox(party_fields, textvariable=self.pending_party_var, state="normal", width=56)
        self.pending_party_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=3)
        self.pending_party_combo.bind("<KeyRelease>", self.on_pending_party_keyrelease)
        self.pending_party_combo.bind("<<ComboboxSelected>>", self.on_pending_party_selected)
        ttk.Button(party_fields, text="Show Pending", style="Primary.TButton", command=self.refresh_pending_rows).grid(row=1, column=1, padx=4)
        ttk.Button(party_fields, text="Export Pending PDF", command=self.export_pending_pdf).grid(row=1, column=2, padx=4)
        ttk.Label(party_fields, text="Agent-wise PDF (optional)", background="#ffffff").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(7, 2))
        self.pending_agent_filter_var = tk.StringVar(value="ALL AGENTS")
        self.pending_agent_filter_combo = ttk.Combobox(party_fields, textvariable=self.pending_agent_filter_var, state="readonly", width=38)
        self.pending_agent_filter_combo.grid(row=4, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Button(party_fields, text="Export Agent Pending PDF", command=self.export_pending_pdf).grid(row=4, column=1, padx=4, sticky="w")
        self.pending_summary_var = tk.StringVar(value="Select a Party to see its pending order sizes.")
        ttk.Label(party_fields, textvariable=self.pending_summary_var, background="#ffffff", foreground="#65758b").grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))
        party_fields.columnconfigure(0, weight=1)

        pending_card = self.make_card(self.pending_content, "PENDING ORDER DETAILS — tick Dispatch, edit dispatch size/quantity if required")
        pending_card.pack(fill="x", pady=(0, 8))
        self.pending_rows_header = tk.Frame(pending_card, bg="#000000", padx=1, pady=1)
        self.pending_rows_header.pack(fill="x")
        # Sr. No. is removed. Description is intentionally compact and centered.
        pending_headers = [("Order No.",0),("Description",1),("Dispatch?",2),("Order Size",3),
                           ("Pending Qty",4),("Amount",5),("Discount",6),("Dispatch Qty",7),("Details",8),("Cancel",9)]
        for label, col in pending_headers:
            tk.Label(self.pending_rows_header, text=label, bg="#e7edf5", fg="#17365d",
                     font=("Segoe UI", 8, "bold"), anchor="center", padx=3, pady=5,
                     relief="flat", bd=0, highlightthickness=0).grid(row=0, column=col, sticky="nsew", padx=0, pady=0)
        for col, weight in enumerate((1,1,1,1,1,1,1,1,2,1)):
            self.pending_rows_header.columnconfigure(col, weight=weight, minsize=52, uniform="pending_table_cols")
        self.pending_rows_container = ttk.Frame(pending_card, style="Card.TFrame")
        self.pending_rows_container.pack(fill="x")
        self.pending_row_widgets = []

        dispatch_card = self.make_card(self.pending_content, "DISPATCHED DETAILS")
        dispatch_card.pack(fill="x", pady=(0, 8))
        dispatch_fields = ttk.Frame(dispatch_card, style="Card.TFrame")
        dispatch_fields.pack(fill="x")
        self.dispatch_date_var = tk.StringVar(value="")
        self.dispatch_invoice_var = tk.StringVar(value="")
        date_cell = ttk.Frame(dispatch_fields, style="Card.TFrame")
        date_cell.pack(side="left", fill="x", expand=False, padx=(0, 18))
        ttk.Label(date_cell, text="Dispatched Date", background="#ffffff").pack(anchor="w", pady=(0, 3))
        self.dispatch_date_entry = ttk.Entry(date_cell, textvariable=self.dispatch_date_var, width=20)
        self.dispatch_date_entry.pack(anchor="w", ipady=3)
        self.dispatch_date_entry.bind("<FocusOut>", self.normalize_dispatch_date)
        invoice_cell = ttk.Frame(dispatch_fields, style="Card.TFrame")
        invoice_cell.pack(side="left", fill="x", expand=True)
        ttk.Label(invoice_cell, text="Invoice Number (Optional)", background="#ffffff").pack(anchor="w", pady=(0, 3))
        self.dispatch_invoice_entry = ttk.Entry(invoice_cell, textvariable=self.dispatch_invoice_var, width=32)
        self.dispatch_invoice_entry.pack(anchor="w", ipady=3)
        self.dispatch_status_var = tk.StringVar(value="Only checked Dispatch rows will be saved. Unticked quantities stay pending.")
        ttk.Label(dispatch_card, textvariable=self.dispatch_status_var, background="#ffffff", foreground="#65758b").pack(anchor="w", pady=(6, 8))
        self.save_dispatch_button = ttk.Button(dispatch_card, text="Save to Dispatched Order", style="Primary.TButton", command=self.save_dispatches)
        self.save_dispatch_button.pack(side="left", anchor="w")
        ttk.Button(dispatch_card, text="Create Dispatch CSV", command=self.create_dispatch_import_template).pack(side="left", anchor="w", padx=(8, 0))
        ttk.Button(dispatch_card, text="Import Dispatch CSV", command=self.import_dispatch_csv).pack(side="left", anchor="w", padx=(8, 0))
        self.cancel_selected_button = ttk.Button(dispatch_card, text="Cancel Selected", command=self.cancel_selected_pending_items)
        self.cancel_selected_button.pack(side="left", anchor="w", padx=(8, 0))
        self.cancel_selected_button.pack_forget()

        dispatched_card = self.make_card(self.dispatched_orders_tab, "DISPATCHED ORDERS — sorted party-wise")
        dispatched_card.pack(fill="both", expand=True)
        filter_bar = ttk.Frame(dispatched_card, style="Card.TFrame")
        filter_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(filter_bar, text="Party Filter:").pack(side="left")
        self.dispatched_party_filter_var = tk.StringVar(value="ALL PARTIES")
        self.dispatched_party_filter_combo = ttk.Combobox(filter_bar, textvariable=self.dispatched_party_filter_var, state="readonly", width=38)
        self.dispatched_party_filter_combo.pack(side="left", padx=(6, 12))
        self.dispatched_party_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_dispatched_tree())
        ttk.Label(filter_bar, text="Agent Filter:").pack(side="left")
        self.dispatched_agent_filter_var = tk.StringVar(value="ALL AGENTS")
        self.dispatched_agent_filter_combo = ttk.Combobox(filter_bar, textvariable=self.dispatched_agent_filter_var, state="readonly", width=25)
        self.dispatched_agent_filter_combo.pack(side="left", padx=(6, 10))
        self.dispatched_agent_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_dispatched_tree())
        ttk.Button(filter_bar, text="Refresh", command=self.refresh_dispatched_tree).pack(side="left", padx=(0, 6))
        ttk.Button(filter_bar, text="Export Dispatched PDF", command=self.export_dispatched_pdf).pack(side="left", padx=(0, 12))
        ttk.Label(filter_bar, text="Selected Invoice No.:").pack(side="left")
        self.invoice_edit_var = tk.StringVar(value="")
        ttk.Entry(filter_bar, textvariable=self.invoice_edit_var, width=20).pack(side="left", padx=5)
        ttk.Button(filter_bar, text="Update Invoice No.", command=self.update_selected_dispatch_invoice).pack(side="left", padx=4)
        ttk.Button(filter_bar, text="Return to Pending", command=self.return_selected_dispatch_to_pending).pack(side="left", padx=4)
        # Compact, professional dispatched table: one row per order item/dispatch batch,
        # with quantities shown in size-specific columns rather than repeating each size.
        dispatch_columns = ("party", "agent", "date", "order_no", "description", "m_qty", "l_qty", "xl_qty", "xxl_qty", "invoice_number", "details")
        dispatch_headings = {"party":"Party Name", "agent":"Agent", "date":"Dispatch Date", "order_no":"Order No.", "description":"Description",
                             "m_qty":"M (38)\nQty", "l_qty":"L (40)\nQty", "xl_qty":"XL (42)\nQty", "xxl_qty":"XXL (44)\nQty",
                             "invoice_number":"Invoice Number", "details":"Details"}
        dispatch_widths = {"party":165, "agent":120, "date":100, "order_no":75, "description":150,
                           "m_qty":70, "l_qty":70, "xl_qty":70, "xxl_qty":75, "invoice_number":115, "details":170}
        self.dispatched_tree = self.create_tree(dispatched_card, dispatch_columns, dispatch_headings, dispatch_widths)
        self.dispatched_tree.bind("<<TreeviewSelect>>", self.on_dispatched_row_selected)
        self.dispatched_party_id_by_display = {}
        self.refresh_pending_party_lookup()

    def _export_order_report_pdf(self, title, headers, rows, suggested_name):
        """Save a clean A4 report; exporting never modifies order or dispatch data."""
        path = filedialog.asksaveasfilename(parent=self, title="Save PDF Report", defaultextension=".pdf",
                                            initialfile=suggested_name, filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            if not ensure_reportlab_installed():
                raise RuntimeError("PDF library (ReportLab) could not be installed. Run the PDF library installer for your system; see pdf_install_error.log for the detailed reason.")
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            page = landscape(A4) if len(headers) > 6 else A4
            doc = SimpleDocTemplate(path, pagesize=page, rightMargin=10*mm, leftMargin=10*mm, topMargin=12*mm, bottomMargin=12*mm)
            styles = getSampleStyleSheet()
            body = ParagraphStyle("SmallReport", parent=styles["BodyText"], fontSize=7, leading=9)
            story = [Paragraph(title, styles["Title"]), Paragraph(f"Generated: {datetime.now():%d-%m-%Y %H:%M}", styles["Normal"]), Spacer(1, 5*mm)]
            table_data = [[Paragraph(str(h), body) for h in headers]]
            table_data += [[Paragraph(str(v if v is not None else ""), body) for v in row] for row in rows]
            if len(table_data) == 1:
                table_data.append([Paragraph("No matching records.", body)] + [""] * (len(headers)-1))
            table = Table(table_data, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),colors.HexColor("#17365d")),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.black),
                ("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f6fb")]),
                ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
            story.append(table); doc.build(story)
            messagebox.showinfo("PDF Saved", f"Report saved successfully:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", f"Could not create the PDF.\n\n{exc}", parent=self)

    def export_pending_pdf(self):
        """Export pending orders grouped by product with one column per size."""
        display = self.pending_party_var.get().strip()
        party_id = getattr(self, "pending_party_id_by_display", {}).get(display)
        sql = """SELECT o.order_no,o.order_date,p.party_name,i.sr_no,i.particulars,s.size_code,s.ordered_qty,
                 COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS sent,
                 p.state,a.agent_name,o.id AS order_id,i.id AS item_id
                 FROM orders o JOIN parties p ON p.id=o.party_id
                 LEFT JOIN agents a ON a.id=p.agent_id JOIN order_items i ON i.order_id=o.id
                 JOIN order_item_sizes s ON s.order_item_id=i.id
                 WHERE COALESCE(o.cancelled,0)=0 AND COALESCE(s.cancelled,0)=0"""
        params=[]
        if party_id:
            sql += " AND p.id=?"; params.append(party_id)
        agent_filter = getattr(self, "pending_agent_filter_var", tk.StringVar(value="ALL AGENTS")).get().strip()
        if agent_filter and agent_filter != "ALL AGENTS":
            sql += " AND a.agent_name=?"; params.append(agent_filter)
        sql += " ORDER BY p.party_name COLLATE NOCASE,o.order_date,o.order_no,i.sr_no,s.size_code"
        size_names = {"M": "M (38)", "L": "L (40)", "XL": "XL (42)", "XXL": "XXL (44)"}
        grouped = {}
        import re
        for r in self.conn.execute(sql,params).fetchall():
            ordered=int(r["ordered_qty"] or 0); sent=min(ordered,int(r["sent"] or 0)); pending=max(0,ordered-sent)
            if not pending:
                continue
            key=(r["order_no"], self.show_date(r["order_date"]), r["party_name"], r["agent_name"] or "—",
                 r["state"] or "—", r["particulars"], int(r["item_id"]))
            if key not in grouped:
                grouped[key]={"sizes":{"M":0,"L":0,"XL":0,"XXL":0},"other":[]}
            raw=str(r["size_code"] or "").strip().upper()
            m=re.match(r"^(XXL|XL|L|M)\b", raw)
            size=m.group(1) if m else ""
            if size in grouped[key]["sizes"]:
                grouped[key]["sizes"][size]+=pending
            else:
                grouped[key]["other"].append((raw,pending))
        report_rows=[]
        for key,data in grouped.items():
            order_no,order_date,party,agent,state,description,_item_id=key
            sizes=data["sizes"]
            report_rows.append((order_no,order_date,party,agent,state,description,
                                sizes["M"] or "—",sizes["L"] or "—",sizes["XL"] or "—",sizes["XXL"] or "—",
                                "; ".join(f"{sz}: {qty}" for sz,qty in data["other"])))
        scope = f" — {display}" if party_id else (f" — Agent: {agent_filter}" if agent_filter != "ALL AGENTS" else " — All Parties")
        if party_id and agent_filter != "ALL AGENTS":
            scope += f" | Agent: {agent_filter}"
        label = "Pending Order Report" + scope
        headers=["Order No.","Order Date","Party","Agent","State","Design / Item","M (38) Qty","L (40) Qty","XL (42) Qty","XXL (44) Qty","Other Sizes"]
        self._export_order_report_pdf(label,headers,report_rows,"Shubhvastra_Pending_Orders.pdf")

    def export_dispatched_pdf(self):
        """Export the Dispatched Orders preview using the same grouped rows and columns."""
        display = self.dispatched_party_filter_var.get().strip()
        party_id = getattr(self, "dispatched_party_id_by_display", {}).get(display) if display != "ALL PARTIES" else None
        # Keep the export query aligned with the live preview's dispatch records.
        sql = """SELECT p.party_name, a.agent_name, o.order_no, d.dispatch_date, d.invoice_number,
                        i.particulars, d.dispatched_size, d.qty, d.details, s.size_code
                 FROM order_dispatches d
                 JOIN order_item_sizes s ON s.id=d.order_size_id
                 JOIN order_items i ON i.id=s.order_item_id
                 JOIN orders o ON o.id=i.order_id
                 JOIN parties p ON p.id=o.party_id
                 LEFT JOIN agents a ON a.id=p.agent_id
                 WHERE 1=1"""
        params = []
        if party_id:
            sql += " AND p.id=?"
            params.append(party_id)
        agent_filter = getattr(self, "dispatched_agent_filter_var", tk.StringVar(value="ALL AGENTS")).get().strip()
        if agent_filter and agent_filter != "ALL AGENTS":
            sql += " AND a.agent_name=?"
            params.append(agent_filter)
        sql += " ORDER BY p.party_name COLLATE NOCASE, d.dispatch_date DESC, o.order_no DESC, i.sr_no, d.id"
        rows = self.conn.execute(sql, params).fetchall()
        grouped = {}
        for row in rows:
            key = (row["party_name"], row["agent_name"] or "—", row["dispatch_date"], row["order_no"],
                   row["particulars"], row["invoice_number"] or "", row["details"] or "")
            if key not in grouped:
                grouped[key] = {"sizes": {"M": 0, "L": 0, "XL": 0, "XXL": 0}}
            raw_size = str(row["dispatched_size"] or row["size_code"] or "").strip().upper()
            import re
            match = re.match(r"^(XXL|XL|L|M)\b", raw_size)
            size_key = match.group(1) if match else ""
            if size_key in grouped[key]["sizes"]:
                grouped[key]["sizes"][size_key] += int(row["qty"] or 0)
        report_rows = []
        for key, data in grouped.items():
            party, agent, dispatch_date, order_no, description, invoice_number, details = key
            report_rows.append((party, agent, self.show_date(dispatch_date), order_no, description,
                                data["sizes"]["M"] or "—", data["sizes"]["L"] or "—",
                                data["sizes"]["XL"] or "—", data["sizes"]["XXL"] or "—",
                                invoice_number, details))
        label = "Dispatched Orders" + (f" — {display}" if party_id else (f" — Agent: {agent_filter}" if agent_filter != "ALL AGENTS" else " — All Parties"))
        if party_id and agent_filter != "ALL AGENTS":
            label += f" | Agent: {agent_filter}"
        headers = ["Party Name", "Agent", "Dispatch Date", "Order No.", "Description",
                   "M (38) Qty", "L (40) Qty", "XL (42) Qty", "XXL (44) Qty", "Invoice Number", "Details"]
        self._export_order_report_pdf(label, headers, report_rows, "Shubhvastra_Dispatched_Orders.pdf")

    def refresh_pending_party_lookup(self):
        if not hasattr(self, "pending_party_combo"):
            return
        rows = self.conn.execute("SELECT * FROM parties ORDER BY party_name COLLATE NOCASE, city COLLATE NOCASE, id").fetchall()
        values, row_map, id_map = [], {}, {}
        counts = {}
        for row in rows:
            base = f"{row['party_name']} — {row['city']} — {row['phone_number']}"
            counts[base] = counts.get(base, 0) + 1
            display = base if counts[base] == 1 else f"{base} ({counts[base]})"
            values.append(display)
            row_map[display] = row
            id_map[display] = int(row["id"])
        current = self.pending_party_var.get()
        self.pending_party_rows_by_display = row_map
        self.pending_party_id_by_display = id_map
        self.pending_party_combo.configure(values=values)
        self.dispatched_party_id_by_display = {display: pid for display, pid in id_map.items()}
        if hasattr(self, "dispatched_party_filter_combo"):
            self.dispatched_party_filter_combo.configure(values=["ALL PARTIES"] + values)
            if self.dispatched_party_filter_var.get() not in ["ALL PARTIES"] + values:
                self.dispatched_party_filter_var.set("ALL PARTIES")
        agent_names = [r[0] for r in self.conn.execute("SELECT agent_name FROM agents ORDER BY agent_name COLLATE NOCASE").fetchall()]
        if hasattr(self, "pending_agent_filter_combo"):
            agent_values = ["ALL AGENTS"] + agent_names
            self.pending_agent_filter_combo.configure(values=agent_values)
            if self.pending_agent_filter_var.get() not in agent_values:
                self.pending_agent_filter_var.set("ALL AGENTS")
        if hasattr(self, "dispatched_agent_filter_combo"):
            agent_values = ["ALL AGENTS"] + agent_names
            self.dispatched_agent_filter_combo.configure(values=agent_values)
            if self.dispatched_agent_filter_var.get() not in agent_values:
                self.dispatched_agent_filter_var.set("ALL AGENTS")
        if current and current not in id_map:
            self.pending_party_var.set("")
            self.refresh_pending_rows()

    def on_pending_party_keyrelease(self, event=None):
        """Filter suggestions without stealing keystrokes; load rows on an exact valid match."""
        if event and event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Left", "Right", "Home", "End"):
            return
        query = self.pending_party_var.get().strip().casefold()
        values = list(getattr(self, "pending_party_id_by_display", {}).keys())
        matches = [v for v in values if query in v.casefold()] if query else values
        self.pending_party_combo.configure(values=matches)
        exact = self.pending_party_var.get().strip()
        if exact in self.pending_party_id_by_display:
            self.refresh_pending_rows()
            return
        # If the user types the exact Party Master name (without city/phone suffix),
        # resolve it automatically when it uniquely identifies one party.
        name_matches = [(display, row) for display, row in getattr(self, "pending_party_rows_by_display", {}).items()
                        if str(row["party_name"] or "").strip().casefold() == exact.casefold()] if exact else []
        if len(name_matches) == 1:
            self.pending_party_var.set(name_matches[0][0])
            self.refresh_pending_rows()
        else:
            self.clear_pending_rows("Typing to search — select a matching Party from the dropdown to load its pending orders.")

    def on_pending_party_selected(self, _event=None):
        self.refresh_pending_rows()

    def clear_pending_rows(self, message=None):
        if not hasattr(self, "pending_rows_container"):
            return
        for child in self.pending_rows_container.winfo_children():
            child.destroy()
        self.pending_row_widgets = []
        if message:
            self.pending_summary_var.set(message)

    def refresh_pending_rows(self):
        if not hasattr(self, "pending_rows_container"):
            return
        display = self.pending_party_var.get().strip()
        party_id = self.pending_party_id_by_display.get(display)
        self.clear_pending_rows()
        if not party_id:
            self.pending_summary_var.set("Select a Party to see its pending order sizes.")
            return
        rows = self.conn.execute("""
            SELECT s.id AS size_id, s.size_code, s.ordered_qty, i.id AS item_id, i.sr_no, i.particulars,
                   i.piece_rate, i.discount, o.id AS order_id, o.order_no, o.order_date,
                   COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS dispatched_qty,
                   (SELECT SUM(s2.ordered_qty) FROM order_item_sizes s2 WHERE s2.order_item_id=i.id) AS line_total_qty
            FROM order_item_sizes s
            JOIN order_items i ON i.id=s.order_item_id
            JOIN orders o ON o.id=i.order_id
            WHERE o.party_id=? AND COALESCE(o.cancelled,0)=0 AND COALESCE(s.cancelled,0)=0
            ORDER BY o.order_date, o.order_no, i.sr_no,
                     CASE s.size_code WHEN 'M (38)' THEN 1 WHEN 'L (40)' THEN 2 WHEN 'XL (42)' THEN 3 ELSE 4 END
        """, (party_id,)).fetchall()
        pending_rows = []
        for row in rows:
            pending_qty = int(row["ordered_qty"]) - int(row["dispatched_qty"] or 0)
            if pending_qty > 0:
                line_total = int(row["line_total_qty"] or 0)
                disc = round(float(row["discount"] or 0) * pending_qty / line_total, 2) if line_total else 0.0
                amount = max(0.0, pending_qty * float(row["piece_rate"] or 0) - disc)
                pending_rows.append((row, pending_qty, disc, amount))
        if not pending_rows:
            self.pending_summary_var.set("આ Partyના બધા order sizes dispatch થઈ ગયા છે અથવા હજી કોઈ Order નથી.")
            return
        total_qty = sum(qty for _, qty, _, _ in pending_rows)
        order_count = len({int(r["order_id"]) for r, _, _, _ in pending_rows})
        self.pending_summary_var.set(f"Pending orders: {order_count}  |  Pending size rows: {len(pending_rows)}  |  Pending pieces: {total_qty}")
        for idx, (record, pending_qty, discount, amount) in enumerate(pending_rows):
            bg = "#ffffff" if idx % 2 == 0 else "#f2f6fb"
            # Thin black grid: a single 1px gutter between cells, without heavy double borders.
            frame = tk.Frame(self.pending_rows_container, bg="#000000", padx=1, pady=1,
                             highlightthickness=0, bd=0)
            frame.pack(fill="x", expand=True, pady=0)
            vals = [str(record["order_no"]), record["particulars"], record["size_code"],
                    str(pending_qty), f"{amount:,.2f}", f"{discount:,.2f}"]
            value_columns = [0, 1, 3, 4, 5, 6]
            for value, grid_col in zip(vals, value_columns):
                # Description and all its text are centered, with a smaller column width.
                anchor = "center" if grid_col in (0, 1, 3, 4) else "e"
                tk.Label(frame, text=value, bg=bg, fg="#243247", anchor=anchor, padx=3,
                         font=("Segoe UI", 8), relief="flat", bd=0,
                         highlightthickness=0).grid(row=0, column=grid_col, sticky="nsew", padx=0, pady=0)
            dispatch_var = tk.BooleanVar(value=False)
            qty_var = tk.StringVar(value=str(pending_qty))
            details_var = tk.StringVar(value="")
            # Use explicit symbols so Dispatch always shows a tick (✓), not the OS theme's X mark.
            dispatch_check = tk.Checkbutton(
                frame, text="Dispatch", variable=dispatch_var, indicatoron=False,
                bg=bg, fg="#243247", selectcolor="#d9ead3", activebackground=bg,
                activeforeground="#243247", relief="flat", bd=0, highlightthickness=0, padx=3, pady=2,
                font=("Segoe UI", 8),
                command=lambda v=dispatch_var, w=None: None,
            )
            dispatch_check.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)
            qty_entry = tk.Entry(frame, textvariable=qty_var, width=7, state="disabled", justify="center", bd=0, relief="flat", highlightthickness=0, bg="#ffffff")
            qty_entry.grid(row=0, column=7, sticky="nsew", padx=0, pady=0)
            details_entry = tk.Entry(frame, textvariable=details_var, width=14, state="disabled", bd=0, relief="flat", highlightthickness=0, bg="#ffffff")
            details_entry.grid(row=0, column=8, sticky="nsew", padx=0, pady=0)
            cancel_var = tk.BooleanVar(value=False)
            cancel_box = tk.Frame(frame, bg="#e57373", padx=0, pady=0, bd=0, highlightthickness=0)
            cancel_box.grid(row=0, column=9, sticky="nsew", padx=0, pady=0, ipadx=0, ipady=0)
            cancel_check = tk.Checkbutton(
                cancel_box, text="Cancel", variable=cancel_var, indicatoron=False,
                bg="#e57373", fg="#ffffff", selectcolor="#c62828",
                activebackground="#ef9a9a", activeforeground="#ffffff",
                font=("Segoe UI", 8, "bold"), relief="flat", bd=0, highlightthickness=0, padx=5, pady=2,
                command=lambda r=record, v=cancel_var, w=None: None,
            )
            cancel_check.pack()
            def update_cancel_mark(r=record, v=cancel_var, w=cancel_check):
                # Checkbox only selects rows; cancellation is committed with one button below.
                w.configure(text=("✕ Cancel" if v.get() else "Cancel"))
                self.update_cancel_selection_button()
            cancel_check.configure(command=update_cancel_mark)
            row_data = {"record": record, "pending_qty": pending_qty, "dispatch_var": dispatch_var,
                        "qty_var": qty_var, "qty_entry": qty_entry, "details_var": details_var,
                        "details_entry": details_entry, "cancel_var": cancel_var, "frame": frame}
            def update_dispatch_mark(v=dispatch_var, w=dispatch_check):
                w.configure(text=("✓ Dispatch" if v.get() else "Dispatch"))
                self.toggle_pending_dispatch_row(row_data)
            dispatch_check.configure(command=update_dispatch_mark)
            for col, weight in enumerate((1,1,1,1,1,1,1,1,2,1)):
                frame.grid_columnconfigure(col, weight=weight, minsize=52, uniform="pending_table_cols")
            self.pending_row_widgets.append(row_data)
        self.update_cancel_selection_button()

    def update_cancel_selection_button(self):
        """Show the batch-cancel action only while one or more Cancel boxes are selected."""
        if not hasattr(self, "cancel_selected_button"):
            return
        has_selection = any(row.get("cancel_var") and row["cancel_var"].get() for row in self.pending_row_widgets)
        if has_selection:
            if not self.cancel_selected_button.winfo_manager():
                self.cancel_selected_button.pack(side="left", anchor="w", padx=(8, 0))
        else:
            self.cancel_selected_button.pack_forget()

    def cancel_selected_pending_items(self):
        selected = [row for row in self.pending_row_widgets if row.get("cancel_var") and row["cancel_var"].get()]
        if not selected:
            self.update_cancel_selection_button()
            return
        try:
            with self.conn:
                for row in selected:
                    self.conn.execute("UPDATE order_item_sizes SET cancelled=1 WHERE id=?", (int(row["record"]["size_id"]),))
            count = len(selected)
            self.refresh_pending_rows()
            self.refresh_dispatched_tree()
            self.refresh_order_reports()
            self.dispatch_status_var.set(f"Cancelled {count} selected item-size row(s).")
            messagebox.showinfo("Cancellation Saved", f"Cancelled {count} selected item-size row(s).", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Cancel Failed", f"Could not cancel selected item-size rows.\n\n{exc}", parent=self)

    def cancel_pending_order(self, record, cancel_var):
        order_id = int(record["order_id"])
        order_no = record["order_no"]
        if not cancel_var.get():
            return
        size_code = record["size_code"]
        item_name = record["particulars"]
        confirmed = messagebox.askyesno(
            "Cancel Item / Size",
            f"Cancel only this item and size?\n\nOrder No.: {order_no}\nItem: {item_name}\nSize: {size_code}\n\nOnly this order's selected item-size row will be cancelled. Other items and sizes in the same order will remain active.",
            parent=self,
        )
        if not confirmed:
            cancel_var.set(False)
            return
        try:
            with self.conn:
                self.conn.execute("UPDATE order_item_sizes SET cancelled=1 WHERE id=?", (int(record["size_id"]),))
            self.refresh_pending_rows()
            self.refresh_dispatched_tree()
            self.refresh_order_reports()
            messagebox.showinfo("Item / Size Cancelled", f"Order No. {order_no}: {item_name} / {size_code} cancelled. Other item sizes remain active.", parent=self)
        except sqlite3.Error as exc:
            cancel_var.set(False)
            messagebox.showerror("Cancel Failed", f"Could not cancel order.\n\n{exc}", parent=self)

    def toggle_pending_dispatch_row(self, row):
        enabled = row["dispatch_var"].get()
        state = "readonly" if enabled else "disabled"
        row["qty_entry"].configure(state="normal" if enabled else "disabled")
        row["details_entry"].configure(state="normal" if enabled else "disabled")
        if enabled and not row["qty_var"].get().strip():
            row["qty_var"].set(str(row["pending_qty"]))

    def normalize_dispatch_date(self, _event=None):
        try:
            self.dispatch_date_var.set(self.parse_date_value(self.dispatch_date_var.get()).strftime("%d-%m-%Y"))
        except ValueError:
            return

    def save_dispatches(self):
        display = self.pending_party_var.get().strip()
        party_id = self.pending_party_id_by_display.get(display)
        if not party_id:
            messagebox.showwarning("Select Party", "Dispatch save કરતાં પહેલાં Party select કરો.", parent=self)
            return
        try:
            date_text = self.dispatch_date_var.get().strip()
            dispatch_date = (self.parse_date_value(date_text) if date_text else date.today()).isoformat()
        except ValueError as exc:
            messagebox.showwarning("Invalid Dispatch Date", str(exc), parent=self)
            self.dispatch_date_entry.focus_set()
            return
        selected = [row for row in self.pending_row_widgets if row["dispatch_var"].get()]
        if not selected:
            messagebox.showwarning("No Dispatch Selected", "Dispatch checkbox tick કરેલી ઓછામાં ઓછી એક row પસંદ કરો.", parent=self)
            return
        valid = []
        errors = []
        for row in selected:
            record = row["record"]
            try:
                qty = int(row["qty_var"].get().strip())
                if qty <= 0 or qty > row["pending_qty"]:
                    raise ValueError
            except ValueError:
                errors.append(f"Order {record['order_no']} / {record['size_code']}: Dispatch Qty must be between 1 and {row['pending_qty']}.")
                continue
            # Dispatch size is the order's selected size; no separate dispatch-size control is needed.
            dispatched_size = record["size_code"]
            valid.append((record["size_id"], dispatched_size, qty, dispatch_date, row["details_var"].get().strip(), self.dispatch_invoice_var.get().strip()))
        if errors:
            messagebox.showwarning("Check Dispatch Details", "Please correct these details:\n\n" + "\n".join(errors[:12]), parent=self)
            return
        if not messagebox.askyesno("Confirm Dispatch", f"Save {len(valid)} dispatch row(s) for this Party?\n\nOnly the selected quantities will be dispatched. Any remaining quantity will stay in Pending Orders.", parent=self):
            return
        try:
            with self.conn:
                for size_id, dispatched_size, qty, dt, details, invoice_number in valid:
                    self.conn.execute("INSERT INTO order_dispatches(order_size_id, dispatched_size, qty, dispatch_date, details, invoice_number) VALUES(?,?,?,?,?,?)",
                                      (size_id, dispatched_size, qty, dt, details, invoice_number))
            # Keep the date entry visually blank after saving; a blank date means today.
            self.dispatch_date_var.set("")
            self.refresh_pending_rows()
            self.refresh_dispatched_tree()
            self.refresh_order_reports()
            self.pending_notebook.select(self.pending_work_tab)
            self.dispatch_status_var.set(f"Saved {len(valid)} dispatched row(s). Unshipped quantities remain pending.")
            messagebox.showinfo("Dispatch Saved", f"Dispatch saved successfully for {len(valid)} selected row(s).\n\nThe dispatched quantities now appear in Dispatched Orders. Remaining quantities are still pending.", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Dispatch Save Failed", f"Could not save dispatch details.\n\n{exc}", parent=self)

    def refresh_dispatched_tree(self):
        if not hasattr(self, "dispatched_tree"):
            return
        selected = self.dispatched_tree.selection() if self.dispatched_tree.winfo_exists() else ()
        selected_id = selected[0] if selected else None
        self.dispatched_tree.delete(*self.dispatched_tree.get_children())
        display = self.dispatched_party_filter_var.get() if hasattr(self, "dispatched_party_filter_var") else "ALL PARTIES"
        party_id = None if display == "ALL PARTIES" else getattr(self, "dispatched_party_id_by_display", {}).get(display)
        sql = """
            SELECT p.party_name, a.agent_name, o.order_no, o.order_date, i.sr_no, i.particulars,
                   s.size_code AS order_size, d.dispatched_size, d.qty, d.dispatch_date, d.invoice_number, d.details, d.id
            FROM order_dispatches d
            JOIN order_item_sizes s ON s.id=d.order_size_id
            JOIN order_items i ON i.id=s.order_item_id
            JOIN orders o ON o.id=i.order_id
            JOIN parties p ON p.id=o.party_id
            LEFT JOIN agents a ON a.id=p.agent_id
        """
        params = []
        where = []
        if party_id:
            where.append("p.id=?")
            params.append(party_id)
        agent_filter = getattr(self, "dispatched_agent_filter_var", tk.StringVar(value="ALL AGENTS")).get().strip()
        if agent_filter and agent_filter != "ALL AGENTS":
            where.append("a.agent_name=?")
            params.append(agent_filter)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.party_name COLLATE NOCASE, d.dispatch_date DESC, o.order_no DESC, i.sr_no, d.id"
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return
        grouped = {}
        # Group records by order/item and shared dispatch metadata; quantities for each
        # size are accumulated into columns so the dispatched list stays compact.
        for row in rows:
            key = (row["party_name"], row["agent_name"] or "—", row["dispatch_date"], row["order_no"],
                   row["particulars"], row["invoice_number"] or "", row["details"] or "")
            if key not in grouped:
                grouped[key] = {"ids": [], "sizes": {"M": 0, "L": 0, "XL": 0, "XXL": 0}}
            grouped[key]["ids"].append(int(row["id"]))
            raw_size = str(row["dispatched_size"] or row["order_size"] or "").strip().upper()
            # Support values such as M, M (38), XL(42), etc.
            import re
            match = re.match(r"^(XXL|XL|L|M)\b", raw_size)
            size_key = match.group(1) if match else ""
            if size_key in grouped[key]["sizes"]:
                grouped[key]["sizes"][size_key] += int(row["qty"] or 0)
        for idx, (key, data) in enumerate(grouped.items()):
            party, agent, dispatch_date, order_no, description, invoice_number, details = key
            tag = "row_even" if idx % 2 == 0 else "row_odd"
            group_iid = "grp_" + "_".join(str(x) for x in sorted(data["ids"]))
            self.dispatched_tree.insert("", "end", iid=group_iid, values=(
                party, agent, self.show_date(dispatch_date), order_no, description,
                data["sizes"]["M"] or "—", data["sizes"]["L"] or "—", data["sizes"]["XL"] or "—", data["sizes"]["XXL"] or "—",
                invoice_number, details
            ), tags=(tag,))
        if selected_id and self.dispatched_tree.exists(selected_id):
            self.dispatched_tree.selection_set(selected_id)

    def on_dispatched_row_selected(self, _event=None):
        selected = self.dispatched_tree.selection() if hasattr(self, "dispatched_tree") else ()
        if not selected:
            return
        values = self.dispatched_tree.item(selected[0], "values")
        # Invoice Number is column index 9 in the grouped Dispatched Orders list.
        if len(values) > 9:
            self.invoice_edit_var.set(values[9] or "")

    def update_selected_dispatch_invoice(self):
        selected = self.dispatched_tree.selection() if hasattr(self, "dispatched_tree") else ()
        if not selected:
            messagebox.showwarning("Select Dispatch", "પહેલાં Dispatched Ordersની listમાંથી એક dispatch row select કરો.", parent=self)
            return
        try:
            selected_iid = selected[0]
            if not selected_iid.startswith("grp_"):
                raise ValueError("Please select a grouped dispatched order row.")
            dispatch_ids = [int(x) for x in selected_iid[4:].split("_") if x]
            if not dispatch_ids:
                raise ValueError("No dispatch records found in the selected row.")
            invoice_number = self.invoice_edit_var.get().strip()
            placeholders = ",".join("?" for _ in dispatch_ids)
            with self.conn:
                cursor = self.conn.execute(f"UPDATE order_dispatches SET invoice_number=? WHERE id IN ({placeholders})", [invoice_number, *dispatch_ids])
                if cursor.rowcount == 0:
                    raise ValueError("Selected dispatch records were not found.")
            self.refresh_dispatched_tree()
            self.refresh_order_reports()
            self.dispatch_status_var.set(f"Invoice Number updated for {cursor.rowcount} dispatch record(s).")
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Invoice Update Failed", f"Could not update Invoice Number.\n\n{exc}", parent=self)

    def return_selected_dispatch_to_pending(self):
        """Undo a mistakenly dispatched grouped row by removing its dispatch records.

        The order itself and its sizes are retained. Removing dispatch records causes
        their quantities to return to Pending Orders.
        """
        selected = self.dispatched_tree.selection() if hasattr(self, "dispatched_tree") else ()
        if not selected:
            messagebox.showwarning(
                "Select Dispatched Order",
                "પહેલાં Dispatched Ordersની listમાંથી જે order પાછો Pendingમાં લાવવો છે તે row select કરો.",
                parent=self,
            )
            return
        selected_iid = selected[0]
        if not selected_iid.startswith("grp_"):
            messagebox.showwarning("Select Dispatched Order", "કૃપા કરીને Dispatched Ordersની grouped row select કરો.", parent=self)
            return
        try:
            dispatch_ids = [int(value) for value in selected_iid[4:].split("_") if value]
            if not dispatch_ids:
                raise ValueError("Selected row has no dispatch records.")
            placeholders = ",".join("?" for _ in dispatch_ids)
            records = self.conn.execute(
                f"SELECT d.id, d.qty, o.order_no, p.party_name "
                f"FROM order_dispatches d "
                f"JOIN order_item_sizes s ON s.id=d.order_size_id "
                f"JOIN order_items i ON i.id=s.order_item_id "
                f"JOIN orders o ON o.id=i.order_id "
                f"JOIN parties p ON p.id=o.party_id "
                f"WHERE d.id IN ({placeholders})",
                dispatch_ids,
            ).fetchall()
            if not records:
                messagebox.showwarning("Dispatch Not Found", "Selected dispatch records no longer exist. Please refresh the list.", parent=self)
                self.refresh_dispatched_tree()
                return
            total_qty = sum(int(record["qty"] or 0) for record in records)
            order_numbers = sorted({str(record["order_no"]) for record in records})
            parties = sorted({str(record["party_name"]) for record in records})
            confirmed = messagebox.askyesno(
                "Return to Pending",
                "આ selected dispatched quantityને પાછી Pendingમાં લાવવી છે?\n\n"
                f"Party: {', '.join(parties)}\n"
                f"Order No.: {', '.join(order_numbers)}\n"
                f"Quantity to return: {total_qty}\n\n"
                "Confirm કરતાં પસંદ કરેલા dispatch records દૂર થશે. Order અને item details delete નહીં થાય.",
                parent=self,
            )
            if not confirmed:
                return
            with self.conn:
                cursor = self.conn.execute(f"DELETE FROM order_dispatches WHERE id IN ({placeholders})", dispatch_ids)
                if cursor.rowcount == 0:
                    raise ValueError("No dispatch records were returned to Pending.")
            self.refresh_dispatched_tree()
            self.refresh_pending_rows()
            self.refresh_order_reports()
            if hasattr(self, "refresh_dashboard"):
                self.refresh_dashboard()
            self.dispatch_status_var.set(f"Returned {cursor.rowcount} dispatch record(s) to Pending Orders.")
            messagebox.showinfo(
                "Returned to Pending",
                f"Selected dispatch quantity ({total_qty}) returned to Pending Orders successfully.\n\n"
                "Order and item details have been kept.",
                parent=self,
            )
        except (sqlite3.Error, ValueError, KeyError) as exc:
            messagebox.showerror("Return to Pending Failed", f"Could not return the selected dispatch to Pending.\n\n{exc}", parent=self)

    def build_order_reports_tab(self):
        """Order Reports submenu: Pending Order List, Agent-wise Order, SKU-wise State Sale."""
        self.reports_notebook = ttk.Notebook(self.reports_tab)
        self.reports_notebook.pack(fill="both", expand=True)
        self.pending_report_tab = ttk.Frame(self.reports_notebook, padding=8)
        self.agent_report_tab = ttk.Frame(self.reports_notebook, padding=8)
        self.sku_state_report_tab = ttk.Frame(self.reports_notebook, padding=8)
        self.reports_notebook.add(self.pending_report_tab, text="  Pending Order List  ")
        self.reports_notebook.add(self.agent_report_tab, text="  Agent Wise Order  ")
        self.reports_notebook.add(self.sku_state_report_tab, text="  SKU Wise State Sale Report  ")

        # 1. Pending Order List tab
        top = ttk.Frame(self.pending_report_tab)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="PENDING ORDER LIST", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.report_last_updated_var = tk.StringVar(value="Select a Party, Agent, and/or multiple Product Codes.")
        ttk.Label(top, textvariable=self.report_last_updated_var, foreground="#65758b").pack(side="left", padx=14)
        ttk.Button(top, text="Refresh List", style="Primary.TButton", command=self.refresh_order_reports).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Export Pending PDF", command=self.export_pending_list_pdf).pack(side="right", padx=(6, 0))

        filters = ttk.LabelFrame(self.pending_report_tab, text="Pending Order Filters", padding=8)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Party-wise Pending List:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        self.report_party_var = tk.StringVar(value="ALL PARTIES")
        self.report_party_combo = ttk.Combobox(filters, textvariable=self.report_party_var, state="readonly", width=36, values=["ALL PARTIES"])
        self.report_party_combo.grid(row=0, column=1, sticky="w", padx=(0, 18), pady=3)
        self.report_party_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_pending_list_view())
        ttk.Label(filters, text="Agent-wise Pending Parties:").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=3)
        self.report_agent_var = tk.StringVar(value="ALL AGENTS")
        self.report_agent_combo = ttk.Combobox(filters, textvariable=self.report_agent_var, state="readonly", width=28, values=["ALL AGENTS"])
        self.report_agent_combo.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=3)
        self.report_agent_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_pending_list_view())
        ttk.Label(filters, text="Multiple Product Codes / SKU (select more than one with Ctrl/Command):").grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 3))
        sku_frame = ttk.Frame(filters)
        sku_frame.grid(row=2, column=0, columnspan=4, sticky="ew")
        filters.columnconfigure(3, weight=1)
        self.report_sku_list = tk.Listbox(sku_frame, selectmode="extended", height=4, exportselection=False)
        sku_scroll = ttk.Scrollbar(sku_frame, orient="vertical", command=self.report_sku_list.yview)
        self.report_sku_list.configure(yscrollcommand=sku_scroll.set)
        self.report_sku_list.pack(side="left", fill="x", expand=True)
        sku_scroll.pack(side="right", fill="y")
        sku_actions = ttk.Frame(filters)
        sku_actions.grid(row=3, column=0, columnspan=4, sticky="w", pady=(5, 0))
        ttk.Button(sku_actions, text="Show Selected SKU Orders", command=self.refresh_pending_list_view).pack(side="left")
        ttk.Button(sku_actions, text="Clear SKU Selection", command=self.clear_report_sku_selection).pack(side="left", padx=8)
        card = self.make_card(self.pending_report_tab, "PENDING ORDER DETAILS — GROUPED BY PRODUCT WITH SIZE QTY COLUMNS")
        card.pack(fill="both", expand=True)
        columns = ("order_no", "order_date", "party", "agent", "state", "product", "m_qty", "l_qty", "xl_qty", "xxl_qty", "other_sizes", "pending_qty")
        headings = {"order_no":"Order No.", "order_date":"Order Date", "party":"Party Name", "agent":"Agent", "state":"State", "product":"Product Code / SKU", "m_qty":"M (38) Qty", "l_qty":"L (40) Qty", "xl_qty":"XL (42) Qty", "xxl_qty":"XXL (44) Qty", "other_sizes":"Other Sizes / Qty", "pending_qty":"Pending Qty"}
        widths = {"order_no":80, "order_date":95, "party":175, "agent":125, "state":120, "product":125, "m_qty":75, "l_qty":75, "xl_qty":75, "xxl_qty":75, "other_sizes":145, "pending_qty":85}
        self.pending_report_tree = self.create_tree(card, columns, headings, widths)
        self.pending_report_tree.bind("<Double-1>", lambda _e: self.export_pending_list_pdf())
        self.order_report_trees = {"pending_list": self.pending_report_tree}
        self.analytics_trees = {}
        self._pending_report_rows = []
        self._report_party_ids = {"ALL PARTIES": None}
        self._report_sku_values = []

        # 2. Agent Wise Order tab
        agent_top = ttk.Frame(self.agent_report_tab)
        agent_top.pack(fill="x", pady=(0, 8))
        ttk.Label(agent_top, text="AGENT-WISE TOTAL ORDERS", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.agent_report_status = tk.StringVar(value="Agent, party, SKU and total pieces report")
        ttk.Label(agent_top, textvariable=self.agent_report_status, foreground="#65758b").pack(side="left", padx=12)
        ttk.Button(agent_top, text="Refresh Report", style="Primary.TButton", command=self.open_agent_order_report).pack(side="right", padx=(6, 0))
        ttk.Button(agent_top, text="Export PDF", command=self.export_agent_order_report_pdf).pack(side="right")
        agent_card = self.make_card(self.agent_report_tab, "AGENT LIST — DOUBLE-CLICK AN AGENT TO VIEW ITS PARTIES")
        agent_card.pack(fill="both", expand=True)
        self.agent_report_tree = self.create_tree(agent_card, ("agent",),
            {"agent":"Agent Name"}, {"agent":520})
        self.agent_report_tree.bind("<Double-1>", self.open_agent_parties)

        # 3. SKU Wise State Sale Report tab
        sku_top = ttk.Frame(self.sku_state_report_tab)
        sku_top.pack(fill="x", pady=(0, 8))
        ttk.Label(sku_top, text="SKU-WISE TOTAL PIECES & STATE SALES", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.sku_state_report_status = tk.StringVar(value="SKU and state sales report")
        ttk.Label(sku_top, textvariable=self.sku_state_report_status, foreground="#65758b").pack(side="left", padx=12)
        ttk.Button(sku_top, text="Refresh Report", style="Primary.TButton", command=self.open_sku_state_sales_report).pack(side="right", padx=(6, 0))
        ttk.Button(sku_top, text="Export PDF", command=self.export_sku_state_sales_pdf).pack(side="right")
        sku_card = self.make_card(self.sku_state_report_tab, "PRODUCT CODE / SKU → STATE → TOTAL ORDERS / PIECES SOLD")
        sku_card.pack(fill="both", expand=True)
        self.sku_state_report_tree = self.create_tree(sku_card, ("sku", "state", "orders", "pieces"),
            {"sku":"Product Code / SKU", "state":"State", "orders":"Total Orders", "pieces":"Total Pieces Sold"},
            {"sku":240, "state":220, "orders":130, "pieces":150})

    def _open_analytics_report_window(self, title, columns, headings, widths, rows, pdf_title, pdf_name):
        """Open a report window with a preview table and A4 PDF export."""
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("1180x650")
        win.minsize(850, 450)
        win.transient(self)
        outer = ttk.Frame(win, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text=f"Rows: {len(rows)} | Generated: {datetime.now():%d-%m-%Y %H:%M}", foreground="#65758b").pack(side="left")
        ttk.Button(bar, text="Export PDF", command=lambda: self._export_order_report_pdf(pdf_title, headings, rows, pdf_name)).pack(side="right")
        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=65, anchor="center", stretch=True)
        for idx, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=("even" if idx % 2 == 0 else "odd",))
        tree.tag_configure("even", background="#ffffff")
        tree.tag_configure("odd", background="#f2f6fb")
        return win

    def open_agent_order_report(self):
        """Show only agent names; double-clicking an agent opens its linked party list."""
        try:
            sql = """SELECT a.id AS agent_id, a.agent_name AS agent
                     FROM agents a
                     WHERE EXISTS (SELECT 1 FROM parties p WHERE p.agent_id=a.id)
                     ORDER BY a.agent_name COLLATE NOCASE"""
            data = self.conn.execute(sql).fetchall()
            agent_rows = [(int(r["agent_id"]), str(r["agent"] or "").strip()) for r in data if str(r["agent"] or "").strip()]
            unassigned = self.conn.execute("SELECT 1 FROM parties WHERE agent_id IS NULL OR agent_id NOT IN (SELECT id FROM agents) LIMIT 1").fetchone()
            self.agent_report_tree.delete(*self.agent_report_tree.get_children())
            self._agent_report_rows = []
            for idx, (agent_id, name) in enumerate(agent_rows):
                self.agent_report_tree.insert("", "end", iid=f"agent_{agent_id}", values=(name,), tags=("even" if idx % 2 == 0 else "odd",))
                self._agent_report_rows.append((name,))
            if unassigned:
                self.agent_report_tree.insert("", "end", iid="agent_unassigned", values=("Direct / Unassigned",), tags=("even" if len(agent_rows) % 2 == 0 else "odd",))
                self._agent_report_rows.append(("Direct / Unassigned",))
            self.agent_report_tree.tag_configure("even", background="#ffffff")
            self.agent_report_tree.tag_configure("odd", background="#f2f6fb")
            self.agent_report_status.set(f"{len(self._agent_report_rows)} agents — double-click to view parties")
        except sqlite3.Error as exc:
            messagebox.showerror("Agent Report Failed", f"Could not build Agent-wise Order Report.\n\n{exc}", parent=self)

    def open_agent_parties(self, event=None):
        """Open the selected agent's party names; selecting a party opens its order details."""
        tree = self.agent_report_tree
        row_id = tree.identify_row(event.y) if event is not None else (tree.selection()[0] if tree.selection() else "")
        if not row_id:
            return
        try:
            if row_id == "agent_unassigned":
                agent_label = "Direct / Unassigned"
                parties = self.conn.execute("""SELECT p.id, p.party_name, p.city FROM parties p
                    WHERE p.agent_id IS NULL OR p.agent_id NOT IN (SELECT id FROM agents)
                    ORDER BY p.party_name COLLATE NOCASE, p.city COLLATE NOCASE, p.id""").fetchall()
            else:
                agent_id = int(row_id.split("_", 1)[1])
                agent = self.conn.execute("SELECT agent_name FROM agents WHERE id=?", (agent_id,)).fetchone()
                if not agent:
                    return
                agent_label = str(agent["agent_name"] or "")
                parties = self.conn.execute("""SELECT p.id, p.party_name, p.city FROM parties p
                    WHERE p.agent_id=? ORDER BY p.party_name COLLATE NOCASE, p.city COLLATE NOCASE, p.id""", (agent_id,)).fetchall()
            win = tk.Toplevel(self)
            win.title(f"Parties — {agent_label}")
            win.geometry("760x540")
            win.minsize(520, 360)
            win.transient(self)
            ttk.Label(win, text=f"PARTIES — {agent_label}", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
            ttk.Label(win, text="Click a party to open its order details.", foreground="#65758b").pack(anchor="w", padx=12, pady=(0, 8))
            wrap = ttk.Frame(win, padding=(12, 0, 12, 8)); wrap.pack(fill="both", expand=True)
            party_tree = ttk.Treeview(wrap, columns=("party",), show="headings", selectmode="browse")
            party_tree.heading("party", text="Party Name")
            party_tree.column("party", width=620, anchor="w", stretch=True)
            ybar = ttk.Scrollbar(wrap, orient="vertical", command=party_tree.yview)
            party_tree.configure(yscrollcommand=ybar.set)
            party_tree.grid(row=0, column=0, sticky="nsew"); ybar.grid(row=0, column=1, sticky="ns")
            wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
            for idx, party in enumerate(parties):
                party_tree.insert("", "end", iid=str(int(party["id"])), values=(party["party_name"] or "",), tags=("even" if idx % 2 == 0 else "odd",))
            party_tree.tag_configure("even", background="#ffffff")
            party_tree.tag_configure("odd", background="#f2f6fb")
            if not parties:
                ttk.Label(win, text="No parties linked to this agent.", foreground="#65758b").pack(anchor="w", padx=12, pady=(0, 10))
            # Selecting a party opens its saved order details immediately.
            party_tree.bind("<<TreeviewSelect>>", lambda _ev, tv=party_tree: self.open_party_order_details(tree=tv))
        except sqlite3.Error as exc:
            messagebox.showerror("Agent Parties Failed", f"Could not load parties for this agent.\n\n{exc}", parent=self)

    def export_agent_order_report_pdf(self):
        rows = getattr(self, "_agent_report_rows", [])
        self._export_order_report_pdf("2. AGENT LIST", ("Agent Name",), rows, "Shubhvastra_Agent_List.pdf")

    def open_sku_state_sales_report(self):
        """Refresh SKU-wise pieces sold by state, for comparing demand by SKU/state."""
        try:
            sql = """SELECT i.particulars AS sku, COALESCE(NULLIF(TRIM(p.state),''),'Unknown') AS state,
                            COUNT(DISTINCT o.id) AS order_count, SUM(s.ordered_qty) AS pieces
                     FROM orders o JOIN parties p ON p.id=o.party_id
                     JOIN order_items i ON i.order_id=o.id
                     JOIN order_item_sizes s ON s.order_item_id=i.id
                     WHERE COALESCE(o.cancelled,0)=0 AND COALESCE(s.cancelled,0)=0
                     GROUP BY i.particulars, state
                     ORDER BY i.particulars COLLATE NOCASE, pieces DESC, state COLLATE NOCASE"""
            data = self.conn.execute(sql).fetchall()
            rows = [(r["sku"] or "", r["state"] or "Unknown", int(r["order_count"] or 0), int(r["pieces"] or 0)) for r in data]
            self.sku_state_report_tree.delete(*self.sku_state_report_tree.get_children())
            for idx, row in enumerate(rows):
                self.sku_state_report_tree.insert("", "end", values=row, tags=("even" if idx % 2 == 0 else "odd",))
            self.sku_state_report_tree.tag_configure("even", background="#ffffff")
            self.sku_state_report_tree.tag_configure("odd", background="#f2f6fb")
            self._sku_state_report_rows = rows
            self.sku_state_report_status.set(f"{len(rows)} SKU–State rows")
        except sqlite3.Error as exc:
            messagebox.showerror("SKU Report Failed", f"Could not build SKU-wise State Sales Report.\n\n{exc}", parent=self)

    def export_sku_state_sales_pdf(self):
        rows = getattr(self, "_sku_state_report_rows", [])
        self._export_order_report_pdf("3. SKU-WISE TOTAL PIECES & STATE SALES", ("Product Code / SKU", "State", "Total Orders", "Total Pieces Sold"), rows, "Shubhvastra_SKU_State_Sales.pdf")

    def clear_report_sku_selection(self):
        if hasattr(self, "report_sku_list"):
            self.report_sku_list.selection_clear(0, "end")
            self.refresh_pending_list_view()

    def refresh_pending_list_view(self):
        """Apply party, agent and multi-SKU filters to pending-only rows."""
        if not hasattr(self, "pending_report_tree"):
            return
        party_display = self.report_party_var.get().strip() or "ALL PARTIES"
        party_id = getattr(self, "_report_party_ids", {}).get(party_display)
        agent_name = self.report_agent_var.get().strip() or "ALL AGENTS"
        selected_indices = self.report_sku_list.curselection() if hasattr(self, "report_sku_list") else ()
        selected_skus = {self.report_sku_list.get(i).split(" — ", 1)[0].strip().casefold() for i in selected_indices}
        rows = getattr(self, "_pending_report_rows", [])
        if party_id:
            rows = [r for r in rows if r["party_id"] == party_id]
        if agent_name != "ALL AGENTS":
            rows = [r for r in rows if (r["agent"] or "Direct / Unassigned").casefold() == agent_name.casefold()]
        if selected_skus:
            rows = [r for r in rows if r["product"].casefold() in selected_skus]
        self.pending_report_tree.delete(*self.pending_report_tree.get_children())
        for idx, r in enumerate(rows):
            values = (r["order_no"], r["order_date"], r["party"], r["agent"] or "—", r["state"] or "—", r["product"],
                      r["sizes"].get("M", 0) or "—", r["sizes"].get("L", 0) or "—", r["sizes"].get("XL", 0) or "—", r["sizes"].get("XXL", 0) or "—",
                      "; ".join(f"{k}: {v}" for k, v in r["other_sizes"].items() if v), r["pending_qty"])
            self.pending_report_tree.insert("", "end", values=values, tags=("row_even" if idx % 2 == 0 else "row_odd",))
        party_label = party_display if party_id else "All Parties"
        agent_label = agent_name if agent_name != "ALL AGENTS" else "All Agents"
        sku_label = f" | {len(selected_skus)} SKU selected" if selected_skus else " | All SKUs"
        self.report_last_updated_var.set(f"{len(rows)} pending product/order rows | {party_label} | {agent_label}{sku_label} | Updated {datetime.now():%d-%m-%Y %H:%M}")

    def refresh_order_reports(self):
        """Rebuild pending-order report rows from saved orders and dispatch quantities."""
        if not hasattr(self, "pending_report_tree"):
            return
        sql = """SELECT o.id AS order_id, o.order_no, o.order_date, p.id AS party_id, p.party_name, p.state,
                        a.agent_name, i.id AS item_id, i.particulars, s.size_code, s.ordered_qty,
                        COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS dispatched_qty
                 FROM orders o JOIN parties p ON p.id=o.party_id
                 LEFT JOIN agents a ON a.id=p.agent_id
                 JOIN order_items i ON i.order_id=o.id
                 JOIN order_item_sizes s ON s.order_item_id=i.id
                 WHERE COALESCE(o.cancelled,0)=0 AND COALESCE(s.cancelled,0)=0
                 ORDER BY p.party_name COLLATE NOCASE, o.order_date, o.order_no, i.sr_no, s.size_code"""
        grouped = {}
        for row in self.conn.execute(sql).fetchall():
            ordered = max(0, int(row["ordered_qty"] or 0))
            sent = max(0, int(row["dispatched_qty"] or 0))
            pending = max(0, ordered - sent)
            if pending <= 0:
                continue
            key = (int(row["order_id"]), int(row["item_id"]))
            if key not in grouped:
                grouped[key] = {"order_no":row["order_no"], "order_date":self.show_date(row["order_date"]),
                    "party_id":int(row["party_id"]), "party":row["party_name"] or "", "agent":row["agent_name"] or "Direct / Unassigned",
                    "state":row["state"] or "", "product":str(row["particulars"] or ""), "sizes":{"M":0,"L":0,"XL":0,"XXL":0}, "other_sizes":{}, "pending_qty":0}
            entry = grouped[key]
            raw = str(row["size_code"] or "").strip().upper()
            import re
            match = re.match(r"^(XXL|XL|L|M)\b", raw)
            size = match.group(1) if match else ""
            if size in entry["sizes"]:
                entry["sizes"][size] += pending
            else:
                entry["other_sizes"][raw or "Unknown"] = entry["other_sizes"].get(raw or "Unknown", 0) + pending
            entry["pending_qty"] += pending
        self._pending_report_rows = list(grouped.values())

        # Refresh party and agent choices while preserving current selections.
        old_party = getattr(self, "report_party_var", tk.StringVar(value="ALL PARTIES")).get()
        old_agent = getattr(self, "report_agent_var", tk.StringVar(value="ALL AGENTS")).get()
        party_rows = self.conn.execute("SELECT id, party_name, city, phone_number FROM parties ORDER BY party_name COLLATE NOCASE, city COLLATE NOCASE, id").fetchall()
        party_map = {"ALL PARTIES": None}
        party_values = ["ALL PARTIES"]
        for pr in party_rows:
            display = f"{pr['party_name']} — {pr['city'] or ''} — {pr['phone_number'] or ''}"
            if display in party_map:
                display += f" (ID {pr['id']})"
            party_map[display] = int(pr["id"])
            party_values.append(display)
        self._report_party_ids = party_map
        self.report_party_combo.configure(values=party_values)
        self.report_party_var.set(old_party if old_party in party_map else "ALL PARTIES")
        agent_rows = self.conn.execute("SELECT DISTINCT agent_name FROM agents WHERE TRIM(COALESCE(agent_name,''))<>'' ORDER BY agent_name COLLATE NOCASE").fetchall()
        agent_values = ["ALL AGENTS"] + [str(r[0]) for r in agent_rows]
        self.report_agent_combo.configure(values=agent_values)
        self.report_agent_var.set(old_agent if old_agent in agent_values else "ALL AGENTS")

        old_skus = set()
        if hasattr(self, "report_sku_list"):
            old_skus = {self.report_sku_list.get(i).split(" — ", 1)[0].strip().casefold() for i in self.report_sku_list.curselection()}
            self.report_sku_list.delete(0, "end")
            sku_values = sorted({r["product"] for r in self._pending_report_rows if r["product"]}, key=str.casefold)
            self._report_sku_values = sku_values
            for sku in sku_values:
                self.report_sku_list.insert("end", sku)
            for idx, sku in enumerate(sku_values):
                if sku.casefold() in old_skus:
                    self.report_sku_list.selection_set(idx)
        self.refresh_pending_list_view()
        if hasattr(self, "agent_report_tree"):
            self.open_agent_order_report()
        if hasattr(self, "sku_state_report_tree"):
            self.open_sku_state_sales_report()

    def export_pending_list_pdf(self):
        """Export the exact filtered Pending Order List to a compact A4 landscape PDF."""
        if not hasattr(self, "pending_report_tree"):
            return
        rows = [self.pending_report_tree.item(iid, "values") for iid in self.pending_report_tree.get_children()]
        path = filedialog.asksaveasfilename(parent=self, title="Export Pending Order List PDF", defaultextension=".pdf",
            initialfile="Shubhvastra_Pending_Order_List.pdf", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            if not ensure_reportlab_installed():
                raise RuntimeError("PDF library (ReportLab) is unavailable. Run install_pdf_library.bat (Windows) or ./install_pdf_library.command (Mac), then retry.")
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=7*mm, rightMargin=7*mm, topMargin=8*mm, bottomMargin=8*mm)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle("PendingListTitle", parent=styles["Title"], fontSize=13, leading=15, alignment=1)
            small = ParagraphStyle("PendingListCell", parent=styles["BodyText"], fontSize=6.3, leading=7.5, wordWrap="CJK")
            # PDF table header paragraphs need an explicit white text color; TableStyle TEXTCOLOR alone
            # does not override the text color already defined by a Paragraph's style.
            header_style = ParagraphStyle("PendingListHeader", parent=small, textColor=colors.white, fontName="Helvetica-Bold", alignment=1)
            party = self.report_party_var.get().strip()
            agent = self.report_agent_var.get().strip()
            selected_skus = [self.report_sku_list.get(i) for i in self.report_sku_list.curselection()]
            subtitle = f"Party: {party} | Agent: {agent} | SKU: {', '.join(selected_skus) if selected_skus else 'All'}"
            story = [Paragraph("SHUBHVASTRA — PENDING ORDER LIST", title_style), Paragraph(subtitle, small),
                     Paragraph(f"Generated: {datetime.now():%d-%m-%Y %H:%M}", small), Spacer(1, 3*mm)]
            headers = ["Order No.", "Order Date", "Party Name", "Agent", "State", "Product Code / SKU", "M (38) Qty", "L (40) Qty", "XL (42) Qty", "XXL (44) Qty", "Other Sizes / Qty", "Pending Qty"]
            table_data = [[Paragraph(str(h), header_style) for h in headers]]
            table_data.extend([[Paragraph(str(v if v is not None else "—"), small) for v in row] for row in rows])
            if not rows:
                table_data.append([Paragraph("No matching pending orders.", small)] + [""] * (len(headers)-1))
            avail = landscape(A4)[0] - 14*mm
            weights = [0.65,0.8,1.5,1.0,0.9,1.1,0.65,0.65,0.65,0.7,1.0,0.75]
            total = sum(weights)
            widths = [avail*w/total for w in weights]
            table = Table(table_data, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365d")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("GRID",(0,0),(-1,-1),0.35,colors.black),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f6fb")]),
                ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
                ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
            story.append(table)
            doc.build(story)
            messagebox.showinfo("PDF Saved", f"Pending Order List PDF saved successfully:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", f"Could not create Pending Order List PDF.\n\n{exc}", parent=self)

    def open_party_order_details(self, event=None, tree=None):
        tree = tree or self.order_report_trees.get("party")
        if tree is None:
            return
        row_id = tree.identify_row(event.y) if event is not None else (tree.selection()[0] if tree.selection() else "")
        if not row_id:
            return
        try:
            party_id = int(row_id)
        except (TypeError, ValueError):
            return
        party = self.conn.execute("SELECT party_name, city, state FROM parties WHERE id=?", (party_id,)).fetchone()
        if not party:
            return
        win = tk.Toplevel(self)
        win.title(f"Party Order Details — {party['party_name']}")
        win.geometry("1150x650")
        win.transient(self)
        ttk.Label(win, text=f"{party['party_name']}  |  {party['city'] or ''}  |  {party['state'] or ''}",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=10)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        specs = [
            ("dispatched", "Dispatched Orders", ("order_no", "order_date", "item", "size", "ordered", "dispatched"),
             ("Order No.", "Order Date", "Item", "Size", "Ordered Qty", "Dispatched Qty")),
            ("pending", "Pending Orders", ("order_no", "order_date", "item", "size", "ordered", "dispatched", "pending"),
             ("Order No.", "Order Date", "Item", "Size", "Ordered Qty", "Dispatched Qty", "Pending Qty")),
            ("cancelled_orders", "Cancelled Orders", ("order_no", "order_date", "item", "size", "ordered", "dispatched", "cancel_type"),
             ("Order No.", "Order Date", "Item", "Size", "Ordered Qty", "Dispatched Qty", "Cancellation")),
        ]
        trees = {}
        for key, title, cols, labels in specs:
            tab = ttk.Frame(nb, padding=8)
            nb.add(tab, text=f" {title} ")
            wrap = ttk.Frame(tab); wrap.pack(fill="both", expand=True)
            tv = ttk.Treeview(wrap, columns=cols, show="headings")
            for col, label in zip(cols, labels):
                tv.heading(col, text=label)
                tv.column(col, width=145 if col in ("item", "order_no") else 110, anchor="w")
            y = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
            x = ttk.Scrollbar(wrap, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=y.set, xscrollcommand=x.set)
            tv.grid(row=0, column=0, sticky="nsew"); y.grid(row=0, column=1, sticky="ns"); x.grid(row=1, column=0, sticky="ew")
            wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
            trees[key] = tv
        rows = self.conn.execute("""
            SELECT o.order_no, o.order_date, o.cancelled AS order_cancelled,
                   i.particulars, s.size_code, s.ordered_qty, s.cancelled AS size_cancelled,
                   COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS dispatched_qty
            FROM orders o JOIN order_items i ON i.order_id=o.id
            JOIN order_item_sizes s ON s.order_item_id=i.id
            WHERE o.party_id=?
            ORDER BY o.order_date DESC, o.order_no DESC, i.sr_no, s.size_code
        """, (party_id,)).fetchall()
        for r in rows:
            ordered = int(r["ordered_qty"] or 0)
            dispatched = min(ordered, int(r["dispatched_qty"] or 0))
            pending = max(0, ordered-dispatched)
            common = (r["order_no"], self.show_date(r["order_date"]), r["particulars"], r["size_code"], ordered, dispatched)
            if int(r["order_cancelled"] or 0):
                trees["cancelled_orders"].insert("", "end", values=common + ("Whole order cancelled",))
            elif int(r["size_cancelled"] or 0):
                trees["cancelled_orders"].insert("", "end", values=common + ("Item / size cancelled",))
            else:
                if dispatched > 0:
                    trees["dispatched"].insert("", "end", values=common)
                if pending > 0:
                    trees["pending"].insert("", "end", values=common + (pending,))

    def build_agent_tab(self):
        form = self.make_card(self.agent_tab, "AGENT MASTER — agents must be added manually")
        form.pack(fill="x", pady=(0, 10))
        self.agent_name_var = tk.StringVar()
        self.agent_phone_var = tk.StringVar()
        fields = ttk.Frame(form, style="Card.TFrame")
        fields.pack(fill="x")
        for col, (label, var) in enumerate([("Agent Name *", self.agent_name_var), ("Agent Phone Number *", self.agent_phone_var)]):
            cell = ttk.Frame(fields, style="Card.TFrame")
            cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 14, 0), pady=4)
            ttk.Label(cell, text=label).pack(anchor="w", pady=(0, 3))
            ttk.Entry(cell, textvariable=var).pack(fill="x", ipady=4)
            fields.columnconfigure(col, weight=1)
        buttons = ttk.Frame(form, style="Card.TFrame")
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Save Agent", style="Primary.TButton", command=self.save_agent).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Update Selected Agent", command=self.update_agent).pack(side="left", padx=6)
        ttk.Button(buttons, text="Delete Selected Agent", style="Danger.TButton", command=self.delete_agent).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear Form", command=self.clear_agent_form).pack(side="left", padx=6)

        listing = self.make_card(self.agent_tab, "SAVED AGENT LIST")
        listing.pack(fill="both", expand=True)
        columns = ("id", "agent_name", "phone", "party_count")
        headings = {"id":"ID", "agent_name":"Agent Name", "phone":"Agent Phone Number", "party_count":"Linked Parties"}
        widths = {"id":70, "agent_name":350, "phone":250, "party_count":140}
        self.agent_tree = self.create_tree(listing, columns, headings, widths)
        self.agent_tree.bind("<<TreeviewSelect>>", self.on_agent_row_selected)

    def build_backup_tab(self):
        about = self.make_card(self.backup_tab, "BACKUP AND RESTORE DATABASE")
        about.pack(fill="x", pady=(0, 12))
        ttk.Label(about, text="Backup creates a separate copy of Party, Agent, Order and Dispatch records. Restore replaces the current database with the selected backup file.",
                  background="#ffffff", foreground="#40536b", wraplength=1200).pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(about, style="Card.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Create Backup File", style="Primary.TButton", command=self.backup_database).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Restore Backup File", command=self.restore_database).pack(side="left", padx=8)
        self.auto_backup_status_var = tk.StringVar(value="Automatic backup is scheduled every 5 minutes.")
        ttk.Label(about, textvariable=self.auto_backup_status_var, background="#ffffff", foreground="#17633b",
                  font=("Segoe UI", 9, "bold"), wraplength=1200).pack(anchor="w", pady=(12, 0))
        safety = self.make_card(self.backup_tab, "IMPORTANT — AUTOMATIC BACKUP")
        safety.pack(fill="x")
        ttk.Label(safety, text="• The software makes an automatic SQLite backup at startup and every 5 minutes while it is open.\n• Automatic backups are stored in backups/automatic and the latest 288 snapshots (about 24 hours) are retained to limit disk usage.\n• Manual backups are retained until you remove them. Restore replaces current records; a safety backup is created first.\n• If transferring this software to another PC, close the software and copy the full folder, including party_reporting.db.",
                  background="#ffffff", foreground="#65758b", justify="left", wraplength=1200).pack(anchor="w")

    def refresh_all(self):
        self.refresh_agent_lookup()
        self.refresh_dashboard()
        self.refresh_agent_tree()
        self.on_reference_change()
        if hasattr(self, "order_party_combo"):
            self.refresh_order_party_lookup()
        if hasattr(self, "pending_party_combo"):
            self.refresh_pending_party_lookup()
            if self.pending_party_var.get().strip() in getattr(self, "pending_party_id_by_display", {}):
                self.refresh_pending_rows()
        if hasattr(self, "dispatched_tree"):
            self.refresh_dispatched_tree()
        if hasattr(self, "order_report_trees"):
            self.refresh_order_reports()

    def refresh_agent_lookup(self):
        rows = self.conn.execute("SELECT id, agent_name, phone_number FROM agents ORDER BY agent_name COLLATE NOCASE").fetchall()
        self.agent_id_by_name = {row["agent_name"]: row["id"] for row in rows}
        self.agent_phone_by_name = {row["agent_name"]: row["phone_number"] for row in rows}
        self.agent_name_by_id = {row["id"]: row["agent_name"] for row in rows}
        if hasattr(self, "party_widgets") and "agent" in self.party_widgets:
            names = list(self.agent_id_by_name.keys())
            self.party_widgets["agent"]["values"] = names
            current = self.party_vars["agent"].get()
            if current not in names:
                self.party_vars["agent"].set("")
                self.party_vars["agent_phone"].set("")

    def refresh_dashboard(self):
        if not hasattr(self, "party_tree"):
            return
        selected = self.party_tree.selection()
        selected_id = selected[0] if selected else None
        self.party_tree.delete(*self.party_tree.get_children())
        search = self.dashboard_search_var.get().strip().casefold()
        ref_filter = self.dashboard_filter_var.get()
        rows = self.conn.execute("""
            SELECT p.*, a.agent_name AS agent_name
            FROM parties p LEFT JOIN agents a ON a.id = p.agent_id
            ORDER BY p.party_name COLLATE NOCASE, p.id
        """).fetchall()
        visible = 0
        for p in rows:
            if ref_filter != "ALL" and p["reference"] != ref_filter:
                continue
            searchable = " ".join(str(p[k] or "") for k in ["party_name", "phone_number", "address", "city", "state", "gst_number", "reference", "transport_details", "transport_gst_number", "agent_name"]).casefold()
            if search and search not in searchable:
                continue
            row_tag = "row_even" if visible % 2 == 0 else "row_odd"
            self.party_tree.insert("", "end", iid=str(p["id"]), values=(
                p["party_name"], p["phone_number"], p["address"], p["city"], p["state"],
                p["gst_number"], p["reference"], p["agent_name"] or "—", p["transport_details"], p["transport_gst_number"]
            ), tags=(row_tag,))
            visible += 1
        self.kpi_parties.set(str(self.conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]))
        self.kpi_agents.set(str(self.conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]))
        self.kpi_agent_linked.set(str(self.conn.execute("SELECT COUNT(*) FROM parties WHERE reference='AGENT' AND agent_id IS NOT NULL").fetchone()[0]))
        self.refresh_order_kpis()
        if selected_id and self.party_tree.exists(selected_id):
            self.party_tree.selection_set(selected_id)
        if hasattr(self, "status_var"):
            self.status_var.set(f"Showing {visible} of {len(rows)} saved parties. Data saves automatically to party_reporting.db.")

    def refresh_order_kpis(self):
        """Update live order/dispatch cards without counting item-size joins as orders."""
        if not hasattr(self, "order_kpi_vars"):
            return
        row = self.conn.execute("""
            SELECT COUNT(DISTINCT o.id) AS orders, COUNT(DISTINCT o.id) AS bills,
                   COALESCE(SUM(s.ordered_qty),0) AS ordered_pieces,
                   COALESCE(SUM(MIN(s.ordered_qty, COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0))),0) AS dispatched_pieces,
                   COALESCE(SUM(MAX(0, s.ordered_qty-COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0))),0) AS pending_pieces
            FROM orders o JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
            WHERE COALESCE(o.cancelled,0)=0
        """).fetchone()
        status = self.conn.execute("""
            SELECT o.id, SUM(s.ordered_qty) AS ordered,
                   SUM(MIN(s.ordered_qty, COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0))) AS dispatched
            FROM orders o JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
            WHERE COALESCE(o.cancelled,0)=0
            GROUP BY o.id
        """).fetchall()
        pending = partial = complete = 0
        for r in status:
            ordered, sent = int(r["ordered"] or 0), int(r["dispatched"] or 0)
            if sent <= 0: pending += 1
            elif sent < ordered: partial += 1
            else: complete += 1
        vals = {"bills": row["bills"], "orders": row["orders"], "pending": pending, "partial": partial, "dispatched": complete,
                "pending_pieces": row["pending_pieces"], "dispatched_pieces": row["dispatched_pieces"]}
        for key, value in vals.items(): self.order_kpi_vars[key].set(f"{int(value or 0):,}")

    def refresh_agent_tree(self):
        if not hasattr(self, "agent_tree"):
            return
        current = self.agent_tree.selection()
        selected_id = current[0] if current else None
        self.agent_tree.delete(*self.agent_tree.get_children())
        rows = self.conn.execute("""
            SELECT a.id, a.agent_name, a.phone_number, COUNT(p.id) AS party_count
            FROM agents a LEFT JOIN parties p ON p.agent_id = a.id
            GROUP BY a.id ORDER BY a.agent_name COLLATE NOCASE
        """).fetchall()
        for a in rows:
            self.agent_tree.insert("", "end", iid=str(a["id"]), values=(a["id"], a["agent_name"], a["phone_number"], a["party_count"]))
        if selected_id and self.agent_tree.exists(selected_id):
            self.agent_tree.selection_set(selected_id)

    def on_reference_change(self, _event=None):
        if not hasattr(self, "party_vars") or not hasattr(self, "agent_detail_frame"):
            return
        if self.party_vars["reference"].get().strip() == "AGENT":
            self.agent_detail_frame.pack(fill="x", pady=(3, 2))
            self.refresh_agent_lookup()
        else:
            self.agent_detail_frame.pack_forget()
            self.party_vars["agent"].set("")
            self.party_vars["agent_phone"].set("")

    def on_agent_selected(self, _event=None):
        name = self.party_vars["agent"].get().strip()
        self.party_vars["agent_phone"].set(self.agent_phone_by_name.get(name, ""))

    @staticmethod
    def nonempty(value):
        return bool(value and str(value).strip())

    def get_party_values(self, show_messages=True):
        fields = {
            "party_name": "Party Name", "phone_number": "Phone Number", "address": "Address", "city": "City",
            "state": "State", "gst_number": "Party GST Number", "reference": "Reference",
            "transport_details": "Transport Details", "transport_gst_number": "Transport GST Number"
        }
        values = {key: self.party_vars[key].get().strip() for key in fields}
        missing = [label for key, label in fields.items() if not self.nonempty(values[key])]
        if missing:
            if show_messages:
                messagebox.showwarning("Required Details", "Please fill all required fields:\n\n" + "\n".join("• " + x for x in missing), parent=self)
            return None
        if values["reference"] not in REFERENCES:
            if show_messages:
                messagebox.showwarning("Reference Required", "Please select a valid Reference.", parent=self)
            return None
        agent_id = None
        if values["reference"] == "AGENT":
            agent_name = self.party_vars["agent"].get().strip()
            agent_id = self.agent_id_by_name.get(agent_name)
            if not agent_name or agent_id is None:
                if show_messages:
                    messagebox.showwarning("Agent Required", "Reference = AGENT છે. પહેલાં Agent Masterમાં Agent ઉમેરો અને પછી Agent પસંદ કરો.", parent=self)
                return None
        values["agent_id"] = agent_id
        return values

    def duplicate_party_exists(self, values, exclude_id=None):
        """Duplicate only when name, phone, city and state all match (case/space insensitive)."""
        rows = self.conn.execute("SELECT id, party_name, phone_number, city, state FROM parties").fetchall()
        norm = lambda v: " ".join(str(v or "").strip().casefold().split())
        target = tuple(norm(values[k]) for k in ("party_name", "phone_number", "city", "state"))
        for row in rows:
            if exclude_id is not None and int(row["id"]) == int(exclude_id):
                continue
            existing = tuple(norm(row[k]) for k in ("party_name", "phone_number", "city", "state"))
            if existing == target:
                return row
        return None

    def save_party(self):
        if self.party_form_mode != "new":
            messagebox.showinfo("View Only", "To create a Party, click + Add Party first.", parent=self)
            return
        values = self.get_party_values()
        if values is None:
            return
        duplicate = self.duplicate_party_exists(values)
        if duplicate:
            messagebox.showwarning("Duplicate Party", f"આ Party પહેલેથી છે: {duplicate['party_name']} — {duplicate['city']} — {duplicate['phone_number']}. Name, phone, city અને state ચારેય same હોય તો ફરી add કરી શકાતી નથી.", parent=self)
            return
        try:
            with self.conn:
                cur = self.conn.execute("""
                    INSERT INTO parties (party_name, phone_number, address, city, state, gst_number, reference, transport_details, transport_gst_number, agent_id)
                    VALUES (:party_name, :phone_number, :address, :city, :state, :gst_number, :reference, :transport_details, :transport_gst_number, :agent_id)
                """, values)
                new_id = cur.lastrowid
            self.clear_party_form()
            self.refresh_all()
            self.notebook.select(self.dashboard_tab)
            messagebox.showinfo("Saved", "Party saved successfully and shown in Party List.", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Save Failed", f"Could not save Party.\n\n{exc}", parent=self)

    def update_party(self):
        if self.party_form_mode != "edit":
            messagebox.showinfo("View Only", "Click Edit before changing Party details.", parent=self)
            return
        if self.selected_party_id is None:
            messagebox.showinfo("Select Party", "Dashboardમાં Party select કરીને Edit Selected દબાવો.", parent=self)
            return
        values = self.get_party_values()
        if values is None:
            return
        duplicate = self.duplicate_party_exists(values, exclude_id=self.selected_party_id)
        if duplicate:
            messagebox.showwarning("Duplicate Party", f"બીજી Partyમાં Name, phone, city અને state ચારેય same છે: {duplicate['party_name']} — {duplicate['city']} — {duplicate['phone_number']}.", parent=self)
            return
        values["id"] = self.selected_party_id
        try:
            with self.conn:
                self.conn.execute("""
                    UPDATE parties SET party_name=:party_name, phone_number=:phone_number, address=:address,
                    city=:city, state=:state, gst_number=:gst_number, reference=:reference,
                    transport_details=:transport_details, transport_gst_number=:transport_gst_number,
                    agent_id=:agent_id WHERE id=:id
                """, values)
            updated_id = self.selected_party_id
            self.refresh_all()
            self.load_party_details(updated_id, mode="view", switch_tab=False)
            self.notebook.select(self.party_tab)
            if self.party_tree.exists(str(updated_id)):
                self.party_tree.selection_set(str(updated_id))
                self.party_tree.see(str(updated_id))
            messagebox.showinfo("Updated", "Party details saved successfully. The details are now in View Only mode.", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Update Failed", f"Could not update Party.\n\n{exc}", parent=self)

    def set_party_form_mode(self, mode):
        """Toggle the Party Details form between view-only, edit and new modes."""
        self.party_form_mode = mode
        view_only = mode == "view"
        editable = mode in ("new", "edit")

        for key, widget in self.party_widgets.items():
            if key in ("reference", "agent"):
                # Disabled in view mode so the displayed value cannot be changed accidentally.
                try:
                    widget.configure(state="disabled" if view_only else "readonly")
                except tk.TclError:
                    pass
            elif key == "agent_phone":
                # The phone comes from Agent Master and is never manually editable.
                try:
                    widget.configure(state="readonly")
                except tk.TclError:
                    pass
            else:
                try:
                    widget.configure(state="readonly" if view_only else "normal")
                except tk.TclError:
                    pass

        for button in (self.save_new_party_button, self.clear_party_button, self.edit_party_button,
                       self.save_changes_button, self.cancel_party_button, self.delete_detail_party_button,
                       self.back_to_list_button):
            button.pack_forget()

        if mode == "view":
            self.party_form_status_var.set("VIEW ONLY — Click Edit to make changes")
            self.edit_party_button.pack(side="left", padx=(0, 6))
            self.delete_detail_party_button.pack(side="left", padx=6)
            self.back_to_list_button.pack(side="left", padx=6)
        elif mode == "edit":
            self.party_form_status_var.set("EDIT MODE — Save Changes to keep your edits, or Cancel to discard them")
            self.save_changes_button.pack(side="left", padx=(0, 6))
            self.cancel_party_button.pack(side="left", padx=6)
            self.back_to_list_button.pack(side="left", padx=6)
        else:
            self.party_form_status_var.set("NEW PARTY — Enter details, then save")
            self.save_new_party_button.pack(side="left", padx=(0, 6))
            self.clear_party_button.pack(side="left", padx=6)
            self.back_to_list_button.pack(side="left", padx=6)

        # Keep AGENT selection logic correct after changing widget states.
        self.on_reference_change()

    def new_party(self):
        self.clear_party_form()
        self.set_party_form_mode("new")
        self.notebook.select(self.party_tab)
        self.party_widgets["party_name"].focus_set()

    def load_party_details(self, party_id, mode="view", switch_tab=True):
        row = self.conn.execute(
            "SELECT p.*, a.agent_name, a.phone_number AS agent_phone FROM parties p "
            "LEFT JOIN agents a ON a.id=p.agent_id WHERE p.id=?", (party_id,)
        ).fetchone()
        if not row:
            messagebox.showerror("Not Found", "Selected Party could not be found.", parent=self)
            self.refresh_dashboard()
            return False

        self.selected_party_id = int(party_id)
        self.last_viewed_party_id = int(party_id)
        for key in ["party_name", "phone_number", "address", "city", "state", "gst_number",
                    "reference", "transport_details", "transport_gst_number"]:
            self.party_vars[key].set(row[key] or "")
        self.party_vars["agent"].set(row["agent_name"] or "")
        self.party_vars["agent_phone"].set(row["agent_phone"] or "")
        self.set_party_form_mode(mode)
        # Reference change can refresh Agent choices; then restore the saved linked Agent values.
        self.party_vars["agent"].set(row["agent_name"] or "")
        self.party_vars["agent_phone"].set(row["agent_phone"] or "")
        if switch_tab:
            self.notebook.select(self.party_tab)
        return True

    def view_selected_party(self):
        selection = self.party_tree.selection()
        if not selection:
            messagebox.showinfo("Select Party", "Please select a Party from the Party List first.", parent=self)
            return
        try:
            party_id = int(selection[0])
        except ValueError:
            return
        self.load_party_details(party_id, mode="view")

    def on_dashboard_row_click(self, event):
        row_id = self.party_tree.identify_row(event.y)
        if not row_id:
            return
        # Defer until the Treeview's own mouse handler has completed selection.
        self.after_idle(lambda selected_id=row_id: self._open_clicked_party(selected_id))

    def _open_clicked_party(self, party_id):
        if self.party_tree.exists(str(party_id)):
            self.party_tree.selection_set(str(party_id))
            self.party_tree.focus(str(party_id))
            self.load_party_details(int(party_id), mode="view")

    def start_edit_party(self):
        if self.selected_party_id is None:
            messagebox.showinfo("Select Party", "Please select a Party from Party List first.", parent=self)
            return
        if self.party_form_mode == "view":
            self.set_party_form_mode("edit")
            self.party_widgets["party_name"].focus_set()

    def cancel_party_changes(self):
        if self.party_form_mode == "edit" and self.selected_party_id is not None:
            if not messagebox.askyesno("Discard Changes", "Discard unsaved changes and return to View Only mode?", parent=self):
                return
            self.load_party_details(self.selected_party_id, mode="view", switch_tab=False)
        else:
            self.clear_party_form()
            self.set_party_form_mode("new")

    def back_to_party_list(self):
        if self.party_form_mode == "edit":
            if not messagebox.askyesno("Discard Changes", "You have unsaved changes. Discard them and return to Party List?", parent=self):
                return
            if self.selected_party_id is not None:
                self.load_party_details(self.selected_party_id, mode="view", switch_tab=False)
            else:
                self.clear_party_form()
                self.set_party_form_mode("new")
        self.notebook.select(self.dashboard_tab)

    def delete_party(self):
        selection = self.party_tree.selection()
        if selection:
            try:
                self.selected_party_id = int(selection[0])
            except ValueError:
                pass
        if self.selected_party_id is None:
            messagebox.showinfo("Select Party", "Please select a Party from the Dashboard list first.", parent=self)
            return
        row = self.conn.execute("SELECT party_name FROM parties WHERE id=?", (self.selected_party_id,)).fetchone()
        if not row:
            messagebox.showerror("Not Found", "Selected Party could not be found.", parent=self)
            self.selected_party_id = None
            self.refresh_dashboard()
            return
        linked_orders = self.conn.execute("SELECT COUNT(*) FROM orders WHERE party_id=?", (self.selected_party_id,)).fetchone()[0]
        if linked_orders:
            messagebox.showwarning("Party Has Orders", f"Party '{row['party_name']}' has {linked_orders} saved order(s) and cannot be deleted. Keep this Party record so order and dispatch history remain correct.", parent=self)
            return
        if not messagebox.askyesno("Confirm Delete", f"Delete Party '{row['party_name']}'? This cannot be undone.", parent=self):
            return
        with self.conn:
            self.conn.execute("DELETE FROM parties WHERE id=?", (self.selected_party_id,))
        self.clear_party_form()
        self.refresh_all()
        self.notebook.select(self.dashboard_tab)
        messagebox.showinfo("Deleted", "Party deleted successfully.", parent=self)

    def clear_party_form(self):
        self.selected_party_id = None
        self.last_viewed_party_id = None
        for var in self.party_vars.values():
            var.set("")
        self.agent_detail_frame.pack_forget()
        if hasattr(self, "party_tree"):
            for item in self.party_tree.selection():
                self.party_tree.selection_remove(item)
        if hasattr(self, "save_new_party_button"):
            self.set_party_form_mode("new")

    def agent_values(self):
        name = self.agent_name_var.get().strip()
        phone = self.agent_phone_var.get().strip()
        if not name or not phone:
            messagebox.showwarning("Required Details", "Agent Name અને Agent Phone Number બંને ભરવા જરૂરી છે.", parent=self)
            return None
        return name, phone

    def save_agent(self):
        values = self.agent_values()
        if values is None:
            return
        try:
            with self.conn:
                self.conn.execute("INSERT INTO agents (agent_name, phone_number) VALUES (?, ?)", values)
            self.clear_agent_form()
            self.refresh_all()
            messagebox.showinfo("Saved", "Agent saved successfully and now appears in Agent List.", parent=self)
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate Agent", "આ Agent Name પહેલેથી હાજર છે. અલગ નામ આપો અથવા હાલનો Agent Update કરો.", parent=self)

    def update_agent(self):
        if self.selected_agent_id is None:
            messagebox.showinfo("Select Agent", "Agent Listમાંથી Agent select કરો.", parent=self)
            return
        values = self.agent_values()
        if values is None:
            return
        try:
            with self.conn:
                self.conn.execute("UPDATE agents SET agent_name=?, phone_number=? WHERE id=?", (*values, self.selected_agent_id))
            self.clear_agent_form()
            self.refresh_all()
            messagebox.showinfo("Updated", "Agent details updated successfully.", parent=self)
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate Agent", "આ Agent Name પહેલેથી હાજર છે. અલગ નામ આપો.", parent=self)

    def delete_agent(self):
        selection = self.agent_tree.selection()
        if selection:
            try:
                self.selected_agent_id = int(selection[0])
            except ValueError:
                pass
        if self.selected_agent_id is None:
            messagebox.showinfo("Select Agent", "Agent Listમાંથી Agent select કરો.", parent=self)
            return
        count = self.conn.execute("SELECT COUNT(*) FROM parties WHERE agent_id=?", (self.selected_agent_id,)).fetchone()[0]
        if count:
            messagebox.showwarning("Agent Has Parties", f"આ Agent સાથે {count} Party જોડાયેલી છે. પહેલાં Partyનું Agent બદલો અથવા Reference બદલો.", parent=self)
            return
        if not messagebox.askyesno("Confirm Delete", "Delete selected Agent? This cannot be undone.", parent=self):
            return
        with self.conn:
            self.conn.execute("DELETE FROM agents WHERE id=?", (self.selected_agent_id,))
        self.clear_agent_form()
        self.refresh_all()
        messagebox.showinfo("Deleted", "Agent deleted successfully.", parent=self)

    def clear_agent_form(self):
        self.selected_agent_id = None
        self.agent_name_var.set("")
        self.agent_phone_var.set("")
        for item in self.agent_tree.selection():
            self.agent_tree.selection_remove(item)

    def on_agent_row_selected(self, _event=None):
        selection = self.agent_tree.selection()
        if not selection:
            return
        try:
            self.selected_agent_id = int(selection[0])
        except ValueError:
            return
        row = self.conn.execute("SELECT * FROM agents WHERE id=?", (self.selected_agent_id,)).fetchone()
        if row:
            self.agent_name_var.set(row["agent_name"])
            self.agent_phone_var.set(row["phone_number"])

    def download_sample_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Save Party CSV Sample", defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")], initialfile="party_import_sample.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                csv.writer(handle).writerow(CSV_HEADERS)
            messagebox.showinfo("Sample Ready", f"CSV sample file saved successfully:\n{path}\n\nFill the rows below the header, then use Import CSV.", parent=self)
        except OSError as exc:
            messagebox.showerror("Sample Failed", f"Could not create sample CSV.\n\n{exc}", parent=self)

    def export_party_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export All Parties", defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")], initialfile="party_export.csv")
        if not path:
            return
        rows = self.conn.execute("""
            SELECT p.id, p.party_name, p.phone_number, p.address, p.city, p.state,
                   p.gst_number, p.reference, p.transport_details, p.transport_gst_number,
                   a.agent_name
            FROM parties p LEFT JOIN agents a ON a.id=p.agent_id
            ORDER BY p.party_name COLLATE NOCASE, p.id
        """).fetchall()
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(CSV_HEADERS)
                for row in rows:
                    writer.writerow([row["id"], row["party_name"], row["phone_number"], row["address"], row["city"], row["state"],
                                     row["gst_number"], row["reference"], row["transport_details"], row["transport_gst_number"], row["agent_name"] or ""])
            messagebox.showinfo("Export Complete", f"Exported {len(rows)} Party record(s) to:\n{path}", parent=self)
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not write CSV file.\n\n{exc}", parent=self)

    @staticmethod
    def normalize_header(value):
        return " ".join((value or "").replace("\ufeff", "").strip().casefold().split())

    @staticmethod
    def decode_csv_file(path):
        """Read CSV exported from Excel or other common Windows tools.

        Excel may save CSV as UTF-8, UTF-8 with BOM, UTF-16, or ANSI/Windows-1252.
        Byte 0x95, for example, is a bullet character in Windows-1252 but is not
        valid as a standalone UTF-8 byte. Try BOM-specific decoding first, then
        UTF-8, Windows-1252, and finally Latin-1 so ordinary CSV files can be read.
        """
        raw = Path(path).read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    @staticmethod
    def detect_csv_dialect(text):
        """Detect comma or semicolon delimiters commonly used by Excel locales."""
        try:
            return csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            return csv.excel

    def import_party_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import Parties from CSV",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            csv_text = self.decode_csv_file(path)
            dialect = self.detect_csv_dialect(csv_text)
            reader = csv.DictReader(io.StringIO(csv_text, newline=""), dialect=dialect)
            if not reader.fieldnames:
                messagebox.showwarning("Empty File", "CSV fileમાં column headings નથી.", parent=self)
                return
            header_map = {self.normalize_header(h): h for h in reader.fieldnames}
            missing_headers = [h for h in CSV_HEADERS[1:] if self.normalize_header(h) not in header_map]
            if missing_headers:
                messagebox.showerror("Wrong CSV Format", "આ columns મળ્યા નથી:\n\n" + "\n".join(missing_headers) + "\n\nParty Detailsમાંથી Download Sample CSV વાપરો.", parent=self)
                return
            raw_rows = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc:
            messagebox.showerror("Import Failed", f"Could not read CSV file.\n\n{exc}", parent=self)
            return

        if not raw_rows:
            messagebox.showinfo("No Data", "CSVમાં header સિવાય કોઈ Party data નથી.", parent=self)
            return

        agents = self.conn.execute("SELECT id, agent_name FROM agents").fetchall()
        agent_ids = {r["agent_name"].casefold(): r["id"] for r in agents}
        prepared, errors = [], []
        for line_no, raw in enumerate(raw_rows, start=2):
            row = {key: (raw.get(header_map.get(self.normalize_header(key), "")) or "").strip() for key in CSV_HEADERS}
            party_id_text = row["Party ID"]
            missing = [key for key in REQUIRED_CSV_FIELDS if not row[key]]
            ref = row["Reference"].upper().strip()
            if missing:
                errors.append(f"Row {line_no}: Missing {', '.join(missing)}")
                continue
            if ref not in REFERENCES:
                errors.append(f"Row {line_no}: Invalid Reference '{row['Reference']}'")
                continue
            if ref == "AGENT":
                agent_name = row["Agent Name"].strip()
                agent_id = agent_ids.get(agent_name.casefold()) if agent_name else None
                if agent_id is None:
                    errors.append(f"Row {line_no}: Agent '{agent_name or '(blank)'}' not found in Agent Master. Add Agent manually first.")
                    continue
            else:
                agent_id = None
            party_id = None
            if party_id_text:
                try:
                    party_id = int(party_id_text)
                    exists = self.conn.execute("SELECT 1 FROM parties WHERE id=?", (party_id,)).fetchone()
                    if not exists:
                        errors.append(f"Row {line_no}: Party ID {party_id} does not exist. Leave Party ID blank to add a new Party.")
                        continue
                except ValueError:
                    errors.append(f"Row {line_no}: Party ID must be blank or a number.")
                    continue
            prepared.append({
                "id": party_id, "party_name": row["Party Name"], "phone_number": row["Phone Number"],
                "address": row["Address"], "city": row["City"], "state": row["State"],
                "gst_number": row["Party GST Number"], "reference": ref,
                "transport_details": row["Transport Details"], "transport_gst_number": row["Transport GST Number"],
                "agent_id": agent_id,
            })

        inserted = updated = 0
        try:
            with self.conn:
                for item in prepared:
                    if item["id"] is None:
                        self.conn.execute("""
                            INSERT INTO parties (party_name, phone_number, address, city, state, gst_number, reference, transport_details, transport_gst_number, agent_id)
                            VALUES (:party_name, :phone_number, :address, :city, :state, :gst_number, :reference, :transport_details, :transport_gst_number, :agent_id)
                        """, item)
                        inserted += 1
                    else:
                        self.conn.execute("""
                            UPDATE parties SET party_name=:party_name, phone_number=:phone_number, address=:address,
                            city=:city, state=:state, gst_number=:gst_number, reference=:reference,
                            transport_details=:transport_details, transport_gst_number=:transport_gst_number, agent_id=:agent_id
                            WHERE id=:id
                        """, item)
                        updated += 1
        except sqlite3.Error as exc:
            messagebox.showerror("Import Failed", f"Database did not accept the CSV. No import was completed.\n\n{exc}", parent=self)
            return
        self.clear_party_form()
        self.refresh_all()
        self.notebook.select(self.dashboard_tab)
        summary = f"Import complete.\n\nNew Parties added: {inserted}\nExisting Parties updated by Party ID: {updated}\nRows skipped due to errors: {len(errors)}\n\nExisting Parties not included in the CSV have been kept. Agent Master was not changed."
        if errors:
            summary += "\n\nFirst row errors:\n" + "\n".join(errors[:12])
            if len(errors) > 12:
                summary += f"\n...and {len(errors) - 12} more error(s)."
        messagebox.showinfo("Import Summary", summary, parent=self)

    def schedule_automatic_backup(self):
        """Schedule the next automatic snapshot five minutes from now."""
        try:
            if self.winfo_exists():
                self._auto_backup_after_id = self.after(self.AUTO_BACKUP_INTERVAL_MS, self._automatic_backup_tick)
        except tk.TclError:
            self._auto_backup_after_id = None

    def _automatic_backup_tick(self):
        self.create_automatic_backup()
        self.schedule_automatic_backup()

    def create_automatic_backup(self):
        """Make a consistent SQLite snapshot without interrupting the user with popups."""
        backup_dir = BASE_DIR / "backups" / "automatic"
        temp_path = None
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_path = backup_dir / f"auto_backup_{stamp}.db"
            temp_path = backup_dir / f".auto_backup_{stamp}.tmp"
            target = sqlite3.connect(str(temp_path))
            try:
                self.conn.backup(target)
                target.commit()
            finally:
                target.close()
            os.replace(temp_path, final_path)
            snapshots = sorted(backup_dir.glob("auto_backup_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
            for old_path in snapshots[self.AUTO_BACKUP_KEEP_COUNT:]:
                try:
                    old_path.unlink()
                except OSError:
                    pass
            if hasattr(self, "auto_backup_status_var"):
                self.auto_backup_status_var.set(f"Automatic backup ACTIVE — last saved {datetime.now():%d-%m-%Y %H:%M:%S}. Latest snapshots are in: backups/automatic")
            try:
                log_path = backup_dir / "auto_backup_log.txt"
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | OK | {final_path.name}\n")
            except OSError:
                pass
            return final_path
        except (OSError, sqlite3.Error) as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if hasattr(self, "auto_backup_status_var"):
                self.auto_backup_status_var.set(f"Automatic backup WARNING — {datetime.now():%d-%m-%Y %H:%M:%S}: {exc}")
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                with (backup_dir / "auto_backup_log.txt").open("a", encoding="utf-8") as log:
                    log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | ERROR | {exc}\n")
            except OSError:
                pass
            return None

    def backup_database(self):
        path = filedialog.asksaveasfilename(parent=self, title="Save Database Backup", defaultextension=".db",
                                            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
                                            initialfile=f"party_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
        if not path:
            return
        if Path(path).resolve() == DB_PATH.resolve():
            messagebox.showerror("Invalid Location", "Backup file cannot replace the active database file.", parent=self)
            return
        try:
            target = sqlite3.connect(path)
            try:
                self.conn.backup(target)
            finally:
                target.close()
            messagebox.showinfo("Backup Complete", f"Party, Agent, Order and Dispatch data backed up to:\n{path}", parent=self)
        except sqlite3.Error as exc:
            messagebox.showerror("Backup Failed", f"Could not create backup.\n\n{exc}", parent=self)

    def restore_database(self):
        path = filedialog.askopenfilename(parent=self, title="Select Backup File to Restore",
                                          filetypes=[("SQLite database", "*.db *.sqlite *.sqlite3"), ("All files", "*.*")])
        if not path:
            return
        source_path = Path(path).resolve()
        if source_path == DB_PATH.resolve():
            messagebox.showinfo("Already Active", "The selected file is the database currently in use.", parent=self)
            return
        try:
            source = sqlite3.connect(source_path)
            try:
                table_names = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"parties", "agents"}.issubset(table_names):
                    messagebox.showerror("Invalid Backup", "This file does not contain both Party and Agent tables.", parent=self)
                    return
                party_cols = {r[1] for r in source.execute("PRAGMA table_info(parties)")}
                agent_cols = {r[1] for r in source.execute("PRAGMA table_info(agents)")}
                if not {"id", "party_name", "phone_number", "address", "city", "state", "gst_number", "reference", "transport_details", "transport_gst_number", "agent_id"}.issubset(party_cols) or not {"id", "agent_name", "phone_number"}.issubset(agent_cols):
                    messagebox.showerror("Invalid Backup", "The selected database is not compatible with this version of the software.", parent=self)
                    return
                if not messagebox.askyesno("Confirm Restore", "Restore this backup?\n\nCurrent Party, Agent, Order and Dispatch data will be replaced. A safety backup of the current database will be created automatically first.", parent=self):
                    return
                backup_dir = BASE_DIR / "backups"
                backup_dir.mkdir(exist_ok=True)
                safety_path = backup_dir / f"before_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
                safety = sqlite3.connect(safety_path)
                try:
                    self.conn.backup(safety)
                finally:
                    safety.close()
                source.backup(self.conn)
            finally:
                source.close()
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.create_tables()
            self.selected_party_id = None
            self.selected_agent_id = None
            self.clear_party_form()
            self.clear_agent_form()
            self.refresh_all()
            messagebox.showinfo("Restore Complete", f"Backup restored successfully.\n\nSafety backup saved at:\n{safety_path}", parent=self)
        except (OSError, sqlite3.Error) as exc:
            messagebox.showerror("Restore Failed", f"Could not restore database.\n\n{exc}", parent=self)

    def on_close(self):
        try:
            pending_after = getattr(self, "_auto_backup_after_id", None)
            if pending_after:
                try:
                    self.after_cancel(pending_after)
                except tk.TclError:
                    pass
            self.create_automatic_backup()
            self.conn.close()
        finally:
            self.destroy()


def main():
    try:
        app = PartyReportingApp()
        app.mainloop()
    except Exception as exc:
        import traceback
        error_text = traceback.format_exc()
        log_path = BASE_DIR / "startup_error.txt"
        try:
            log_path.write_text(error_text, encoding="utf-8")
        except OSError:
            pass
        print("\nPARTY MANAGEMENT DASHBOARD STARTUP ERROR\n")
        print(error_text)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Party Management Dashboard - Startup Error",
                                 f"The software could not start.\n\n{exc}\n\nError details saved to:\n{log_path}", parent=root)
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
