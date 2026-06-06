import customtkinter as ctk
import tkintermapview
import threading
import os
from tkinter import filedialog, messagebox
from datetime import datetime
import sys
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import polyline as _polyline_lib
    _HAS_POLYLINE = True
except ImportError:
    _HAS_POLYLINE = False

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.components import DestinationList, ResultCard
from utils import config_manager, data_importer, history_manager
from api import maps_engine, openroute_engine, nominatim_engine

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAP_CACHE = os.path.join(_ROOT, ".map_cache.db")

_TILE_SERVERS = {
    "Voyager":        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "Light":          "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "Dark":           "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "Standard (OSM)": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

_PROVIDER_NAMES = ["Google Maps", "OpenRouteService", "Free (Nominatim)"]
# Migrate old config values that used internal identifiers
_PROVIDER_LEGACY = {
    "google": "Google Maps",
    "openrouteservice": "OpenRouteService",
    "free": "Free (Nominatim)",
}


def create_circle_marker_icon(text, bg_color="#3498db", size=28):
    # Create an image with transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Main circle
    draw.ellipse([2, 2, size - 3, size - 3], fill=bg_color, outline="white", width=2)
    
    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except IOError:
        font = ImageFont.load_default()
        
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow versions
        w, h = draw.textsize(text, font=font)
        
    x = (size - w) / 2
    y = (size - h) / 2 - 1
    draw.text((x, y), text, fill="white", font=font)
    
    return ImageTk.PhotoImage(img)


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.config = config_manager.load_config()
        ctk.set_appearance_mode(self.config.get("theme", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title("Nearest Destination Finder")
        self.geometry("1100x700")
        self.minsize(900, 600)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()

        self.google_key_entry.insert(0, self.config.get("google_api_key", ""))
        self.ors_key_entry.insert(0, self.config.get("openrouteservice_api_key", ""))
        raw = self.config.get("default_provider", "Google Maps")
        provider = _PROVIDER_LEGACY.get(raw, raw)
        self.provider_var.set(provider)
        self._on_provider_change(provider)

        self.mode_var.set(self.config.get("mode", "Find Nearest"))

        self.current_pins = []
        self._marker_icons = []
        self.current_polyline = None
        self._last_results = None
        self._last_is_tsp = False

        self.origin_entry.bind("<Return>", lambda event: self.start_calculation())
        self.departure_entry.bind("<Return>", lambda event: self.start_calculation())
        self._on_mode_change(self.mode_var.get())

        self.checked_run_vars = {}
        self.rebuild_history_list()

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(21, weight=1)    # spacer pushes Save to bottom

        ctk.CTkLabel(self.sidebar, text="Settings",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 10))

        # Provider
        self.provider_var = ctk.StringVar(value="Google Maps")
        ctk.CTkLabel(self.sidebar, text="Provider:").grid(
            row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar, values=_PROVIDER_NAMES, variable=self.provider_var,
            command=self._on_provider_change,
        ).grid(row=2, column=0, padx=20, pady=(5, 5), sticky="ew")

        # Nominatim info note (shown only when Free (Nominatim) is selected)
        self._nominatim_note = ctk.CTkLabel(
            self.sidebar,
            text="ℹ Straight-line distances only. No routing or travel times.",
            text_color=("gray40", "gray60"),
            wraplength=240,
            font=ctk.CTkFont(size=11),
            justify="left",
            anchor="w",
        )
        self._nominatim_note.grid(row=3, column=0, padx=20, pady=(0, 5), sticky="w")
        self._nominatim_note.grid_remove()

        # API keys with show/hide toggle
        self._google_key_label = ctk.CTkLabel(self.sidebar, text="Google API Key:")
        self._google_key_label.grid(row=4, column=0, padx=20, pady=(5, 0), sticky="w")
        self.google_key_entry, self._google_key_frame = self._key_row(self.sidebar, row=5)

        self._ors_key_label = ctk.CTkLabel(self.sidebar, text="OpenRouteService API Key:")
        self._ors_key_label.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ors_key_entry, self._ors_key_frame = self._key_row(self.sidebar, row=7)

        # Mode
        self.mode_var = ctk.StringVar(value="Find Nearest")
        ctk.CTkLabel(self.sidebar, text="Mode:").grid(
            row=8, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Find Nearest", "Traveling Salesman (TSP)"],
            variable=self.mode_var,
            command=self._on_mode_change,
        ).grid(row=9, column=0, padx=20, pady=(5, 5), sticky="ew")

        # Round-trip TSP (Return to Origin) checkbox
        self.round_trip_var = ctk.BooleanVar(value=self.config.get("round_trip", False))
        self.round_trip_cb = ctk.CTkCheckBox(
            self.sidebar, text="Return to Origin (Round-Trip)",
            variable=self.round_trip_var
        )
        self.round_trip_cb.grid(row=10, column=0, padx=20, pady=(5, 10), sticky="w")

        # Transport Mode
        self.transport_var = ctk.StringVar(value=self.config.get("transport_mode", "Driving"))
        ctk.CTkLabel(self.sidebar, text="Transport Mode:").grid(
            row=11, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Driving", "Walking", "Bicycling", "Transit"],
            variable=self.transport_var,
        ).grid(row=12, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Departure Time
        self.departure_var = ctk.StringVar(value="now")
        ctk.CTkLabel(self.sidebar, text="Departure Time (YYYY-MM-DD HH:MM or 'now'):").grid(
            row=13, column=0, padx=20, pady=(10, 0), sticky="w")
        self.departure_entry = ctk.CTkEntry(self.sidebar, textvariable=self.departure_var)
        self.departure_entry.grid(row=14, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Theme
        self.theme_var = ctk.StringVar(value=self.config.get("theme", "Dark"))
        ctk.CTkLabel(self.sidebar, text="Theme:").grid(
            row=15, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Dark", "Light", "System"],
            variable=self.theme_var,
            command=lambda v: ctk.set_appearance_mode(v),
        ).grid(row=16, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Map style
        self.map_style_var = ctk.StringVar(value=self.config.get("map_style", "Voyager"))
        ctk.CTkLabel(self.sidebar, text="Map Style:").grid(
            row=17, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=list(_TILE_SERVERS.keys()),
            variable=self.map_style_var,
            command=self._apply_map_style,
        ).grid(row=18, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Distance Unit
        self.unit_var = ctk.StringVar(value=self.config.get("unit", "Metric (km)"))
        ctk.CTkLabel(self.sidebar, text="Distance Unit:").grid(
            row=19, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Metric (km)", "Imperial (mi)"],
            variable=self.unit_var,
            command=self._on_unit_change,
        ).grid(row=20, column=0, padx=20, pady=(5, 10), sticky="ew")

        ctk.CTkButton(self.sidebar, text="Save Settings",
                      command=self.save_settings).grid(
            row=22, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _key_row(self, parent: ctk.CTkFrame, row: int) -> tuple:
        """Returns (CTkEntry, frame) — frame can be grid_remove()'d to hide the row."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, padx=20, pady=(5, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(frame, show="*")
        entry.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(frame, text="👁", width=32,
                      command=lambda e=entry: e.configure(
                          show="" if e.cget("show") == "*" else "*")
                      ).grid(row=0, column=1, padx=(5, 0))
        return entry, frame

    def _apply_map_style(self, style: str) -> None:
        url = _TILE_SERVERS.get(style, _TILE_SERVERS["Voyager"])
        self.map_widget.set_tile_server(url, max_zoom=19)

    def _on_provider_change(self, provider: str) -> None:
        """Show/hide API key rows and Nominatim note depending on provider."""
        is_nominatim = provider == "Free (Nominatim)"
        show_keys = not is_nominatim

        for w in (self._google_key_label, self._google_key_frame,
                  self._ors_key_label, self._ors_key_frame):
            if show_keys:
                w.grid()
            else:
                w.grid_remove()

        if is_nominatim:
            self._nominatim_note.grid()
        else:
            self._nominatim_note.grid_remove()

    # ── Main area ─────────────────────────────────────────────────────────────

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=2)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_map_panel()

    def _build_left_panel(self):
        self.left_panel = ctk.CTkTabview(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.tab_calculator = self.left_panel.add("Calculator")
        self.tab_compare = self.left_panel.add("Compare & History")
        
        # Configure tab grids
        self.tab_calculator.grid_columnconfigure(0, weight=1)
        self.tab_calculator.grid_rowconfigure(4, weight=1)   # dest_list expands
        self.tab_calculator.grid_rowconfigure(7, weight=2)   # results_area expands more

        self.tab_compare.grid_columnconfigure(0, weight=1)
        self.tab_compare.grid_rowconfigure(1, weight=1)      # history scroll expands
        self.tab_compare.grid_rowconfigure(2, weight=1)      # comparison dashboard expands

        # ── Calculator Tab Components ──────────────────────────────────────────

        # Origin
        ctk.CTkLabel(self.tab_calculator, text="Origin:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.origin_entry = ctk.CTkEntry(self.tab_calculator,
                                         placeholder_text="e.g. Rome, Piazza Venezia")
        self.origin_entry.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        # Destinations header: label + Add + Clear All
        dest_header = ctk.CTkFrame(self.tab_calculator, fg_color="transparent")
        dest_header.grid(row=2, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(dest_header, text="Destinations:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(dest_header, text="Clear All", width=72,
                      command=lambda: self.dest_list.clear_all()).pack(side="right")
        ctk.CTkButton(dest_header, text="+ Add", width=65,
                      command=lambda: self.dest_list.add_entry()).pack(side="right", padx=(0, 5))

        # CSV import / export bar
        csv_bar = ctk.CTkFrame(self.tab_calculator, fg_color="transparent")
        csv_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 0))
        csv_bar.grid_columnconfigure(0, weight=1)
        csv_bar.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(csv_bar, text="Import CSV",
                      command=self.import_csv).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(csv_bar, text="Export CSV",
                      command=self.export_destinations_csv).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # Destination list
        self.dest_list = DestinationList(self.tab_calculator, height=180, on_enter_pressed=self.start_calculation)
        self.dest_list.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")

        # Calculate / Validate button bar
        calc_bar = ctk.CTkFrame(self.tab_calculator, fg_color="transparent")
        calc_bar.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        calc_bar.grid_columnconfigure(0, weight=3)
        calc_bar.grid_columnconfigure(1, weight=2)

        self.btn_calculate = ctk.CTkButton(calc_bar, text="Calculate Routes",
                                           command=self.start_calculation)
        self.btn_calculate.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_validate = ctk.CTkButton(calc_bar, text="Validate Addresses",
                                          command=self.start_validation,
                                          fg_color="gray50", hover_color="gray60")
        self.btn_validate.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # Results header: label + Export Results button
        results_header = ctk.CTkFrame(self.tab_calculator, fg_color="transparent")
        results_header.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 0))
        ctk.CTkLabel(results_header, text="Results:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.btn_export_results = ctk.CTkButton(
            results_header, text="Export CSV", width=100,
            state="disabled", command=self.export_results_csv)
        self.btn_export_results.pack(side="right")

        # Results area
        self.results_area = ctk.CTkScrollableFrame(self.tab_calculator, height=180)
        self.results_area.grid(row=7, column=0, padx=10, pady=(2, 0), sticky="nsew")
        self.results_area.grid_columnconfigure(0, weight=1)

        # Status label
        self.status_label = ctk.CTkLabel(self.tab_calculator, text="", text_color="gray")
        self.status_label.grid(row=8, column=0, padx=10, pady=(2, 5))

        # ── Compare & History Tab Components ───────────────────────────────────

        history_header = ctk.CTkFrame(self.tab_compare, fg_color="transparent")
        history_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkLabel(history_header, text="Saved Routes:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(history_header, text="Clear History", width=90, fg_color="gray50", hover_color="gray60",
                      command=self.clear_history_action).pack(side="right")

        self.history_scroll = ctk.CTkScrollableFrame(self.tab_compare, height=180)
        self.history_scroll.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.history_scroll.grid_columnconfigure(0, weight=1)

        self.comparison_frame = ctk.CTkScrollableFrame(self.tab_compare, height=200)
        self.comparison_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.comparison_frame.grid_columnconfigure(0, weight=1)

    def _build_map_panel(self):
        self.map_panel = ctk.CTkFrame(self.main_frame)
        self.map_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # database_path enables persistent SQLite tile cache — tiles load from disk after first visit
        self.map_widget = tkintermapview.TkinterMapView(
            self.map_panel, corner_radius=0, database_path=_MAP_CACHE)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(41.8719, 12.5674)
        self.map_widget.set_zoom(6)
        self._apply_map_style(self.map_style_var.get())

    # ── Settings & import/export ──────────────────────────────────────────────

    def save_settings(self):
        self.config["google_api_key"] = self.google_key_entry.get().strip()
        self.config["openrouteservice_api_key"] = self.ors_key_entry.get().strip()
        self.config["default_provider"] = self.provider_var.get()
        self.config["transport_mode"] = self.transport_var.get()
        self.config["mode"] = self.mode_var.get()
        self.config["theme"] = self.theme_var.get()
        self.config["map_style"] = self.map_style_var.get()
        self.config["unit"] = self.unit_var.get()
        self.config["round_trip"] = self.round_trip_var.get()
        if config_manager.save_config(self.config):
            messagebox.showinfo("Settings Saved", "Settings saved successfully.")
        else:
            messagebox.showerror("Error", "Could not save settings.")

    def import_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
        addresses = data_importer.import_addresses_from_csv(file_path)
        if addresses:
            self.dest_list.load_from_list(addresses)
            messagebox.showinfo("CSV Import", f"Imported {len(addresses)} address(es).")
        else:
            messagebox.showwarning("Warning", "No addresses found or invalid file format.")

    def export_destinations_csv(self):
        destinations = self.dest_list.get_destinations()
        if not destinations:
            messagebox.showwarning("Warning", "No destinations to export.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Export Destinations",
        )
        if not file_path:
            return
        if data_importer.export_addresses_to_csv(file_path, destinations):
            messagebox.showinfo("Export", f"Saved {len(destinations)} address(es) to:\n{file_path}")
        else:
            messagebox.showerror("Export Error", "Could not save the file.")

    def export_results_csv(self):
        if not self._last_results:
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Export Results",
        )
        if not file_path:
            return
        results = self._last_results.get("results", [])
        
        # Format results for CSV
        formatted_results = []
        for r in results:
            formatted_r = r.copy()
            if not r.get("error") and "distance_value" in r:
                formatted_r["distance_text"] = self._format_distance(r["distance_value"])
            formatted_results.append(formatted_r)
            
        # Calculate total distance
        total_dist_val = sum(
            r.get("distance_value", 0)
            for r in results
            if r.get("distance_value") is not None and r.get("distance_value") != float('inf')
        )
        total_dist_text = self._format_distance(total_dist_val)

        ok = data_importer.export_results_to_csv(
            file_path, formatted_results, self._last_is_tsp,
            total_distance=total_dist_text,
            total_duration=self._last_results.get("total_duration", ""),
        )
        if ok:
            messagebox.showinfo("Export", f"Results saved to:\n{file_path}")
        else:
            messagebox.showerror("Export Error", "Could not save the file.")

    # ── Map helpers ───────────────────────────────────────────────────────────

    def clear_results(self):
        for widget in self.results_area.winfo_children():
            widget.destroy()

    def clear_map(self):
        self.current_pins.clear()
        self._marker_icons.clear()
        self.current_polyline = None
        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()

    def _fit_map_to_coords(self, coords: list) -> None:
        """Center and zoom the map to fit all given (lat, lon) coordinates."""
        valid = [c for c in coords if c is not None]
        if not valid:
            return
        if len(valid) == 1:
            self.map_widget.set_position(valid[0][0], valid[0][1])
            self.map_widget.set_zoom(13)
            return

        lats = [c[0] for c in valid]
        lons = [c[1] for c in valid]
        center_lat = (min(lats) + max(lats)) / 2
        center_lon = (min(lons) + max(lons)) / 2
        span = max(max(lats) - min(lats), max(lons) - min(lons))

        if span < 0.01:    zoom = 15
        elif span < 0.05:  zoom = 13
        elif span < 0.1:   zoom = 12
        elif span < 0.5:   zoom = 10
        elif span < 1.0:   zoom = 9
        elif span < 2.0:   zoom = 8
        elif span < 5.0:   zoom = 7
        elif span < 10.0:  zoom = 6
        elif span < 20.0:  zoom = 5
        else:              zoom = 4

        self.map_widget.set_position(center_lat, center_lon)
        self.map_widget.set_zoom(zoom)

    # ── Calculation flow ──────────────────────────────────────────────────────

    def start_calculation(self):
        self._reset_entry_borders()
        origin = self.origin_entry.get().strip()
        destinations_with_settings = self.dest_list.get_destinations_with_settings()
        destinations = [d["address"] for d in destinations_with_settings]
        provider = self.provider_var.get()
        mode = self.mode_var.get()
        transport_mode = self.transport_var.get()
        dep_str = self.departure_var.get().strip()
        round_trip = self.round_trip_var.get()

        if dep_str.lower() == "now":
            departure_time = datetime.now()
        else:
            try:
                departure_time = datetime.strptime(dep_str, "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showerror("Error", "Invalid departure time format. Use YYYY-MM-DD HH:MM or 'now'.")
                return

        if not origin:
            messagebox.showerror("Error", "Please enter an origin address.")
            return
        if not destinations:
            messagebox.showerror("Error", "Please enter at least one destination.")
            return

        if provider == "Google Maps":
            api_key = self.google_key_entry.get().strip()
        elif provider == "OpenRouteService":
            api_key = self.ors_key_entry.get().strip()
        else:
            api_key = None

        if provider != "Free (Nominatim)" and not api_key:
            messagebox.showerror("Error", f"Please enter an API key for {provider}.")
            return

        self.btn_calculate.configure(state="disabled", text="Calculating...")
        self.btn_export_results.configure(state="disabled")
        self._last_results = None
        self.status_label.configure(text="")
        self.clear_results()
        self.clear_map()

        wait_msg = (
            f"Geocoding {len(destinations)} address(es) via Nominatim — ~{len(destinations) + 1}s…"
            if provider == "Free (Nominatim)"
            else "Communicating with API, please wait..."
        )
        ctk.CTkLabel(self.results_area, text=wait_msg).pack(pady=20)

        threading.Thread(
            target=self.run_api_request,
            args=(provider, mode, api_key, origin, destinations_with_settings, transport_mode, departure_time, round_trip),
            daemon=True,
        ).start()

    def run_api_request(self, provider, mode, api_key, origin, destinations, transport_mode, departure_time, round_trip):
        is_tsp = mode == "Traveling Salesman (TSP)"
        if provider == "Google Maps":
            engine = maps_engine
        elif provider == "OpenRouteService":
            engine = openroute_engine
        else:
            engine = nominatim_engine

        if is_tsp:
            dest_addresses = [d["address"] for d in destinations]
            res = engine.get_optimized_route(api_key, origin, dest_addresses, transport_mode, departure_time, round_trip=round_trip)
        else:
            has_overrides = any(d.get("transport_mode", "Default") != "Default" or d.get("departure_time", "Default") != "Default" for d in destinations)
            
            if not has_overrides:
                dest_addresses = [d["address"] for d in destinations]
                res = engine.get_distance_matrix(api_key, origin, dest_addresses, transport_mode, departure_time)
            else:
                overall_results = []
                origin_coords = None
                
                # Geocode origin first
                if provider == "Google Maps":
                    origin_coords = maps_engine.geocode_address(api_key, origin)
                elif provider == "OpenRouteService":
                    origin_coords = openroute_engine.geocode_address(api_key, origin)
                else:
                    origin_coords = nominatim_engine.geocode_address(origin)
                    
                if not origin_coords:
                    res = {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}
                    self.after(0, self.display_results, res, False)
                    return
                    
                for d in destinations:
                    addr = d["address"]
                    dest_mode = d.get("transport_mode", "Default")
                    if dest_mode == "Default":
                        dest_mode = transport_mode
                        
                    dest_dep = d.get("departure_time", "Default")
                    if dest_dep == "Default":
                        dest_dep = departure_time
                    else:
                        if dest_dep.lower() == "now":
                            dest_dep = datetime.now()
                        else:
                            try:
                                dest_dep = datetime.strptime(dest_dep, "%Y-%m-%d %H:%M")
                            except ValueError:
                                dest_dep = departure_time
                                
                    single_res = engine.get_distance_matrix(api_key, origin, [addr], dest_mode, dest_dep)
                    
                    if single_res.get("status") == "ERROR":
                        overall_results.append({
                            "destination": addr,
                            "original_destination": addr,
                            "distance_text": "N/A",
                            "distance_value": float('inf'),
                            "duration_text": "N/A",
                            "duration_value": float('inf'),
                            "error": single_res.get("error_message", "Calculation failed")
                        })
                    else:
                        results = single_res.get("results", [])
                        if results:
                            overall_results.append(results[0])
                        else:
                            overall_results.append({
                                "destination": addr,
                                "original_destination": addr,
                                "distance_text": "N/A",
                                "distance_value": float('inf'),
                                "duration_text": "N/A",
                                "duration_value": float('inf'),
                                "error": "No results returned"
                            })
                            
                overall_results.sort(key=lambda x: x.get("distance_value", float('inf')))
                res = {
                    "status": "OK",
                    "results": overall_results,
                    "origin_coords": origin_coords
                }

        self.after(0, self.display_results, res, is_tsp)

    def display_results(self, response, is_tsp):
        self.clear_results()
        self.clear_map()
        self.btn_calculate.configure(state="normal", text="Calculate Routes")

        if response.get("status") == "ERROR":
            messagebox.showerror("API Error", response.get("error_message", "Unknown error"))
            return

        self._last_results = response
        self._last_is_tsp = is_tsp

        results = response.get("results", [])
        origin_coords = response.get("origin_coords")
        all_coords = []

        if origin_coords:
            all_coords.append(origin_coords)
            p = self.map_widget.set_marker(
                origin_coords[0], origin_coords[1],
                text="Origin",
                icon=self.get_marker_icon("S", bg_color="#2e7d32")
            )
            self.current_pins.append(p)

        if is_tsp:
            total_dist_val = sum(
                r.get("distance_value", 0)
                for r in results
                if r.get("distance_value") is not None and r.get("distance_value") != float('inf')
            )
            tot_dist = self._format_distance(total_dist_val)
            tot_dur = response.get("total_duration", "N/A")
            ctk.CTkLabel(self.results_area,
                         text=f"Total trip: {tot_dist} — {tot_dur}",
                         font=ctk.CTkFont(weight="bold")).pack(pady=5)

            for res in results:
                dist_text = self._format_distance(res.get("distance_value")) if not res.get("error") else ""
                ResultCard(self.results_area, res["destination"],
                           dist_text, res["duration_text"],
                           step=res.get("step")).pack(fill="x", pady=2, padx=2)
                dest_coords = res.get("dest_coords")
                if dest_coords:
                    all_coords.append(dest_coords)
                    if origin_coords and (abs(dest_coords[0] - origin_coords[0]) < 1e-7 and abs(dest_coords[1] - origin_coords[1]) < 1e-7):
                        continue
                    p = self.map_widget.set_marker(
                        dest_coords[0], dest_coords[1],
                        text=f"Stop {res.get('step', '')}",
                        icon=self.get_marker_icon(str(res.get("step", "")))
                    )
                    self.current_pins.append(p)

            polyline_path = response.get("polyline_path")
            if not polyline_path and response.get("polyline") and _HAS_POLYLINE:
                polyline_path = _polyline_lib.decode(response["polyline"])
            if polyline_path and len(polyline_path) >= 2:
                self.current_polyline = self.map_widget.set_path(polyline_path)

        else:
            for i, res in enumerate(results):
                if res.get("error"):
                    error_text = res.get("error", "Calculation error")
                    ResultCard(self.results_area, res["destination"], "", "",
                               is_error=True, error_text=error_text).pack(fill="x", pady=2, padx=2)
                else:
                    dist_text = self._format_distance(res.get("distance_value"))
                    ResultCard(self.results_area, res["destination"],
                               dist_text, res["duration_text"]).pack(
                        fill="x", pady=2, padx=2)
                    dest_coords = res.get("dest_coords")
                    if dest_coords:
                        all_coords.append(dest_coords)
                        if origin_coords and (abs(dest_coords[0] - origin_coords[0]) < 1e-7 and abs(dest_coords[1] - origin_coords[1]) < 1e-7):
                            continue
                        p = self.map_widget.set_marker(
                            dest_coords[0], dest_coords[1],
                            text=res["destination"][:30],
                            icon=self.get_marker_icon(str(i + 1))
                        )
                        self.current_pins.append(p)

        valid_count = sum(1 for r in results if not r.get("error"))
        self.status_label.configure(text=f"Done — {valid_count} destination(s) calculated")

        if valid_count > 0:
            self.btn_export_results.configure(state="normal")
            
            # Save this run to history
            try:
                origin = self.origin_entry.get().strip()
                destinations = self.dest_list.get_destinations()
                provider = self.provider_var.get()
                mode = self.mode_var.get()
                transport_mode = self.transport_var.get()
                dep_str = self.departure_var.get().strip()
                round_trip = self.round_trip_var.get()
                
                history_manager.add_run(
                    origin=origin,
                    destinations=destinations,
                    provider=provider,
                    mode=mode,
                    transport_mode=transport_mode,
                    departure_time_str=dep_str,
                    round_trip=round_trip,
                    response=response,
                    is_tsp=is_tsp
                )
                self.rebuild_history_list()
            except Exception as e:
                print(f"Error saving run to history: {e}")

        self._fit_map_to_coords(all_coords)

    # ── Custom helpers & validation ───────────────────────────────────────────

    def get_marker_icon(self, text, bg_color="#3498db"):
        icon = create_circle_marker_icon(text, bg_color)
        self._marker_icons.append(icon)
        return icon

    def _format_distance(self, meters):
        if meters is None or meters == float('inf') or isinstance(meters, str):
            return "N/A"
        is_mi = self.unit_var.get() == "Imperial (mi)"
        provider = self.provider_var.get()
        is_straight = provider == "Free (Nominatim)"
        
        if is_mi:
            val = meters * 0.000621371
            suffix = " mi"
        else:
            val = meters / 1000.0
            suffix = " km"
            
        if is_straight:
            suffix += " (straight-line)"
            
        return f"{val:.1f}{suffix}"

    def _on_unit_change(self, value):
        if self._last_results:
            self.display_results(self._last_results, self._last_is_tsp)

    def _on_mode_change(self, mode):
        if mode == "Traveling Salesman (TSP)":
            self.round_trip_cb.configure(state="normal")
        else:
            self.round_trip_cb.configure(state="disabled")
            self.round_trip_var.set(False)

    def _reset_entry_borders(self):
        self.origin_entry.configure(border_color=["#979DA2", "#565B5E"])
        for entry in self.dest_list.entries:
            entry.configure(border_color=["#979DA2", "#565B5E"])

    def start_validation(self):
        provider = self.provider_var.get()
        if provider == "Google Maps":
            api_key = self.google_key_entry.get().strip()
            if not api_key:
                messagebox.showerror("Error", "Please enter a Google API Key for validation.")
                return
        elif provider == "OpenRouteService":
            api_key = self.ors_key_entry.get().strip()
            if not api_key:
                messagebox.showerror("Error", "Please enter an OpenRouteService API Key for validation.")
                return
        else:
            api_key = None

        origin = self.origin_entry.get().strip()
        destinations = self.dest_list.get_destinations()

        self.btn_validate.configure(state="disabled", text="Validating...")
        self.btn_calculate.configure(state="disabled")
        self._reset_entry_borders()

        threading.Thread(
            target=self.run_validation,
            args=(provider, api_key, origin, destinations),
            daemon=True
        ).start()

    def run_validation(self, provider, api_key, origin, destinations):
        if provider == "Google Maps":
            engine = maps_engine
        elif provider == "OpenRouteService":
            engine = openroute_engine
        else:
            engine = nominatim_engine

        origin_ok = False
        if origin:
            coords = self._geocode_via_engine(engine, api_key, origin)
            origin_ok = coords is not None

        dest_results = []
        for entry in self.dest_list.entries:
            addr = entry.get().strip()
            if not addr:
                dest_results.append((entry, None))
            else:
                coords = self._geocode_via_engine(engine, api_key, addr)
                dest_results.append((entry, coords is not None))

        self.after(0, self.finish_validation, origin_ok, dest_results)

    def _geocode_via_engine(self, engine, api_key, address):
        if engine == nominatim_engine:
            return engine.geocode_address(address)
        else:
            return engine.geocode_address(api_key, address)

    def finish_validation(self, origin_ok, dest_results):
        self.btn_validate.configure(state="normal", text="Validate Addresses")
        self.btn_calculate.configure(state="normal")

        if self.origin_entry.get().strip():
            if origin_ok:
                self.origin_entry.configure(border_color=["#2ecc71", "#27ae60"])
            else:
                self.origin_entry.configure(border_color=["#e74c3c", "#c0392b"])
        else:
            self.origin_entry.configure(border_color=["#979DA2", "#565B5E"])

        valid_count = 0
        invalid_count = 0

        for entry, is_valid in dest_results:
            if is_valid is None:
                entry.configure(border_color=["#979DA2", "#565B5E"])
            elif is_valid:
                entry.configure(border_color=["#2ecc71", "#27ae60"])
                valid_count += 1
            else:
                entry.configure(border_color=["#e74c3c", "#c0392b"])
                invalid_count += 1

        origin_entered = bool(self.origin_entry.get().strip())
        origin_status = "Origin is valid." if (origin_entered and origin_ok) else ("Origin is invalid!" if origin_entered else "Origin is empty.")
        msg = f"{origin_status}\nDestinations: {valid_count} valid, {invalid_count} invalid."

        if invalid_count > 0 or (origin_entered and not origin_ok):
            messagebox.showwarning("Validation Results", f"Some addresses failed validation:\n\n{msg}")
        else:
            messagebox.showinfo("Validation Results", f"All addresses are valid!\n\n{msg}")

    # ── History & Comparison ──────────────────────────────────────────────────

    def rebuild_history_list(self):
        # Clear existing widgets in self.history_scroll
        for w in self.history_scroll.winfo_children():
            w.destroy()
            
        history = history_manager.load_history()
        
        # Clean up checked_run_vars for runs that no longer exist
        valid_ids = {item.get("id") for item in history}
        self.checked_run_vars = {run_id: var for run_id, var in self.checked_run_vars.items() if run_id in valid_ids}
        
        if not history:
            lbl = ctk.CTkLabel(self.history_scroll, text="No saved routes in history.", text_color="gray")
            lbl.pack(pady=20)
            return
            
        for run in history:
            run_id = run["id"]
            
            # Ensure we have a BooleanVar for this run_id
            if run_id not in self.checked_run_vars:
                self.checked_run_vars[run_id] = ctk.BooleanVar(value=False)
                
            var = self.checked_run_vars[run_id]
            
            run_frame = ctk.CTkFrame(self.history_scroll)
            run_frame.pack(fill="x", pady=2, padx=2)
            
            # Checkbox
            cb = ctk.CTkCheckBox(run_frame, text="", variable=var, width=24, command=self.on_comparison_toggled)
            cb.pack(side="left", padx=(5, 0))
            
            # Info block
            info_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=5)
            
            name_lbl = ctk.CTkLabel(info_frame, text=run["name"], font=ctk.CTkFont(weight="bold"), anchor="w", justify="left")
            name_lbl.pack(fill="x", anchor="w")
            
            # Subtitle with details
            mode_tag = "TSP" if run["is_tsp"] else "Nearest"
            details = f"{run['timestamp']} | {mode_tag} - {run['transport_mode']} | {len(run['destinations'])} stops"
            details_lbl = ctk.CTkLabel(info_frame, text=details, font=ctk.CTkFont(size=11), text_color="gray", anchor="w", justify="left")
            details_lbl.pack(fill="x", anchor="w")
            
            # Actions frame
            actions_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
            actions_frame.pack(side="right", padx=5)
            
            # Load button
            load_btn = ctk.CTkButton(actions_frame, text="Load", width=45, height=24,
                                     command=lambda r=run: self.load_run_inputs(r))
            load_btn.pack(side="left", padx=2)
            
            # Rename button
            rename_btn = ctk.CTkButton(actions_frame, text="✏", width=24, height=24,
                                       command=lambda r=run: self.rename_run_prompt(r))
            rename_btn.pack(side="left", padx=2)
            
            # Delete button
            delete_btn = ctk.CTkButton(actions_frame, text="✕", width=24, height=24, fg_color="gray50", hover_color="gray60",
                                       command=lambda r=run: self.delete_run_action(r))
            delete_btn.pack(side="left", padx=2)

    def load_run_inputs(self, run):
        # Switch back to Calculator tab
        self.left_panel.set("Calculator")
        
        # Populate Origin
        self.origin_entry.delete(0, "end")
        self.origin_entry.insert(0, run.get("origin", ""))
        
        # Populate Destinations
        destinations = run.get("destinations", [])
        self.dest_list.load_from_list(destinations)
        
        # Populate Config Settings
        self.provider_var.set(run.get("provider", "Google Maps"))
        self.mode_var.set(run.get("mode", "Find Nearest"))
        self.transport_var.set(run.get("transport_mode", "Driving"))
        self.departure_var.set(run.get("departure_time", "now"))
        self.round_trip_var.set(run.get("round_trip", False))
        
        # Trigger change handlers to update UI visibility
        self._on_provider_change(run.get("provider", "Google Maps"))
        self._on_mode_change(run.get("mode", "Find Nearest"))
        
        # Notify user
        messagebox.showinfo("Route Loaded", f"Route inputs loaded into Calculator:\n\nOrigin: {run.get('origin')}\nStops: {len(destinations)}")

    def rename_run_prompt(self, run):
        dialog = ctk.CTkInputDialog(text="Enter new name for this route run:", title="Rename Route")
        new_name = dialog.get_input()
        if new_name and new_name.strip():
            history_manager.rename_run(run["id"], new_name.strip())
            self.rebuild_history_list()
            # If it's checked, update comparison dashboard
            checked_ids = [run_id for run_id, var in self.checked_run_vars.items() if var.get()]
            if run["id"] in checked_ids:
                self.on_comparison_toggled()

    def delete_run_action(self, run):
        if messagebox.askyesno("Delete Route", f"Are you sure you want to delete '{run['name']}' from history?"):
            history_manager.delete_run(run["id"])
            self.rebuild_history_list()
            self.on_comparison_toggled()

    def clear_history_action(self):
        if messagebox.askyesno("Clear History", "Are you sure you want to delete all saved routes from history?"):
            history_manager.clear_history()
            self.rebuild_history_list()
            self.on_comparison_toggled()

    def on_comparison_toggled(self):
        # Find which runs are checked
        checked_ids = []
        for run_id, var in self.checked_run_vars.items():
            if var.get():
                checked_ids.append(run_id)
                
        # Load history to get run data
        history = history_manager.load_history()
        checked_runs = [item for item in history if item.get("id") in checked_ids]
        
        # Update Dashboard
        self.update_comparison_dashboard(checked_runs)
        
        # Redraw map
        self.clear_map()
        
        if not checked_runs:
            return
            
        COLORS = ["#3498db", "#2ecc71", "#e74c3c", "#9b59b6", "#f1c40f", "#1abc9c"]
        all_coords = []
        drawn_origins = set()
        
        for idx, run in enumerate(checked_runs):
            color = COLORS[idx % len(COLORS)]
            
            origin_coords = run.get("origin_coords")
            if origin_coords:
                all_coords.append(origin_coords)
                origin_tuple = tuple(origin_coords)
                if origin_tuple not in drawn_origins:
                    p = self.map_widget.set_marker(
                        origin_coords[0], origin_coords[1],
                        text="Origin",
                        icon=self.get_marker_icon("S", bg_color="#2e7d32")
                    )
                    self.current_pins.append(p)
                    drawn_origins.add(origin_tuple)
            
            # Draw path
            if run.get("is_tsp"):
                path = run.get("polyline_path")
                if path and len(path) >= 2:
                    self.map_widget.set_path(path, color=color, width=5)
            else:
                # Draw lines from origin to destinations
                if origin_coords:
                    for res in run.get("results", []):
                        dest_c = res.get("dest_coords")
                        if dest_c:
                            self.map_widget.set_path([origin_coords, dest_c], color=color, width=3)
                            
            # Add markers for destinations in matched color
            for res in run.get("results", []):
                dest_coords = res.get("dest_coords")
                if dest_coords:
                    all_coords.append(dest_coords)
                    # Check if it overlaps with origin
                    if origin_coords and (abs(dest_coords[0] - origin_coords[0]) < 1e-7 and abs(dest_coords[1] - origin_coords[1]) < 1e-7):
                        continue
                    
                    label_text = str(res.get("step")) if run.get("is_tsp") else "D"
                    p = self.map_widget.set_marker(
                        dest_coords[0], dest_coords[1],
                        text=f"{run['name'][:10]} - {res['destination'][:20]}",
                        icon=self.get_marker_icon(label_text, bg_color=color)
                    )
                    self.current_pins.append(p)
                    
        # Fit map to show all coordinates
        self._fit_map_to_coords(all_coords)

    def update_comparison_dashboard(self, checked_runs):
        # Destroy existing widgets in self.comparison_frame
        for w in self.comparison_frame.winfo_children():
            w.destroy()
            
        if len(checked_runs) < 2:
            lbl = ctk.CTkLabel(self.comparison_frame, text="Select 2 or more routes in the list above to compare them.", text_color="gray")
            lbl.pack(pady=20)
            return

        # Title
        ctk.CTkLabel(self.comparison_frame, text="Route Comparison", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5), anchor="w")
        
        # Grid/Table Frame
        table_frame = ctk.CTkFrame(self.comparison_frame)
        table_frame.pack(fill="x", pady=5)
        
        # Columns: Color/Name, Mode/Provider, Distance, Duration
        headers = ["Route", "Transport / Provider", "Distance", "Duration"]
        for col, text in enumerate(headers):
            lbl = ctk.CTkLabel(table_frame, text=text, font=ctk.CTkFont(weight="bold"), anchor="w")
            lbl.grid(row=0, column=col, padx=10, pady=5, sticky="w")
            
        # Define color representation mapping
        COLORS = ["#3498db", "#2ecc71", "#e74c3c", "#9b59b6", "#f1c40f", "#1abc9c"]
        
        # Populate rows
        for row, run in enumerate(checked_runs, start=1):
            color = COLORS[(row - 1) % len(COLORS)]
            
            # Colored circle indicator + Name
            name_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
            name_frame.grid(row=row, column=0, padx=10, pady=5, sticky="w")
            
            color_indicator = ctk.CTkLabel(name_frame, text="■", text_color=color, font=ctk.CTkFont(size=16))
            color_indicator.pack(side="left")
            
            name_lbl = ctk.CTkLabel(name_frame, text=run["name"][:35], anchor="w")
            name_lbl.pack(side="left", padx=5)
            
            # Mode / Provider
            details_text = f"{run['transport_mode']} ({run['provider']})"
            details_lbl = ctk.CTkLabel(table_frame, text=details_text, anchor="w")
            details_lbl.grid(row=row, column=1, padx=10, pady=5, sticky="w")
            
            # Distance
            dist_lbl = ctk.CTkLabel(table_frame, text=run["total_distance"], anchor="w")
            dist_lbl.grid(row=row, column=2, padx=10, pady=5, sticky="w")
            
            # Duration
            dur_lbl = ctk.CTkLabel(table_frame, text=run["total_duration"], anchor="w")
            dur_lbl.grid(row=row, column=3, padx=10, pady=5, sticky="w")
            
        # Calculate stats for highlights
        run_stats = []
        for row, run in enumerate(checked_runs):
            color = COLORS[row % len(COLORS)]
            
            # Sum values to ensure correct comparison
            total_d = sum(r.get("distance_value", 0) for r in run.get("results", []) if r.get("distance_value") is not None and r.get("distance_value") != float('inf'))
            total_t = sum(r.get("duration_value", 0) for r in run.get("results", []) if r.get("duration_value") is not None and r.get("duration_value") != float('inf'))
            
            run_stats.append({
                "run": run,
                "distance": total_d,
                "duration": total_t,
                "color": color
            })
            
        # Find shortest (min distance) and fastest (min duration)
        shortest = min(run_stats, key=lambda x: x["distance"])
        fastest = min(run_stats, key=lambda x: x["duration"])
        
        # Highlights block
        highlights_frame = ctk.CTkFrame(self.comparison_frame, border_width=1, border_color=("gray70", "gray30"))
        highlights_frame.pack(fill="x", pady=(10, 5))
        
        ctk.CTkLabel(highlights_frame, text="Highlights", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5, 2))
        
        # Shortest
        s_text = f"🏆 Shortest Route: {shortest['run']['name']} ({shortest['run']['total_distance']})"
        s_lbl = ctk.CTkLabel(highlights_frame, text=s_text, text_color=shortest["color"], font=ctk.CTkFont(weight="bold"), anchor="w")
        s_lbl.pack(fill="x", padx=10, pady=2)
        
        # Fastest
        f_text = f"⚡ Fastest Route: {fastest['run']['name']} ({fastest['run']['total_duration']})"
        f_lbl = ctk.CTkLabel(highlights_frame, text=f_text, text_color=fastest["color"], font=ctk.CTkFont(weight="bold"), anchor="w")
        f_lbl.pack(fill="x", padx=10, pady=(2, 5))
