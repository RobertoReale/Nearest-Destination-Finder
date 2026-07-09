import requests
import time
from math import radians, cos, sin, asin, sqrt
from utils.logger import get_logger
from api.nominatim_engine import _geocode_all, _haversine_km

logger = get_logger("osrm")

_OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
_OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"
_HEADERS = {"User-Agent": "nearest-destination-finder/1.0"}


def _format_distance_duration(dist_meters: float, dur_seconds: float) -> tuple[str, str]:
    dist_text = f"{dist_meters / 1000.0:.1f} km"
    hours = int(dur_seconds // 3600)
    minutes = int((dur_seconds % 3600) // 60)
    if hours > 0:
        dur_text = f"{hours} h {minutes} min"
    else:
        dur_text = f"{minutes} min" if minutes > 0 else "< 1 min"
    return dist_text, dur_text


def geocode_address(api_key, address: str):
    """Uses Nominatim OSM geocoder for free address lookup."""
    from api.nominatim_engine import geocode_address as nom_geocode
    return nom_geocode(address)


def _get_osrm_table(coords_list: list[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]]] | None:
    """Fetches distance (meters) and duration (seconds) matrices using OSRM Table API.
    coords_list: list of (lat, lon) tuples.
    Returns (dist_matrix, dur_matrix) or None if API fails.
    """
    if not coords_list or len(coords_list) < 2:
        return None
    try:
        # OSRM expects {lon},{lat};{lon},{lat}...
        coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords_list)
        logger.info(f"Fetching OSRM distance table for {len(coords_list)} points...")
        r = requests.get(
            f"{_OSRM_TABLE_URL}/{coords_str}",
            params={"annotations": "distance,duration"},
            headers=_HEADERS,
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == "Ok" and "distances" in data and "durations" in data:
                return data["distances"], data["durations"]
    except Exception as e:
        logger.warning(f"OSRM Table API failed or timed out: {e}. Falling back to haversine estimation.")
    return None


def _run_2opt(dist_matrix: list[list[float]], initial_order: list[int], round_trip: bool) -> list[int]:
    """Applies 2-Opt local search optimization over the given TSP order.
    Returns the optimized order indices.
    """
    n = len(initial_order)
    if n <= 2:
        return initial_order

    order = list(initial_order)
    improved = True
    iterations = 0
    max_iterations = 200  # Prevent infinite loop on edge cases

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                a, b = order[i - 1], order[i]
                c, d = order[j - 1], order[j]

                old_dist = dist_matrix[a][b] + dist_matrix[c][d]
                new_dist = dist_matrix[a][c] + dist_matrix[b][d]

                if new_dist + 1e-6 < old_dist:
                    order[i:j] = order[i:j][::-1]
                    improved = True
                    break
            if improved:
                break

    return order


def get_distance_matrix(api_key, origin: str, destinations: list, transport_mode="Driving", departure_time=None) -> dict:
    """Calculates road-accurate distance matrix from origin to destinations via OSRM or Haversine fallback."""
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
        logger.error(f"OSRM Distance matrix failed: Could not geocode origin '{origin}'")
        return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

    valid_indices = []
    locations = [origin_coords]
    for i, dest in enumerate(destinations):
        if coords[i + 1]:
            valid_indices.append(i)
            locations.append(coords[i + 1])

    if not valid_indices:
        logger.error("OSRM Distance matrix failed: Could not geocode any destinations")
        return {"status": "ERROR", "error_message": "Could not geocode any destinations"}

    table_res = _get_osrm_table(locations)

    results = []
    valid_idx = 1
    for i, dest in enumerate(destinations):
        dest_coords = coords[i + 1]
        if not dest_coords:
            results.append({
                "destination": dest,
                "original_destination": dest,
                "distance_text": "N/A",
                "distance_value": float("inf"),
                "duration_text": "N/A",
                "duration_value": float("inf"),
                "error": "Geocoding failed",
            })
        else:
            if table_res and table_res[0][0][valid_idx] is not None:
                dist_val = float(table_res[0][0][valid_idx])
                dur_val = float(table_res[1][0][valid_idx])
                dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                if transport_mode == "Walking":
                    dur_val = (dist_val / 1000.0) / 5.0 * 3600
                    dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                elif transport_mode == "Bicycling":
                    dur_val = (dist_val / 1000.0) / 15.0 * 3600
                    dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
            else:
                dist_km = _haversine_km(*origin_coords, *dest_coords)
                dist_val = dist_km * 1000.0
                speed_kmh = 5.0 if transport_mode == "Walking" else (15.0 if transport_mode == "Bicycling" else 50.0)
                dur_val = (dist_km / speed_kmh) * 3600.0
                dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                if not table_res:
                    dist_text += " (est.)"

            results.append({
                "destination": dest,
                "original_destination": dest,
                "distance_text": dist_text,
                "distance_value": dist_val,
                "duration_text": dur_text,
                "duration_value": dur_val,
                "dest_coords": dest_coords,
            })
            valid_idx += 1

    if transport_mode == "Transit":
        results.sort(key=lambda x: x.get("duration_value", float("inf")))
    else:
        results.sort(key=lambda x: x.get("distance_value", float("inf")))

    return {"status": "OK", "results": results, "origin_coords": origin_coords}


def get_optimized_route(api_key, origin: str, destinations: list, transport_mode="Driving", departure_time=None, round_trip=False) -> dict:
    """Calculates an optimized TSP route using OSRM Table + Greedy Nearest-Neighbor + 2-Opt Local Search optimization."""
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
        logger.error(f"OSRM Optimized route failed: Could not geocode origin '{origin}'")
        return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

    valid_dests = []
    valid_coords = []
    for i, dest in enumerate(destinations):
        if coords[i + 1]:
            valid_dests.append(dest)
            valid_coords.append(coords[i + 1])

    if not valid_dests:
        logger.error("OSRM Optimized route failed: Could not geocode any destinations")
        return {"status": "ERROR", "error_message": "Could not geocode any destinations"}

    locations = [origin_coords] + valid_coords
    n = len(valid_dests)

    table_res = _get_osrm_table(locations)
    if table_res:
        dist_matrix = table_res[0]
        dur_matrix = table_res[1]
    else:
        m = len(locations)
        dist_matrix = [
            [_haversine_km(*locations[i], *locations[j]) * 1000.0 for j in range(m)]
            for i in range(m)
        ]
        speed_kmh = 5.0 if transport_mode == "Walking" else (15.0 if transport_mode == "Bicycling" else 50.0)
        dur_matrix = [
            [(dist_matrix[i][j] / 1000.0) / speed_kmh * 3600.0 for j in range(m)]
            for i in range(m)
        ]

    visited = [False] * (n + 1)
    visited[0] = True
    order = []
    curr = 0
    for _ in range(n):
        best = min(
            (i for i in range(1, n + 1) if not visited[i]),
            key=lambda i: dist_matrix[curr][i]
        )
        order.append(best)
        visited[best] = True
        curr = best

    full_order = [0] + order
    optimized_full = _run_2opt(dist_matrix, full_order, round_trip)
    order = optimized_full[1:]

    results = []
    total_dist = 0.0
    total_dur = 0.0
    prev_idx = 0

    ordered_locations = [origin_coords] + [locations[idx] for idx in order]
    if round_trip:
        ordered_locations.append(origin_coords)

    polyline_path = None
    leg_details = None
    try:
        coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in ordered_locations)
        r = requests.get(
            f"{_OSRM_ROUTE_URL}/{coords_str}",
            params={"overview": "full", "geometries": "geojson", "steps": "true"},
            headers=_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route_obj = data["routes"][0]
                total_dist = float(route_obj.get("distance", 0))
                total_dur = float(route_obj.get("duration", 0))
                if "geometry" in route_obj and "coordinates" in route_obj["geometry"]:
                    polyline_path = [(lat, lon) for lon, lat in route_obj["geometry"]["coordinates"]]
                if "legs" in route_obj:
                    leg_details = route_obj["legs"]
    except Exception as e:
        logger.warning(f"OSRM Route geometry fetch failed: {e}. Using straight lines and table sums.")

    if not polyline_path:
        polyline_path = ordered_locations

    for step, idx in enumerate(order):
        if leg_details and step < len(leg_details):
            dist_val = float(leg_details[step].get("distance", 0))
            dur_val = float(leg_details[step].get("duration", 0))
        else:
            dist_val = float(dist_matrix[prev_idx][idx])
            dur_val = float(dur_matrix[prev_idx][idx])
            total_dist += dist_val
            total_dur += dur_val

        dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
        results.append({
            "destination": valid_dests[idx - 1],
            "distance_text": dist_text,
            "distance_value": dist_val,
            "duration_text": dur_text,
            "duration_value": dur_val,
            "step": step + 1,
            "dest_coords": locations[idx],
        })
        prev_idx = idx

    if round_trip:
        step_idx = len(order)
        if leg_details and step_idx < len(leg_details):
            dist_val = float(leg_details[step_idx].get("distance", 0))
            dur_val = float(leg_details[step_idx].get("duration", 0))
        else:
            dist_val = float(dist_matrix[prev_idx][0])
            dur_val = float(dur_matrix[prev_idx][0])
            total_dist += dist_val
            total_dur += dur_val

        dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
        results.append({
            "destination": origin,
            "distance_text": dist_text,
            "distance_value": dist_val,
            "duration_text": dur_text,
            "duration_value": dur_val,
            "step": len(order) + 1,
            "dest_coords": origin_coords,
        })

    total_dist_text, total_dur_text = _format_distance_duration(total_dist, total_dur)

    return {
        "status": "OK",
        "results": results,
        "polyline_path": polyline_path,
        "origin_coords": origin_coords,
        "total_distance": total_dist_text,
        "total_duration": total_dur_text,
    }
