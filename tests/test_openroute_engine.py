import pytest
from unittest.mock import patch, MagicMock
from api.openroute_engine import get_distance_matrix, get_optimized_route
from utils.geo_cache import _get_conn

@pytest.fixture(autouse=True)
def clear_cache():
    with _get_conn() as conn:
        conn.execute("DELETE FROM geocode")
        conn.commit()

@patch('openrouteservice.Client')
def test_get_distance_matrix_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock geocode responses
    def pelias_mock(text, size):
        if text == "Rome":
            return {'features': [{'geometry': {'coordinates': [12.4964, 41.9028]}}]}
        elif text == "Naples":
            return {'features': [{'geometry': {'coordinates': [14.2681, 40.8518]}}]}
        return {'features': []}
    mock_client.pelias_search.side_effect = pelias_mock
    
    # Mock distance matrix response
    mock_client.distance_matrix.return_value = {
        'distances': [[200000]],
        'durations': [[7200]]
    }
    
    result = get_distance_matrix("dummy_key", "Rome", ["Naples"])
    
    assert result["status"] == "OK"
    assert result["origin_coords"] == (41.9028, 12.4964)
    assert len(result["results"]) == 1
    assert result["results"][0]["destination"] == "Naples"
    assert result["results"][0]["distance_value"] == 200000
    assert result["results"][0]["duration_value"] == 7200

@patch('openrouteservice.Client')
def test_get_distance_matrix_no_key(mock_client_class):
    result = get_distance_matrix("", "Rome", ["Naples"])
    assert result["status"] == "ERROR"
    assert "Missing API Key" in result["error_message"]
