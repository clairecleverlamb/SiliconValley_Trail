"""Layer event choice + minigame result into a single coherent report line."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# (event_id, choice_label) -> minigame_key -> success -> format template
# Templates use .format(**stats) plus optional label= from context.
_LAYERED: Dict[Tuple[str, str], Dict[str, Dict[bool, str]]] = {
    (
        "vc_pitch",
        "Decline politely",
    ): {
        "mining": {
            True: (
                "Bonus WON — Polite decline on the pitch—then a sharp crystal-mining sprint. "
                "The partner smirks: you’re not desperate, but you execute. "
                "Small bridge check, warm intro, and a real coffee. "
                "(+${cash} cash, +{coffee} coffee, +{morale} morale, +{bonus_hype} hype)"
            ),
            False: (
                "Bonus LOST — You declined politely, then the mining sprint collapsed. "
                "The partner reads nerves as lack of execution. "
                "(−{fail_morale} morale, −{fail_hype} hype—the buzz you built earlier looks shaky.)"
            ),
        },
        "typing": {
            True: (
                "Bonus WON — Polite pass on the pitch—then a flawless coffee typing sprint. "
                "Your analyst notices discipline. They slide a stipend and a warm intro. "
                "(+{coffee} coffee, +{morale} morale, +{bonus_hype} hype)"
            ),
            False: (
                "Bonus LOST — You declined politely, then the typing sprint looked like a botched macro. "
                "The room cools. (−{fail_morale} morale, −{fail_hype} hype.)"
            ),
        },
        "coffee_hunt": {
            True: (
                "Bonus WON — Polite decline—then you bag the beans on the hunt. "
                "Your ops story gets cred. (+{coffee} coffee, +{morale} morale, +{bonus_hype} hype)"
            ),
            False: (
                "Bonus LOST — Polite decline—then a whiffed hunt on the flying beans. "
                "Your team looks tired. (−{fail_morale} morale, −{fail_hype} hype.)"
            ),
        },
    },
}


def bonus_outcome_message(
    state: Dict[str, Any],
    minigame: str,
    success: bool,
    default_message: str,
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    """
    If we have last_event_choice and a layered template, return that; else a soft bridge
    using the choice label; else the mechanical default_message.
    """
    stats = dict(stats or {})
    ctx = state.get("last_event_choice") or {}
    event_id = ctx.get("event_id")
    label = ctx.get("choice_label") or ""

    key = (event_id, label)
    layered = _LAYERED.get(key, {}).get(minigame, {}).get(success)
    if layered:
        try:
            return layered.format(**stats)
        except (KeyError, ValueError):
            return layered

    if label:
        return f'After “{label}”: {default_message}'
    return default_message
