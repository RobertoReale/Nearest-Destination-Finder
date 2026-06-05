import openrouteservice
from openrouteservice import convert

def _format_distance_duration(dist_val, dur_val):
    # dist in meters, dur in seconds
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
            coords = res['features'][0]['geometry']['coordinates']
            return coords # [lon, lat] for ORS
    except:
        pass
    return None

def get_distance_matrix(api_key, origin, destinations):
    if not api_key:
        return {"status": "ERROR", "error_message": "API Key mancante per OpenRouteService"}
        
    try:
        client = openrouteservice.Client(key=api_key)
        
        # ORS requires coordinates, so we must geocode everything first
        origin_coords = _geocode_address(client, origin)
        if not origin_coords:
            return {"status": "ERROR", "error_message": f"Impossibile geocodificare l'origine: {origin}"}
            
        locations = [origin_coords]
        valid_destinations = []
        for dest in destinations:
            coords = _geocode_address(client, dest)
            if coords:
                locations.append(coords)
                valid_destinations.append(dest)
        
        if not valid_destinations:
            return {"status": "ERROR", "error_message": "Impossibile geocodificare le destinazioni"}
            
        # Call distance matrix: origin is index 0, destinations are 1 to N
        # We want distances FROM 0 TO 1..N
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
        for i, dest in enumerate(valid_destinations):
            dist_val = distances[i]
            dur_val = durations[i]
            if dist_val is not None and dur_val is not None:
                dist_text, dur_text = _format_distance_duration(dist_val, dur_val)
                results.append({
                    "destination": dest,
                    "original_destination": dest,
                    "distance_text": dist_text,
                    "distance_value": dist_val,
                    "duration_text": dur_text,
                    "duration_value": dur_val
                })
                
        results.sort(key=lambda x: x['distance_value'])
        
        return {
            "status": "OK",
            "results": results,
            "origin_coords": (origin_coords[1], origin_coords[0]) # return (lat, lon) for map
        }
        
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}

def get_optimized_route(api_key, origin, destinations):
    if not api_key:
        return {"status": "ERROR", "error_message": "API Key mancante per OpenRouteService"}
        
    try:
        client = openrouteservice.Client(key=api_key)
        
        origin_coords = _geocode_address(client, origin)
        if not origin_coords:
            return {"status": "ERROR", "error_message": f"Impossibile geocodificare l'origine: {origin}"}
            
        jobs = []
        locations = []
        valid_destinations = []
        
        for i, dest in enumerate(destinations):
            coords = _geocode_address(client, dest)
            if coords:
                # Add as a job for optimization
                jobs.append({
                    "id": i,
                    "location": coords
                })
                valid_destinations.append(dest)
                locations.append(coords)
                
        if not jobs:
            return {"status": "ERROR", "error_message": "Impossibile geocodificare le destinazioni"}
            
        # Optimization API (VRP) to find best order
        # We start at origin, but where do we end? 
        # OpenRouteService optimization: vehicle starts at origin
        vehicles = [{
            "id": 1,
            "profile": "driving-car",
            "start": origin_coords
        }]
        
        response = client.optimization(
            jobs=jobs,
            vehicles=vehicles
        )
        
        if 'code' in response and response['code'] != 0:
            return {"status": "ERROR", "error_message": response.get('error', 'Errore Optimization API')}
            
        route_steps = response['routes'][0]['steps']
        
        # We have the optimized order, now we might want the polyline.
        # The optimization API doesn't return a full polyline, just coordinates of steps.
        # We need to call Directions API with the optimized locations to get the polyline.
        
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
                    "step": len(results) + 1
                })
                
        # Now get directions for polyline
        dir_res = client.directions(
            coordinates=ordered_coords,
            profile='driving-car',
            format='geojson'
        )
        
        polyline = None
        if 'features' in dir_res and len(dir_res['features']) > 0:
            # We can extract coordinates and encode them, or just let the GUI decode geojson.
            # tkintermapview has set_path which takes list of (lat, lon)
            coords = dir_res['features'][0]['geometry']['coordinates']
            # coords are [lon, lat], tkintermapview needs (lat, lon)
            polyline_path = [(c[1], c[0]) for c in coords]
            polyline = polyline_path
        
        return {
            "status": "OK",
            "results": results,
            "polyline_path": polyline, # Different from google's encoded polyline
            "origin_coords": (origin_coords[1], origin_coords[0]),
            "total_distance": _format_distance_duration(total_dist, total_dur)[0],
            "total_duration": _format_distance_duration(total_dist, total_dur)[1]
        }
        
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}
