import pytest
import customtkinter as ctk
from gui.components import DestinationList


def test_destination_list_overrides():
    # Initialize a dummy application for Tkinter context
    app = ctk.CTk()
    
    dest_list = DestinationList(app)
    
    # Initially 1 empty entry is created
    assert len(dest_list.entries) == 1
    
    # Add an entry with overrides
    dest_list.add_entry("Naples", "Walking", "18:00")
    assert len(dest_list.entries) == 2
    
    dest_data = dest_list.get_destinations_with_settings()
    # First entry is empty string, get_destinations_with_settings skips empty strings
    assert len(dest_data) == 1
    assert dest_data[0]["address"] == "Naples"
    assert dest_data[0]["transport_mode"] == "Walking"
    assert dest_data[0]["departure_time"] == "18:00"
    
    # Load from list containing both string and dict
    mixed_list = [
        "Rome",
        {"address": "Milan", "transport_mode": "Transit", "departure_time": "now"}
    ]
    dest_list.load_from_list(mixed_list)
    
    loaded_data = dest_list.get_destinations_with_settings()
    assert len(loaded_data) == 2
    
    assert loaded_data[0]["address"] == "Rome"
    assert loaded_data[0]["transport_mode"] == "Default"
    assert loaded_data[0]["departure_time"] == "Default"
    
    assert loaded_data[1]["address"] == "Milan"
    assert loaded_data[1]["transport_mode"] == "Transit"
    assert loaded_data[1]["departure_time"] == "now"
    
    # Destroy tkinter context
    app.destroy()


def test_destination_list_reorder():
    app = ctk.CTk()
    dest_list = DestinationList(app)
    dest_list.entries[0].insert(0, "Florence")
    dest_list.add_entry("Rome")
    dest_list.add_entry("Milan")
    
    # [Florence, Rome, Milan]
    assert dest_list.entries[0].get() == "Florence"
    assert dest_list.entries[1].get() == "Rome"
    
    # Move Florence down -> [Rome, Florence, Milan]
    dest_list.move_down(dest_list.entries[0])
    assert dest_list.entries[0].get() == "Rome"
    assert dest_list.entries[1].get() == "Florence"
    
    # Move Florence up -> [Florence, Rome, Milan]
    dest_list.move_up(dest_list.entries[1])
    assert dest_list.entries[0].get() == "Florence"
    assert dest_list.entries[1].get() == "Rome"
    
    app.destroy()

