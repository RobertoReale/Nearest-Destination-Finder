import customtkinter as ctk


class DestinationList(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.entries = []
        self.add_entry()

    def add_entry(self, default_text=""):
        row_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        entry = ctk.CTkEntry(row_frame, placeholder_text="Enter destination...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        if default_text:
            entry.insert(0, default_text)

        ctk.CTkButton(row_frame, text="✕", width=30,
                      command=lambda f=row_frame, e=entry: self.remove_entry(f, e)
                      ).pack(side="right")

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
        for widget in self.winfo_children():
            widget.destroy()
        self.entries.clear()
        for dest in dest_list:
            self.add_entry(dest)
        if not dest_list:
            self.add_entry()


class ResultCard(ctk.CTkFrame):
    def __init__(self, master, destination, distance, duration,
                 step=None, is_error=False, **kwargs):
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ("gray70", "gray30"))
        super().__init__(master, **kwargs)

        header_text = f"Stop {step}: {destination}" if step is not None else destination
        ctk.CTkLabel(self, text=header_text,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w", justify="left", wraplength=280).pack(
            fill="x", padx=10, pady=(8, 2))

        if is_error:
            ctk.CTkLabel(self, text="Calculation error",
                         text_color="red", anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))
        else:
            info = ctk.CTkFrame(self, fg_color="transparent")
            info.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkLabel(info, text=f"Distance: {distance}",
                         text_color=("gray30", "gray70")).pack(side="left")
            ctk.CTkLabel(info, text=f"Time: {duration}",
                         text_color=("gray30", "gray70")).pack(side="right")
