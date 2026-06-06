import requests
import time
from math import radians, cos, sin, asin, sqrt

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "nearest-destination-finder/1.0"}


from functools import lru_cache

@lru_cache(maxsize=1024)
def _geocode_single(address: str):
    try:
        r = requests.get(
            _NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers=_HEADERS,
            timeout=10,
        )
        data = r.json()
        if data:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception:
        pass
    return None


def _geocode_all(addresses: list) -> list:
    """Sequential geocoding — Nominatim enforces max 1 req/sec."""
    results = []
    for i, addr in enumerate(addresses):
        results.append(_geocode_single(addr))
        if i < len(addresses) - 1:
            time.sleep(1.1)
    return results


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(min(1.0, a)))


def _fmt_dist(km: float) -> str:
    return f"{km:.1f} km (straight-line)"


def get_distance_matrix(api_key, origin: str, destinations: list) -> dict:
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
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


def get_optimized_route(api_key, origin: str, destinations: list) -> dict:
    coords = _geocode_all([origin] + destinations)
    origin_coords = coords[0]
    if not origin_coords:
        return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

    valid_dests = []
    valid_coords = []
    for i, dest in enumerate(destinations):
        if coords[i + 1]:
            valid_dests.append(dest)
            valid_coords.append(coords[i + 1])

    if not valid_dests:
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

    polyline_path = [origin_coords] + [valid_coords[i] for i in order]

    return {
        "status": "OK",
        "results": results,
        "polyline_path": polyline_path,
        "origin_coords": origin_coords,
        "total_distance": f"{total_dist:.1f} km (straight-line)",
        "total_duration": "N/A",
    }
