import customtkinter as ctk

class DestinationList(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.entries = []
        self.add_entry() # Start with one empty entry
        
    def add_entry(self, default_text=""):
        row_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)
        
        entry = ctk.CTkEntry(row_frame, placeholder_text="Inserisci destinazione...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        if default_text:
            entry.insert(0, default_text)
            
        remove_btn = ctk.CTkButton(row_frame, text="X", width=30, 
                                   command=lambda f=row_frame, e=entry: self.remove_entry(f, e))
        remove_btn.pack(side="right")
        
        self.entries.append(entry)
        
    def remove_entry(self, frame, entry):
        if len(self.entries) > 1:
            frame.destroy()
            self.entries.remove(entry)
            
    def get_destinations(self):
        return [e.get().strip() for e in self.entries if e.get().strip()]
        
    def clear_all(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.entries.clear()
        self.add_entry()
        
    def load_from_list(self, dest_list):
        self.clear_all()
        # Remove the default empty one created by clear_all if we have items
        if dest_list:
            # We don't really want to destroy the first if we just use it, but clear_all already creates one.
            # Let's just destroy everything and recreate
            for widget in self.winfo_children():
                widget.destroy()
            self.entries.clear()
            
            for dest in dest_list:
                self.add_entry(dest)
        else:
            if not self.entries:
                 self.add_entry()

class ResultCard(ctk.CTkFrame):
    def __init__(self, master, destination, distance, duration, step=None, is_error=False, **kwargs):
        super().__init__(master, **kwargs)
        
        self.pack(fill="x", pady=5, padx=5)
        
        # Header (Step / Destination)
        header_text = destination
        if step is not None:
            header_text = f"Tappa {step}: {destination}"
            
        header_lbl = ctk.CTkLabel(self, text=header_text, font=ctk.CTkFont(size=14, weight="bold"), anchor="w", justify="left")
        header_lbl.pack(fill="x", padx=10, pady=(5, 0))
        
        if is_error:
            err_lbl = ctk.CTkLabel(self, text="Errore nel calcolo", text_color="red")
            err_lbl.pack(fill="x", padx=10, pady=(0, 5))
        else:
            # Info (Distance, Duration)
            info_frame = ctk.CTkFrame(self, fg_color="transparent")
            info_frame.pack(fill="x", padx=10, pady=(0, 5))
            
            dist_lbl = ctk.CTkLabel(info_frame, text=f"Distanza: {distance}")
            dist_lbl.pack(side="left")
            
            dur_lbl = ctk.CTkLabel(info_frame, text=f"Tempo: {duration}")
            dur_lbl.pack(side="right")
