import customtkinter as ctk
import tkintermapview
import threading
from tkinter import filedialog, messagebox
import sys
import os

# Aggiungi la cartella root al path per i moduli
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
        
        # Grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self._build_sidebar()
        self._build_main_area()
        
        # Inizializza i campi con la config
        self.google_key_entry.insert(0, self.config.get("google_api_key", ""))
        self.ors_key_entry.insert(0, self.config.get("openrouteservice_api_key", ""))
        self.provider_var.set(self.config.get("default_provider", "google"))
        
        self.current_pins = []
        self.current_polyline = None
        
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(9, weight=1) # Spacer
        
        lbl_title = ctk.CTkLabel(self.sidebar, text="Impostazioni", font=ctk.CTkFont(size=20, weight="bold"))
        lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Provider Selection
        self.provider_var = ctk.StringVar(value="google")
        lbl_prov = ctk.CTkLabel(self.sidebar, text="Provider:")
        lbl_prov.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.provider_menu = ctk.CTkOptionMenu(self.sidebar, values=["google", "openrouteservice"], variable=self.provider_var)
        self.provider_menu.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="ew")
        
        # API Keys
        lbl_gkey = ctk.CTkLabel(self.sidebar, text="Google API Key:")
        lbl_gkey.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.google_key_entry = ctk.CTkEntry(self.sidebar, show="*")
        self.google_key_entry.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="ew")
        
        lbl_orskey = ctk.CTkLabel(self.sidebar, text="OpenRouteService API Key:")
        lbl_orskey.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ors_key_entry = ctk.CTkEntry(self.sidebar, show="*")
        self.ors_key_entry.grid(row=6, column=0, padx=20, pady=(5, 10), sticky="ew")
        
        # Mode Selection
        self.mode_var = ctk.StringVar(value="nearest")
        lbl_mode = ctk.CTkLabel(self.sidebar, text="Modalità:")
        lbl_mode.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        self.mode_menu = ctk.CTkOptionMenu(self.sidebar, values=["Trova il più vicino", "Commesso Viaggiatore (TSP)"], variable=self.mode_var)
        self.mode_menu.grid(row=8, column=0, padx=20, pady=(5, 10), sticky="ew")
        
        # Save config button
        btn_save = ctk.CTkButton(self.sidebar, text="Salva Impostazioni", command=self.save_settings)
        btn_save.grid(row=10, column=0, padx=20, pady=10, sticky="ew")
        
    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.main_frame.grid_columnconfigure(0, weight=1) # Form and results
        self.main_frame.grid_columnconfigure(1, weight=2) # Map
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        self._build_left_panel()
        self._build_map_panel()
        
    def _build_left_panel(self):
        self.left_panel = ctk.CTkFrame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.left_panel.grid_rowconfigure(3, weight=1) # Results list gets weight
        
        # Origin
        lbl_origin = ctk.CTkLabel(self.left_panel, text="Origine:", font=ctk.CTkFont(weight="bold"))
        lbl_origin.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.origin_entry = ctk.CTkEntry(self.left_panel, placeholder_text="Es: Milano, Piazza Duomo")
        self.origin_entry.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")
        
        # Destinations
        dest_header_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        dest_header_frame.grid(row=2, column=0, sticky="ew", padx=10)
        
        lbl_dest = ctk.CTkLabel(dest_header_frame, text="Destinazioni:", font=ctk.CTkFont(weight="bold"))
        lbl_dest.pack(side="left")
        
        btn_import = ctk.CTkButton(dest_header_frame, text="Importa CSV", width=100, command=self.import_csv)
        btn_import.pack(side="right")
        
        btn_add = ctk.CTkButton(dest_header_frame, text="+ Aggiungi", width=100, command=lambda: self.dest_list.add_entry())
        btn_add.pack(side="right", padx=5)
        
        self.dest_list = DestinationList(self.left_panel, height=200)
        self.dest_list.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        
        # Action button
        self.btn_calculate = ctk.CTkButton(self.left_panel, text="Calcola Percorsi", command=self.start_calculation)
        self.btn_calculate.grid(row=4, column=0, padx=10, pady=10, sticky="ew")
        
        # Results area
        self.results_area = ctk.CTkScrollableFrame(self.left_panel, height=200)
        self.results_area.grid(row=5, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
    def _build_map_panel(self):
        self.map_panel = ctk.CTkFrame(self.main_frame)
        self.map_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        self.map_widget = tkintermapview.TkinterMapView(self.map_panel, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        # Posizione iniziale (Italia)
        self.map_widget.set_position(41.8719, 12.5674) 
        self.map_widget.set_zoom(6)
        
    def save_settings(self):
        self.config["google_api_key"] = self.google_key_entry.get().strip()
        self.config["openrouteservice_api_key"] = self.ors_key_entry.get().strip()
        self.config["default_provider"] = self.provider_var.get()
        if config_manager.save_config(self.config):
            messagebox.showinfo("Successo", "Impostazioni salvate correttamente.")
        else:
            messagebox.showerror("Errore", "Impossibile salvare le impostazioni.")
            
    def import_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            addresses = data_importer.import_addresses_from_csv(file_path)
            if addresses:
                self.dest_list.load_from_list(addresses)
                messagebox.showinfo("Importazione", f"Importati {len(addresses)} indirizzi.")
            else:
                messagebox.showwarning("Attenzione", "Nessun indirizzo trovato o formato file non valido.")

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
            messagebox.showerror("Errore", "Inserisci l'indirizzo di origine.")
            return
            
        if not destinations:
            messagebox.showerror("Errore", "Inserisci almeno una destinazione.")
            return
            
        api_key = self.google_key_entry.get().strip() if provider == "google" else self.ors_key_entry.get().strip()
        if not api_key:
            messagebox.showerror("Errore", f"Inserisci l'API Key per {provider}.")
            return
            
        self.btn_calculate.configure(state="disabled", text="Calcolo in corso...")
        self.clear_results()
        self.clear_map()
        
        lbl_loading = ctk.CTkLabel(self.results_area, text="Attendere, comunicazione con le API in corso...")
        lbl_loading.pack(pady=20)
        
        # Avvia in un thread separato
        threading.Thread(target=self.run_api_request, args=(provider, mode, api_key, origin, destinations), daemon=True).start()
        
    def run_api_request(self, provider, mode, api_key, origin, destinations):
        is_tsp = "Commesso Viaggiatore" in mode
        
        if provider == "google":
            engine = maps_engine
        else:
            engine = openroute_engine
            
        if is_tsp:
            res = engine.get_optimized_route(api_key, origin, destinations)
        else:
            res = engine.get_distance_matrix(api_key, origin, destinations)
            
        # Torna al main thread per aggiornare la GUI
        self.after(0, self.display_results, res, is_tsp)
        
    def display_results(self, response, is_tsp):
        self.clear_results()
        self.btn_calculate.configure(state="normal", text="Calcola Percorsi")
        
        if response.get("status") == "ERROR":
            messagebox.showerror("Errore API", response.get("error_message", "Errore sconosciuto"))
            return
            
        results = response.get("results", [])
        origin_coords = response.get("origin_coords")
        
        # Aggiorna la mappa con l'origine
        if origin_coords:
            p = self.map_widget.set_marker(origin_coords[0], origin_coords[1], text="Origine", marker_color_outside="green")
            self.current_pins.append(p)
            self.map_widget.set_position(origin_coords[0], origin_coords[1])
            self.map_widget.set_zoom(10)
            
        if is_tsp:
            # Mostra risultati TSP
            tot_dist = response.get("total_distance", "N/A")
            tot_dur = response.get("total_duration", "N/A")
            
            tot_lbl = ctk.CTkLabel(self.results_area, text=f"Totale Viaggio: {tot_dist} - {tot_dur}", font=ctk.CTkFont(weight="bold"))
            tot_lbl.pack(pady=5)
            
            for res in results:
                ResultCard(self.results_area, res["destination"], res["distance_text"], res["duration_text"], step=res.get("step")).pack(fill="x", pady=2)
                
            # Disegna la polyline se presente
            # Se è Google, abbiamo polyline. Se è ORS, abbiamo polyline_path
            polyline_path = response.get("polyline_path")
            if not polyline_path and response.get("polyline"):
                # Decodifica google polyline (se la si vuole implementare) - per ora ci accontentiamo dei marker
                # TkinterMapView set_path necessita di coordinate decodificate. Implementerò un fallback o decodifica.
                try:
                    import polyline as pl
                    polyline_path = pl.decode(response.get("polyline"))
                except ImportError:
                    print("pip install polyline per visualizzare i percorsi google")
            
            if polyline_path:
                self.current_polyline = self.map_widget.set_path(polyline_path)
                
            # Aggiunge i pin delle tappe
            # Potremmo farlo ricavando le coordinate dalla risposta (non sempre disponibili facilmente per ogni step se non richieste esplicitamente, ma possiamo usare il fallback)
            # Per semplificare, in modalità TSP disegniamo la linea.
                
        else:
            # Mostra risultati Nearest
            for res in results:
                if res.get("error"):
                    ResultCard(self.results_area, res["destination"], "", "", is_error=True).pack(fill="x", pady=2)
                else:
                    ResultCard(self.results_area, res["destination"], res["distance_text"], res["duration_text"]).pack(fill="x", pady=2)
                    
            # Aggiungiamo il pin della destinazione più vicina (il primo risultato) se possiamo geocodificarlo
            # Visto che non abbiamo le coordinate esatte nella response basic della matrice, per la prima release possiamo mostrare solo l'origine, oppure lasciare all'utente di vedere l'indirizzo.
            # In fututo potremmo aggiungere la geocodifica inversa per il pin.
            
        messagebox.showinfo("Completato", "Calcolo completato.")
