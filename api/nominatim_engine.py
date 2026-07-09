import requests
import time
from math import radians, cos, sin, asin, sqrt
from utils.logger import get_logger
from utils.geo_cache import get_cached_coords, set_cached_coords

logger = get_logger("nominatim")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "nearest-destination-finder/1.0"}

_last_request_time = 0.0


def _geocode_single(address: str):
    cached = get_cached_coords(address)
    if cached:
        return cached

    global _last_request_time
    try:
        now = time.time()
        time_since_last = now - _last_request_time
        if time_since_last < 1.1:
            time.sleep(1.1 - time_since_last)

        logger.info(f"Geocoding address via Nominatim: {address}")
        r = requests.get(
            _NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers=_HEADERS,
            timeout=10,
        )
        _last_request_time = time.time()

        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            coords = (float(data[0]["lat"]), float(data[0]["lon"]))
            set_cached_coords(address, coords)
            return coords
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error geocoding '{address}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error geocoding '{address}': {e}", exc_info=True)

    logger.warning(f"Geocoding failed for: {address}")
    return None


def _geocode_all(addresses: list) -> list:
    """Sequential geocoding — Nominatim enforces max 1 req/sec."""
    return [_geocode_single(addr) for addr in addresses]


def geocode_address(address: str):
    return _geocode_single(address)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(min(1.0, a)))


def _fmt_dist(km: float) -> str:
    return f"{km:.1f} km (straight-line)"


def get_distance_matrix(api_key, origin: str, destinations: list, transport_mode="Driving", departure_time=None) -> dict:
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
        logger.error(f"Distance matrix failed: Could not geocode origin '{origin}'")
        return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

    results = []
    for i, dest in enumerate(destinations):
        dest_coords = coords[i + 1]
        if dest_coords:
            dist_km = _haversine_km(*origin_coords, *dest_coords)
            results.append({
                "destination": dest,
                "original_destination": dest,
                "distance_text": _fmt_dist(dist_km),
                "distance_value": dist_km * 1000,
                "duration_text": "N/A",
                "duration_value": float("inf"),
                "dest_coords": dest_coords,
            })
        else:
            results.append({
                "destination": dest,
                "original_destination": dest,
                "distance_text": "N/A",
                "distance_value": float("inf"),
                "duration_text": "N/A",
                "duration_value": float("inf"),
                "error": "Geocoding failed",
            })

    results.sort(key=lambda x: x["distance_value"])
    return {"status": "OK", "results": results, "origin_coords": origin_coords}


def get_optimized_route(api_key, origin: str, destinations: list, transport_mode="Driving", departure_time=None, round_trip=False) -> dict:
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
        logger.error(f"Optimized route failed: Could not geocode origin '{origin}'")
        return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

    valid_dests = []
    valid_coords = []
    for i, dest in enumerate(destinations):
        if coords[i + 1]:
            valid_dests.append(dest)
            valid_coords.append(coords[i + 1])

    if not valid_dests:
        logger.error("Optimized route failed: Could not geocode any destinations")
        return {"status": "ERROR", "error_message": "Could not geocode any destinations"}

    n = len(valid_dests)
    dist_matrix = [
        [_haversine_km(*valid_coords[i], *valid_coords[j]) for j in range(n)]
        for i in range(n)
    ]
    origin_to = [_haversine_km(*origin_coords, *valid_coords[j]) for j in range(n)]

    # Greedy nearest-neighbor TSP
    visited = [False] * n
    order = []
    row = origin_to
    for _ in range(n):
        best = min((i for i in range(n) if not visited[i]), key=lambda i: row[i])
        order.append(best)
        visited[best] = True
        row = dist_matrix[best]

    # Apply 2-Opt local search optimization
    if n > 2:
        full_coords = [origin_coords] + valid_coords
        full_order = [0] + [idx + 1 for idx in order]
        improved = True
        iterations = 0
        while improved and iterations < 150:
            improved = False
            iterations += 1
            for i in range(1, len(full_order) - 1):
                for j in range(i + 1, len(full_order)):
                    if j - i == 1:
                        continue
                    a, b = full_order[i - 1], full_order[i]
                    c, d = full_order[j - 1], full_order[j]
                    old_d = _haversine_km(*full_coords[a], *full_coords[b]) + _haversine_km(*full_coords[c], *full_coords[d])
                    new_d = _haversine_km(*full_coords[a], *full_coords[c]) + _haversine_km(*full_coords[b], *full_coords[d])
                    if new_d + 1e-6 < old_d:
                        full_order[i:j] = full_order[i:j][::-1]
                        improved = True
                        break
                if improved:
                    break
        order = [idx - 1 for idx in full_order[1:]]

    results = []
    total_dist = 0.0
    prev = origin_coords
    for step, idx in enumerate(order):
        dist_km = _haversine_km(*prev, *valid_coords[idx])
        total_dist += dist_km
        results.append({
            "destination": valid_dests[idx],
            "distance_text": _fmt_dist(dist_km),
            "distance_value": dist_km * 1000,
            "duration_text": "N/A",
            "duration_value": float("inf"),
            "step": step + 1,
            "dest_coords": valid_coords[idx],
        })
        prev = valid_coords[idx]

    if round_trip:
        dist_km = _haversine_km(*prev, *origin_coords)
        total_dist += dist_km
        results.append({
            "destination": origin,
            "distance_text": _fmt_dist(dist_km),
            "distance_value": dist_km * 1000,
            "duration_text": "N/A",
            "duration_value": float("inf"),
            "step": len(order) + 1,
            "dest_coords": origin_coords,
        })
        polyline_path = [origin_coords] + [valid_coords[i] for i in order] + [origin_coords]
    else:
        polyline_path = [origin_coords] + [valid_coords[i] for i in order]

    return {
        "status": "OK",
        "results": results,
        "polyline_path": polyline_path,
        "origin_coords": origin_coords,
        "total_distance": f"{total_dist:.1f} km (straight-line)",
        "total_duration": "N/A",
    }
