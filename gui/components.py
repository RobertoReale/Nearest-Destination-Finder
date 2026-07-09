import threading
import customtkinter as ctk
from api import autocomplete_engine


class AutocompleteEntry(ctk.CTkEntry):
    def __init__(self, master, on_select=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_select_callback = on_select
        self.selected_coords = None  # (lat, lon) if selected from dropdown
        self.popup = None
        self._popup_frame = None
        self._last_query = ""
        
        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<FocusOut>", self._on_focus_out)

    def _on_key_release(self, event):
        # Ignore navigation keys and Return
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            if event.keysym == "Escape":
                self._hide_popup()
            return
            
        query = self.get().strip()
        if len(query) < 3:
            self._hide_popup()
            return
            
        if query == self._last_query:
            return
            
        self._last_query = query
        threading.Thread(target=self._fetch_suggestions, args=(query,), daemon=True).start()

    def _fetch_suggestions(self, query):
        suggestions = autocomplete_engine.get_suggestions(query, limit=5)
        # Schedule GUI update on main thread
        try:
            self.after(0, lambda: self._show_popup(suggestions, query))
        except Exception:
            pass

    def _show_popup(self, suggestions, query):
        if not suggestions or self.get().strip() != query:
            self._hide_popup()
            return

        top = self.winfo_toplevel()
        if not self.popup or not self.popup.winfo_exists():
            self.popup = ctk.CTkToplevel(top)
            self.popup.overrideredirect(True)
            self.popup.attributes("-topmost", True)
            self._popup_frame = ctk.CTkFrame(self.popup, corner_radius=6, border_width=1, border_color="#3B82F6")
            self._popup_frame.pack(fill="both", expand=True)
        else:
            for child in self._popup_frame.winfo_children():
                child.destroy()

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        width = max(self.winfo_width(), 320)
        self.popup.geometry(f"{width}x{min(len(suggestions) * 36 + 8, 200)}+{x}+{y}")

        for s in suggestions:
            btn = ctk.CTkButton(
                self._popup_frame,
                text=f"📍 {s['display_text']}",
                anchor="w",
                height=32,
                fg_color="transparent",
                hover_color="#3B82F6",
                text_color=("gray10", "gray90"),
                command=lambda item=s: self._select_item(item),
            )
            btn.pack(fill="x", padx=4, pady=1)

        self.popup.deiconify()

    def _select_item(self, item):
        self.delete(0, "end")
        self.insert(0, item["display_text"])
        self.selected_coords = (item.get("lat"), item.get("lon"))
        self._hide_popup()
        if self.on_select_callback:
            self.on_select_callback(item)

    def _on_focus_out(self, event):
        try:
            self.after(250, self._hide_popup)
        except Exception:
            pass

    def _hide_popup(self):
        if self.popup and self.popup.winfo_exists():
            try:
                self.popup.destroy()
            except Exception:
                pass
        self.popup = None
        self._popup_frame = None


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

        entry = AutocompleteEntry(row_frame, placeholder_text="Enter destination...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        if default_text:
            entry.insert(0, default_text)

        if self.on_enter_pressed:
            entry.bind("<Return>", lambda event, cb=self.on_enter_pressed: cb())

        # Up button
        ctk.CTkButton(row_frame, text="▲", width=26, fg_color="gray50", hover_color="gray60",
                      command=lambda e=entry: self.move_up(e)).pack(side="left", padx=(0, 2))

        # Down button
        ctk.CTkButton(row_frame, text="▼", width=26, fg_color="gray50", hover_color="gray60",
                      command=lambda e=entry: self.move_down(e)).pack(side="left", padx=(0, 4))

        # Settings gear button
        settings_btn = ctk.CTkButton(row_frame, text="⚙", width=30, fg_color="gray60", hover_color="gray70",
                                     command=lambda e=entry: self.open_settings(e))
        settings_btn.pack(side="left", padx=(0, 4))
        
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

    def move_up(self, entry):
        if entry not in self.entries:
            return
        idx = self.entries.index(entry)
        if idx > 0:
            self._swap_entries(idx, idx - 1)

    def move_down(self, entry):
        if entry not in self.entries:
            return
        idx = self.entries.index(entry)
        if idx < len(self.entries) - 1:
            self._swap_entries(idx, idx + 1)

    def _swap_entries(self, idx1, idx2):
        e1, e2 = self.entries[idx1], self.entries[idx2]
        t1, t2 = e1.get(), e2.get()
        e1.delete(0, "end")
        e1.insert(0, t2)
        e2.delete(0, "end")
        e2.insert(0, t1)

        ov1, ov2 = self.overrides.get(e1, {}), self.overrides.get(e2, {})
        self.overrides[e1], self.overrides[e2] = ov2, ov1

        self._update_settings_btn(e1)
        self._update_settings_btn(e2)

    def _update_settings_btn(self, entry):
        btn = self.settings_btns.get(entry)
        if not btn:
            return
        ov = self.overrides.get(entry, {"transport_mode": "Default", "departure_time": "Default"})
        is_custom = (ov.get("transport_mode", "Default") != "Default" or ov.get("departure_time", "Default") != "Default")
        if is_custom:
            btn.configure(fg_color="#3498db", text="⚙ (Custom)")
        else:
            btn.configure(fg_color="gray60", text="⚙")

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
        popup = ctk.CTkToplevel(self.winfo_toplevel())
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
                 step=None, is_error=False, error_text="Calculation error",
                 on_click_map=None, coords=None, **kwargs):
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ("gray75", "gray25"))
        kwargs.setdefault("corner_radius", 6)
        super().__init__(master, **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(8, 2))

        if step is not None:
            badge = ctk.CTkLabel(
                header_frame, text=f" #{step} ", fg_color="#3498db", text_color="white",
                font=ctk.CTkFont(size=12, weight="bold"), corner_radius=4
            )
            badge.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(header_frame, text=destination,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w", justify="left", wraplength=280).pack(
            side="left", fill="x", expand=True)

        if not is_error and on_click_map and coords:
            ctk.CTkButton(
                header_frame, text="📍", width=30, height=24,
                fg_color="transparent", hover_color=("gray85", "gray30"),
                text_color=("#2980b9", "#5dade2"), font=ctk.CTkFont(size=14),
                command=lambda: on_click_map(coords)
            ).pack(side="right")

        if is_error:
            ctk.CTkLabel(self, text=error_text,
                         text_color="red", anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))
        else:
            info = ctk.CTkFrame(self, fg_color="transparent")
            info.pack(fill="x", padx=10, pady=(2, 8))
            ctk.CTkLabel(info, text=f"📏 {distance}",
                         text_color=("gray30", "gray70"), font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(info, text=f"⏱️ {duration}",
                         text_color=("gray30", "gray70"), font=ctk.CTkFont(size=12)).pack(side="right")
