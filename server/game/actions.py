"""Player action handlers — mutate state in place; return log message."""

from __future__ import annotations

import random
from typing import Any, Callable, Dict

from api import weather as weather_api
from . import resources
from . import state as game_state

ActionFn = Callable[[Dict[str, Any]], str]


def _idx(state: Dict[str, Any]) -> int:
    return int(state["current_location_index"])


def _effects_line(before: Dict[str, int], after: Dict[str, int]) -> str:
    d = resources.format_deltas(resources.delta_snapshots(before, after))
    return d if d else "no resource change"


def action_travel(state: Dict[str, Any]) -> str:
    i = _idx(state)
    if i >= 9:
        raise ValueError("cannot_travel")
    dest = game_state.LOCATIONS[i + 1]
    w = state.get("weather_cache", {}).get(dest["name"], weather_api.WEATHER_FALLBACK.get(dest["name"], {}))
    cond = str(w.get("condition") or "—")

    state["resources"]["cash"] -= 1500
    state["resources"]["morale"] -= 5
    base_line = "Base travel: -$1,500 cash, -5 morale."

    mid = resources.resource_snapshot(state)
    weather_api.apply_weather_modifiers(state, w)
    resources.clamp_resources(state)
    after_w = resources.resource_snapshot(state)
    weather_d = resources.format_deltas(resources.delta_snapshots(mid, after_w))
    if weather_d:
        weather_line = f"Weather ({cond}): {weather_d}."
    else:
        weather_line = f"Weather ({cond}): no extra travel modifier."

    return (
        f"You hit the road toward {dest['name']}. "
        f"{base_line} "
        f"{weather_line}"
    )


def action_rest(state: Dict[str, Any]) -> str:
    before = resources.resource_snapshot(state)
    r = state["resources"]
    r["morale"] += 20
    r["coffee"] -= 8
    r["bugs"] += 2
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    return (
        "The team rests and recharges (slowly). "
        f"Rest effects: {_effects_line(before, after)}."
    )


def action_hackathon(state: Dict[str, Any]) -> str:
    before = resources.resource_snapshot(state)
    r = state["resources"]
    r["bugs"] -= 10
    r["morale"] -= 10
    r["coffee"] -= 10
    r["hype"] += 5
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    return (
        "Hackathon sprint: you burn down a backlog of bugs and pick up hype—"
        "worth it when tech debt or launch pressure is high, but it drains morale and coffee. "
        f"Hackathon effects: {_effects_line(before, after)}."
    )


def action_pitch_vc(state: Dict[str, Any]) -> str:
    i = _idx(state)
    loc = game_state.LOCATIONS[min(i, len(game_state.LOCATIONS) - 1)]["name"]
    before = resources.resource_snapshot(state)
    r = state["resources"]
    if random.random() < 0.6:
        r["cash"] += 15000
        r["hype"] += 20
        resources.clamp_resources(state)
        after = resources.resource_snapshot(state)
        return (
            f"Great pitch in {loc}! They're interested in Series A. "
            f"Pitch outcome (success): {_effects_line(before, after)}."
        )
    r["morale"] -= 20
    r["hype"] -= 10
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    return (
        f"Pitch flopped in {loc}. Team morale took a hit. "
        f"Pitch outcome (flop): {_effects_line(before, after)}."
    )


def action_marketing_push(state: Dict[str, Any]) -> str:
    before = resources.resource_snapshot(state)
    r = state["resources"]
    r["cash"] -= 3000
    r["hype"] += 25
    r["morale"] -= 5
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    return (
        "Marketing push lands—loud, expensive, visible. "
        f"Marketing effects: {_effects_line(before, after)}."
    )


def action_buy_supplies(state: Dict[str, Any]) -> str:
    before = resources.resource_snapshot(state)
    r = state["resources"]
    r["cash"] -= 1500
    r["coffee"] += 20
    r["morale"] += 5
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    return (
        "Supplies acquired. Beans and hope restocked. "
        f"Supply run effects: {_effects_line(before, after)}."
    )


ACTIONS: Dict[str, ActionFn] = {
    "travel": action_travel,
    "rest": action_rest,
    "hackathon": action_hackathon,
    "pitch_vc": action_pitch_vc,
    "marketing_push": action_marketing_push,
    "buy_supplies": action_buy_supplies,
}


def run_action(state: Dict[str, Any], name: str) -> str:
    if name not in ACTIONS:
        raise KeyError("invalid_action")
    return ACTIONS[name](state)
