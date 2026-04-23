"""HTTP API for games — resource-oriented paths under /api/games.

Parses request bodies, delegates to game engine, handles errors, and returns JSON responses.
Contains no game business logic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Blueprint, jsonify, request

from api.weather import fetch_all_weather
from game import loop
from game import minigames as game_minigames
from game.state import (
    DAILY_OVERHEAD_CASH,
    LOCATIONS,
    MAX_JOURNEY_DAYS,
    create_initial_state,
    get_game,
    new_game_id,
    put_game,
)

bp = Blueprint("games", __name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_GAMES_DIR = _PROJECT_ROOT / "games"


def _json_with_outcome(state: dict, outcome: str = "") -> object:
    body = dict(state)
    body["outcome"] = outcome
    return jsonify(body)


def _not_found() -> tuple:
    return jsonify({"error": "Game not found"}), 404


def _require_bool_success(data: dict) -> tuple | None:
    """Return a 400 response if 'success' is absent or not a JSON boolean, else None."""
    if not isinstance(data.get("success"), bool):
        return jsonify({"error": "'success' must be a JSON boolean (true or false)"}), 400
    return None


_SAVE_SLUG_MAX = 48 #it is the filename of the save file, it is a unique identifier for the save file


def _save_slug(display: str) -> str | None:
    """Return a safe filename stem, or None if there is nothing usable."""
    s = display.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return None
    return s[:_SAVE_SLUG_MAX]


def _prune_other_named_saves_for_game(games_dir: Path, game_id: str, keep_slug: str) -> None:
    """Drop old slug files for this game after renaming (keep only games/<keep_slug>.json and games/<game_id>.json)."""
    uuid_backup = games_dir / f"{game_id}.json"
    keep_path = games_dir / f"{keep_slug}.json"
    for path in games_dir.glob("*.json"):
        if path == uuid_backup or path == keep_path:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("game_id") == game_id:
            try:
                path.unlink()
            except OSError:
                pass


def _finalize_loaded_state(st: dict) -> None:
    st.setdefault("mining_eligible", False)
    st.setdefault("minigame_type", None)
    if st.get("minigame_type") == "bug_squash":
        st["minigame_type"] = "mining"
    st.setdefault("first_event_bonus_pending", False)
    st.setdefault("events_since_bonus", 0)
    st.setdefault("max_days", MAX_JOURNEY_DAYS)
    st.setdefault("daily_overhead_cash", DAILY_OVERHEAD_CASH)
    st.setdefault("save_name", None)


@bp.post("")
def new_game():
    gid = new_game_id()
    weather = fetch_all_weather(LOCATIONS)
    st = create_initial_state(gid, weather)
    put_game(st)
    return _json_with_outcome(st, "New game started.")


@bp.get("/<game_id>")
def get_state(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()
    return _json_with_outcome(st, "")


@bp.post("/<game_id>/moves")
def take_action(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    data = request.get_json(silent=True) or {}
    action = data.get("action")

    if st.get("current_event"):
        return jsonify({"error": "Resolve the current event first"}), 400

    try:
        st, outcome = loop.resolve_turn(st, action)
    except KeyError:
        return jsonify({"error": "Invalid action"}), 400
    except ValueError as exc:
        code = str(exc)
        if code == "cannot_travel":
            return jsonify({"error": "Cannot travel"}), 400
        return jsonify({"error": code}), 400

    put_game(st)
    return _json_with_outcome(st, outcome)


@bp.post("/<game_id>/events/choices")
def resolve_event(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    data = request.get_json(silent=True) or {}
    choice = data.get("choice")

    if choice not in (1, 2, 3):
        return jsonify({"error": "Invalid choice"}), 400

    try:
        st, outcome = loop.resolve_event_turn(st, int(choice))
    except ValueError as exc:
        if str(exc) == "no_event":
            return jsonify({"error": "No active event"}), 400
        return jsonify({"error": str(exc)}), 400

    put_game(st)
    return _json_with_outcome(st, outcome)


@bp.put("/<game_id>/saves")
def save_game(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    payload = request.get_json(silent=True) or {}
    raw_label = (payload.get("save_name") or payload.get("username") or "").strip()
    if not raw_label:
        return jsonify({"error": "Save name is required."}), 400

    slug = _save_slug(raw_label)
    if not slug:
        return jsonify(
            {
                "error": "Save name needs at least one letter or number (use a–z, 0–9, spaces become underscores).",
            }
        ), 400

    named = _GAMES_DIR / f"{slug}.json"
    if named.is_file():
        try:
            with open(named, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            return jsonify(
                {
                    "error": f'A save file "{slug}.json" exists but could not be read. Remove it or pick another name.',
                }
            ), 500
        existing_gid = existing.get("game_id")
        if existing_gid != st["game_id"]:
            return jsonify(
                {
                    "error": "That save name is already used by another game. Choose a different name, or load that save from the title screen and continue it.",
                }
            ), 409

    st["save_name"] = raw_label[:120]

    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    path = _GAMES_DIR / f'{st["game_id"]}.json'
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f)

    with open(named, "w", encoding="utf-8") as f:
        json.dump(st, f)
    _prune_other_named_saves_for_game(_GAMES_DIR, st["game_id"], slug)
    disp = st.get("save_name") or slug
    msg = (
        f'Game saved as "{disp}" — on the title screen, choose Load and type that same name. '
        f"(A server copy is also kept as {path.name}.)"
    )

    put_game(st)
    return _json_with_outcome(st, msg)


@bp.post("/restore-save")
def restore_save():
    """Load a game from games/<save_slug>.json (name chosen when saving)."""
    data = request.get_json(silent=True) or {}
    raw = (data.get("save_name") or data.get("username") or "").strip()
    slug = _save_slug(raw)
    if not slug:
        return jsonify({"error": "Enter a save name with at least one letter or number."}), 400

    path = _GAMES_DIR / f"{slug}.json"
    if not path.is_file():
        return jsonify({"error": "No saved game found for that name."}), 404

    with open(path, encoding="utf-8") as f:
        st = json.load(f)

    gid = st.get("game_id")
    if not isinstance(gid, str) or not gid:
        return jsonify({"error": "Save file is corrupted (missing game_id)."}), 500

    _finalize_loaded_state(st)
    put_game(st)
    return _json_with_outcome(st, "Game loaded.")


@bp.post("/<game_id>/loads")
def load_game(game_id: str):
    path = _GAMES_DIR / f"{game_id}.json"
    if not path.is_file():
        return jsonify({"error": "Save file not found"}), 404

    with open(path, encoding="utf-8") as f:
        st = json.load(f)

    if st.get("game_id") != game_id:
        return jsonify({"error": "Save file game_id does not match the requested id."}), 500

    _finalize_loaded_state(st)
    put_game(st)
    return _json_with_outcome(st, "Game loaded.")


@bp.post("/<game_id>/minigames/mining")
def mining_minigame(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    data = request.get_json(silent=True) or {}
    err = _require_bool_success(data)
    if err:
        return err

    st, outcome = game_minigames.apply_mining_result(st, data["success"])
    put_game(st)
    return _json_with_outcome(st, outcome)


@bp.post("/<game_id>/minigames/typing")
def typing_minigame(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    data = request.get_json(silent=True) or {}
    err = _require_bool_success(data)
    if err:
        return err

    st, outcome = game_minigames.apply_typing_result(st, data["success"])
    put_game(st)
    return _json_with_outcome(st, outcome)


@bp.post("/<game_id>/minigames/coffee_hunt")
def coffee_hunt_minigame(game_id: str):
    st = get_game(game_id)
    if not st:
        return _not_found()

    data = request.get_json(silent=True) or {}
    err = _require_bool_success(data)
    if err:
        return err

    st, outcome = game_minigames.apply_coffee_hunt_result(st, data["success"])
    put_game(st)
    return _json_with_outcome(st, outcome)
