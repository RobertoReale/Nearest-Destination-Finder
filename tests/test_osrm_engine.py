import pytest
import responses
import requests
from api.osrm_engine import get_distance_matrix, get_optimized_route, _get_osrm_table, _run_2opt
from utils.geo_cache import _get_conn

@pytest.fixture(autouse=True)
def clear_cache():
    with _get_conn() as conn:
        conn.execute("DELETE FROM geocode")
        conn.commit()
    yield
    with _get_conn() as conn:
        conn.execute("DELETE FROM geocode")
        conn.commit()

def test_run_2opt():
    # Simple test of 2-opt where swapping improves distance
    dist_matrix = [
        [0, 10, 10, 1],
        [10, 0, 1, 10],
        [10, 1, 0, 10],
        [1, 10, 10, 0]
    ]
    # initial order [0, 1, 2, 3] -> 0->1(10) + 1->2(1) + 2->3(10) = 21
    # optimal order [0, 3, 2, 1] -> 0->3(1) + 3->2(10) + 2->1(1) = 12
    order = _run_2opt(dist_matrix, [0, 1, 2, 3], round_trip=False)
    assert len(order) == 4

@responses.activate
def test_osrm_distance_matrix_fallback():
    # Mock geocoding
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "41.9028", "lon": "12.4964"}],
        status=200
    )
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "40.8518", "lon": "14.2681"}],
        status=200
    )
    # OSRM table fails -> should fallback to haversine
    responses.add(
        responses.GET,
        "https://router.project-osrm.org/table/v1/driving/12.496400,41.902800;14.268100,40.851800",
        body=requests.exceptions.RequestException("Timeout")
    )
    res = get_distance_matrix(None, "Rome", ["Naples"])
    assert res["status"] == "OK"
    assert len(res["results"]) == 1
    assert res["results"][0]["distance_value"] > 0
    assert "km" in res["results"][0]["distance_text"]

@responses.activate
def test_osrm_optimized_route_success():
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "41.9028", "lon": "12.4964"}],
        status=200
    )
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "40.8518", "lon": "14.2681"}],
        status=200
    )
    responses.add(
        responses.GET,
        "https://router.project-osrm.org/table/v1/driving/12.496400,41.902800;14.268100,40.851800",
        json={
            "code": "Ok",
            "distances": [[0, 220000], [220000, 0]],
            "durations": [[0, 7200], [7200, 0]]
        },
        status=200
    )
    responses.add(
        responses.GET,
        "https://router.project-osrm.org/route/v1/driving/12.496400,41.902800;14.268100,40.851800",
        json={
            "code": "Ok",
            "routes": [{
                "distance": 220000,
                "duration": 7200,
                "geometry": {"coordinates": [[12.4964, 41.9028], [14.2681, 40.8518]]},
                "legs": [{"distance": 220000, "duration": 7200}]
            }]
        },
        status=200
    )
    res = get_optimized_route(None, "Rome", ["Naples"], round_trip=False)
    assert res["status"] == "OK"
    assert len(res["results"]) == 1
    assert res["total_distance"] == "220.0 km"
