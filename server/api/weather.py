"""Open-Meteo fetch (no API key), server-level TTL cache, and travel modifiers.

See https://open-meteo.com/

Rate-limit strategy
-------------------
Open-Meteo is a free, keyless API with fair-use rate limits. To stay well within
those limits and avoid hammering the API on every game turn, every successful
response is cached server-wide for _CACHE_TTL_SECONDS (5 minutes). Cache entries
are keyed by city name and guarded by a threading.Lock so concurrent requests
for the same city don't produce duplicate live fetches.

If the API returns a 429 (Too Many Requests) or any other error, the code falls
back to WEATHER_FALLBACK mock data — play always continues. The cache naturally
absorbs bursts: a city fetched for one player's game is reused for all other
players within the TTL window.

Production upgrade path: replace the in-process dict with Redis (shared across
dynos, configurable TTL, survives restarts).
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

import requests

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# Server-level weather cache — shared across all games/players in the process.
# Tuple value is (weather_dict, monotonic_timestamp_of_fetch).
_CACHE_TTL_SECONDS = 300  # 5 minutes: fine-grained enough for gameplay, coarse enough to spare the API
_server_weather_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_cache_lock = threading.Lock()

# Peninsula cities → coordinates for Open-Meteo (lat, lon).
CITY_COORDS: Dict[str, Tuple[float, float]] = {
    "San Jose": (37.3382, -121.8863),
    "Santa Clara": (37.3541, -121.9552),
    "Sunnyvale": (37.3688, -122.0363),
    "Cupertino": (37.3230, -122.0322),
    "Mountain View": (37.3861, -122.0839),
    "Palo Alto": (37.4419, -122.1430),
    "Menlo Park": (37.4530, -122.1817),
    "Redwood City": (37.4852, -122.2364),
    "San Mateo": (37.5630, -122.3255),
    "San Francisco": (37.7749, -122.4194),
}

WEATHER_FALLBACK: Dict[str, Dict[str, Any]] = {
    "San Jose": {"condition": "Clear", "temp": 72},
    "Santa Clara": {"condition": "Cloudy", "temp": 68},
    "Sunnyvale": {"condition": "Clear", "temp": 74},
    "Cupertino": {"condition": "Clear", "temp": 70},
    "Mountain View": {"condition": "Foggy", "temp": 62},
    "Palo Alto": {"condition": "Clear", "temp": 71},
    "Menlo Park": {"condition": "Cloudy", "temp": 67},
    "Redwood City": {"condition": "Rain", "temp": 60},
    "San Mateo": {"condition": "Clear", "temp": 65},
    "San Francisco": {"condition": "Foggy", "temp": 58},
}


def _wmo_code_to_condition(code: int) -> str:
    """Map WMO weather code from Open-Meteo `current.weather_code` to a display string."""
    if code == 0:
        return "Clear"
    if code == 1:
        return "Mainly clear"
    if code == 2:
        return "Partly cloudy"
    if code == 3:
        return "Cloudy"
    if code in (45, 48):
        return "Foggy"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Cloudy"


def fetch_weather(city: str) -> Dict[str, Any]:
    """Live forecast from Open-Meteo, or WEATHER_FALLBACK on error / unknown city / offline mode.

    Successful responses are cached server-wide for _CACHE_TTL_SECONDS to stay within
    Open-Meteo fair-use rate limits and avoid a round-trip on every game turn.
    Errors (including HTTP 429 Too Many Requests) always fall back to WEATHER_FALLBACK
    so the game never blocks on weather availability.
    """
    if os.getenv("WEATHER_OFFLINE", "").strip() in ("1", "true", "yes"):
        return dict(WEATHER_FALLBACK.get(city, WEATHER_FALLBACK["San Jose"]))

    coords = CITY_COORDS.get(city)
    if not coords:
        return dict(WEATHER_FALLBACK.get(city, WEATHER_FALLBACK["San Jose"]))

    # Return cached entry if still fresh.
    with _cache_lock:
        cached = _server_weather_cache.get(city)
        if cached and (time.monotonic() - cached[1]) < _CACHE_TTL_SECONDS:
            return dict(cached[0])

    lat, lon = coords
    try:
        res = requests.get(
            OPEN_METEO_FORECAST,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit",
            },
            timeout=5,
        )
        res.raise_for_status()
        data = res.json()
        cur = data.get("current") or {}
        code = int(cur.get("weather_code", 3))
        temp = int(round(float(cur.get("temperature_2m", 70))))
        result = {"condition": _wmo_code_to_condition(code), "temp": temp}
        # Only cache successful live responses; errors fall back without poisoning the cache.
        with _cache_lock:
            _server_weather_cache[city] = (result, time.monotonic())
        return dict(result)
    except Exception:
        return dict(WEATHER_FALLBACK.get(city, WEATHER_FALLBACK["San Jose"]))


def fetch_all_weather(locations: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """Fetch Open-Meteo for every city in parallel so new-game POST is not 10× sequential latency."""
    names = [loc["name"] for loc in locations]
    if not names:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    workers = min(len(names), 10)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_city = {pool.submit(fetch_weather, name): name for name in names}
        for fut in as_completed(future_to_city):
            city = future_to_city[fut]
            try:
                out[city] = fut.result()
            except Exception:
                out[city] = dict(WEATHER_FALLBACK.get(city, WEATHER_FALLBACK["San Jose"]))
    return out


def refresh_city_in_state(state: Dict[str, Any], city: str) -> None:
    """Replace one cache entry (Open-Meteo live, unless WEATHER_OFFLINE or request fails)."""
    state.setdefault("weather_cache", {})
    state["weather_cache"][city] = fetch_weather(city)


def condition_bucket(condition: Any) -> str:
    """
    Map display condition strings into a small set the game rules understand.
    Works for Open-Meteo-derived labels (Drizzle, Thunderstorm, …) and legacy test strings.
    """
    c = str(condition or "").strip().lower()
    if any(s in c for s in ("thunderstorm", "drizzle", "rain", "shower")):
        return "rain"
    if c in ("clear", "mainly clear"):
        return "clear"
    if any(s in c for s in ("fog", "mist", "haze", "smoke")):
        return "fog"
    if "cloud" in c or "overcast" in c or c == "partly cloudy":
        return "clouds"
    if "snow" in c:
        return "other"
    return "other"


def apply_weather_modifiers(state: Dict[str, Any], weather: Dict[str, Any]) -> None:
    bucket = condition_bucket(weather.get("condition"))
    if bucket == "rain":
        state["resources"]["cash"] -= 500
        state["resources"]["morale"] -= 5
    elif bucket == "clear":
        state["resources"]["morale"] += 5
    elif bucket == "fog":
        state["resources"]["coffee"] -= 2
    elif bucket == "clouds":
        state["resources"]["cash"] -= 200
        state["resources"]["morale"] -= 2
    elif bucket == "other":
        state["resources"]["morale"] -= 1
