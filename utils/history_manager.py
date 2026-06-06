import json
import os
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(_ROOT, "route_history.json")


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading route history: {e}")
        return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving route history: {e}")
        return False


def add_run(origin, destinations, provider, mode, transport_mode, departure_time_str, round_trip, response, is_tsp):
    history = load_history()
    
    # Generate unique ID
    run_id = 1 if not history else max(item.get("id", 0) for item in history) + 1
    
    # Calculate total distance and duration from results if not explicitly provided
    results = response.get("results", [])
    total_dist_val = 0
    valid_results = 0
    for r in results:
        dist_val = r.get("distance_value")
        if dist_val is not None and dist_val != float('inf') and not isinstance(dist_val, str):
            total_dist_val += dist_val
            valid_results += 1

    # Find durations for fallback
    total_dur_val = 0
    for r in results:
        dur_val = r.get("duration_value")
        if dur_val is not None and dur_val != float('inf') and not isinstance(dur_val, str):
            total_dur_val += dur_val

    # Format fallback total distance and duration
    if is_tsp:
        total_distance = response.get("total_distance") or f"{total_dist_val / 1000.0:.1f} km"
        total_duration = response.get("total_duration")
        if not total_duration or total_duration == "N/A":
            hours = total_dur_val // 3600
            minutes = (total_dur_val % 3600) // 60
            if hours > 0:
                total_duration = f"{hours} h {minutes} min"
            elif minutes > 0:
                total_duration = f"{minutes} min"
            else:
                total_duration = "N/A"
    else:
        suffix = " (straight-line)" if provider == "Free (Nominatim)" else ""
        total_distance = f"{total_dist_val / 1000.0:.1f} km{suffix}"
        hours = total_dur_val // 3600
        minutes = (total_dur_val % 3600) // 60
        if hours > 0:
            total_duration = f"{hours} h {minutes} min"
        else:
            total_duration = f"{minutes} min"

    # Auto-generate a descriptive run name
    timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_tag = "TSP" if is_tsp else "Nearest"
    run_name = f"Run #{run_id}: {mode_tag} {transport_mode} ({total_distance})"
    
    # Ensure coords are stored properly as list of lists
    polyline_path = response.get("polyline_path")
    if polyline_path:
        polyline_path = [[c[0], c[1]] for c in polyline_path]

    origin_coords = response.get("origin_coords")
    if origin_coords:
        origin_coords = [origin_coords[0], origin_coords[1]]

    formatted_results = []
    for r in results:
        fr = r.copy()
        # Convert dest_coords tuple to list for JSON serialization
        d_coords = r.get("dest_coords")
        if d_coords:
            fr["dest_coords"] = [d_coords[0], d_coords[1]]
        # Replace float('inf') — not JSON-serializable — with None
        for field in ("distance_value", "duration_value"):
            if fr.get(field) == float("inf"):
                fr[field] = None
        formatted_results.append(fr)

    run_entry = {
        "id": run_id,
        "name": run_name,
        "timestamp": timestamp_now,
        "origin": origin,
        "destinations": destinations,
        "provider": provider,
        "mode": mode,
        "transport_mode": transport_mode,
        "departure_time": departure_time_str,
        "round_trip": round_trip,
        "results": formatted_results,
        "polyline_path": polyline_path,
        "origin_coords": origin_coords,
        "total_distance": total_distance,
        "total_duration": total_duration,
        "is_tsp": is_tsp
    }
    
    history.append(run_entry)
    save_history(history)
    return run_entry


def rename_run(run_id, new_name):
    history = load_history()
    for item in history:
        if item.get("id") == run_id:
            item["name"] = new_name
            save_history(history)
            return True
    return False


def delete_run(run_id):
    history = load_history()
    new_history = [item for item in history if item.get("id") != run_id]
    if len(new_history) != len(history):
        save_history(new_history)
        return True
    return False


def clear_history():
    return save_history([])
