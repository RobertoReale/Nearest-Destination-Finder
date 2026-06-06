import customtkinter as ctk
import tkintermapview
import threading
import os
from tkinter import filedialog, messagebox
from datetime import datetime
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.components import DestinationList, ResultCard
from utils import config_manager, data_importer
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
        self.current_polyline = None
        self._last_results: dict | None = None
        self._last_is_tsp: bool = False

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(18, weight=1)    # spacer pushes Save to bottom

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
        ).grid(row=9, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Transport Mode
        self.transport_var = ctk.StringVar(value=self.config.get("transport_mode", "Driving"))
        ctk.CTkLabel(self.sidebar, text="Transport Mode:").grid(
            row=10, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Driving", "Walking", "Bicycling", "Transit"],
            variable=self.transport_var,
        ).grid(row=11, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Departure Time
        self.departure_var = ctk.StringVar(value="now")
        ctk.CTkLabel(self.sidebar, text="Departure Time (YYYY-MM-DD HH:MM or 'now'):").grid(
            row=12, column=0, padx=20, pady=(10, 0), sticky="w")
        self.departure_entry = ctk.CTkEntry(self.sidebar, textvariable=self.departure_var)
        self.departure_entry.grid(row=13, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Theme
        self.theme_var = ctk.StringVar(value=self.config.get("theme", "Dark"))
        ctk.CTkLabel(self.sidebar, text="Theme:").grid(
            row=14, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Dark", "Light", "System"],
            variable=self.theme_var,
            command=lambda v: ctk.set_appearance_mode(v),
        ).grid(row=15, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Map style
        self.map_style_var = ctk.StringVar(value=self.config.get("map_style", "Voyager"))
        ctk.CTkLabel(self.sidebar, text="Map Style:").grid(
            row=16, column=0, padx=20, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(
            self.sidebar,
            values=list(_TILE_SERVERS.keys()),
            variable=self.map_style_var,
            command=self._apply_map_style,
        ).grid(row=17, column=0, padx=20, pady=(5, 10), sticky="ew")

        ctk.CTkButton(self.sidebar, text="Save Settings",
                      command=self.save_settings).grid(
            row=19, column=0, padx=20, pady=(0, 20), sticky="ew")

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
        self.left_panel = ctk.CTkFrame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(4, weight=1)   # dest_list expands
        self.left_panel.grid_rowconfigure(7, weight=2)   # results_area expands more

        # Origin
        ctk.CTkLabel(self.left_panel, text="Origin:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.origin_entry = ctk.CTkEntry(self.left_panel,
                                         placeholder_text="e.g. Rome, Piazza Venezia")
        self.origin_entry.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        # Destinations header: label + Add + Clear All
        dest_header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        dest_header.grid(row=2, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(dest_header, text="Destinations:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(dest_header, text="Clear All", width=72,
                      command=lambda: self.dest_list.clear_all()).pack(side="right")
        ctk.CTkButton(dest_header, text="+ Add", width=65,
                      command=lambda: self.dest_list.add_entry()).pack(side="right", padx=(0, 5))

        # CSV import / export bar
        csv_bar = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        csv_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 0))
        csv_bar.grid_columnconfigure(0, weight=1)
        csv_bar.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(csv_bar, text="Import CSV",
                      command=self.import_csv).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(csv_bar, text="Export CSV",
                      command=self.export_destinations_csv).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # Destination list
        self.dest_list = DestinationList(self.left_panel, height=200)
        self.dest_list.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")

        # Calculate button
        self.btn_calculate = ctk.CTkButton(self.left_panel, text="Calculate Routes",
                                           command=self.start_calculation)
        self.btn_calculate.grid(row=5, column=0, padx=10, pady=10, sticky="ew")

        # Results header: label + Export Results button
        results_header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        results_header.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 0))
        ctk.CTkLabel(results_header, text="Results:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.btn_export_results = ctk.CTkButton(
            results_header, text="Export CSV", width=100,
            state="disabled", command=self.export_results_csv)
        self.btn_export_results.pack(side="right")

        # Results area
        self.results_area = ctk.CTkScrollableFrame(self.left_panel, height=200)
        self.results_area.grid(row=7, column=0, padx=10, pady=(2, 0), sticky="nsew")
        self.results_area.grid_columnconfigure(0, weight=1)

        # Status label
        self.status_label = ctk.CTkLabel(self.left_panel, text="", text_color="gray")
        self.status_label.grid(row=8, column=0, padx=10, pady=(2, 10))

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
        ok = data_importer.export_results_to_csv(
            file_path, results, self._last_is_tsp,
            total_distance=self._last_results.get("total_distance", ""),
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
        origin = self.origin_entry.get().strip()
        destinations = self.dest_list.get_destinations()
        provider = self.provider_var.get()
        mode = self.mode_var.get()
        transport_mode = self.transport_var.get()
        dep_str = self.departure_var.get().strip()

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
            args=(provider, mode, api_key, origin, destinations, transport_mode, departure_time),
            daemon=True,
        ).start()

    def run_api_request(self, provider, mode, api_key, origin, destinations, transport_mode, departure_time):
        is_tsp = mode == "Traveling Salesman (TSP)"
        if provider == "Google Maps":
            engine = maps_engine
        elif provider == "OpenRouteService":
            engine = openroute_engine
        else:
            engine = nominatim_engine

        if is_tsp:
            res = engine.get_optimized_route(api_key, origin, destinations, transport_mode, departure_time)
        else:
            res = engine.get_distance_matrix(api_key, origin, destinations, transport_mode, departure_time)

        self.after(0, self.display_results, res, is_tsp)

    def display_results(self, response, is_tsp):
        self.clear_results()
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
            p = self.map_widget.set_marker(origin_coords[0], origin_coords[1],
                                           text="Origin", marker_color_outside="green")
            self.current_pins.append(p)

        if is_tsp:
            tot_dist = response.get("total_distance", "N/A")
            tot_dur = response.get("total_duration", "N/A")
            ctk.CTkLabel(self.results_area,
                         text=f"Total trip: {tot_dist} — {tot_dur}",
                         font=ctk.CTkFont(weight="bold")).pack(pady=5)

            for res in results:
                ResultCard(self.results_area, res["destination"],
                           res["distance_text"], res["duration_text"],
                           step=res.get("step")).pack(fill="x", pady=2, padx=2)
                dest_coords = res.get("dest_coords")
                if dest_coords:
                    all_coords.append(dest_coords)
                    p = self.map_widget.set_marker(dest_coords[0], dest_coords[1],
                                                   text=f"Stop {res.get('step', '')}")
                    self.current_pins.append(p)

            polyline_path = response.get("polyline_path")
            if not polyline_path and response.get("polyline"):
                try:
                    import polyline as pl
                    polyline_path = pl.decode(response["polyline"])
                except ImportError:
                    pass
            if polyline_path and len(polyline_path) >= 2:
                self.current_polyline = self.map_widget.set_path(polyline_path)

        else:
            for res in results:
                if res.get("error"):
                    error_text = res.get("error", "Calculation error")
                    ResultCard(self.results_area, res["destination"], "", "",
                               is_error=True, error_text=error_text).pack(fill="x", pady=2, padx=2)
                else:
                    ResultCard(self.results_area, res["destination"],
                               res["distance_text"], res["duration_text"]).pack(
                        fill="x", pady=2, padx=2)
                    dest_coords = res.get("dest_coords")
                    if dest_coords:
                        all_coords.append(dest_coords)
                        p = self.map_widget.set_marker(dest_coords[0], dest_coords[1],
                                                       text=res["destination"][:30])
                        self.current_pins.append(p)

        valid_count = sum(1 for r in results if not r.get("error"))
        self.status_label.configure(text=f"Done — {valid_count} destination(s) calculated")

        if valid_count > 0:
            self.btn_export_results.configure(state="normal")

        self._fit_map_to_coords(all_coords)
