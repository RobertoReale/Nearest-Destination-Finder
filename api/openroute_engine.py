import openrouteservice
from concurrent.futures import ThreadPoolExecutor, as_completed


def _format_distance_duration(dist_val, dur_val):
    dist_text = f"{dist_val / 1000.0:.1f} km"
    hours = int(dur_val // 3600)
    minutes = int((dur_val % 3600) // 60)
    if hours > 0:
        dur_text = f"{hours} h {minutes} min"
    else:
        dur_text = f"{minutes} min"
    return dist_text, dur_text


def _geocode_address(client, address):
    try:
        res = client.pelias_search(text=address, size=1)
        if res['features']:
            return res['features'][0]['geometry']['coordinates']  # [lon, lat]
    except Exception:
        pass
    return None


def _geocode_all(client, addresses):
    """Geocode multiple addresses in parallel. Returns a list of coords in input order."""
    results = [None] * len(addresses)
    with ThreadPoolExecutor(max_workers=min(10, len(addresses))) as executor:
        future_to_idx = {executor.submit(_geocode_address, client, addr): i
                         for i, addr in enumerate(addresses)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = None
    return results


def get_distance_matrix(api_key, origin, destinations):
    if not api_key:
        return {"status": "ERROR", "error_message": "Missing API Key for OpenRouteService"}

    try:
        client = openrouteservice.Client(key=api_key)

        all_coords = _geocode_all(client, [origin] + destinations)
        origin_coords = all_coords[0]

        if not origin_coords:
            return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

        locations = [origin_coords]
        valid_destinations = []
        valid_dest_coords = []

        for i, dest in enumerate(destinations):
            coords = all_coords[i + 1]
            if coords:
                locations.append(coords)
                valid_destinations.append(dest)
                valid_dest_coords.append(coords)

        if not valid_destinations:
            return {"status": "ERROR", "error_message": "Could not geocode any destinations"}

        response = client.distance_matrix(
            locations=locations,
            sources=[0],
            destinations=list(range(1, len(locations))),
            profile='driving-car',
            metrics=['distance', 'duration']
        )

        distances = response['distances'][0]
        durations = response['durations'][0]

        results = []
        valid_idx = 0
        for i, dest in enumerate(destinations):
            coords = all_coords[i + 1]
            if not coords:
                results.append({
                    "destination": dest,
                    "original_destination": dest,
                    "distance_text": "N/A",
                    "distance_value": float('inf'),
                    "duration_text": "N/A",
                    "duration_value": float('inf'),
                    "error": "Geocoding failed"
                })
            else:
                dist_val = distances[valid_idx]
                dur_val = durations[valid_idx]
                if dist_val is not None and dur_val is not None:
                    dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                    results.append({
                        "destination": dest,
                        "original_destination": dest,
                        "distance_text": dist_text,
                        "distance_value": dist_val,
                        "duration_text": dur_text,
                        "duration_value": dur_val,
                        "dest_coords": (valid_dest_coords[valid_idx][1], valid_dest_coords[valid_idx][0])
                    })
                else:
                    results.append({
                        "destination": dest,
                        "original_destination": dest,
                        "distance_text": "N/A",
                        "distance_value": float('inf'),
                        "duration_text": "N/A",
                        "duration_value": float('inf'),
                        "error": "Unreachable"
                    })
                valid_idx += 1

        results.sort(key=lambda x: x['distance_value'])

        return {
            "status": "OK",
            "results": results,
            "origin_coords": (origin_coords[1], origin_coords[0])  # (lat, lon)
        }

    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}


def get_optimized_route(api_key, origin, destinations):
    if not api_key:
        return {"status": "ERROR", "error_message": "Missing API Key for OpenRouteService"}

    try:
        client = openrouteservice.Client(key=api_key)

        all_coords = _geocode_all(client, [origin] + destinations)
        origin_coords = all_coords[0]

        if not origin_coords:
            return {"status": "ERROR", "error_message": f"Could not geocode origin: {origin}"}

        jobs = []
        locations = []
        valid_destinations = []

        for i, dest in enumerate(destinations):
            coords = all_coords[i + 1]
            if coords:
                job_idx = len(jobs)  # Sequential IDs matching the locations array
                jobs.append({"id": job_idx, "location": coords})
                valid_destinations.append(dest)
                locations.append(coords)

        if not jobs:
            return {"status": "ERROR", "error_message": "Could not geocode any destinations"}

        vehicles = [{"id": 1, "profile": "driving-car", "start": origin_coords}]

        response = client.optimization(jobs=jobs, vehicles=vehicles)

        if 'code' in response and response['code'] != 0:
            return {"status": "ERROR", "error_message": response.get('error', 'Optimization API error')}

        route_steps = response['routes'][0]['steps']

        ordered_coords = [origin_coords]
        results = []
        total_dist = 0
        total_dur = 0

        for step in route_steps:
            if step['type'] == 'job':
                job_id = step['job']
                ordered_coords.append(locations[job_id])

                dist_val = step.get('distance', 0)
                dur_val = step.get('duration', 0)
                total_dist += dist_val
                total_dur += dur_val

                dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                results.append({
                    "destination": valid_destinations[job_id],
                    "distance_text": dist_text,
                    "distance_value": dist_val,
                    "duration_text": dur_text,
                    "duration_value": dur_val,
                    "step": len(results) + 1,
                    "dest_coords": (locations[job_id][1], locations[job_id][0])  # (lat, lon)
                })

        dir_res = client.directions(
            coordinates=ordered_coords,
            profile='driving-car',
            format='geojson'
        )

        polyline_path = None
        if 'features' in dir_res and dir_res['features']:
            coords = dir_res['features'][0]['geometry']['coordinates']
            polyline_path = [(c[1], c[0]) for c in coords]  # (lat, lon)

        total_dist_text, total_dur_text = _format_distance_duration(total_dist, total_dur)

        return {
            "status": "OK",
            "results": results,
            "polyline_path": polyline_path,
            "origin_coords": (origin_coords[1], origin_coords[0]),
            "total_distance": total_dist_text,
            "total_duration": total_dur_text
        }

    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}
