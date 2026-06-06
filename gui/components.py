import customtkinter as ctk


class DestinationList(ctk.CTkScrollableFrame):
    def __init__(self, master, on_enter_pressed=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_enter_pressed = on_enter_pressed
        self.entries = []
        self.overrides = {}
        self.settings_btns = {}
        self.add_entry()

    def add_entry(self, default_text="", transport_mode="Default", departure_time="Default"):
        row_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        entry = ctk.CTkEntry(row_frame, placeholder_text="Enter destination...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        if default_text:
            entry.insert(0, default_text)

        if self.on_enter_pressed:
            entry.bind("<Return>", lambda event: self.on_enter_pressed())

        # Settings gear button
        settings_btn = ctk.CTkButton(row_frame, text="⚙", width=30, fg_color="gray60", hover_color="gray70",
                                     command=lambda e=entry: self.open_settings(e))
        settings_btn.pack(side="left", padx=(0, 5))
        
        # Color indicator if loaded with overrides
        if transport_mode != "Default" or departure_time != "Default":
            settings_btn.configure(fg_color="#3498db", text="⚙ (Custom)")

        # Delete button
        ctk.CTkButton(row_frame, text="✕", width=30,
                      command=lambda f=row_frame, e=entry: self.remove_entry(f, e)
                      ).pack(side="right")

        self.entries.append(entry)
        self.overrides[entry] = {
            "transport_mode": transport_mode,
            "departure_time": departure_time
        }
        self.settings_btns[entry] = settings_btn

    def remove_entry(self, frame, entry):
        if len(self.entries) > 1:
            frame.destroy()
            self.entries.remove(entry)
            self.overrides.pop(entry, None)
            self.settings_btns.pop(entry, None)

    def get_destinations(self):
        return [e.get().strip() for e in self.entries if e.get().strip()]

    def get_destinations_with_settings(self):
        result = []
        for entry in self.entries:
            addr = entry.get().strip()
            if addr:
                ov = self.overrides.get(entry, {"transport_mode": "Default", "departure_time": "Default"})
                result.append({
                    "address": addr,
                    "transport_mode": ov.get("transport_mode", "Default"),
                    "departure_time": ov.get("departure_time", "Default")
                })
        return result

    def clear_all(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.entries.clear()
        self.overrides.clear()
        self.settings_btns.clear()
        self.add_entry()

    def load_from_list(self, dest_list):
        for widget in self.winfo_children():
            widget.destroy()
        self.entries.clear()
        self.overrides.clear()
        self.settings_btns.clear()
        
        for item in dest_list:
            if isinstance(item, dict):
                addr = item.get("address", "")
                mode = item.get("transport_mode", "Default")
                dep = item.get("departure_time", "Default")
                self.add_entry(addr, mode, dep)
            else:
                self.add_entry(str(item))
                
        if not dest_list:
            self.add_entry()

    def open_settings(self, entry):
        addr = entry.get().strip()
        display_name = addr if addr else "This Destination"
        
        # Create popup window
        popup = ctk.CTkToplevel(self)
        popup.title(f"Settings: {display_name[:30]}")
        popup.geometry("380x250")
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        
        popup.update_idletasks()
        main_win = self.winfo_toplevel()
        x = main_win.winfo_x() + (main_win.winfo_width() - 380) // 2
        y = main_win.winfo_y() + (main_win.winfo_height() - 250) // 2
        popup.geometry(f"+{x}+{y}")
        
        current_ov = self.overrides.get(entry, {"transport_mode": "Default", "departure_time": "Default"})
        
        ctk.CTkLabel(popup, text="Destination Custom Overrides", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        
        ctk.CTkLabel(popup, text="Transport Mode:").pack(anchor="w", padx=20)
        mode_var = ctk.StringVar(value=current_ov.get("transport_mode", "Default"))
        mode_opt = ctk.CTkOptionMenu(popup, values=["Default", "Driving", "Walking", "Bicycling", "Transit"], variable=mode_var)
        mode_opt.pack(fill="x", padx=20, pady=(2, 10))
        
        ctk.CTkLabel(popup, text="Departure Time (YYYY-MM-DD HH:MM or 'now'):").pack(anchor="w", padx=20)
        dep_var = ctk.StringVar(value=current_ov.get("departure_time", "Default"))
        dep_entry = ctk.CTkEntry(popup, textvariable=dep_var)
        dep_entry.pack(fill="x", padx=20, pady=(2, 15))
        
        def save_action():
            self.overrides[entry] = {
                "transport_mode": mode_var.get(),
                "departure_time": dep_var.get().strip()
            }
            btn = self.settings_btns.get(entry)
            if btn:
                is_custom = (mode_var.get() != "Default" or dep_var.get().strip() != "Default")
                if is_custom:
                    btn.configure(fg_color="#3498db", text="⚙ (Custom)")
                else:
                    btn.configure(fg_color="gray60", text="⚙")
            popup.destroy()
            
        ctk.CTkButton(popup, text="Apply Settings", command=save_action).pack(pady=10)


class ResultCard(ctk.CTkFrame):
    def __init__(self, master, destination, distance, duration,
                 step=None, is_error=False, error_text="Calculation error", **kwargs):
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ("gray70", "gray30"))
        super().__init__(master, **kwargs)

        header_text = f"Stop {step}: {destination}" if step is not None else destination
        ctk.CTkLabel(self, text=header_text,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w", justify="left", wraplength=280).pack(
            fill="x", padx=10, pady=(8, 2))

        if is_error:
            ctk.CTkLabel(self, text=error_text,
                         text_color="red", anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))
        else:
            info = ctk.CTkFrame(self, fg_color="transparent")
            info.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkLabel(info, text=f"Distance: {distance}",
                         text_color=("gray30", "gray70")).pack(side="left")
            ctk.CTkLabel(info, text=f"Time: {duration}",
                         text_color=("gray30", "gray70")).pack(side="right")
