"""Layer event choice + minigame result into a single coherent report line.

Design
------
_NARRATIVES stores only the unique flavor sentence for each
(event_id, choice_label, minigame, success) combination.
All boilerplate — "Bonus WON/LOST", resource change formatting — is
generated once in _build_message, keeping narrative content and
presentation logic fully separated.

Fallback chain in bonus_outcome_message:
  1. Layered narrative exists  → rich bespoke message
  2. Choice label known        → 'After "label": <default_message>'
  3. No context                → bare default_message
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Resource-change suffixes — generated once per minigame/outcome combination.
# ---------------------------------------------------------------------------

def _success_suffix(minigame: str, stats: Dict[str, Any]) -> str:
    try:
        if minigame == "mining":
            return (
                f"(+${stats['cash']} cash, +{stats['coffee']} coffee, "
                f"+{stats['morale']} morale, +{stats['bonus_hype']} hype)"
            )
        # typing and coffee_hunt share the same reward shape (no cash)
        return (
            f"(+{stats['coffee']} coffee, +{stats['morale']} morale, "
            f"+{stats['bonus_hype']} hype)"
        )
    except (KeyError, TypeError):
        return ""


def _fail_suffix(stats: Dict[str, Any]) -> str:
    try:
        return f"(−{stats['fail_morale']} morale, −{stats['fail_hype']} hype)"
    except (KeyError, TypeError):
        return ""


def _build_message(narrative: str, minigame: str, success: bool, stats: Dict[str, Any]) -> str:
    """Combine prefix + unique narrative + resource suffix into one line."""
    prefix = "Bonus WON — " if success else "Bonus LOST — "
    suffix = _success_suffix(minigame, stats) if success else _fail_suffix(stats)
    return f"{prefix}{narrative} {suffix}".strip()


# ---------------------------------------------------------------------------
# Narrative content — only the unique prose sentence per combination.
# (event_id, choice_label) -> minigame -> success -> flavor string
# ---------------------------------------------------------------------------

_NARRATIVES: Dict[Tuple[str, str], Dict[str, Dict[bool, str]]] = {

    # ── VC PITCH (Santa Clara) ────────────────────────────────────────────────
    ("vc_pitch", "Decline politely"): {
        "mining":      {True:  "Polite decline on the pitch—then a sharp mining sprint. The partner smirks: you're not desperate, but you execute.",
                        False: "Declined politely, then the mining sprint collapsed. The partner reads nerves as lack of execution."},
        "typing":      {True:  "Polite pass on the pitch—then a flawless typing sprint. Your analyst notices discipline. They slide a warm intro.",
                        False: "Declined politely, then the typing sprint looked like a botched macro. The room cools."},
        "coffee_hunt": {True:  "Polite decline—then you bag the beans on the hunt. Your ops story gets cred.",
                        False: "Polite decline—then a whiffed hunt on the flying beans. Your team looks tired."},
    },
    ("vc_pitch", "Pitch unprepared"): {
        "mining":      {True:  "Swung for the pitch with nothing prepared, then nailed the mining haul. Bold execution back-to-back. The room is uncertain but impressed.",
                        False: "Unprepared pitch and a failed mining sprint. Two swings, two misses. Morale reads the room."},
        "typing":      {True:  "Winged the pitch, then typed out a perfect coffee order. Maybe chaos is your workflow.",
                        False: "Unprepared pitch, botched typing sprint. The team is quietly updating their LinkedIn."},
        "coffee_hunt": {True:  "Went in blind on the pitch, then hunted down every bean. Chaos, caffeine, confidence.",
                        False: "Unprepared pitch and a whiffed hunt. Double-down, double-loss."},
    },
    ("vc_pitch", "Ask for prep time"): {
        "mining":      {True:  "Took the prep day, then mined clean. Methodical is your brand.",
                        False: "Spent the day prepping, then the mining sprint fell apart. The VC wonders if you execute."},
        "typing":      {True:  "Prepared thoroughly, then nailed the typing sprint. Diligence compounds.",
                        False: "Prepped all day, then fumbled the typing. Preparation without execution is just a plan."},
        "coffee_hunt": {True:  "Took time to prep, then bagged every bean. Solid ops game.",
                        False: "Prep day spent, hunt missed. The runway feels shorter."},
    },

    # ── APPLE RECRUITER (Cupertino) ───────────────────────────────────────────
    ("apple_recruiter", "Ignore it"): {
        "mining":      {True:  "Ignored the recruiter and mined clean. Bet on loyalty, paid off.",
                        False: "Ignored the recruiter, then the sprint flopped. The dev is typing a Slack message you don't want to read."},
        "typing":      {True:  "Bet on loyalty, then nailed the order sprint. Team still here, coffee secured.",
                        False: "Ignored the Apple email and fumbled the typing sprint. A bad omen."},
        "coffee_hunt": {True:  "Ignored the recruiter, bagged the beans. Focus wins the morning.",
                        False: "Ignored the recruiter and whiffed the hunt. Your dev is now on a Zoom call you weren't invited to."},
    },

    # ── GARAGE LANDLORD (San Jose) ────────────────────────────────────────────
    ("garage_landlord", "Host a demo day"): {
        "mining":      {True:  "Demo day held and the mining haul came in clean. Investors saw execution, not desperation.",
                        False: "Demo day gamble flopped, then the mining sprint crashed. The landlord is still calling."},
        "typing":      {True:  "Demo day done, then a sharp typing sprint sealed the coffee supply. Landlord problems feel smaller when you're caffeinated.",
                        False: "Demo day flopped and the typing sprint bombed. Double exposure."},
        "coffee_hunt": {True:  "Held the demo day, then hunted down the beans. Scrappy and resourceful—that's the pitch.",
                        False: "Demo day risk taken, coffee hunt missed. The garage smells like failure and drip coffee."},
    },

    # ── SAND HILL POWER WALK (Palo Alto) ──────────────────────────────────────
    ("sand_hill_walk", "Quote Paul Graham"): {
        "mining":      {True:  "PG quote landed somehow, then the mining sprint crushed it. They'll be quoting you by next week.",
                        False: "The PG quote didn't land, and neither did the mining sprint. Wrong crowd, wrong vibes, wrong day."},
        "typing":      {True:  "Quoted PG and then typed the fastest order on Sand Hill. They didn't get the reference but they got the hustle.",
                        False: "PG quote flopped and the typing sprint followed. The partner is already on the phone with someone else."},
        "coffee_hunt": {True:  "Dropped the quote, bagged the beans. Tactical pivot mid-walk.",
                        False: "Quote missed, hunt whiffed. At least the walk was scenic."},
    },

    # ── SUNNYVALE MEETUP (Sunnyvale) ───────────────────────────────────────────
    ("meetup_pizza", "Give a lightning talk"): {
        "mining":      {True:  "Lightning talk delivered, then a clean mining haul. The crowd left with your pitch deck URL and you left with ore.",
                        False: "Lightning talk bombed, mining sprint crashed. You ate the free pizza but left with nothing else."},
        "typing":      {True:  "Survived the talk, then nailed the typing sprint. Adrenaline makes for fast fingers.",
                        False: "Talk didn't land and neither did the typing sprint. Next meetup, maybe."},
        "coffee_hunt": {True:  "Gave the talk, then hunted the beans like a pro. The crowd thinks you're everywhere at once.",
                        False: "Talk landed awkward, hunt whiffed. The pizza was fine though."},
    },

    # ── TECHCRUNCH (Palo Alto) ────────────────────────────────────────────────
    ("techcrunch", "Leak the roadmap"): {
        "mining":      {True:  "Leaked the roadmap and mined a haul in the hype window. Chaotic, lucrative, possibly ill-advised.",
                        False: "Leaked the roadmap, then the mining sprint imploded. Competitors are reading your source code by now."},
        "typing":      {True:  "Roadmap leaked and the coffee order went out perfectly. You run on chaos and caffeine.",
                        False: "Leaked everything, then fumbled the typing sprint. Pressure does weird things to fingers."},
        "coffee_hunt": {True:  "Dropped the leak, bagged the beans before anyone could ask questions.",
                        False: "Roadmap public, hunt missed, inbox exploding. Not your best Tuesday."},
    },

    # ── BIKE THE BAY (San Mateo) ──────────────────────────────────────────────
    ("almost_sf_tolls", "Bike the bay"): {
        "mining":      {True:  "Biked the bay AND mined a haul on arrival. Legendary. The LinkedIn post writes itself.",
                        False: "Biked the bay, arrived broken, then the mining sprint broke too. Heroic but counterproductive."},
        "typing":      {True:  "Biked across the bay and still typed faster than anyone in the office. Endurance unlocked.",
                        False: "Biked 20 miles and couldn't hit the keys straight. Legs: yes. Fingers: no."},
        "coffee_hunt": {True:  "Rode into SF on two wheels and hunted down every bean in sight. This is the origin story.",
                        False: "Biked the bay and whiffed the hunt. Your calves are impressive. The rest, less so."},
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bonus_outcome_message(
    state: Dict[str, Any],
    minigame: str,
    success: bool,
    default_message: str,
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the best available narrative for this minigame outcome.

    Priority:
      1. Layered narrative (_NARRATIVES hit) → rich bespoke message
      2. Choice label known                  → 'After "label": <default_message>'
      3. No context                          → bare default_message
    """
    stats = dict(stats or {})
    ctx = state.get("last_event_choice") or {}
    event_id = ctx.get("event_id")
    label = ctx.get("choice_label") or ""

    narrative = _NARRATIVES.get((event_id, label), {}).get(minigame, {}).get(success)
    if narrative:
        return _build_message(narrative, minigame, success, stats)

    if label:
        return f'After "{label}": {default_message}'
    return default_message
