"""Optional client-driven minigames — server applies rewards (authoritative state)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from . import bonus_narrative
from . import resources
from . import state as game_state

MINING_BONUS_CASH = 750
MINING_BONUS_COFFEE = 5
MINING_BONUS_MORALE = 3
MINING_BONUS_HYPE = 3
MINING_FAIL_MORALE = 5
MINING_FAIL_HYPE = 10

TYPING_BONUS_COFFEE = 15
TYPING_BONUS_MORALE = 3
TYPING_BONUS_HYPE = 2
TYPING_FAIL_MORALE = 5
TYPING_FAIL_HYPE = 8

HUNT_COFFEE_BONUS = 18
HUNT_COFFEE_MORALE = 2
HUNT_BONUS_HYPE = 2
HUNT_FAIL_MORALE = 4
HUNT_FAIL_HYPE = 8


def _clear_bonus_round(state: Dict[str, Any]) -> None:
    state["mining_eligible"] = False
    state["minigame_type"] = None
    state.pop("last_event_choice", None)


def _wrong_minigame(state: Dict[str, Any], expected: str) -> bool:
    if state.get("status") != "playing":
        return True
    if not state.get("mining_eligible"):
        return True
    if state.get("minigame_type") != expected:
        return True
    return False


def apply_mining_result(state: Dict[str, Any], success: bool) -> Tuple[Dict[str, Any], str]:
    if state.get("status") != "playing":
        return state, "The journey is already over."
    if _wrong_minigame(state, "mining"):
        return state, "No mining bonus available right now."

    if success:
        default = (
            f"Bonus WON — Mining haul secured: +${MINING_BONUS_CASH} cash, +{MINING_BONUS_COFFEE} coffee, "
            f"+{MINING_BONUS_MORALE} morale, +{MINING_BONUS_HYPE} hype."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "mining",
            True,
            default,
            {
                "cash": MINING_BONUS_CASH,
                "coffee": MINING_BONUS_COFFEE,
                "morale": MINING_BONUS_MORALE,
                "bonus_hype": MINING_BONUS_HYPE,
            },
        )
    else:
        default = (
            f"Bonus LOST — Mining missed: −{MINING_FAIL_MORALE} morale, −{MINING_FAIL_HYPE} hype "
            f"(the room questions whether the buzz was real)."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "mining",
            False,
            default,
            {"fail_morale": MINING_FAIL_MORALE, "fail_hype": MINING_FAIL_HYPE},
        )

    _clear_bonus_round(state)
    r = state["resources"]
    if success:
        r["cash"] = r.get("cash", 0) + MINING_BONUS_CASH
        r["coffee"] = r.get("coffee", 0) + MINING_BONUS_COFFEE
        r["morale"] = min(100, r.get("morale", 0) + MINING_BONUS_MORALE)
        r["hype"] = min(100, r.get("hype", 0) + MINING_BONUS_HYPE)
        game_state.append_log(
            state,
            f"Codebase mining haul: +${MINING_BONUS_CASH} cash, +{MINING_BONUS_COFFEE} coffee, +{MINING_BONUS_MORALE} morale, +{MINING_BONUS_HYPE} hype.",
        )
        resources.clamp_resources(state)
        return state, out
    r["morale"] = max(0, r.get("morale", 0) - MINING_FAIL_MORALE) 
    r["hype"] = max(0, r.get("hype", 0) - MINING_FAIL_HYPE)
    game_state.append_log(
        state,
        f"Mining drill failed: -{MINING_FAIL_MORALE} morale, -{MINING_FAIL_HYPE} hype.",
    )
    resources.clamp_resources(state) 
    return state, out


def apply_typing_result(state: Dict[str, Any], success: bool) -> Tuple[Dict[str, Any], str]:
    if state.get("status") != "playing":
        return state, "The journey is already over."
    if _wrong_minigame(state, "typing"):
        return state, "No typing bonus available right now."

    if success:
        default = (
            f"Bonus WON — Order placed: +{TYPING_BONUS_COFFEE} coffee, +{TYPING_BONUS_MORALE} morale, "
            f"+{TYPING_BONUS_HYPE} hype."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "typing",
            True,
            default,
            {
                "coffee": TYPING_BONUS_COFFEE,
                "morale": TYPING_BONUS_MORALE,
                "bonus_hype": TYPING_BONUS_HYPE,
            },
        )
    else:
        default = (
            f"Bonus LOST — Typing failed: −{TYPING_FAIL_MORALE} morale, −{TYPING_FAIL_HYPE} hype "
            f"(your brand takes a ding online)."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "typing",
            False,
            default,
            {"fail_morale": TYPING_FAIL_MORALE, "fail_hype": TYPING_FAIL_HYPE},
        )

    _clear_bonus_round(state)
    r = state["resources"]
    if success:
        r["coffee"] = r.get("coffee", 0) + TYPING_BONUS_COFFEE
        r["morale"] = min(100, r.get("morale", 0) + TYPING_BONUS_MORALE)
        r["hype"] = min(100, r.get("hype", 0) + TYPING_BONUS_HYPE)
        game_state.append_log(
            state,
            f"Coffee order rush: +{TYPING_BONUS_COFFEE} coffee, +{TYPING_BONUS_MORALE} morale, +{TYPING_BONUS_HYPE} hype.",
        )
        resources.clamp_resources(state)
        return state, out
    r["morale"] = max(0, r.get("morale", 0) - TYPING_FAIL_MORALE)
    r["hype"] = max(0, r.get("hype", 0) - TYPING_FAIL_HYPE)
    game_state.append_log(
        state,
        f"Order botched: -{TYPING_FAIL_MORALE} morale, -{TYPING_FAIL_HYPE} hype.",
    )
    resources.clamp_resources(state)
    return state, out


def apply_coffee_hunt_result(state: Dict[str, Any], success: bool) -> Tuple[Dict[str, Any], str]:
    if state.get("status") != "playing":
        return state, "The journey is already over."
    if _wrong_minigame(state, "coffee_hunt"):
        return state, "No coffee hunt bonus available right now."

    if success:
        default = (
            f"Bonus WON — Beans secured: +{HUNT_COFFEE_BONUS} coffee, +{HUNT_COFFEE_MORALE} morale, "
            f"+{HUNT_BONUS_HYPE} hype."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "coffee_hunt",
            True,
            default,
            {
                "coffee": HUNT_COFFEE_BONUS,
                "morale": HUNT_COFFEE_MORALE,
                "bonus_hype": HUNT_BONUS_HYPE,
            },
        )
    else:
        default = (
            f"Bonus LOST — Hunt missed: −{HUNT_FAIL_MORALE} morale, −{HUNT_FAIL_HYPE} hype "
            f"(the clip goes nowhere)."
        )
        out = bonus_narrative.bonus_outcome_message(
            state,
            "coffee_hunt",
            False,
            default,
            {"fail_morale": HUNT_FAIL_MORALE, "fail_hype": HUNT_FAIL_HYPE},
        )

    _clear_bonus_round(state)
    r = state["resources"]
    if success:
        r["coffee"] = r.get("coffee", 0) + HUNT_COFFEE_BONUS
        r["morale"] = min(100, r.get("morale", 0) + HUNT_COFFEE_MORALE)
        r["hype"] = min(100, r.get("hype", 0) + HUNT_BONUS_HYPE)
        game_state.append_log(
            state,
            f"Coffee hunt: bagged beans for the office. +{HUNT_COFFEE_BONUS} coffee, +{HUNT_COFFEE_MORALE} morale, +{HUNT_BONUS_HYPE} hype.",
        )
        resources.clamp_resources(state)
        return state, out
    r["morale"] = max(0, r.get("morale", 0) - HUNT_FAIL_MORALE)
    r["hype"] = max(0, r.get("hype", 0) - HUNT_FAIL_HYPE)
    game_state.append_log(
        state,
        f"Coffee hunt whiffed: -{HUNT_FAIL_MORALE} morale, -{HUNT_FAIL_HYPE} hype.",
    )
    resources.clamp_resources(state)
    return state, out
