"""
Autocomplete Engine — Real-time address suggestions via Photon (Komoot) and Nominatim.
Provides fast, debounced, search-as-you-type address completion with coordinates.
"""
from __future__ import annotations

import logging
import time
from typing import Any
import requests

logger = logging.getLogger("app_logger.autocomplete")

# In-memory cache: query string -> list of suggestion dicts
_CACHE: dict[str, list[dict[str, Any]]] = {}
_LAST_REQ_TIME: float = 0.0
_MIN_REQ_INTERVAL: float = 0.15  # 150ms rate limit protection for typing


def get_suggestions(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch address suggestions for a query string (min 3 chars).

    Returns a list of dicts:
        [
            {
                "display_text": "Piazza del Duomo, Milano, Lombardia, Italia",
                "name": "Piazza del Duomo",
                "city": "Milano",
                "lat": 45.4641,
                "lon": 9.1895,
            },
            ...
        ]
    """
    global _LAST_REQ_TIME

    if not query or not isinstance(query, str) or len(query.strip()) < 3:
        return []

    clean_q = query.strip().lower()
    if clean_q in _CACHE:
        return _CACHE[clean_q]

    # Enforce minimum request interval
    now = time.time()
    elapsed = now - _LAST_REQ_TIME
    if elapsed < _MIN_REQ_INTERVAL:
        time.sleep(_MIN_REQ_INTERVAL - elapsed)
    _LAST_REQ_TIME = time.time()

    suggestions = _fetch_photon(clean_q, limit)
    if not suggestions:
        suggestions = _fetch_nominatim(clean_q, limit)

    if suggestions:
        # Cache the results (limit cache size to 500 entries)
        if len(_CACHE) > 500:
            _CACHE.clear()
        _CACHE[clean_q] = suggestions

    return suggestions


def _fetch_photon(query: str, limit: int) -> list[dict[str, Any]]:
    """Fetch suggestions from Photon (Komoot) API."""
    url = "https://photon.komoot.io/api/"
    params = {"q": query, "limit": limit}
    headers = {"User-Agent": "NearestDestinationFinder/2.0 (Autocomplete Engine)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=3.5)
        if resp.status_code != 200:
            return []
        data = resp.json()
        features = data.get("features", [])
        results = []

        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", []) if geom else []
            if len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            name = props.get("name", "")
            street = props.get("street", "")
            housenumber = props.get("housenumber", "")
            city = props.get("city") or props.get("town") or props.get("village") or props.get("county", "")
            state = props.get("state", "")
            country = props.get("country", "")

            # Build readable display text
            parts = []
            if name and name != street:
                parts.append(name)
            if street:
                addr_line = f"{street} {housenumber}".strip() if housenumber else street
                if addr_line not in parts:
                    parts.append(addr_line)
            if city and city not in parts:
                parts.append(city)
            if state and state not in parts:
                parts.append(state)
            if country and country not in parts:
                parts.append(country)

            if not parts:
                continue

            display_text = ", ".join(parts)
            results.append({
                "display_text": display_text,
                "name": name or display_text,
                "city": city,
                "lat": lat,
                "lon": lon,
            })

        return results
    except Exception as e:
        logger.debug(f"Photon autocomplete error: {e}")
        return []


def _fetch_nominatim(query: str, limit: int) -> list[dict[str, Any]]:
    """Fallback to OpenStreetMap Nominatim search API."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
    }
    headers = {"User-Agent": "NearestDestinationFinder/2.0 (Autocomplete Engine fallback)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=4.0)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            lat_str = item.get("lat")
            lon_str = item.get("lon")
            display_name = item.get("display_name", "")
            if not lat_str or not lon_str or not display_name:
                continue

            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                continue

            # Format a slightly cleaner display name from Nominatim parts
            parts = [p.strip() for p in display_name.split(",") if p.strip()]
            display_text = ", ".join(parts[:4]) if len(parts) > 4 else display_name

            results.append({
                "display_text": display_text,
                "name": parts[0] if parts else display_text,
                "city": "",
                "lat": lat,
                "lon": lon,
            })

        return results
    except Exception as e:
        logger.debug(f"Nominatim autocomplete error: {e}")
        return []


def clear_cache() -> None:
    """Clear the in-memory autocomplete cache."""
    _CACHE.clear()
