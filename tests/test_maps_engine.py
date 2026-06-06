import pytest
from unittest.mock import patch, MagicMock
from api.maps_engine import get_distance_matrix, get_optimized_route
from utils.geo_cache import _get_conn

@pytest.fixture(autouse=True)
def clear_cache():
    with _get_conn() as conn:
        conn.execute("DELETE FROM geocode")
        conn.commit()

@patch('googlemaps.Client')
def test_get_distance_matrix_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock distance_matrix response
    mock_client.distance_matrix.return_value = {
        'status': 'OK',
        'rows': [{
            'elements': [{
                'status': 'OK',
                'distance': {'text': '200 km', 'value': 200000},
                'duration': {'text': '2 hours', 'value': 7200}
            }]
        }],
        'destination_addresses': ['Naples, Italy']
    }
    
    # Mock geocode response
    def geocode_mock(address):
        if address == "Rome":
            return [{'geometry': {'location': {'lat': 41.9028, 'lng': 12.4964}}}]
        elif address == "Naples" or address == "Naples, Italy":
            return [{'geometry': {'location': {'lat': 40.8518, 'lng': 14.2681}}}]
        return []
    mock_client.geocode.side_effect = geocode_mock
    
    result = get_distance_matrix("dummy_key", "Rome", ["Naples"])
    
    assert result["status"] == "OK"
    assert result["origin_coords"] == (41.9028, 12.4964)
    assert len(result["results"]) == 1
    assert result["results"][0]["destination"] == "Naples, Italy"
    assert result["results"][0]["distance_value"] == 200000

@patch('googlemaps.Client')
def test_get_distance_matrix_no_key(mock_client_class):
    result = get_distance_matrix("", "Rome", ["Naples"])
    assert result["status"] == "ERROR"
    assert "Missing API Key" in result["error_message"]

@patch('googlemaps.Client')
def test_get_optimized_route_round_trip(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_client.directions.return_value = [{
        'legs': [
            {
                'distance': {'text': '100 km', 'value': 100000},
                'duration': {'text': '1 hour', 'value': 3600},
                'end_address': 'Naples, Italy',
                'end_location': {'lat': 40.8518, 'lng': 14.2681},
                'start_location': {'lat': 41.9028, 'lng': 12.4964}
            },
            {
                'distance': {'text': '100 km', 'value': 100000},
                'duration': {'text': '1 hour', 'value': 3600},
                'end_address': 'Rome, Italy',
                'end_location': {'lat': 41.9028, 'lng': 12.4964},
                'start_location': {'lat': 40.8518, 'lng': 14.2681}
            }
        ],
        'overview_polyline': {'points': 'mock_polyline'}
    }]
    
    result = get_optimized_route("dummy_key", "Rome", ["Naples"], round_trip=True)
    assert result["status"] == "OK"
    assert result["origin_coords"] == (41.9028, 12.4964)
    assert len(result["results"]) == 2
    assert result["results"][0]["destination"] == "Naples, Italy"
    assert result["results"][1]["destination"] == "Rome, Italy"
    assert result["polyline"] == "mock_polyline"

@patch('googlemaps.Client')
def test_get_optimized_route_non_round_trip(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_client.directions.return_value = [{
        'legs': [
            {
                'distance': {'text': '100 km', 'value': 100000},
                'duration': {'text': '1 hour', 'value': 3600},
                'end_address': 'Naples, Italy',
                'end_location': {'lat': 40.8518, 'lng': 14.2681},
                'start_location': {'lat': 41.9028, 'lng': 12.4964}
            }
        ],
        'overview_polyline': {'points': 'mock_polyline'}
    }]
    
    result = get_optimized_route("dummy_key", "Rome", ["Naples"], round_trip=False)
    assert result["status"] == "OK"
    assert result["origin_coords"] == (41.9028, 12.4964)
    assert len(result["results"]) == 1
    assert result["results"][0]["destination"] == "Naples, Italy"
    assert result["polyline"] == "mock_polyline"
