import pytest
import requests
import responses
from api.nominatim_engine import get_distance_matrix, get_optimized_route, _geocode_single

@responses.activate
def test_geocode_single_success():
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "41.9028", "lon": "12.4964"}],
        status=200
    )
    # Clear the cache for the test to run
    _geocode_single.cache_clear()
    
    result = _geocode_single("Rome")
    assert result == (41.9028, 12.4964)

@responses.activate
def test_geocode_single_failure():
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        body=requests.exceptions.RequestException("Timeout")
    )
    _geocode_single.cache_clear()
    
    result = _geocode_single("InvalidPlace")
    assert result is None

@responses.activate
def test_get_distance_matrix_success():
    # Mocking coordinates for Rome and Naples
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "41.9028", "lon": "12.4964"}],
        status=200,
        match=[responses.matchers.query_param_matcher({"q": "Rome", "format": "json", "limit": "1"})]
    )
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[{"lat": "40.8518", "lon": "14.2681"}],
        status=200,
        match=[responses.matchers.query_param_matcher({"q": "Naples", "format": "json", "limit": "1"})]
    )
    _geocode_single.cache_clear()
    
    result = get_distance_matrix(None, "Rome", ["Naples"])
    assert result["status"] == "OK"
    assert result["origin_coords"] == (41.9028, 12.4964)
    assert len(result["results"]) == 1
    assert result["results"][0]["destination"] == "Naples"
    assert result["results"][0]["distance_value"] > 0

@responses.activate
def test_get_distance_matrix_origin_failure():
    responses.add(
        responses.GET,
        "https://nominatim.openstreetmap.org/search",
        json=[],
        status=200
    )
    _geocode_single.cache_clear()
    
    result = get_distance_matrix(None, "Nowhere", ["Naples"])
    assert result["status"] == "ERROR"
    assert "Could not geocode origin" in result["error_message"]
