# Silicon Valley Trail

A replayable, Oregon Trail–style survival game for a scrappy startup driving from **San Jose** to **San Francisco** along real Peninsula cities. You manage cash, morale, coffee, hype, and bugs while random location events and live (or mocked) weather push back.

---

<table>
<tr><td><strong>Source Code</strong></td><td><a href="https://github.com/clairecleverlamb/SiliconValley_Trail" target="_blank" rel="noopener noreferrer">github.com/clairecleverlamb/SiliconValley_Trail</a></td></tr>
<tr><td><strong>Live App</strong></td><td><a href="https://siliconvalleytrail-0a70c4621c3e.herokuapp.com/" target="_blank" rel="noopener noreferrer">siliconvalleytrail-0a70c4621c3e.herokuapp.com</a></td></tr>
<tr><td><strong>Demo Video</strong></td><td><a href="https://youtu.be/0FNCjyeTJsQ" target="_blank" rel="noopener noreferrer">youtu.be/0FNCjyeTJsQ</a></td></tr>
<tr><td><strong>Trello Board</strong></td><td><a href="https://trello.com/b/ywkWAan0/silicon-valley-trail" target="_blank" rel="noopener noreferrer">trello.com/b/ywkWAan0/silicon-valley-trail</a></td></tr>
<tr><td><strong>Design Notes</strong></td><td><a href="https://docs.google.com/document/d/1R2eA5L-KQ59NZut7s5cs9GnEsiwRfGLMpWYfgsh1hNQ/edit?tab=t.0" target="_blank" rel="noopener noreferrer">Google Doc</a></td></tr>
<tr><td><strong>Test Tracker</strong></td><td><a href="https://docs.google.com/spreadsheets/d/1Ze7bkQS1GjRClXzMj7oVHJIh56OzV7ZNF-kzHdV8vNc/edit?gid=0#gid=0" target="_blank" rel="noopener noreferrer">Google Sheets</a></td></tr>
</table>

---

## Required features — how each is met

**1. Testing** — 31 passing pytest tests cover every critical area: resource updates (travel, weather modifiers, all action types), all four lose conditions (cash, morale, coffee, bugs, calendar timeout), win condition, event choice effects, bonus minigame offer/skip/pity rules, weather API fallbacks, and the full save/load cycle. All randomness is injectable via an `rng` parameter so tests use a controlled `Mock` instead of patching global state.

**2. Documentation** — This README documents the tech stack, API contract, status code matrix, game balance constants, storage layers, thread safety, and tradeoffs, with every claim verified against the code. [Design Notes](https://docs.google.com/document/d/1R2eA5L-KQ59NZut7s5cs9GnEsiwRfGLMpWYfgsh1hNQ/edit?tab=t.0) cover key architectural decisions and tradeoffs. [Test Tracker](https://docs.google.com/spreadsheets/d/1Ze7bkQS1GjRClXzMj7oVHJIh56OzV7ZNF-kzHdV8vNc/edit?gid=0#gid=0) logs manual testing scenarios.

**3. Decency & safety** — All Open-Meteo calls are wrapped in `try/except` with a static fallback so the game never crashes on network issues. Route handlers return structured `{"error": "..."}` JSON with correct status codes; no stack traces reach the browser. The app has no API keys (Open-Meteo is keyless); all environment flags use `os.getenv()`. No user data is collected — sessions are anonymous server-generated UUIDs, save files contain only game state, and there are no cookies, logins, or analytics.

---

## Tech stack (authoritative)

Use this section for write-ups, proposals. It matches what this repository actually runs.

| Area | Choice | Notes |
|------|--------|--------|
| **Language (server)** | **Python 3** | Game rules, HTTP API, tests, and weather integration are all Python. |
| **HTTP framework** | **[Flask](https://flask.palletsprojects.com/)** | REST-style JSON API under `/api/games`, CORS for local dev, static hosting of the client from `client/`. *Not* Node.js or Express. |
| **Language (client)** | **Vanilla JavaScript** | No React/Vue build step; `client/game.js` drives a single-page UI. |
| **Markup & style** | **Plain HTML + CSS** | `client/index.html`, `client/style.css`. |
| **Persistence** | **No database** | Active games live in an **in-memory** `dict` keyed by `game_id` (`server/game/state.py`). **Optional** save/load writes the same state shape to **`games/*.json`** on disk. On Heroku, **both layers are ephemeral** — RAM and disk reset on every dyno restart. The proposed production upgrade path is Redis (active sessions) + PostgreSQL (save files). No implementation of Redis and PostgreSQL yet. |
| **External weather API** | **[Open-Meteo](https://open-meteo.com/)** | Free JSON forecast, **no API key**. On failure or `WEATHER_OFFLINE=1`, the server uses **`WEATHER_FALLBACK`** mock data in `server/api/weather.py`. |
| **HTTP client (server)** | **`requests`** | Blocking calls; bulk fetch for new games runs all cities **in parallel** via `ThreadPoolExecutor` — wall-clock time is one round-trip instead of ten sequential fetches. |
| **Tests** | **[pytest](https://pytest.org/)** | 31 tests in `tests/`; run from repo root. pytest is a **Python** test runner — it fits a Flask backend, not a Node-only stack. |
| **Config** | **`python-dotenv`** | Optional `.env` (see `.env.example`) for flags like `WEATHER_OFFLINE`. |

**Server is Python end-to-end** — Flask, pytest, game logic, and weather integration are all in the same Python codebase. The browser client only communicates via HTTP/JSON and contains no game logic.

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

> **Single-process only.** Active game sessions live in an in-memory Python dict. Running with multiple workers (e.g. `gunicorn --workers 2 app:app`) splits that dict across processes, so a second request for the same game can hit a different worker and return "Game not found." The default `flask run` is single-process — safe for local dev. Production uses `gunicorn --workers 1 --threads 4` for the same reason: one process, multiple threads share the same dict.

To run the API on another port:

```bash
flask --app app run --port 5000
```

## Weather (Open-Meteo) and offline play

1. **Live fetch** — The server calls [Open-Meteo](https://open-meteo.com/) (no API key required) using fixed lat/lon coordinates for each trail city. Temperature is returned in Fahrenheit; conditions are derived from the WMO `weather_code` field and mapped to the labels the game rules understand (`rain`, `fog`, `clouds`, `clear`).

2. **Server-side cache** — Every successful response is cached in-process for 5 minutes, shared across all concurrent games. This keeps the app well within Open-Meteo's fair-use limits even under load, and means a city fetched for one player's turn is immediately reused for others within the TTL window.

3. **Offline mode** — Copy `.env.example` to `.env` and set `WEATHER_OFFLINE=1` to bypass all network calls entirely. The server uses `WEATHER_FALLBACK` — a static per-city dict in `server/api/weather.py` — with realistic Peninsula conditions for each location.

4. **Fault tolerance** — Any live request that fails (network timeout, non-200 response, malformed JSON, or HTTP 429 rate-limit) falls back to the same `WEATHER_FALLBACK` dict. The game never blocks or crashes on weather unavailability.

## Architecture overview

| Layer | Role |
|--------|------|
| **Flask** (`server/app.py`) | HTTP API, CORS, serves the static client from `client/`. Port is read from `$PORT` (Heroku) with a fallback of 5000 for local dev. |
| **`server/game/`** | All rules: state shape, actions, turn loop, events, win/lose checks. No business rules in route handlers beyond parsing JSON and delegating. |
| **In-memory state** | Games keyed by `game_id` in a thread-safe `_games` dict (protected by `threading.Lock`) in `server/game/state.py`; optional save/load writes JSON under `games/`. |
| **`server/api/weather.py`** | [Open-Meteo](https://open-meteo.com/) `v1/forecast` (`current=temperature_2m,weather_code`, Fahrenheit), with per-city fallback dict. Bulk fetch parallelised with `ThreadPoolExecutor`. Successful responses are cached server-wide for 5 minutes (`_server_weather_cache`, guarded by `threading.Lock`) to stay within Open-Meteo fair-use limits; any error (including HTTP 429) falls back to the static dict so the game never blocks on weather. |

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
| `400` | Bad client request — invalid action name, missing required field, `success` not a JSON boolean, attempting a move while an event is pending resolution |
| `404` | Resource not found — game not in memory, save file not on disk |
| `409` | Conflict — save name already claimed by a different game |
| `500` | Server-side data error — save file exists but cannot be read or parsed, or its internal `game_id` is missing/mismatched |

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

All tunable numbers live as named constants rather than inline values, so the full difficulty profile is visible in one place and changing any single value requires editing one line.

| Constant | Value | Meaning |
|----------|-------|---------|
| `STARTING_CASH` | $20,000 | Cash every new run begins with |
| `DAILY_OVERHEAD_CASH` | $320 | Cash burned every turn (payroll + burn rate) |
| `MAX_JOURNEY_DAYS` | 20 | Calendar days before time-out loss |
| `BUGS_LOSE_THRESHOLD` | 20 | Bug count that triggers a loss (strictly greater than 20) |
| `BONUS_MINIGAME_CHANCE` | 55% | Probability of a bonus minigame after each event |
| `VC_PITCH_SUCCESS_RATE` | 60% | Chance a VC pitch succeeds |
| `P_WEATHER_EVENT_ROUGH` | 42% | Chance a weather event fires under rain, fog, or clouds |
| `P_WEATHER_EVENT_CALM` | 24% | Same chance under clear skies — intentionally lower |

### Weather

The server fetches live conditions from [Open-Meteo](https://open-meteo.com/) — a free, keyless API — for each city on the trail. Conditions are mapped to four gameplay buckets:

- **Rain** — extra travel cash cost and morale hit
- **Clear** — small morale boost on arrival
- **Fog** — slight extra coffee drain
- **Clouds** — mild cash and morale penalty

On top of direct modifiers, each arrival also rolls against weather-event probabilities. Rough conditions (rain, fog, clouds) produce a weather event 42% of the time; clear skies produce one 24% of the time. This gap is intentional — bad weather should feel meaningfully more disruptive.

To stay within Open-Meteo's fair-use limits, every successful response is cached for 5 minutes and shared across all active games. If a fetch fails for any reason — timeout, bad response, or HTTP 429 — the server falls back to a static per-city forecast so the game never blocks on weather. Set `WEATHER_OFFLINE=1` in `.env` to skip live calls entirely and always use the static fallback.

### Storage and persistence

The app has two storage layers:

| | Active session | Saved game |
|---|---|---|
| Where | RAM (`_games` dict) | Disk (`games/*.json`) |
| Created | When you start a new game | When you click Save Progress |
| Survives browser tab close | No | Yes (localhost only) |
| Survives server restart | No | Yes (localhost only) |
| Survives Heroku dyno restart | **No** | **No** |

Both layers are ephemeral on Heroku — the platform periodically restarts its servers and wipes both RAM and disk when it does. The "Game not found" error means the active session in RAM was cleared. Save files disappear for the same reason. The production upgrade path is Redis for active sessions and PostgreSQL for saves; because all storage access is isolated to two files, nothing else in the app would need to change.

### Thread safety

All active games share a single in-memory dict across every request thread. Both read (`get_game`) and write (`put_game`) operations are protected by a `threading.Lock` so concurrent requests cannot interleave and corrupt state. The weather cache uses a separate lock for the same reason. Per-game locking — serialising multiple simultaneous moves on the *same* game — would be the next step for higher concurrency.

### Minigame integrity

Minigame rewards are **applied on the server only**. The browser runs the visual game and reports `true` or `false`; the server decides what, if anything, to award. Two layers of protection prevent cheating:

1. **Strict input validation** — the `success` field must be a real JSON boolean. Strings, integers, or missing fields are rejected with `400`. This matters because Python's `bool("no")` evaluates to `True`, so a loose type cast would silently accept strings.

2. **State guards** — before applying any reward, the server checks that the game is still in progress, that a minigame was actually offered this turn, and that the POST matches the correct minigame type. A request that fails any check gets a no-op response and leaves state unchanged.

### Bonus narrative

After a minigame resolves, the game produces a message that ties the player's most recent story choice to the outcome. This uses a three-level fallback:

1. **Bespoke prose** — for high-drama combinations (e.g. declining a VC pitch and then winning the mining sprint), a hand-written sentence captures the irony. These are stored as a lookup table keyed by event + choice.
2. **Label bridge** — if no hand-written entry exists, the player's choice label is prepended to the standard outcome message: *After "Pay for rush shipping": Bonus WON — ...*
3. **Bare default** — if there is no event context at all, the plain mechanical result is returned.

Every combination produces a valid message. Higher levels just produce more meaning.

### Key design decisions

- **The server owns all game state.** The browser never calculates rewards or advances the game on its own — it sends an action and re-renders from whatever the server returns. This makes cheating structurally difficult and keeps the client trivially simple.
- **Every response returns the full state.** Rather than sending a diff, the server always returns a complete snapshot. The client never has to merge, track deltas, or risk falling out of sync.
- **The game is designed to never crash on external failures.** Weather API calls always have a fallback. Routes always return structured error JSON. No unhandled exception reaches the browser.
- **Win takes priority over lose.** Reaching San Francisco on a turn where resources also hit a threshold counts as a win, not a loss — the destination is the goal.
- **No arrival event fires on the final city.** San Francisco triggers the win screen immediately, not another decision modal.
- **All randomness is testable without changing production code.** Functions that use random values accept an injectable source, so tests can control outcomes precisely without patching global state.

## Future Improvements — Systems Thinking at Scale

The current app is intentionally scoped for a single-server demo: clean, quick, and deployable. The limitations below are known tradeoffs, not oversights, each one has a clear upgrade path when the use case demands it in the future.

**Scale** — The app is currently single-server by design: all active sessions live in one process's memory, so adding a second server or worker would split that state and break the game. Moving session storage to Redis — a shared, external key-value store — decouples state from any individual server instance, making horizontal scaling straightforward without changing the game logic.

**Reliability** — In-memory state and on-disk save files are both wiped on every server restart. Durability requires moving each layer to a purpose-built store: Redis for active sessions (fast reads/writes, configurable TTL) and PostgreSQL for save files (durable, queryable, survives restarts). This separation also matches each store to what it's good at rather than using one solution for both.

**Consistency** — The current lock prevents two threads from corrupting the shared games dict, but it doesn't prevent a race on a single game: two simultaneous moves could both read the same state snapshot, and whichever write lands second silently discards the first. The fix is optimistic concurrency control, by stamping each state with a version number and rejecting writes that are based on a stale version, so the second request retries on fresh state rather than overwriting it.

**Security** — Right now, when an event appears, the server sends the full event object to the browser, including the exact resource effects of every choice. A player who inspects the network response can see what each option does before choosing. This is fine for a demo, but a production version would send only the display text and resolve the effects server-side when a choice is submitted, so the outcome data is never exposed.

**Observability** — Errors in weather fetches are silently swallowed by the fallback. A production version would log every caught exception with enough context to diagnose it, add a health-check endpoint so a monitor can verify the server is alive, and emit structured request logs that feed into a dashboard or alerting system.

**Inbound rate limiting** — There is currently no throttling on incoming requests. Any client can hit the API as fast as they want. Since the app has no user accounts, the natural key is IP address. Adding per-IP throttling on the moves endpoint would be the first step before opening the app to anonymous traffic.

**Content and stretch features** — Once persistence moves to a real database, a range of gameplay expansions become straightforward:

- **More minigames** — the dispatch system is already modular; a new minigame is one new endpoint and one new client screen with no changes to the core game loop.
- **User profiles, leaderboards, and DMs** — persistent identity unlocks social features. A leaderboard is a simple query on run outcomes; direct messages between travelers are a small messages table.
- **Multiplayer / network version** — multiple travelers on the same trail whose decisions affect each other. Players could see each other's resource state in real time, trade, or compete. Social dynamics — cooperation vs. sabotage — emerge naturally from shared state. Real-time updates would use WebSockets or long-polling so each player is notified when it's their turn.
- **Event memory system** — track which events a player has already seen and deprioritise repeats, so longer runs feel fresh. A richer version could unlock follow-up events based on past choices, turning individual events into branching story threads.

## AI usage in development

This project was built in active collaboration with an AI coding assistant (Cursor / Claude). I want to be transparent and specific about what that collaboration looked like, because I think *how* I used AI is as meaningful as *what* I built.

**What the AI helped with**

- **Frontend scaffolding** — The initial HTML structure, CSS layout, and JavaScript fetch wiring in `client/` were drafted with AI assistance. I directed the interaction model (single-page, server-authoritative state, modal flow for events and minigames) and reviewed every output against the API contract I had designed.
- **Documentation** — The README structure, section framing, and much of the prose were drafted collaboratively. I provided the design decisions; the AI helped articulate them clearly and consistently. Every technical claim was cross-checked against the actual code before committing.
- **Bug identification and fixes** — I ran a systematic code-analysis pass and brought the findings to the AI one by one. Together we diagnosed and fixed: incorrect `Path().parent` chains, a `KeyError` in offline weather fallback, missing thread safety on `_games`, wrong HTTP status codes (`400` where `404`/`409`/`500` belonged), a win/lose condition ordering bug, a day-counter off-by-one on losing turns, and redundant inline clamping in action handlers.
- **Refactoring for quality** — The `bonus_narrative.py` data/logic separation, the `rng` injection pattern for testable randomness, the extraction of magic numbers into named constants (`BONUS_MINIGAME_CHANCE`, `P_WEATHER_EVENT_ROUGH`, `STARTING_CASH`, etc.), and the strict boolean validation on minigame endpoints were all improvements I worked through with AI assistance.

**What I owned and drove**

- **All game design decisions** — the trail cities, resource types, win/lose thresholds, event content, minigame mechanics, bonus pity rules, and narrative writing are mine.
- **The architecture** — server-authoritative state, REST-ish API shape, the two-layer storage model, the decision to use Flask + vanilla JS, the choice of Open-Meteo. I explained these to the AI, not the other way around.
- **Understanding every change** — I did not merge anything I could not explain. When a fix was non-obvious (e.g. why `check_win` must run before `check_lose`, why `isinstance(x, bool)` is stricter than `bool(x)`, why `rng` injection is better than monkeypatching), I asked until I understood it, then kept the explanation in comments or docs.
- **Test verification** — every `pytest` run was executed and interpreted by me. When tests failed after a refactor, I diagnosed the failure before applying a fix.
- **Integration and judgment** — AI suggestions were starting points. Several were pushed back on, refined, or rejected. The final shape of every file reflects my judgment about what belongs in a production-quality take-home project.

**The honest framing**

Using AI as a collaborator on a take-home is something I'd do on the job too, the way an engineer uses Stack Overflow, a rubber duck, or a code reviewer. The skill being demonstrated is "can you make good architectural decisions, catch bugs before they ship, write clear documentation, and know what quality looks like." I used AI to move faster on the parts where speed was appropriate, and slower, asking more questions, reading more carefully, and on the parts where understanding mattered most.

## Special Note
Claire: "My GitHub repo currently shows only small portions of the total commits I've made, because I had to fix a nested Git repository issue midway through the project. My server/ folder had accidentally been initialized as its own separate Git repo, which meant commits were tracked there instead of at the project root — so client/, tests/, and requirements.txt were never being committed to GitHub at all. To fix the structure properly I removed the nested repo, re-initialized Git at the correct project root, and force-pushed. That reset the commit history, but the codebase itself is complete and unchanged. I'm happy to walk through any part of the code, the design decisions, or the bug fixes I made. Thank you! "
