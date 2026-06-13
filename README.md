# Nearest Destination Finder

A Python tool for comparing travel distances and optimizing multi-stop routes.  
Works out of the box with no API key required — or connect Google Maps / OpenRouteService for road-accurate distances and real travel times.

Available as a **desktop app** (customtkinter) and a **web app** (Streamlit — deployable to a public URL in minutes).

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Find Nearest** — compare distances from one origin to many destinations, sorted closest-first
- **Traveling Salesman (TSP)** — find the optimal visit order to minimize total travel distance
- **Round-trip mode** — TSP can optionally return to the origin
- **Interactive map** — origin pin, numbered destination pins, and the full route polyline drawn on a live map (desktop: tkintermapview; web: Leaflet/Folium)
- **Auto-fit map** — after calculation, the map automatically centers and zooms to fit all markers
- **Three providers** — Google Maps (precise road distances + times), OpenRouteService (free API), or **Free (Nominatim)** (no API key needed — straight-line haversine distances, labeled as such)
- **Per-destination overrides** — set a custom transport mode or departure time for each individual stop
- **Address validation** — geocode all addresses before calculating to catch typos early
- **Export results as CSV** — download a ranked table of distances and durations
- **Import destinations from CSV/TXT** — bulk-load addresses; auto-detects `address`, `destination`, `indirizzo`, `destinazione` columns
- **History** — every successful calculation is saved automatically; load or delete individual runs from the sidebar
- **Unit switching** — Metric (km) and Imperial (mi) with live conversion
- **Transport modes** — Driving, Walking, Bicycling, Transit (provider-dependent)
- **Departure time** — specify a future departure for traffic-aware routing (Google Maps)
- **Persistent geocoding cache** — lookups are stored in a local SQLite database (`.geo_cache.db`) so repeat queries make zero API calls

**Desktop-only features:**
- Compare & History tab — select two or more runs to compare them side-by-side on the map and in a summary table
- Rename / delete saved runs
- Dark / Light / System theme with live preview
- Map styles — Voyager, Light, Dark, Standard (OSM)
- Tile cache for instant repeat map loads
- Persistent settings (`config.json`) — API keys, provider, transport, theme saved locally
- Show / hide API key toggle

---

## Quick start — Web App (public link)

### Run locally

```bash
pip install -r requirements.txt
streamlit run web_app.py
```

Opens at `http://localhost:8501`.

### Deploy to Streamlit Cloud (free public URL)

1. Push this repository to GitHub (already done if you cloned it)
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub
3. Click **New app** → select your repo, branch `main`, file `web_app.py`
4. Click **Deploy** — Streamlit Cloud builds the environment and gives you a permanent public URL:
   **[https://robertoreale-nearest-destination-finder.streamlit.app](https://robertoreale-nearest-destination-finder.streamlit.app)**

No server to manage, no cost. The app restarts automatically when you push updates to GitHub.

> **Note:** On Streamlit Cloud, `route_history.json` and `.geo_cache.db` are ephemeral (reset on each deployment). For persistent history, connect a database or use a cloud-hosted SQLite alternative.

---

## Quick start — Desktop App

### Installation

```bash
git clone https://github.com/yourusername/nearest-destination-finder.git
cd nearest-destination-finder
pip install -r requirements.txt
python main.py
```

---

## Getting API Keys

> **No API key? No problem.** Select **Free (Nominatim)** as the provider — the API key field disappears and the app works immediately using OpenStreetMap geocoding and straight-line (haversine) distances. Results are labeled `(straight-line)` to make the approximation clear. Geocoding is sequential (~1 sec per address) due to Nominatim's 1 req/sec rate limit.

### Google Maps

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable these APIs:
   - **Distance Matrix API** (Find Nearest mode)
   - **Directions API** (TSP mode)
   - **Geocoding API** (map pins and address validation)
3. Create an API key under **APIs & Services → Credentials**

> Google Maps requires a billing account but provides a **$200/month free credit**, which covers thousands of requests for personal use.

### OpenRouteService (free alternative)

1. Sign up at [openrouteservice.org](https://openrouteservice.org/dev/#/signup)
2. Generate a free API key (2,000 requests/day on the free plan)

---

## Usage — Web App

1. **Select a Provider** in the left sidebar (Free, Google Maps, or ORS) and enter an API key if required
2. **Select Units** (Metric or Imperial)
3. Choose a **Mode** and optionally expand **Route options** (transport, departure time, round-trip)
4. Type your **Origin** address
5. Add **Destinations** — click ➕ to add more, or upload a CSV/TXT file
6. (Optional) Expand any destination row to set a custom transport mode or departure time for that stop
7. Click **✅ Validate addresses** to geocode everything before calculating
8. Click **🔍 Calculate** — results appear on the right with a map and a CSV export button
9. Past runs appear in the **History** sidebar — load or delete individual entries

### Transport mode compatibility

| Provider | Driving | Walking | Bicycling | Transit |
|---|---|---|---|---|
| Free (Nominatim) | ✅ | ✅ | ⚠️ (→ Driving) | ⚠️ (→ Driving) |
| OpenRouteService | ✅ | ✅ | ✅ | ⚠️ (→ Driving) |
| Google Maps | ✅ | ✅ | ✅ | ✅ |

---

## Usage — Desktop App

1. Select a **Provider** in the sidebar; enter the API key and click **Save Settings**
2. Select a **Mode** and **Transport Mode**
3. Type your **Origin** address
4. Add **Destinations** one by one, or click **Import CSV** to load from a file
5. (Optional) Click **⚙** on any destination row to override its transport mode or departure time
6. (Optional) Click **Validate Addresses** to check all entries before calculating
7. Click **Calculate Routes**
8. Results appear in the list and on the map; click **Export CSV** next to Results to save them

### Modes explained

| Mode | What it does |
|------|-------------|
| **Find Nearest** | Calls the Distance Matrix API. Returns all destinations sorted by distance from origin. |
| **Traveling Salesman (TSP)** | Calls the Directions / Optimization API with waypoint optimization. Returns the shortest overall route visiting all destinations. |

---

## CSV Format

### Importing destinations

The importer detects a column named `address`, `destination`, `indirizzo`, or `destinazione` (case-insensitive). If none is found, it reads one address per line.

```csv
address
"Rome, Colosseum"
"Florence, Piazza del Duomo"
"Venice, Piazza San Marco"
```

### Exporting results

The **Export results as CSV** button (web app) and **Export Results** button (desktop) produce:

| Find Nearest | Traveling Salesman (TSP) |
|---|---|
| Rank, Destination, Distance, Duration | Step, Destination, Distance, Duration |
| — | TOTAL row appended at the bottom |

---

## Project Structure

```
Nearest-Destination-Finder/
├── main.py                   # Desktop entry point
├── web_app.py                # Streamlit web interface
├── requirements.txt
├── requirements-dev.txt      # Dev/test dependencies (pytest, responses, …)
├── .streamlit/
│   └── config.toml           # Dark theme for the web app
├── config.json               # Desktop local settings — auto-created, not committed
├── route_history.json        # Saved route history — auto-created, not committed
├── gui/
│   ├── app_window.py         # Desktop main window, layout, calculation flow
│   └── components.py        # DestinationList and ResultCard widgets
├── api/
│   ├── maps_engine.py        # Google Maps (Distance Matrix + Directions)
│   ├── openroute_engine.py   # OpenRouteService (Distance Matrix + VROOM Optimization)
│   └── nominatim_engine.py   # Free mode: OSM geocoding + haversine distances
├── utils/
│   ├── config_manager.py     # Load / save config.json
│   ├── data_importer.py      # CSV import and export (stdlib csv, no pandas)
│   ├── geo_cache.py          # Persistent SQLite geocoding cache (.geo_cache.db)
│   ├── history_manager.py    # Save / load / rename / delete route history
│   └── logger.py             # Rotating file (5 MB × 3) + console logger
└── tests/
    ├── test_maps_engine.py
    ├── test_openroute_engine.py
    ├── test_nominatim_engine.py
    ├── test_history_manager.py
    └── test_components.py
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

All 23 unit tests should pass. Tests use a dedicated `.geo_cache_test.db` so the real geocoding cache is never touched.

---

## Notes

- `config.json` and `route_history.json` are listed in `.gitignore` — they store API keys and local data, never commit them
- Map tiles are cached in `.map_cache.db` and geocoding in `.geo_cache.db` — auto-generated and excluded from git
- `app.log` is written to the project root (rotating, max 5 MB × 3 backups) and excluded from git
- Google Maps and ORS geocoding uses `ThreadPoolExecutor` for parallel lookups; Nominatim is sequential (1 req/sec rate limit enforced by a module-level timer)
- Desktop GUI updates from background threads use `self.after(0, callback)` for thread safety
- Failed geocoding lookups are never cached, allowing automatic retries on the next calculation

---

## License

MIT — see [LICENSE](LICENSE) for details.
