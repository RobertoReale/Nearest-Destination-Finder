import customtkinter as ctk
import tkintermapview
import threading
from tkinter import filedialog, messagebox
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.components import DestinationList, ResultCard
from utils import config_manager, data_importer
from api import maps_engine, openroute_engine


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
        self.provider_var.set(self.config.get("default_provider", "google"))

        self.current_pins = []
        self.current_polyline = None

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(11, weight=1)  # spacer before save button

        ctk.CTkLabel(self.sidebar, text="Settings",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 10))

        # Provider
        self.provider_var = ctk.StringVar(value="google")
        ctk.CTkLabel(self.sidebar, text="Provider:").grid(
            row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.provider_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["google", "openrouteservice"], variable=self.provider_var)
        self.provider_menu.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="ew")

        # API Keys
        ctk.CTkLabel(self.sidebar, text="Google API Key:").grid(
            row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.google_key_entry = ctk.CTkEntry(self.sidebar, show="*")
        self.google_key_entry.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="ew")

        ctk.CTkLabel(self.sidebar, text="OpenRouteService API Key:").grid(
            row=5, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ors_key_entry = ctk.CTkEntry(self.sidebar, show="*")
        self.ors_key_entry.grid(row=6, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Mode
        self.mode_var = ctk.StringVar(value="Find Nearest")
        ctk.CTkLabel(self.sidebar, text="Mode:").grid(
            row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        self.mode_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=["Find Nearest", "Traveling Salesman (TSP)"],
            variable=self.mode_var)
        self.mode_menu.grid(row=8, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Theme
        self.theme_var = ctk.StringVar(value=self.config.get("theme", "Dark"))
        ctk.CTkLabel(self.sidebar, text="Theme:").grid(
            row=9, column=0, padx=20, pady=(10, 0), sticky="w")
        self.theme_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=["Dark", "Light", "System"],
            variable=self.theme_var,
            command=lambda v: ctk.set_appearance_mode(v))
        self.theme_menu.grid(row=10, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Save button (below spacer row 11)
        ctk.CTkButton(self.sidebar, text="Save Settings", command=self.save_settings).grid(
            row=12, column=0, padx=20, pady=10, sticky="ew")

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
        self.left_panel.grid_rowconfigure(3, weight=1)   # destination list
        self.left_panel.grid_rowconfigure(5, weight=2)   # results area

        # Origin
        ctk.CTkLabel(self.left_panel, text="Origin:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.origin_entry = ctk.CTkEntry(self.left_panel,
                                         placeholder_text="e.g. Rome, Piazza Venezia")
        self.origin_entry.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        # Destinations header
        dest_header_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        dest_header_frame.grid(row=2, column=0, sticky="ew", padx=10)

        ctk.CTkLabel(dest_header_frame, text="Destinations:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(dest_header_frame, text="Import CSV", width=100,
                      command=self.import_csv).pack(side="right")
        ctk.CTkButton(dest_header_frame, text="+ Add", width=80,
                      command=lambda: self.dest_list.add_entry()).pack(side="right", padx=5)

        self.dest_list = DestinationList(self.left_panel, height=200)
        self.dest_list.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        self.btn_calculate = ctk.CTkButton(self.left_panel, text="Calculate Routes",
                                           command=self.start_calculation)
        self.btn_calculate.grid(row=4, column=0, padx=10, pady=10, sticky="ew")

        self.results_area = ctk.CTkScrollableFrame(self.left_panel, height=200)
        self.results_area.grid(row=5, column=0, padx=10, pady=(0, 5), sticky="nsew")
        self.results_area.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.left_panel, text="", text_color="gray")
        self.status_label.grid(row=6, column=0, padx=10, pady=(0, 10))

    def _build_map_panel(self):
        self.map_panel = ctk.CTkFrame(self.main_frame)
        self.map_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        self.map_widget = tkintermapview.TkinterMapView(self.map_panel, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(41.8719, 12.5674)
        self.map_widget.set_zoom(6)

    def save_settings(self):
        self.config["google_api_key"] = self.google_key_entry.get().strip()
        self.config["openrouteservice_api_key"] = self.ors_key_entry.get().strip()
        self.config["default_provider"] = self.provider_var.get()
        self.config["theme"] = self.theme_var.get()
        if config_manager.save_config(self.config):
            messagebox.showinfo("Settings Saved", "Settings saved successfully.")
        else:
            messagebox.showerror("Error", "Could not save settings.")

    def import_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            addresses = data_importer.import_addresses_from_csv(file_path)
            if addresses:
                self.dest_list.load_from_list(addresses)
                messagebox.showinfo("CSV Import", f"Imported {len(addresses)} addresses.")
            else:
                messagebox.showwarning("Warning", "No addresses found or invalid file format.")

    def clear_results(self):
        for widget in self.results_area.winfo_children():
            widget.destroy()

    def clear_map(self):
        for pin in self.current_pins:
            pin.delete()
        self.current_pins.clear()

        if self.current_polyline:
            self.current_polyline.delete()
            self.current_polyline = None

        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()

    def start_calculation(self):
        origin = self.origin_entry.get().strip()
        destinations = self.dest_list.get_destinations()
        provider = self.provider_var.get()
        mode = self.mode_var.get()

        if not origin:
            messagebox.showerror("Error", "Please enter an origin address.")
            return

        if not destinations:
            messagebox.showerror("Error", "Please enter at least one destination.")
            return

        api_key = (self.google_key_entry.get().strip()
                   if provider == "google"
                   else self.ors_key_entry.get().strip())
        if not api_key:
            messagebox.showerror("Error", f"Please enter an API Key for {provider}.")
            return

        self.btn_calculate.configure(state="disabled", text="Calculating...")
        self.status_label.configure(text="")
        self.clear_results()
        self.clear_map()

        ctk.CTkLabel(self.results_area,
                     text="Communicating with API, please wait...").pack(pady=20)

        threading.Thread(
            target=self.run_api_request,
            args=(provider, mode, api_key, origin, destinations),
            daemon=True
        ).start()

    def run_api_request(self, provider, mode, api_key, origin, destinations):
        is_tsp = mode == "Traveling Salesman (TSP)"
        engine = maps_engine if provider == "google" else openroute_engine

        if is_tsp:
            res = engine.get_optimized_route(api_key, origin, destinations)
        else:
            res = engine.get_distance_matrix(api_key, origin, destinations)

        self.after(0, self.display_results, res, is_tsp)

    def display_results(self, response, is_tsp):
        self.clear_results()
        self.btn_calculate.configure(state="normal", text="Calculate Routes")

        if response.get("status") == "ERROR":
            messagebox.showerror("API Error", response.get("error_message", "Unknown error"))
            return

        results = response.get("results", [])
        origin_coords = response.get("origin_coords")

        if origin_coords:
            p = self.map_widget.set_marker(origin_coords[0], origin_coords[1],
                                           text="Origin", marker_color_outside="green")
            self.current_pins.append(p)
            self.map_widget.set_position(origin_coords[0], origin_coords[1])
            self.map_widget.set_zoom(10)

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

            if polyline_path:
                self.current_polyline = self.map_widget.set_path(polyline_path)

        else:
            for res in results:
                if res.get("error"):
                    ResultCard(self.results_area, res["destination"], "", "",
                               is_error=True).pack(fill="x", pady=2, padx=2)
                else:
                    ResultCard(self.results_area, res["destination"],
                               res["distance_text"], res["duration_text"]).pack(
                        fill="x", pady=2, padx=2)
                    dest_coords = res.get("dest_coords")
                    if dest_coords:
                        label = res["destination"][:30]
                        p = self.map_widget.set_marker(dest_coords[0], dest_coords[1],
                                                       text=label)
                        self.current_pins.append(p)

        valid_count = sum(1 for r in results if not r.get("error"))
        self.status_label.configure(text=f"Done — {valid_count} destination(s) calculated")
