import pytest
import os
from utils.history_manager import load_history, save_history, add_run, rename_run, delete_run, clear_history, HISTORY_FILE


@pytest.fixture(autouse=True)
def temp_history_file():
    # Back up existing history file
    backed_up = False
    if os.path.exists(HISTORY_FILE):
        os.rename(HISTORY_FILE, HISTORY_FILE + ".bak")
        backed_up = True
    
    # Initialize with clean state
    clear_history()
    
    yield
    
    # Clean up temp file
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        
    # Restore backup
    if backed_up:
        os.rename(HISTORY_FILE + ".bak", HISTORY_FILE)


def test_add_and_load_run():
    response = {
        "status": "OK",
        "origin_coords": (41.9028, 12.4964),
        "polyline_path": [(41.9028, 12.4964), (40.8518, 14.2681)],
        "total_distance": "220.0 km",
        "total_duration": "2 hours",
        "results": [
            {
                "destination": "Naples",
                "distance_value": 220000,
                "duration_value": 7200,
                "duration_text": "2 hours",
                "dest_coords": (40.8518, 14.2681)
            }
        ]
    }
    
    run = add_run(
        origin="Rome",
        destinations=["Naples"],
        provider="Free (Nominatim)",
        mode="Traveling Salesman (TSP)",
        transport_mode="Driving",
        departure_time_str="now",
        round_trip=False,
        response=response,
        is_tsp=True
    )
    
    assert run["name"].startswith("Run #1")
    assert run["origin"] == "Rome"
    assert run["destinations"] == ["Naples"]
    assert run["total_distance"] == "220.0 km"
    assert run["total_duration"] == "2 hours"
    assert run["polyline_path"] == [[41.9028, 12.4964], [40.8518, 14.2681]]
    
    history = load_history()
    assert len(history) == 1
    assert history[0]["id"] == run["id"]


def test_rename_run():
    response = {
        "status": "OK",
        "results": []
    }
    
    run = add_run("A", ["B"], "Nominatim", "TSP", "Driving", "now", False, response, True)
    run_id = run["id"]
    
    ok = rename_run(run_id, "Custom Run Name")
    assert ok is True
    
    history = load_history()
    assert history[0]["name"] == "Custom Run Name"


def test_delete_run():
    response = {
        "status": "OK",
        "results": []
    }
    
    run1 = add_run("A", ["B"], "Nominatim", "TSP", "Driving", "now", False, response, True)
    run2 = add_run("C", ["D"], "Nominatim", "TSP", "Driving", "now", False, response, True)
    
    assert len(load_history()) == 2
    
    ok = delete_run(run1["id"])
    assert ok is True
    
    history = load_history()
    assert len(history) == 1
    assert history[0]["id"] == run2["id"]


def test_clear_history():
    response = {
        "status": "OK",
        "results": []
    }
    
    add_run("A", ["B"], "Nominatim", "TSP", "Driving", "now", False, response, True)
    assert len(load_history()) == 1
    
    clear_history()
    assert len(load_history()) == 0
