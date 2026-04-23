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
| **Persistence** | **No database** | Active games live in an **in-memory** `dict` keyed by `game_id` (`server/game/state.py`). **Optional** save/load writes the same state shape to **`games/*.json`** on disk. On Heroku, **both layers are ephemeral** — RAM and disk reset on every dyno restart. The production upgrade path is Redis (active sessions) + PostgreSQL (save files). |
| **External weather API** | **[Open-Meteo](https://open-meteo.com/)** | Free JSON forecast, **no API key**. *Not* OpenWeatherMap. On failure or `WEATHER_OFFLINE=1`, the server uses **`WEATHER_FALLBACK`** mock data in `server/api/weather.py`. |
| **HTTP client (server)** | **`requests`** | Blocking calls; bulk fetch for new games runs all cities **in parallel** via `ThreadPoolExecutor` — wall-clock time is one round-trip instead of ten sequential fetches. |
| **Tests** | **[pytest](https://pytest.org/)** | 31 tests in `tests/`; run from repo root. pytest is a **Python** test runner — it fits a Flask backend, not a Node-only stack. |
| **Config** | **`python-dotenv`** | Optional `.env` (see `.env.example`) for flags like `WEATHER_OFFLINE`. |

**Why this is internally consistent:** A stack of "Node + Express + pytest + in-memory Python dict" would not match a single codebase: pytest and a Python `dict` imply a **Python** server. This project is **Python + Flask** end-to-end on the server, with a **browser** client that only speaks HTTP/JSON.

**How state flows:** The browser sends actions (`POST` moves, event choices, minigame results). The server updates the authoritative state and returns **full JSON state** in every response so the UI always reflects server truth — no client-side simulation of rewards.

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

> **Single-process only.** Active game sessions live in an in-memory Python dict. Running with multiple workers (e.g. `flask run --processes 2` or a multi-worker Gunicorn) splits that dict across processes, so a second request for the same game will hit a different worker and get "Game not found." The default `flask run` is single-process — keep it that way locally. Production uses `gunicorn --workers 1 --threads 4` for the same reason.

To run the API on another port:

```bash
flask --app app run --port 5000
```

## Weather (Open-Meteo) and offline play

1. By default the server calls **[Open-Meteo](https://open-meteo.com/)** (no API key) using fixed lat/lon per trail city. Temperature is requested in **Fahrenheit**; conditions come from WMO `weather_code` mapped to labels the game understands.

2. Optional: copy `.env.example` to `.env` and set **`WEATHER_OFFLINE=1`** to **never** call the network and always use **built-in mock weather** per city in `server/api/weather.py`.

3. If the live request **fails** (timeout, error, bad JSON), the game **falls back** to that same mock map so play always continues.

## Architecture overview

| Layer | Role |
|--------|------|
| **Flask** (`server/app.py`) | HTTP API, CORS, serves the static client from `client/`. Port is read from `$PORT` (Heroku) with a fallback of 5000 for local dev. |
| **`server/game/`** | All rules: state shape, actions, turn loop, events, win/lose checks. No business rules in route handlers beyond parsing JSON and delegating. |
| **In-memory state** | Games keyed by `game_id` in a thread-safe `_games` dict (protected by `threading.Lock`) in `server/game/state.py`; optional save/load writes JSON under `games/`. |
| **`server/api/weather.py`** | [Open-Meteo](https://open-meteo.com/) `v1/forecast` (`current=temperature_2m,weather_code`, Fahrenheit), with per-city fallback dict. Bulk fetch parallelised with `ThreadPoolExecutor`. |

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
| `POST` | `/api/games/<game_id>/loads` | Load `games/<game_id>.json` (by UUID filename). |
| `POST` | `/api/games/<game_id>/minigames/mining` | Body: `{"success": true\|false}` — mining bonus (when eligible and `minigame_type` is `"mining"`). |
| `POST` | `/api/games/<game_id>/minigames/typing` | Same body — coffee typing sprint (`minigame_type`: `"typing"`). |
| `POST` | `/api/games/<game_id>/minigames/coffee_hunt` | Same body — aim-and-shoot bean hunt (`minigame_type`: `"coffee_hunt"`). |

### HTTP status codes

The API uses the full 4xx/5xx matrix rather than returning `400` for every non-200 response:

| Code | When used |
|------|-----------|
| `400` | Bad client request — invalid action name, missing required field, `success` not a JSON boolean |
| `404` | Resource not found — game not in memory, save file not on disk |
| `409` | Conflict — save name already claimed by a different game |
| `500` | Server-side data error — save file on disk has a corrupted or mismatched `game_id` |

This is intentional: a `400` tells the client "you sent bad data, retry differently"; a `404` tells it "this resource doesn't exist"; a `500` tells it "something is wrong on the server, not your fault."

This is **more resource-oriented** than a single `/action` endpoint: the **game id is in the URL**, which matches common REST-style patterns (even though move names are still RPC-like in the JSON body).

After most resolved events, the server sets `mining_eligible` and picks a random `minigame_type` (`"mining"`, `"typing"`, or `"coffee_hunt"`). The **first** event you resolve in a new run always triggers a bonus; after that, the server rolls against `BONUS_MINIGAME_CHANCE = 0.55` (55%) with a **pity** rule — the bonus is guaranteed if you've gone two events without one. The **client** runs the matching modal and POSTs `{"success": true|false}`; **rewards are applied on the server** so state stays authoritative.

## Running tests

From the **project root** (where `pytest.ini` lives), with the virtualenv active:

```bash
pytest tests/
```

The suite runs 31 tests in under a second (excluding the live weather network tests, which use `monkeypatch` to mock the HTTP layer). All randomness is injectable via an `rng` parameter on the public game-logic functions so tests can pass a seeded `random.Random` or a `Mock` with controlled `.random()` / `.choice()` return values — no global state patching required.

## Design notes

### Game balance constants

All tunable numbers that affect gameplay difficulty live as named module-level constants rather than inline magic values:

| Constant | Value | File | Meaning |
|----------|-------|------|---------|
| `STARTING_CASH` | `$20,000` | `state.py` | Cash every new run begins with |
| `DAILY_OVERHEAD_CASH` | `$320` | `state.py` | Cash burned every turn (payroll + rent) |
| `MAX_JOURNEY_DAYS` | `20` | `state.py` | Calendar days before time-out loss |
| `BUGS_LOSE_THRESHOLD` | `20` | `state.py` | Bug count that triggers a loss (strictly greater than) |
| `BONUS_MINIGAME_CHANCE` | `0.55` | `loop.py` | Probability of a bonus minigame after each event |
| `P_WEATHER_EVENT_ROUGH` | `0.42` | `events.py` | Chance a weather event replaces a location event under rain/fog/clouds |
| `P_WEATHER_EVENT_CALM` | `0.24` | `events.py` | Same chance under clear skies (intentionally lower) |
| `VC_PITCH_SUCCESS_RATE` | `0.6` | `actions.py` | 60% of VC pitches succeed |

Naming these constants serves two purposes: a reviewer can find every balance parameter without reading through function bodies, and changing one value (e.g. tightening the runway from $20k to $15k) requires editing a single line.

### Why Open-Meteo

It offers a **free JSON API without an API key** for non-commercial use, documented at [open-meteo.com](https://open-meteo.com/). We map `current.weather_code` (WMO standard) to the same gameplay condition buckets and use `temperature_2m` in Fahrenheit for the UI temperature display.

### How weather affects play

- **Rain** (including drizzle and thunderstorm codes): extra travel cash cost and morale hit (`apply_weather_modifiers` in `server/api/weather.py`).
- **Clear**: small morale boost on travel into that city's forecast.
- **Haze / fog / mist / smoke**: small extra coffee drain (long, weird days).

When arriving at a new city the server also rolls against weather-event probabilities: **42%** under rough conditions (rain, fog, clouds — `P_WEATHER_EVENT_ROUGH`) or **24%** under calm skies (`P_WEATHER_EVENT_CALM`). If the roll triggers, a weather event (`WEATHER_EVENT_RAIN`, `WEATHER_EVENT_SUNNY`, or `WEATHER_EVENT_FOG`) replaces the normal location draw. The two thresholds are different by design — bad weather should make weather events meaningfully more common, not merely slightly more likely.

### Minigame cheat resistance

Minigame rewards are applied **server-side only**. The client runs the visual modal, then POSTs `{"success": true|false}` to the matching endpoint. The server enforces two layers of protection:

**Input validation** — the `success` field must be a strict JSON boolean (`true` or `false`). Any other type — including a string like `"yes"` or an integer like `1` — is rejected with `400`. This matters because `bool("no")` in Python evaluates to `True`, so a naive `bool()` cast would silently accept strings as truthy.

**State guards** — before applying any reward, `_wrong_minigame` (`server/game/minigames.py`) checks three conditions:

| Guard | What it blocks |
|---|---|
| `status != "playing"` | Late POST after win/lose screen |
| `mining_eligible == False` | POST when no minigame was offered this turn |
| `minigame_type != expected` | POST to `/minigames/typing` when it's a `coffee_hunt` turn |

If any guard fails the server returns a no-op message and leaves state unchanged. A client — or a `curl` script — cannot award itself resources by POSTing to minigame endpoints outside the normal flow.

### Bonus narrative — three-level fallback design

After a minigame resolves, `bonus_narrative.py` produces a contextual message that connects the player's story choice to the minigame result. The system uses a **three-level fallback chain** so every possible combination always produces a valid message, but higher levels reward high-drama moments with richer storytelling.

**Level 1 — Bespoke narrative (hand-written for high-drama combinations)**

`_NARRATIVES` is a dict keyed by `(event_id, choice_label)`. If the exact combination exists, `_build_message` composes prefix + unique prose + resource suffix into one contextually meaningful line.

Example — player declined a VC pitch, then won the mining minigame:
```
Bonus WON — Polite decline on the pitch—then a sharp mining sprint.
The partner smirks: you're not desperate, but you execute.
(+$750 cash, +5 coffee, +3 morale, +3 hype)
```
This works because the two events have an ironic relationship: declining a powerful VC and then immediately executing well tells a coherent story. A generic message would lose that.

**Level 2 — Generic bridge (label-prefixed default)**

When `_NARRATIVES` has no entry for this combination, but `last_event_choice` still carries the choice label, the function prefixes the mechanical default with the player's decision:

```python
return f'After "{label}": {default_message}'
```

Example — player paid for rush shipping, then won mining:
```
After "Pay for rush shipping": Bonus WON — Mining haul secured: +$750 cash, +5 coffee, +3 morale, +3 hype.
```
This is correct and intentional. Paying for shipping and then winning at mining have no special narrative relationship — the bridge is informative without inventing meaning that isn't there.

**Level 3 — Bare fallback (no context)**

If there is no prior event context at all (minigame fires after a non-event action, or state is missing context), the raw default message is returned as-is:
```
Bonus WON — Mining haul secured: +$750 cash, +5 coffee, +3 morale, +3 hype.
```

**The code in three lines:**
```python
narrative = _NARRATIVES.get((event_id, label), {}).get(minigame, {}).get(success)
if narrative:               return _build_message(narrative, ...)  # Level 1
if label:                   return f'After "{label}": {default}'   # Level 2
                            return default                          # Level 3
```

**Why data/logic separation matters here:** `_NARRATIVES` stores only the unique one-sentence prose per combination — no boilerplate. `_build_message` generates "Bonus WON/LOST", resource formatting, and spacing once. Changing how resource changes are displayed means editing one function, not hunting through a large data dict. Adding new story content means adding one prose sentence, not copy-pasting a full template block.

### Error handling and fallback

All outbound weather calls sit in `try`/`except`; any failure or rate limit falls back to the static `WEATHER_FALLBACK` map so the game never crashes on network issues. The fallback also uses `.get(city, WEATHER_FALLBACK["San Jose"])` (not direct subscript) so an unknown city name — from a typo or a future expansion — never raises a `KeyError` in offline mode.

Route handlers return structured `{"error": "..."}` JSON for all error cases. Status codes follow the client-vs-server fault model described in the HTTP status codes section above — never raw stack traces to the browser.

### Thread safety

`_games` is a process-wide in-memory dict shared across all Flask threads. Access is protected by `threading.Lock()` in `get_game` and `put_game` (`server/game/state.py`) to prevent concurrent requests for the same game from interleaving reads and writes. For a single-worker deployment this lock prevents corruption at the dict level; per-game locking (to prevent two simultaneous moves on the same game) would be the next step for higher concurrency.

### Data storage — two layers

The app has two separate storage layers with different lifecycles.

**Layer 1 — Active game session (RAM)**

Created the moment you click Start Voyage; lives in the `_games` Python dict in `server/game/state.py`.

```
Player clicks Start    →  POST /api/games                         →  _games["abc-123"] = { cash, morale, … }
Player takes a turn    →  POST /api/games/abc-123/moves           →  _games["abc-123"] updated in RAM
Player resolves event  →  POST /api/games/abc-123/events/choices  →  _games["abc-123"] updated in RAM
```

This layer is **purely in-memory**. It is destroyed the instant the server process stops — whether from a crash, a redeploy, or Heroku's automatic 24-hour dyno restart. The browser error "This game no longer exists on the server" means this dict entry is gone.

**Layer 2 — Saved game (disk)**

Written only when the player explicitly clicks Save Progress. Stored as `games/<slug>.json` on the server's filesystem.

```
Player clicks Save   →  PUT  /api/games/abc-123/saves   →  games/my_save.json written to disk
Player loads a save  →  POST /api/games/restore-save    →  reads games/my_save.json → back into _games
```

This layer survives a browser tab close or a new session — **but only on localhost**. On Heroku, the filesystem is also ephemeral: every dyno restart wipes the disk just like RAM, so saved files disappear at the same time as active sessions.

**Summary**

| | Layer 1 (active) | Layer 2 (saved) |
|---|---|---|
| Storage | RAM (`_games` dict) | Disk (`games/*.json`) |
| Created | `POST /api/games` | `PUT /api/games/<id>/saves` |
| Survives tab close | No | Yes (localhost only) |
| Survives Heroku dyno restart | **No** | **No** (ephemeral filesystem) |
| Survives `flask run` restart on localhost | No | **Yes** |

**Production upgrade path:** replace `get_game` / `put_game` in `server/game/state.py` with Redis (active sessions survive restarts, work across multiple dynos), and replace the `games/*.json` file I/O in `server/routes/game.py` with PostgreSQL `UPSERT` calls (durable saves, queryable leaderboards, user accounts). The rest of the app does not need to change because all storage access is isolated to those two files.

### Tradeoffs

- **Single active session in memory** keeps the stack small and dependency-free; save/load is file-based JSON for local replayability without a database. On Heroku both layers are ephemeral — a dyno restart wipes RAM and disk together. The designed upgrade path is Redis for active sessions and PostgreSQL for saves.
- **Win condition checked before lose condition** in `loop.py` — if a player reaches San Francisco while simultaneously hitting a resource threshold (e.g. $0 cash on the final travel), the win fires and the game ends correctly. Checking lose first would produce a frustrating false loss on the winning turn.
- **Arrival events are skipped on the final hop into San Francisco** so the player gets a clean win state instead of a blocking event modal after victory.
- **Full state in every response** produces slightly larger payloads but keeps the client trivial — it re-renders from the JSON snapshot rather than maintaining its own derived state.
- **`rng` injection on all randomised functions** (`pick_event`, `_apply_choice_outcome`, `action_pitch_vc`, `resolve_event_turn`) means tests can pass a seeded `random.Random(42)` or a controlled `Mock` for fully deterministic assertions, without monkey-patching the global `random` module.

### If I had more time

- User accounts with persistent ownership of multiple saved games (current save system is anonymous, file-per-game).
- Event choices stripped to labels for the client while keeping effects server-only (currently full event data including effects is sent to the browser, which a client could read).
- Stronger narrative variety + achievement tracking tied to run outcomes.
- Per-game locking on top of the current dict-level lock, for stricter concurrency safety if two requests for the same game arrive simultaneously.
- Structured logging and `/healthz` endpoint if this were a production service.

## AI usage in development

Parts of this repository (file layout, docs, and some implementation scaffolding) were drafted with assistance from an AI coding tool, then reviewed, wired together, and tested by a human developer. Game balance, tests, and all bug fixes were verified locally with `pytest`.

## Special Note
Claire: "My GitHub repo currently shows only a few commits because I had to fix a nested Git repository issue midway through the project. My server/ folder had accidentally been initialized as its own separate Git repo, which meant commits were tracked there instead of at the project root — so client/, tests/, and requirements.txt were never being committed to GitHub at all. To fix the structure properly I removed the nested repo, re-initialized Git at the correct project root, and force-pushed. That reset the commit history, but the codebase itself is complete and unchanged. I'm happy to walk through any part of the code, the design decisions, or the bug fixes I made. Thank you! "
