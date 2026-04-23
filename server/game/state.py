"""Game state shape, locations, and in-memory games keyed by game_id."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional

LOCATIONS: List[Dict[str, str]] = [
    {"name": "San Jose", "description": "Your startup's humble garage HQ"},
    {"name": "Santa Clara", "description": "Home of tech giants"},
    {"name": "Sunnyvale", "description": "Where the sun always shines on semiconductors"},
    {"name": "Cupertino", "description": "One Infinite Loop territory"},
    {"name": "Mountain View", "description": "Googleplex energy"},
    {"name": "Palo Alto", "description": "Sand Hill Road VC territory"},
    {"name": "Menlo Park", "description": "Meta HQ and quiet money"},
    {"name": "Redwood City", "description": "The unglamorous middle"},
    {"name": "San Mateo", "description": "Almost there, almost broke"},
    {"name": "San Francisco", "description": "DESTINATION — pitch Series A"},
]

LOG_MAX = 10

# Calendar days in which to reach San Francisco; each action (rest, travel, etc.) uses one day.
MAX_JOURNEY_DAYS = 20

# Starting cash for every new run.
STARTING_CASH = 20_000

# Cash charged every turn after your action (and during events): rent, payroll, burn rate.
# Scaled for short runway + $20k start (see STARTING_CASH).
DAILY_OVERHEAD_CASH = 320

# Lose when bug count exceeds this (strictly more than — i.e. game over at 21+ bugs).
BUGS_LOSE_THRESHOLD = 20

_games: Dict[str, Dict[str, Any]] = {}
_games_lock = threading.Lock()


def get_game(game_id: str) -> Optional[Dict[str, Any]]:
    with _games_lock:
        return _games.get(game_id)


def put_game(state: Dict[str, Any]) -> None:
    with _games_lock:
        _games[state["game_id"]] = state


def new_game_id() -> str:
    return str(uuid.uuid4())


def create_initial_state(game_id: str, weather_cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "game_id": game_id,
        "day": 1,
        "max_days": MAX_JOURNEY_DAYS,
        "daily_overhead_cash": DAILY_OVERHEAD_CASH,
        "status": "playing",
        "lost_reason": None,
        "current_location_index": 0,
        "resources": {
            "cash": STARTING_CASH,
            "morale": 75,
            "coffee": 28,
            "hype": 40,
            "bugs": 0,
        },
        "weather_cache": weather_cache,
        "coffee_emergency_turns": 0,
        "current_event": None,
        "mining_eligible": False,
        "minigame_type": None,
        # First event in a run guarantees a minigame; after that, random + pity (see loop.resolve_event_turn).
        "first_event_bonus_pending": True,
        "events_since_bonus": 0,
        "log": [],
        # Set when the player saves with a display name (also stored in the JSON file on disk).
        "save_name": None,
    }


def append_log(state: Dict[str, Any], message: str) -> None:
    log: List[str] = state.setdefault("log", [])
    log.append(message)
    if len(log) > LOG_MAX:
        del log[: len(log) - LOG_MAX]


