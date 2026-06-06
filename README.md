# Nearest Destination Finder

A Python desktop app for comparing travel distances and optimizing multi-stop routes. Works out of the box with no API key required — or connect Google Maps / OpenRouteService for road-accurate distances and times.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Find Nearest** — compare distances from one origin to many destinations, sorted closest-first
- **Traveling Salesman (TSP)** — find the optimal visit order to minimize total travel distance
- **Interactive map** — origin pin, destination pins, and the full route polyline drawn on a live map
- **Auto-fit map** — after calculation, the map automatically centers and zooms to fit all markers
- **Three providers** — Google Maps (precise road distances + times), OpenRouteService (free API), or **Free (Nominatim)** (no API key needed — straight-line haversine distances)
- **Transport modes** — Driving, Walking, Bicycling, Transit (provider-dependent)
- **Departure time** — specify a future departure for traffic-aware routing (Google Maps)
- **CSV import** — bulk-load destination addresses from a spreadsheet
- **CSV export** — export destination lists or full results (with distances and times) to CSV
- **Clear All** — one-click reset of the destination list
- **Persistent settings** — API keys, provider, mode, transport mode, theme, and map style are saved locally in `config.json`
- **Show / hide API keys** — toggle visibility of each key field with the eye button
- **Dark / Light / System theme** — live preview when switching
- **Map styles** — Voyager, Light, Dark, and Standard (OSM)
- **Tile cache** — visited map tiles are stored in a local SQLite database for instant repeat loads

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/nearest-destination-finder.git
cd nearest-destination-finder
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
python main.py
```

---

## Getting API Keys

> **No API key? No problem.** Select **Free (Nominatim)** as the provider — the API key fields disappear and the app works immediately using OpenStreetMap geocoding and straight-line (haversine) distances. Results are labeled `(straight-line)` to make the approximation clear. Geocoding is sequential (~1 sec per address) due to Nominatim's 1 req/sec rate limit.

### Google Maps

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable these APIs:
   - **Distance Matrix API** (Find Nearest mode)
   - **Directions API** (TSP mode)
   - **Geocoding API** (map pins)
3. Create an API key under **APIs & Services → Credentials**

> Google Maps requires a billing account but provides a **$200/month free credit**, which covers thousands of requests for personal use.

### OpenRouteService (free alternative)

1. Sign up at [openrouteservice.org](https://openrouteservice.org/dev/#/signup)
2. Generate a free API key (2,000 requests/day on the free plan)

---

## Usage

1. Select a **Provider** in the sidebar:
   - **Free (Nominatim)** — no API key needed, straight-line distances
   - **Google Maps** or **OpenRouteService** — enter the API key and click **Save Settings**
2. Select a **Mode** and **Transport Mode**
3. Type your **Origin** address
4. Add **Destinations** one by one, or click **Import CSV** to load from a file
5. Click **Calculate Routes**
6. Results appear in the list and on the map; click **Export CSV** next to Results to save them

### Modes explained

| Mode | What it does |
|------|-------------|
| **Find Nearest** | Calls the Distance Matrix API. Returns all destinations sorted by distance from origin. |
| **Traveling Salesman (TSP)** | Calls the Directions / Optimization API with waypoint optimization. Returns the shortest overall route visiting all destinations. |

---

## CSV Format

### Importing destinations

The importer looks for a column named `address`, `destination`, `indirizzo`, or `destinazione` (case-insensitive). If none is found, the first column is used.

```csv
address
"Rome, Colosseum"
"Florence, Piazza del Duomo"
"Venice, Piazza San Marco"
```

### Exporting results

**Export Destinations** (CSV bar, left panel) — saves the current destination list with an `address` column, ready for re-import.

**Export Results** (Results header, left panel) — saves the calculated results:

| Find Nearest | Traveling Salesman (TSP) |
|---|---|
| Rank, Destination, Distance, Duration | Step, Destination, Leg Distance, Leg Duration |
| Error rows marked with `-` | Total row appended at the bottom |

---

## Project Structure

```
Nearest-Destination-Finder/
├── main.py                   # Entry point
├── requirements.txt
├── config.json               # Local settings — auto-created, not committed
├── gui/
│   ├── app_window.py         # Main window, layout, calculation flow
│   └── components.py         # DestinationList and ResultCard widgets
├── api/
│   ├── maps_engine.py        # Google Maps (Distance Matrix + Directions)
│   ├── openroute_engine.py   # OpenRouteService (Distance Matrix + VROOM Optimization)
│   └── nominatim_engine.py   # Free mode: OSM geocoding + haversine distances
└── utils/
    ├── config_manager.py     # Load / save config.json
    ├── data_importer.py      # CSV import and export (stdlib csv, no pandas)
    └── logger.py             # Rotating file + console logger
```

---

## Notes

- `config.json` is listed in `.gitignore` because it stores your API keys — never commit it
- The tile cache (`.map_cache.db`) is also excluded; it is regenerated automatically
- `app.log` is written to the project root and excluded from git
- Google Maps and ORS geocoding uses `ThreadPoolExecutor` for parallel lookups; Nominatim is sequential (1 req/sec rate limit)
- GUI updates from background threads use `self.after(0, callback)` for thread safety
- All geocoders use a module-level dict cache; failed lookups are never cached, allowing retries

---

## License

MIT — see [LICENSE](LICENSE) for details.
