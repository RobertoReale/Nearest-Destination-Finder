import googlemaps
from datetime import datetime

def _format_distance_duration(dist_val, dur_val):
    # dist in meters, dur in seconds
    dist_text = f"{dist_val / 1000.0:.1f} km"
    hours = dur_val // 3600
    minutes = (dur_val % 3600) // 60
    if hours > 0:
        dur_text = f"{hours} h {minutes} min"
    else:
        dur_text = f"{minutes} min"
    return dist_text, dur_text

def get_distance_matrix(api_key, origin, destinations):
    """
    Uses Google Distance Matrix API to find the distance from origin to all destinations.
    Returns results sorted by distance.
    """
    if not api_key:
        return {"status": "ERROR", "error_message": "API Key mancante per Google Maps"}
    
    try:
        gmaps = googlemaps.Client(key=api_key)
        now = datetime.now()
        
        response = gmaps.distance_matrix(
            origins=[origin],
            destinations=destinations,
            mode="driving",
            departure_time=now
        )
        
        if response['status'] != 'OK':
            return {"status": "ERROR", "error_message": f"Errore API: {response['status']}"}
            
        results = []
        rows = response['rows'][0]
        elements = rows['elements']
        
        for i, element in enumerate(elements):
            if element['status'] == 'OK':
                results.append({
                    "destination": response['destination_addresses'][i] if 'destination_addresses' in response else destinations[i],
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
                
        # Sort by distance
        results.sort(key=lambda x: x['distance_value'])
        
        # Geocode origin to return its coordinates for the map
        origin_coords = None
        geocode_res = gmaps.geocode(origin)
        if geocode_res:
            loc = geocode_res[0]['geometry']['location']
            origin_coords = (loc['lat'], loc['lng'])
            
        return {
            "status": "OK",
            "results": results,
            "origin_coords": origin_coords
        }
        
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}

def get_optimized_route(api_key, origin, destinations):
    """
    Uses Google Directions API to calculate an optimized TSP route visiting all destinations.
    """
    if not api_key:
        return {"status": "ERROR", "error_message": "API Key mancante per Google Maps"}
        
    try:
        gmaps = googlemaps.Client(key=api_key)
        now = datetime.now()
        
        if len(destinations) == 0:
            return {"status": "ERROR", "error_message": "Nessuna destinazione fornita"}
            
        # The last destination is considered the end of the route, unless we loop back to origin.
        # For a standard TSP, we want to visit all. Directions API accepts origin, destination, and waypoints.
        # If we just have destinations, we can set the last one as destination, or origin as destination to complete a loop.
        # Let's assume an open loop where the last element is the destination.
        
        target = destinations[-1]
        waypoints = destinations[:-1]
        
        response = gmaps.directions(
            origin=origin,
            destination=target,
            waypoints=waypoints,
            optimize_waypoints=True,
            mode="driving",
            departure_time=now
        )
        
        if not response:
            return {"status": "ERROR", "error_message": "Nessun percorso trovato"}
            
        route = response[0]
        legs = route['legs']
        waypoint_order = route['waypoint_order']
        
        results = []
        total_dist = 0
        total_dur = 0
        
        # In an optimized route with waypoints:
        # Leg 0 is from origin to first optimized waypoint
        # Leg i is from waypoint i-1 to waypoint i
        # Last leg is from last waypoint to target
        
        for i, leg in enumerate(legs):
            dest_address = leg['end_address']
            
            # The original target passed to the API might not match the end_address string exactly, 
            # but we record what the leg says.
            dist_val = leg['distance']['value']
            dur_val = leg['duration']['value']
            
            total_dist += dist_val
            total_dur += dur_val
            
            results.append({
                "destination": dest_address,
                "distance_text": leg['distance']['text'],
                "distance_value": dist_val,
                "duration_text": leg['duration']['text'],
                "duration_value": dur_val,
                "step": i + 1
            })
            
        polyline = route['overview_polyline']['points']
        
        # Origin coords from the first leg
        origin_coords = (legs[0]['start_location']['lat'], legs[0]['start_location']['lng'])
        
        return {
            "status": "OK",
            "results": results,
            "polyline": polyline,
            "origin_coords": origin_coords,
            "total_distance": _format_distance_duration(total_dist, total_dur)[0],
            "total_duration": _format_distance_duration(total_dist, total_dur)[1]
        }
        
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}
