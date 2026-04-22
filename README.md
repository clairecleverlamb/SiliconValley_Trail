# Silicon Valley Trail

A replayable, Oregon Trail–style survival game for a scrappy startup driving from **San Jose** to **San Francisco** along real Peninsula cities. You manage cash, morale, coffee, hype, and bugs while random location events and live (or mocked) weather push back.

## Tech stack (authoritative)

Use this section for write-ups, proposals, and résumé bullets. It matches what this repository actually runs.

| Area | Choice | Notes |
|------|--------|--------|
| **Language (server)** | **Python 3** | Game rules, HTTP API, tests, and weather integration are all Python. |
| **HTTP framework** | **[Flask](https://flask.palletsprojects.com/)** | REST-style JSON API under `/api/games`, CORS for local dev, static hosting of the client from `client/`. *Not* Node.js or Express. |
| **Language (client)** | **Vanilla JavaScript** | No React/Vue build step; `client/game.js` drives a single-page UI. |
| **Markup & style** | **Plain HTML + CSS** | `client/index.html`, `client/style.css`. |
| **Persistence** | **No database** | Active games live in an **in-memory** `dict` keyed by `game_id` (`server/game/state.py`). **Optional** save/load writes the same state shape to **`games/*.json`** on disk. |
| **External weather API** | **[Open-Meteo](https://open-meteo.com/)** | Free JSON forecast, **no API key**. *Not* OpenWeatherMap. On failure or `WEATHER_OFFLINE=1`, the server uses **`WEATHER_FALLBACK`** mock data in `server/api/weather.py`. |
| **HTTP client (server)** | **`requests`** | Blocking calls; bulk fetch for new games runs cities **in parallel** (thread pool) to avoid slow sequential startup. |
| **Tests** | **[pytest](https://pytest.org/)** | Python tests in `tests/`; run from repo root. pytest is a **Python** test runner—it fits a Flask backend, not a Node-only stack. |
| **Config** | **`python-dotenv`** | Optional `.env` (see `.env.example`) for flags like `WEATHER_OFFLINE`. |

**Why this is internally consistent:** A stack of “Node + Express + pytest + in-memory Python dict” would not match a single codebase: pytest and a Python `dict` imply a **Python** server. This project is **Python + Flask** end-to-end on the server, with a **browser** client that only speaks HTTP/JSON.

**How state flows:** The browser sends actions (`POST` moves, event choices, minigame results). The server updates the authoritative state and returns **full JSON state** in responses so the UI always reflects server truth (no client-side simulation of rewards).

## Quick start (fresh machine)

```bash
cd siliconValleyTrail
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd server
flask --app app run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

To run the API on another port:

```bash
flask --app app run --port 5000
```

## Weather (Open-Meteo) and offline play

1. By default the server calls **[Open-Meteo](https://open-meteo.com/)** (no API key) using fixed lat/lon per trail city. Temperature is requested in **Fahrenheit**; conditions come from WMO `weather_code` mapped to labels the game understands.

2. Optional: copy `.env.example` to `.env` and set **`WEATHER_OFFLINE=1`** to **never** call the network and always use **built‑in mock weather** per city in `server/api/weather.py`.

3. If the live request **fails** (timeout, error, bad JSON), the game **falls back** to that same mock map so play continues.

## Architecture overview

| Layer | Role |
|--------|------|
| **Flask** (`server/app.py`) | HTTP API, CORS, serves the static client from `client/`. |
| **`server/game/`** | All rules: state shape, actions, turn loop, events, win/lose checks. No business rules in route handlers beyond parsing JSON and delegating. |
| **In-memory state** | Games keyed by `game_id` in `server/game/state.py`; optional save/load writes JSON under `games/`. |
| **`server/api/weather.py`** | [Open-Meteo](https://open-meteo.com/) `v1/forecast` (`current=temperature_2m,weather_code`, Fahrenheit), with per-city fallback dict. |

The browser **does not own game state**: after each `fetch`, the UI re-renders from the JSON the server returns.

### HTTP API (resource-oriented)

Registered under **`/api/games`** in `server/app.py` (handlers in `server/routes/game.py`):

| Method | Path | Handler role |
|--------|------|----------------|
| `POST` | `/api/games` | Create a game; JSON includes `game_id`. |
| `GET` | `/api/games/<game_id>` | Read full state (`404` if unknown id). |
| `POST` | `/api/games/<game_id>/moves` | Body: `{"action": "travel" \| …}`. |
| `POST` | `/api/games/<game_id>/events/choices` | Body: `{"choice": 1\|2\|3}`. |
| `PUT` | `/api/games/<game_id>/saves` | Body **required**: `{"save_name": "..."}`. Writes `games/<slug>.json` and `games/<game_id>.json`; sets `save_name` on the stored state. |
| `POST` | `/api/games/restore-save` | Body: `{"save_name": "..."}` — load `games/<slug>.json` into memory. |
| `POST` | `/api/games/<game_id>/loads` | Load `games/<game_id>.json` (for the UUID filename or pasted id). |
| `POST` | `/api/games/<game_id>/minigames/mining` | Body: `{"success": true\|false}` — mining bonus (when eligible and `minigame_type` is `mining`). |
| `POST` | `/api/games/<game_id>/minigames/typing` | Same body — coffee typing sprint (`minigame_type`: `typing`). |
| `POST` | `/api/games/<game_id>/minigames/coffee_hunt` | Same body — aim-and-shoot bean hunt (`minigame_type`: `coffee_hunt`). |

This is **more resource-oriented** than a single `/action` endpoint: the **game id is in the URL**, which matches common REST-style patterns (even though move names are still RPC-like in the JSON body).

After most resolved events, the server sets `mining_eligible` and picks a random `minigame_type` (`mining`, `typing`, or `coffee_hunt`). The **first** event you resolve in a new run always triggers a bonus; after that, there is a high random chance plus a **pity** rule so you never go more than two events in a row without an offered bonus. The **client** runs the matching modal (after a short beat so you can read the outcome) and POSTs success/failure; **rewards are applied on the server** so state stays authoritative.

## Running tests

From the **project root** (where `pytest.ini` lives), with the virtualenv active:

```bash
pytest tests/
```

## Design notes

### Why Open-Meteo

It offers a **free JSON API without an API key** for non-commercial use, documented at [open-meteo.com](https://open-meteo.com/). We map `current.weather_code` (WMO) to the same gameplay condition buckets as before and use `temperature_2m` in Fahrenheit for the UI.

### How weather affects play

- **Rain** (including drizzle / thunderstorm codes that normalize to rain): extra travel cost and morale hit (`apply_weather_modifiers` in `server/api/weather.py`).
- **Clear**: small morale boost on travel into that city’s forecast.
- **Haze / fog / mist / smoke**: small extra coffee drain (long weird days).

Travel also has a **20%** chance to replace the normal location draw with a **weather event** when the cached condition matches **rain**, **clear** (sunny template), or **fog / mist / haze** (see `get_weather_event` / `pick_event` in `server/game/events.py`).

### Error handling and fallback

All outbound weather calls sit in `try`/`except`; any failure or rate limit falls back to the static `WEATHER_FALLBACK` map so the game never crashes on network issues.

Routes return **`400`** with `{"error": "..."}` for invalid actions or resolving events when none is active—never stack traces to the client.

### Tradeoffs

- **Single active session** in memory keeps the stack small; save/load is file-based JSON for replayability without a database.
- **Arrival events** are skipped on the final hop into San Francisco so you get a clear win state instead of a blocking modal after victory.
- **Full state in every response** is slightly larger payloads but keeps the client trivial and guarantees the UI matches the server.

### If I had more time

- Multiple concurrent sessions keyed by cookie or URL `game_id`.
- Event choices stripped to labels for the client while keeping effects server-only.
- Stronger narrative variety + achievement tracking tied to run outcomes.
- Structured logging and health endpoints if this were deployed.

## AI usage in development

Parts of this repository (file layout, docs, and some implementation scaffolding) were drafted with assistance from an AI coding tool, then reviewed, wired together, and tested by a human developer. Game balance and tests were verified locally with `pytest`.

## Special Note
"My GitHub repo currently shows only a few commits because I had to fix a nested Git repository issue midway through the project. My server/ folder had accidentally been initialized as its own separate Git repo, which meant commits were tracked there instead of at the project root — so client/, tests/, and requirements.txt were never being committed to GitHub at all. To fix the structure properly I removed the nested repo, re-initialized Git at the correct project root, and force-pushed. That reset the commit history, but the codebase itself is complete and unchanged. I'm happy to walk through any part of the code, the design decisions, or the bug fixes I made."
