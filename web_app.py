"""
Nearest Destination Finder — Streamlit Web Interface
Run locally:  streamlit run web_app.py
Deploy:       share.streamlit.io  →  select this file  →  get public link
"""
import csv
import io
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

# ── Constants ─────────────────────────────────────────────────────────────────
TRANSPORTS = ["Driving", "Walking", "Bicycling", "Transit"]
_NOM_UNSUPPORTED = {"Bicycling", "Transit"}
_ORS_UNSUPPORTED = {"Transit"}

# ── State ─────────────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "n_dests": 3,
        "results": None,
        "error": None,
        "validation": {},   # addr -> bool (True = found, False = not found)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _engine(provider):
    if provider == "Google Maps":
        return maps_engine
    if provider == "OpenRouteService":
        return openroute_engine
    return nominatim_engine


def _geocode(provider, api_key, address):
    """Unified geocode call across providers (different signatures)."""
    if provider == "Free (Nominatim)":
        return nominatim_engine.geocode_address(address)
    if provider == "Google Maps":
        return maps_engine.geocode_address(api_key, address)
    return openroute_engine.geocode_address(api_key, address)


def _decode_polyline_if_needed(resp):
    """Decode Google Maps encoded polyline string into (lat, lon) list in-place."""
    if resp.get("polyline") and not resp.get("polyline_path"):
        try:
            import polyline as _pl
            resp["polyline_path"] = _pl.decode(resp["polyline"])
        except Exception:
            pass


def _mi(m):
    return f"{m * 0.000621371:.1f} mi"


def _dist_text(r, is_mi):
    dv = r.get("distance_value")
    if dv not in (None, float("inf")):
        return _mi(dv) if is_mi else r.get("distance_text", "N/A")
    return r.get("distance_text", "N/A")


def _convert_total(total_str, is_mi):
    """Convert a formatted total-distance string like '12.3 km' or '12.3 km (straight-line)'."""
    if not total_str or not is_mi:
        return total_str
    try:
        val_km = float(total_str.split()[0].replace(",", ""))
        return _mi(val_km * 1000)
    except Exception:
        return total_str


def _export_csv(results_list, is_tsp, resp, is_mi):
    out = io.StringIO()
    w = csv.writer(out)
    if is_tsp:
        w.writerow(["Step", "Destination", "Distance", "Duration"])
        for r in results_list:
            if r.get("error"):
                w.writerow([r.get("step", ""), r["destination"], "ERROR", r["error"]])
            else:
                w.writerow([r.get("step", ""), r["destination"],
                             _dist_text(r, is_mi), r.get("duration_text", "N/A")])
        td = _convert_total(resp.get("total_distance", ""), is_mi)
        w.writerow(["TOTAL", "", td, resp.get("total_duration", "")])
    else:
        w.writerow(["Rank", "Destination", "Distance", "Duration"])
        for i, r in enumerate(results_list):
            if r.get("error"):
                w.writerow([i + 1, r["destination"], "ERROR", r.get("error", "")])
            else:
                w.writerow([i + 1, r["destination"],
                             _dist_text(r, is_mi), r.get("duration_text", "N/A")])
    return out.getvalue()


def _parse_csv_import(raw: str) -> list[str]:
    """Parse CSV/TXT content: detect address column or fall back to one-per-line."""
    col_names = {"address", "destination", "indirizzo", "destinazione"}
    lines = raw.splitlines()
    if not lines:
        return []
    first = lines[0].lower()
    is_csv = "," in lines[0] or any(c in first for c in col_names)
    if is_csv:
        reader = csv.DictReader(io.StringIO(raw))
        fields = [f.strip().lower() for f in (reader.fieldnames or [])]
        target = next((f for f in fields if f in col_names), fields[0] if fields else None)
        if target:
            return [v.strip() for row in reader
                    for k, v in row.items()
                    if k and k.strip().lower() == target and v.strip()]
    return [ln.strip() for ln in lines if ln.strip()]


def _build_map(resp, is_tsp):
    results_list = resp.get("results", [])
    origin_coords = resp.get("origin_coords")
    polyline_path = resp.get("polyline_path")

    all_pts = []
    if origin_coords:
        all_pts.append([origin_coords[0], origin_coords[1]])
    for r in results_list:
        dc = r.get("dest_coords")
        if dc and not r.get("error"):
            all_pts.append([dc[0], dc[1]])

    center = all_pts[0] if all_pts else [45.4654, 9.1866]
    m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

    if origin_coords:
        folium.Marker(
            location=[origin_coords[0], origin_coords[1]],
            popup=folium.Popup(f"<b>{resp.get('origin', 'Origin')}</b>", max_width=250),
            icon=folium.Icon(color="green", icon="home", prefix="fa"),
            tooltip="Origin",
        ).add_to(m)

    for i, r in enumerate(results_list):
        dc = r.get("dest_coords")
        if dc and not r.get("error"):
            num = r.get("step", i + 1)
            label = f"Stop {num}" if is_tsp else f"#{num}"
            dist_lbl = r.get("distance_text", "")
            dur_lbl = r.get("duration_text", "")
            popup_html = (
                f"<b>{label}: {r['destination']}</b><br>"
                f"📏 {dist_lbl}&nbsp;&nbsp;⏱️ {dur_lbl}"
            )
            folium.Marker(
                location=[dc[0], dc[1]],
                popup=folium.Popup(popup_html, max_width=300),
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

    return m


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    provider = st.selectbox(
        "Provider",
        ["Free (Nominatim)", "Google Maps", "OpenRouteService"],
        help=(
            "Free (Nominatim): no API key, straight-line haversine distances.\n"
            "Google Maps / ORS: road-accurate distances and real travel times."
        ),
    )
    api_key = ""
    if provider == "Google Maps":
        api_key = st.text_input("Google Maps API Key", type="password",
                                help="Requires Distance Matrix API, Directions API, Geocoding API.")
        st.caption("Get a key → [Google Cloud Console](https://console.cloud.google.com/)")
    elif provider == "OpenRouteService":
        api_key = st.text_input("OpenRouteService API Key", type="password",
                                help="Free tier: 2,000 requests/day.")
        st.caption("Get a key → [openrouteservice.org](https://openrouteservice.org/dev/#/signup)")

    unit_pref = st.radio("Units", ["Metric (km)", "Imperial (mi)"])
    is_mi = unit_pref == "Imperial (mi)"

    st.divider()
    st.subheader("📋 History")
    history = history_manager.load_history()
    if history:
        rmap = {f"#{r['id']}: {r['name']}": r for r in reversed(history)}
        sel = st.selectbox("Select run", ["— none —"] + list(rmap))

        hc1, hc2, hc3 = st.columns([2, 1, 1])
        if hc1.button("Load", use_container_width=True) and sel != "— none —":
            st.session_state.results = rmap[sel]
            st.session_state.error = None
            st.rerun()
        if hc2.button("🗑", use_container_width=True, help="Delete this run") and sel != "— none —":
            history_manager.delete_run(rmap[sel]["id"])
            if st.session_state.results and st.session_state.results.get("id") == rmap[sel]["id"]:
                st.session_state.results = None
            st.rerun()
        if hc3.button("✕", use_container_width=True, help="Clear all history"):
            history_manager.clear_history()
            st.session_state.results = None
            st.rerun()
    else:
        st.caption("No history yet.")

# ── Page title ────────────────────────────────────────────────────────────────
st.title("🗺️ Nearest Destination Finder")

form_col, result_col = st.columns([2, 3], gap="large")

# ── Form ──────────────────────────────────────────────────────────────────────
with form_col:
    origin = st.text_input("🏠 Origin", placeholder="e.g. Piazza del Duomo, Milan")
    mode = st.radio("Mode", ["Find Nearest", "Traveling Salesman (TSP)"], horizontal=True)

    with st.expander("Route options"):
        transport = st.selectbox(
            "Transport",
            TRANSPORTS,
            help="Nominatim: Driving and Walking only. Transit requires Google Maps.",
        )
        dep_raw = st.text_input(
            "Departure time", value="Default",
            help="YYYY-MM-DD HH:MM, 'now', or leave as Default for now.",
        )
        round_trip = st.checkbox("Round trip", help="TSP: return to origin after the last stop.")

    # Compatibility warnings
    if provider == "Free (Nominatim)" and transport in _NOM_UNSUPPORTED:
        st.warning(f"⚠️ Nominatim does not support {transport} — will use Driving.")
    if provider == "OpenRouteService" and transport in _ORS_UNSUPPORTED:
        st.warning("⚠️ OpenRouteService does not support Transit — will use Driving.")

    st.subheader("📍 Destinations")
    add_col, rem_col = st.columns(2)
    if add_col.button("➕ Add destination"):
        st.session_state.n_dests += 1
    if rem_col.button("➖ Remove last") and st.session_state.n_dests > 1:
        n = st.session_state.n_dests - 1
        for suffix in (f"dest_{n}", f"mode_{n}", f"dep_{n}"):
            st.session_state.pop(suffix, None)
        st.session_state.n_dests = n

    for i in range(st.session_state.n_dests):
        addr_val = st.session_state.get(f"dest_{i}", "")
        validated = st.session_state.validation.get(addr_val)
        badge = " ✅" if validated is True else " ❌" if validated is False else ""
        with st.expander(f"Destination {i + 1}{badge}", expanded=True):
            st.text_input(
                "Address", placeholder=f"Address {i + 1}",
                key=f"dest_{i}", label_visibility="collapsed",
            )
            if provider != "Free (Nominatim)":
                oc1, oc2 = st.columns(2)
                oc1.selectbox(
                    "Transport override", ["Default"] + TRANSPORTS,
                    key=f"mode_{i}", label_visibility="collapsed",
                    help="Leave as Default to use the global transport setting.",
                )
                oc2.text_input(
                    "Departure override", value="Default",
                    key=f"dep_{i}", label_visibility="collapsed",
                    help="Override departure time for this stop only.",
                )

    # File upload
    uploaded = st.file_uploader(
        "📂 Import CSV / TXT (one address per line)",
        type=["csv", "txt"],
    )
    if uploaded:
        raw = uploaded.read().decode("utf-8", errors="replace")
        addresses = _parse_csv_import(raw)
        if addresses:
            for j in range(st.session_state.n_dests):
                for suf in (f"dest_{j}", f"mode_{j}", f"dep_{j}"):
                    st.session_state.pop(suf, None)
            st.session_state.n_dests = len(addresses)
            for j, addr in enumerate(addresses):
                st.session_state[f"dest_{j}"] = addr
            st.session_state.validation = {}
            st.rerun()

    st.markdown("---")
    bc1, bc2 = st.columns(2)
    validate_clicked = bc1.button("✅ Validate addresses", use_container_width=True)
    calculate = bc2.button("🔍 Calculate", type="primary", use_container_width=True)

# ── Validation ────────────────────────────────────────────────────────────────
if validate_clicked:
    if provider != "Free (Nominatim)" and not api_key:
        st.warning(f"Enter an API key for {provider} before validating.")
    else:
        to_check = []
        if origin.strip():
            to_check.append(origin.strip())
        for i in range(st.session_state.n_dests):
            a = st.session_state.get(f"dest_{i}", "").strip()
            if a:
                to_check.append(a)

        if not to_check:
            st.warning("No addresses to validate.")
        else:
            validated = {}
            with st.spinner(f"Validating {len(to_check)} address(es)…"):
                for addr in to_check:
                    coords = _geocode(provider, api_key, addr)
                    validated[addr] = coords is not None

            st.session_state.validation = validated
            n_ok = sum(1 for v in validated.values() if v)
            n_fail = len(validated) - n_ok
            if n_fail == 0:
                st.success(f"All {n_ok} addresses found ✅")
            else:
                for addr, ok in validated.items():
                    st.write(("✅ " if ok else "❌ ") + addr)

# ── Calculation ───────────────────────────────────────────────────────────────
if calculate:
    dests, overrides = [], []
    for i in range(st.session_state.n_dests):
        addr = st.session_state.get(f"dest_{i}", "").strip()
        if addr:
            dests.append(addr)
            overrides.append((
                st.session_state.get(f"mode_{i}", "Default"),
                st.session_state.get(f"dep_{i}", "Default"),
            ))

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

        # Resolve effective transport (fallback for unsupported combos)
        eff_transport = transport
        if provider == "Free (Nominatim)" and transport in _NOM_UNSUPPORTED:
            eff_transport = "Driving"
        if provider == "OpenRouteService" and transport in _ORS_UNSUPPORTED:
            eff_transport = "Driving"

        eng = _engine(provider)
        has_overrides = any(m != "Default" or d != "Default" for m, d in overrides)

        with st.spinner("Calculating route…"):
            try:
                if is_tsp or not has_overrides:
                    if is_tsp:
                        resp = eng.get_optimized_route(
                            api_key, origin.strip(), dests, eff_transport, dep_time, round_trip
                        )
                    else:
                        resp = eng.get_distance_matrix(
                            api_key, origin.strip(), dests, eff_transport, dep_time
                        )
                else:
                    # Per-destination overrides: group by effective (mode, dep_time) and
                    # make a separate distance-matrix call per group, then merge & sort.
                    groups: dict = {}
                    for dest, (m_ov, d_ov) in zip(dests, overrides):
                        eff_m = m_ov if m_ov != "Default" else eff_transport
                        eff_d = d_ov if d_ov not in ("Default", "") else dep_time
                        groups.setdefault((eff_m, eff_d), []).append(dest)

                    all_results = []
                    origin_coords = None
                    error_resp = None

                    for (grp_mode, grp_dep), grp_dests in groups.items():
                        grp_resp = eng.get_distance_matrix(
                            api_key, origin.strip(), grp_dests, grp_mode, grp_dep
                        )
                        if grp_resp.get("status") == "OK":
                            all_results.extend(grp_resp.get("results", []))
                            if origin_coords is None:
                                origin_coords = grp_resp.get("origin_coords")
                        else:
                            error_resp = grp_resp
                            break

                    if error_resp:
                        resp = error_resp
                    else:
                        all_results.sort(key=lambda x: x.get("distance_value", float("inf")))
                        resp = {
                            "status": "OK",
                            "results": all_results,
                            "origin_coords": origin_coords,
                        }

                if resp.get("status") == "OK":
                    resp["is_tsp"] = is_tsp
                    resp["origin"] = origin.strip()
                    _decode_polyline_if_needed(resp)   # normalize before storing in history
                    st.session_state.results = resp
                    st.session_state.error = None
                    history_manager.add_run(
                        origin.strip(), dests, provider, mode,
                        eff_transport, dep_raw, round_trip, resp, is_tsp, unit_pref,
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
        polyline_path = resp.get("polyline_path")

        # Decode encoded polyline from history entries (Google Maps TSP)
        if resp.get("polyline") and not polyline_path:
            try:
                import polyline as _pl
                polyline_path = _pl.decode(resp["polyline"])
                resp["polyline_path"] = polyline_path
            except Exception:
                pass

        # TSP summary banner
        if is_tsp and resp.get("total_distance"):
            td = _convert_total(resp["total_distance"], is_mi)
            st.success(f"**Total: {td}** &nbsp;&nbsp; ⏱️ {resp.get('total_duration', 'N/A')}")

        # Metadata row
        n_ok = sum(1 for r in results_list if not r.get("error"))
        n_err = len(results_list) - n_ok
        meta_parts = [f"{n_ok} destination{'s' if n_ok != 1 else ''} found"]
        if n_err:
            meta_parts.append(f"{n_err} failed")
        st.caption(" · ".join(meta_parts))

        # Export button
        if results_list:
            csv_bytes = _export_csv(results_list, is_tsp, resp, is_mi).encode("utf-8")
            st.download_button(
                "⬇️ Export results as CSV",
                data=csv_bytes,
                file_name="route_results.csv",
                mime="text/csv",
            )

        st.subheader("📊 Results")
        for i, r in enumerate(results_list):
            label = f"Stop {r.get('step', i + 1)}" if is_tsp else f"#{i + 1}"
            if r.get("error"):
                st.error(f"**{label}: {r['destination']}** — {r['error']}")
            else:
                dist_display = _dist_text(r, is_mi)
                dur_display = r.get("duration_text", "N/A")
                st.markdown(
                    f"**{label}: {r['destination']}**  \n"
                    f"📏 {dist_display} &nbsp;&nbsp; ⏱️ {dur_display}"
                )
                st.divider()

        # Map
        st.subheader("🗺️ Map")
        origin_coords = resp.get("origin_coords")
        all_pts = []
        if origin_coords:
            all_pts.append([origin_coords[0], origin_coords[1]])
        for r in results_list:
            dc = r.get("dest_coords")
            if dc and not r.get("error"):
                all_pts.append([dc[0], dc[1]])

        if all_pts:
            st_folium(_build_map(resp, is_tsp), height=520, use_container_width=True)
        else:
            st.info("No coordinates available to render the map.")
    else:
        m = folium.Map(location=[45.4654, 9.1866], zoom_start=5, tiles="CartoDB positron")
        st_folium(m, height=520, use_container_width=True)
        if not st.session_state.error:
            st.info("Enter an origin and destinations, then click **Calculate**.")
