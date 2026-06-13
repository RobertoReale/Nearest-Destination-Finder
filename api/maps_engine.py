import googlemaps
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


def _format_distance_duration(dist_val, dur_val):
    dist_text = f"{dist_val / 1000.0:.1f} km"
    hours = dur_val // 3600
    minutes = (dur_val % 3600) // 60
    if hours > 0:
        dur_text = f"{hours} h {minutes} min"
    else:
        dur_text = f"{minutes} min"
    return dist_text, dur_text


from utils.geo_cache import get_cached_coords, set_cached_coords

def _geocode_single(gmaps, address):
    cached = get_cached_coords(address)
    if cached:
        return cached
    try:
        res = gmaps.geocode(address)
        if res:
            loc = res[0]['geometry']['location']
            coords = (loc['lat'], loc['lng'])
            set_cached_coords(address, coords)
            return coords
    except Exception:
        pass
    return None


def geocode_address(api_key, address):
    if not api_key:
        return None
    try:
        gmaps = googlemaps.Client(key=api_key)
        return _geocode_single(gmaps, address)
    except Exception:
        return None


def get_distance_matrix(api_key, origin, destinations, transport_mode="Driving", departure_time=None):
    """Uses Google Distance Matrix API to find the distance from origin to all destinations.
    Returns results sorted by distance, each with dest_coords for map pins.
    """
    if not api_key:
        return {"status": "ERROR", "error_message": "Missing API Key for Google Maps"}

    try:
        gmaps = googlemaps.Client(key=api_key)
        
        if departure_time is None:
            departure_time = datetime.now()

        mode_map = {
            "Driving": "driving",
            "Walking": "walking",
            "Bicycling": "bicycling",
            "Transit": "transit"
        }
        gmaps_mode = mode_map.get(transport_mode, "driving")

        response = gmaps.distance_matrix(  # type: ignore[attr-defined]
            origins=[origin],
            destinations=destinations,
            mode=gmaps_mode,
            departure_time=departure_time
        )

        if response['status'] != 'OK':
            return {"status": "ERROR", "error_message": f"API Error: {response['status']}"}

        results = []
        elements = response['rows'][0]['elements']
        dest_addresses = response.get('destination_addresses') or destinations

        for i, element in enumerate(elements):
            dest_name = dest_addresses[i] if i < len(dest_addresses) else destinations[i]
            if element['status'] == 'OK':
                results.append({
                    "destination": dest_name,
                    "original_destination": destinations[i],
                    "distance_text": element['distance']['text'],
                    "distance_value": element['distance']['value'],
                    "duration_text": element['duration']['text'],
                    "duration_value": element['duration']['value']
                })
            else:
                results.append({
                    "destination": destinations[i],
                    "original_destination": destinations[i],
                    "distance_text": "N/A",
                    "distance_value": float('inf'),
                    "duration_text": "N/A",
                    "duration_value": float('inf'),
                    "error": element['status']
                })

        if transport_mode == "Transit":
            results.sort(key=lambda x: x.get('duration_value', float('inf')))
        else:
            results.sort(key=lambda x: x.get('distance_value', float('inf')))

        # Geocode origin + all valid destinations in parallel for map pins
        valid_results = [r for r in results if not r.get("error")]
        to_geocode = [origin] + [r["destination"] for r in valid_results]

        geocoded: dict = {}
        with ThreadPoolExecutor(max_workers=min(10, len(to_geocode))) as executor:
            future_to_addr = {executor.submit(_geocode_single, gmaps, addr): addr
                              for addr in to_geocode}
            for future in as_completed(future_to_addr):
                addr = future_to_addr[future]
                try:
                    geocoded[addr] = future.result()
                except Exception:
                    geocoded[addr] = None

        origin_coords = geocoded.get(origin)
        for r in valid_results:
            r["dest_coords"] = geocoded.get(r["destination"])

        return {
            "status": "OK",
            "results": results,
            "origin_coords": origin_coords
        }

    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}


def get_optimized_route(api_key, origin, destinations, transport_mode="Driving", departure_time=None, round_trip=False):
    """Uses Google Directions API to calculate an optimized TSP route visiting all destinations."""
    if not api_key:
        return {"status": "ERROR", "error_message": "Missing API Key for Google Maps"}

    try:
        gmaps = googlemaps.Client(key=api_key)
        
        if departure_time is None:
            departure_time = datetime.now()

        mode_map = {
            "Driving": "driving",
            "Walking": "walking",
            "Bicycling": "bicycling",
            "Transit": "transit"
        }
        gmaps_mode = mode_map.get(transport_mode, "driving")

        if not destinations:
            return {"status": "ERROR", "error_message": "No destinations provided"}

        if round_trip:
            target = origin
            waypoints = destinations
        else:
            target = destinations[-1]
            waypoints = destinations[:-1]

        response = gmaps.directions(  # type: ignore[attr-defined]
            origin=origin,
            destination=target,
            waypoints=waypoints,
            optimize_waypoints=True,
            mode=gmaps_mode,
            departure_time=departure_time
        )

        if not response:
            return {"status": "ERROR", "error_message": "No route found"}

        route = response[0]
        legs = route['legs']

        results = []
        total_dist = 0
        total_dur = 0

        for i, leg in enumerate(legs):
            dist_val = leg['distance']['value']
            dur_val = leg['duration']['value']
            total_dist += dist_val
            total_dur += dur_val

            results.append({
                "destination": leg['end_address'],
                "distance_text": leg['distance']['text'],
                "distance_value": dist_val,
                "duration_text": leg['duration']['text'],
                "duration_value": dur_val,
                "step": i + 1,
                "dest_coords": (leg['end_location']['lat'], leg['end_location']['lng'])
            })

        polyline = route['overview_polyline']['points']
        origin_coords = (legs[0]['start_location']['lat'], legs[0]['start_location']['lng'])
        total_dist_text, total_dur_text = _format_distance_duration(total_dist, total_dur)

        return {
            "status": "OK",
            "results": results,
            "polyline": polyline,
            "origin_coords": origin_coords,
            "total_distance": total_dist_text,
            "total_duration": total_dur_text
        }

    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}
