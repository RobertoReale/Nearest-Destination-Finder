"""
Nearest Destination Finder — Streamlit Web Interface
Run locally:  streamlit run web_app.py
Deploy:       share.streamlit.io  →  select this file  →  get public link
"""
import os
import sys

import folium
import streamlit as st
from streamlit_folium import st_folium

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api import maps_engine, nominatim_engine, openroute_engine
from utils import history_manager

st.set_page_config(
    page_title="Nearest Destination Finder",
    page_icon="🗺️",
    layout="wide",
)


def _init():
    for k, v in [("n_dests", 3), ("results", None), ("error", None)]:
        if k not in st.session_state:
            st.session_state[k] = v


_init()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    provider = st.selectbox("Provider", ["Free (Nominatim)", "Google Maps", "OpenRouteService"])
    api_key = ""
    if provider == "Google Maps":
        api_key = st.text_input("Google Maps API Key", type="password")
    elif provider == "OpenRouteService":
        api_key = st.text_input("OpenRouteService API Key", type="password")

    unit_pref = st.radio("Units", ["Metric (km)", "Imperial (mi)"])
    is_mi = unit_pref == "Imperial (mi)"

    st.divider()
    st.subheader("📋 History")
    history = history_manager.load_history()
    if history:
        rmap = {f"#{r['id']}: {r['name']}": r for r in reversed(history)}
        sel = st.selectbox("Load run", ["— Select —"] + list(rmap))
        c1, c2 = st.columns(2)
        if c1.button("Load", use_container_width=True) and sel != "— Select —":
            run = rmap[sel]
            st.session_state.results = run
            st.session_state.error = None
            st.rerun()
        if c2.button("🗑️ Clear", use_container_width=True):
            history_manager.clear_history()
            st.session_state.results = None
            st.rerun()
    else:
        st.caption("No history yet.")

# ── Form ──────────────────────────────────────────────────────────────────────
st.title("🗺️ Nearest Destination Finder")

form_col, result_col = st.columns([2, 3], gap="large")

with form_col:
    origin = st.text_input("🏠 Origin", placeholder="e.g. Piazza del Duomo, Milan")
    mode = st.radio("Mode", ["Find Nearest", "Traveling Salesman (TSP)"], horizontal=True)

    with st.expander("Route options"):
        transport = st.selectbox("Transport", ["Driving", "Walking", "Bicycling", "Transit"])
        dep_raw = st.text_input(
            "Departure time", value="Default",
            help="YYYY-MM-DD HH:MM, 'now', or leave as Default"
        )
        round_trip = st.checkbox("Round trip")

    st.subheader("📍 Destinations")
    c1, c2 = st.columns(2)
    if c1.button("➕ Add destination"):
        st.session_state.n_dests += 1
    if c2.button("➖ Remove last") and st.session_state.n_dests > 1:
        st.session_state.pop(f"dest_{st.session_state.n_dests - 1}", None)
        st.session_state.n_dests -= 1

    for i in range(st.session_state.n_dests):
        st.text_input(f"Destination {i + 1}", placeholder=f"Address {i + 1}", key=f"dest_{i}")

    uploaded = st.file_uploader("📂 Import CSV/TXT (one address per line)", type=["csv", "txt"])
    if uploaded:
        lines = [ln.strip() for ln in uploaded.read().decode().splitlines() if ln.strip()]
        for i in range(st.session_state.n_dests):
            st.session_state.pop(f"dest_{i}", None)
        st.session_state.n_dests = len(lines)
        for i, ln in enumerate(lines):
            st.session_state[f"dest_{i}"] = ln
        st.rerun()

    st.markdown("---")
    calculate = st.button("🔍 Calculate", type="primary", use_container_width=True)

# ── Calculation ───────────────────────────────────────────────────────────────
if calculate:
    dests = [
        st.session_state.get(f"dest_{i}", "").strip()
        for i in range(st.session_state.n_dests)
    ]
    dests = [d for d in dests if d]

    if not origin.strip():
        st.session_state.error = "Please enter an origin."
        st.session_state.results = None
    elif not dests:
        st.session_state.error = "Please enter at least one destination."
        st.session_state.results = None
    elif provider != "Free (Nominatim)" and not api_key:
        st.session_state.error = f"Please enter an API key for {provider}."
        st.session_state.results = None
    else:
        is_tsp = mode == "Traveling Salesman (TSP)"
        dep_time = None if dep_raw.strip().lower() in ("default", "") else dep_raw.strip()

        if provider == "Google Maps":
            engine = maps_engine
        elif provider == "OpenRouteService":
            engine = openroute_engine
        else:
            engine = nominatim_engine

        with st.spinner("Calculating route..."):
            try:
                if is_tsp:
                    resp = engine.get_optimized_route(
                        api_key, origin.strip(), dests, transport, dep_time, round_trip
                    )
                else:
                    resp = engine.get_distance_matrix(
                        api_key, origin.strip(), dests, transport, dep_time
                    )

                if resp.get("status") == "OK":
                    resp["is_tsp"] = is_tsp
                    resp["origin"] = origin.strip()
                    st.session_state.results = resp
                    st.session_state.error = None
                    history_manager.add_run(
                        origin.strip(), dests, provider, mode,
                        transport, dep_raw, round_trip, resp, is_tsp, unit_pref
                    )
                else:
                    st.session_state.error = resp.get("error_message", "Unknown error")
                    st.session_state.results = None
            except Exception as exc:
                st.session_state.error = str(exc)
                st.session_state.results = None

# ── Results + Map ─────────────────────────────────────────────────────────────
with result_col:
    if st.session_state.error:
        st.error(st.session_state.error)

    resp = st.session_state.results
    if resp:
        results_list = resp.get("results", [])
        is_tsp = resp.get("is_tsp", False)
        origin_coords = resp.get("origin_coords")
        polyline_path = resp.get("polyline_path")    # ORS + Nominatim: list of (lat, lon)
        polyline_encoded = resp.get("polyline")      # Google Maps: encoded polyline string

        # Decode Google Maps encoded polyline into (lat, lon) pairs
        if polyline_encoded and not polyline_path:
            try:
                import polyline as _pl
                polyline_path = _pl.decode(polyline_encoded)
            except Exception:
                pass

        # TSP summary banner
        if is_tsp and resp.get("total_distance"):
            td = resp["total_distance"]
            if is_mi and "km" in td:
                try:
                    td = f"{float(td.split()[0]) * 0.621371:.1f} mi"
                except Exception:
                    pass
            st.success(f"**Total: {td}** &nbsp;&nbsp; ⏱️ {resp.get('total_duration', 'N/A')}")

        st.subheader("📊 Results")
        for i, r in enumerate(results_list):
            if r.get("error"):
                label = f"Stop {r.get('step', i + 1)}" if is_tsp else f"#{i + 1}"
                st.error(f"**{label}: {r['destination']}** — {r['error']}")
            else:
                label = f"Stop {r.get('step', i + 1)}" if is_tsp else f"#{i + 1}"
                dist_text = r.get("distance_text", "N/A")
                dur_text = r.get("duration_text", "N/A")
                if is_mi:
                    dv = r.get("distance_value")
                    if dv not in (None, float("inf")):
                        dist_text = f"{dv * 0.000621371:.1f} mi"
                st.markdown(
                    f"**{label}: {r['destination']}**  \n"
                    f"📏 {dist_text} &nbsp;&nbsp; ⏱️ {dur_text}"
                )
                st.divider()

        # Map
        st.subheader("🗺️ Map")
        all_pts = []
        if origin_coords:
            all_pts.append([origin_coords[0], origin_coords[1]])
        for r in results_list:
            dc = r.get("dest_coords")
            if dc and not r.get("error"):
                all_pts.append([dc[0], dc[1]])

        if all_pts:
            m = folium.Map(location=all_pts[0], zoom_start=11, tiles="CartoDB positron")

            if origin_coords:
                folium.Marker(
                    location=[origin_coords[0], origin_coords[1]],
                    popup=resp.get("origin", "Origin"),
                    icon=folium.Icon(color="green", icon="home", prefix="fa"),
                    tooltip="Origin",
                ).add_to(m)

            for i, r in enumerate(results_list):
                dc = r.get("dest_coords")
                if dc and not r.get("error"):
                    num = r.get("step", i + 1)
                    folium.Marker(
                        location=[dc[0], dc[1]],
                        popup=r["destination"],
                        icon=folium.DivIcon(
                            html=(
                                f'<div style="background:#3498db;color:white;border-radius:50%;'
                                f'width:28px;height:28px;line-height:28px;text-align:center;'
                                f'font-weight:bold;font-size:13px;border:2px solid white;">{num}</div>'
                            ),
                            icon_size=(28, 28),
                            icon_anchor=(14, 14),
                        ),
                        tooltip=r["destination"],
                    ).add_to(m)

            if polyline_path:
                folium.PolyLine(polyline_path, color="#3498db", weight=4, opacity=0.8).add_to(m)

            if len(all_pts) > 1:
                m.fit_bounds(all_pts)

            st_folium(m, height=500, use_container_width=True)
        else:
            st.info("No coordinates available for the map.")
    else:
        m = folium.Map(location=[45.4654, 9.1866], zoom_start=5, tiles="CartoDB positron")
        st_folium(m, height=500, use_container_width=True)
        if not st.session_state.error:
            st.info("Enter an origin and destinations, then click **Calculate**.")
