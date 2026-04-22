"""Win / lose checks."""

from __future__ import annotations

from typing import Any, Dict

from .state import BUGS_LOSE_THRESHOLD, MAX_JOURNEY_DAYS


def check_win(state: Dict[str, Any]) -> bool:
    if state["current_location_index"] >= 9:
        state["status"] = "won"
        return True
    return False


def check_lose(state: Dict[str, Any]) -> bool:
    r = state["resources"]
    if r["cash"] <= 0:
        state["status"] = "lost"
        state["lost_reason"] = "You ran out of funding. Startup dead."
        return True
    if r["morale"] <= 0:
        state["status"] = "lost"
        state["lost_reason"] = "Team quit. Morale collapsed."
        return True
    # Counts end-of-turn snapshots with coffee <= 0; need 3 in a row before game over
    # so the player gets 2 full turns after first hitting 0 to buy supplies or recover.
    if state["coffee_emergency_turns"] >= 3:
        state["status"] = "lost"
        state["lost_reason"] = "No coffee for 3 turns in a row. Everyone quit."
        return True
    if r["bugs"] > BUGS_LOSE_THRESHOLD:
        state["status"] = "lost"
        state["lost_reason"] = "Technical debt buried you. App crashed."
        return True
    return False


def check_time_out(state: Dict[str, Any]) -> bool:
    """Call after advancing the calendar day. Lose if past max_days."""
    if state["status"] != "playing":
        return False
    limit = int(state.get("max_days", MAX_JOURNEY_DAYS))
    if int(state.get("day", 1)) > limit:
        state["status"] = "lost"
        state["lost_reason"] = (
            "Your runway window closed—the calendar ran out before Series A."
        )
        return True
    return False
