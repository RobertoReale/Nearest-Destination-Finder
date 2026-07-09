from unittest.mock import patch, MagicMock
from api import autocomplete_engine


def test_get_suggestions_short_query():
    assert autocomplete_engine.get_suggestions("") == []
    assert autocomplete_engine.get_suggestions("ab") == []


@patch("api.autocomplete_engine.requests.get")
def test_get_suggestions_photon_success(mock_get):
    autocomplete_engine.clear_cache()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "features": [
            {
                "properties": {
                    "name": "Duomo di Milano",
                    "street": "Piazza del Duomo",
                    "city": "Milano",
                    "country": "Italia",
                },
                "geometry": {"coordinates": [9.1913, 45.4642]},
            }
        ]
    }
    mock_get.return_value = mock_resp

    results = autocomplete_engine.get_suggestions("duomo milano")
    assert len(results) == 1
    assert "Duomo di Milano" in results[0]["display_text"]
    assert results[0]["lat"] == 45.4642
    assert results[0]["lon"] == 9.1913

    # Test cache hit
    mock_get.reset_mock()
    results2 = autocomplete_engine.get_suggestions("duomo milano")
    assert len(results2) == 1
    mock_get.assert_not_called()


@patch("api.autocomplete_engine.requests.get")
def test_get_suggestions_fallback_nominatim(mock_get):
    autocomplete_engine.clear_cache()
    # First call (Photon) returns empty or fails, second call (Nominatim) succeeds
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 500

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = [
        {
            "display_name": "Colosseo, Piazza del Colosseo, Roma, RM, Lazio, 00184, Italia",
            "lat": "41.8902",
            "lon": "12.4922",
        }
    ]

    mock_get.side_effect = [mock_resp1, mock_resp2]
    results = autocomplete_engine.get_suggestions("colosseo")
    assert len(results) == 1
    assert "Colosseo" in results[0]["display_text"]
    assert results[0]["lat"] == 41.8902


@patch("api.autocomplete_engine.requests.get")
def test_get_suggestions_deduplication(mock_get):
    autocomplete_engine.clear_cache()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Simulate Photon returning multiple identical or similar segments along Via Toledo
    mock_resp.json.return_value = {
        "features": [
            {
                "properties": {"street": "Via Toledo", "city": "Napoli", "state": "Campania", "country": "Italia"},
                "geometry": {"coordinates": [14.24, 40.84]},
            },
            {
                "properties": {"street": "Via Toledo", "city": "Napoli", "state": "Campania", "country": "Italia"},
                "geometry": {"coordinates": [14.241, 40.841]},
            },
            {
                "properties": {"street": "Via Toledo", "district": "Quartieri Spagnoli", "city": "Napoli", "postcode": "80134", "country": "Italia"},
                "geometry": {"coordinates": [14.242, 40.842]},
            },
        ]
    }
    mock_get.return_value = mock_resp

    results = autocomplete_engine.get_suggestions("via toledo napoli")
    # The two exact duplicates should be merged to 1, leaving exactly 2 unique suggestions
    assert len(results) == 2
    assert results[0]["display_text"] == "Via Toledo, Napoli, Campania, Italia"
    assert "Quartieri Spagnoli" in results[1]["display_text"]
