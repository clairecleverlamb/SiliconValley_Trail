"""Core per-turn resolution."""

from __future__ import annotations

import random
from typing import Any, Dict, Tuple

from api import weather as weather_api

from . import actions
from . import conditions
from . import events as game_events
from . import resources
from . import state as game_state

# Probability of offering a bonus minigame after an event choice (subject to pity and first-event rules).
BONUS_MINIGAME_CHANCE = 0.55


def _passive_decay(state: Dict[str, Any]) -> None:
    state["resources"]["coffee"] -= 3
    state["resources"]["bugs"] += 1
    overhead = int(state.get("daily_overhead_cash", game_state.DAILY_OVERHEAD_CASH))
    state["resources"]["cash"] -= overhead


def _update_coffee_emergency(state: Dict[str, Any]) -> None:
    if state["resources"]["coffee"] <= 0:
        state["coffee_emergency_turns"] += 1
    else:
        state["coffee_emergency_turns"] = 0

def resolve_turn(state: Dict[str, Any], action: str, rng: Any = random) -> Tuple[Dict[str, Any], str]:
    if state["status"] != "playing":
        return state, "The journey is already over."

    state["mining_eligible"] = False
    state["minigame_type"] = None
    state.pop("last_event_choice", None)

    if state.get("current_event"):
        raise ValueError("event_blocking")

    if action not in actions.ACTIONS:
        raise KeyError("invalid_action")

    before = resources.resource_snapshot(state)
    flavor = actions.run_action(state, action, rng)
    resources.clamp_resources(state)
    after_action = resources.resource_snapshot(state)
    action_d = resources.format_deltas(
        resources.delta_snapshots(before, after_action)
    )

    _passive_decay(state)
    resources.clamp_resources(state)
    after_passive = resources.resource_snapshot(state)
    passive_d = resources.format_deltas(
        resources.delta_snapshots(after_action, after_passive)
    )

    parts = [flavor]
    # Action handlers spell out base vs weather and per-action effects.
    # Client splits on " | Turn: " for the banner "Daily upkeep" section.
    if passive_d:
        parts.append(
            f"| Turn: Daily burn (overhead, coffee drain, bugs creep): {passive_d}."
        )
    msg = " ".join(parts)

    _update_coffee_emergency(state)


##travel action handler, it updates the current location index and refreshes the weather

    if action == "travel":
        new_idx = state["current_location_index"] + 1
        state["current_location_index"] = new_idx
        loc = game_state.LOCATIONS[new_idx]["name"]
        weather_api.refresh_city_in_state(state, loc)
        if new_idx < 9:
            weather = state.get("weather_cache", {}).get(loc, {})
            state["current_event"] = game_events.pick_event(loc, weather, rng)
            ev = state["current_event"]
            msg = f"{msg} You arrive in {loc}. {ev.get('title', 'Something')} demands a decision."
        else:
            state["current_event"] = None
            msg = f"{msg} You arrive in {loc}."

    game_state.append_log(state, msg)

    # Win is checked first: reaching SF is a win regardless of resource state.
    if conditions.check_win(state):
        win_msg = "You made it to San Francisco—time to pitch Series A."
        game_state.append_log(state, win_msg)
        state["day"] = state.get("day", 1) + 1
        return state, win_msg

    if conditions.check_lose(state):
        state["day"] = state.get("day", 1) + 1
        game_state.append_log(state, state.get("lost_reason") or "Game over.")
        return state, state.get("lost_reason") or "Lost."

    state["day"] = state.get("day", 1) + 1
    if conditions.check_time_out(state):
        game_state.append_log(state, state.get("lost_reason") or "Game over.")
        return state, state.get("lost_reason") or "Lost."
    if state["status"] == "playing" and action != "travel":
        idx = int(state.get("current_location_index", 0))
        weather_api.refresh_city_in_state(
            state, game_state.LOCATIONS[idx]["name"]
        )
    return state, msg

def resolve_event_turn(state: Dict[str, Any], choice: int, rng: Any = random) -> Tuple[Dict[str, Any], str]:
    if state["status"] != "playing":
        return state, "The journey is already over."

    try:
        msg = game_events.resolve_event_choice(state, choice, rng)
    except ValueError as e:
        raise ValueError(str(e)) from e

    resources.clamp_resources(state)

    before_decay = resources.resource_snapshot(state)
    _passive_decay(state)
    resources.clamp_resources(state)
    after_decay = resources.resource_snapshot(state)
    passive_d = resources.format_deltas(
        resources.delta_snapshots(before_decay, after_decay)
    )
    if passive_d:
        msg = (
            f"{msg} | Turn: Daily burn (overhead, coffee drain, bugs creep): {passive_d}."
        )

    game_state.append_log(state, msg)

    _update_coffee_emergency(state)

    # Win is checked first: reaching SF is a win regardless of resource state.
    if conditions.check_win(state):
        win_msg = "You made it to San Francisco—time to pitch Series A."
        game_state.append_log(state, win_msg)
        state["day"] = state.get("day", 1) + 1
        return state, win_msg

    if conditions.check_lose(state):
        state["day"] = state.get("day", 1) + 1
        game_state.append_log(state, state.get("lost_reason") or "Game over.")
        return state, state.get("lost_reason") or "Lost."

    state["day"] = state.get("day", 1) + 1
    if conditions.check_time_out(state):
        game_state.append_log(state, state.get("lost_reason") or "Game over.")
        return state, state.get("lost_reason") or "Lost."

    # Bonus minigame: first resolved event in a run always offers one (tutorial beat),
    # then ~55% per event, with a guaranteed offer after 2 misses in a row (pity).
    state.setdefault("events_since_bonus", 0)
    state.setdefault("first_event_bonus_pending", False)

    force_bonus = False
    if state.get("first_event_bonus_pending"):
        force_bonus = True
        state["first_event_bonus_pending"] = False
    elif int(state.get("events_since_bonus", 0)) >= 2:
        force_bonus = True

    if force_bonus or rng.random() < BONUS_MINIGAME_CHANCE:
        state["mining_eligible"] = True
        state["minigame_type"] = rng.choice(["mining", "typing", "coffee_hunt"])
        state["events_since_bonus"] = 0
    else:
        state["mining_eligible"] = False
        state["minigame_type"] = None
        state["events_since_bonus"] = int(state.get("events_since_bonus", 0)) + 1
        state.pop("last_event_choice", None)
    if state["status"] == "playing":
        idx = int(state.get("current_location_index", 0))
        weather_api.refresh_city_in_state(
            state, game_state.LOCATIONS[idx]["name"]
        )
    return state, msg
