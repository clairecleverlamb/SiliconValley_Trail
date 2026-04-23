"""Location event pools, weather hook-ins, and choice resolution."""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List, Optional, Tuple
from api import weather as weather_api

from . import resources

WEATHER_EVENT_RAIN = {
    "id": "rainy_day",
    "title": "Rainy Day Slowdown",
    "description": "Roads are flooded. Team is stuck inside.",
    "choices": [
        {
            "label": "Push through",
            "outcome": "Wet and miserable.",
            "effects": {"morale": -15},
        },
        {
            "label": "Code inside",
            "outcome": "Productive rain day.",
            "effects": {"bugs": -8, "coffee": -5},
        },
        {
            "label": "Team bonding",
            "outcome": "Morale boost!",
            "effects": {"morale": 15, "cash": -500},
        },
    ],
}

WEATHER_EVENT_SUNNY = {
    "id": "clear_skies_day",
    "title": "Clear Skies, Full Calendar",
    "description": "Classic Peninsula sun. The team actually smiles in standup.",
    "choices": [
        {
            "label": "Team lunch on the patio",
            "outcome": "Vitamin D and awkward small talk—in a good way.",
            "effects": {"morale": 18, "cash": -400},
        },
        {
            "label": "Film a hype reel outside",
            "outcome": "Lighting is perfect. Your intern becomes a director.",
            "effects": {"hype": 22, "cash": -550},
        },
        {
            "label": "Skip the sunshine and ship",
            "outcome": "The grind respects no weather report.",
            "effects": {"bugs": -6, "morale": 5},
        },
    ],
}

WEATHER_EVENT_FOG = {
    "id": "marine_layer_fog",
    "title": "Marine Layer Lock-In",
    "description": "Fog swallows the exits. Nobody agrees which building is which.",
    "choices": [
        {
            "label": "Brave the commute",
            "outcome": "Thirty minutes of white-knuckle lanes.",
            "effects": {"morale": -12, "coffee": -4},
        },
        {
            "label": "Go full async",
            "outcome": "Slack threads multiply. Clarity does not.",
            "effects": {"bugs": 4, "morale": -6},
        },
        {
            "label": "Fog-mode coding sprint",
            "outcome": "Heads down until the sun burns through.",
            "effects": {"bugs": -7, "coffee": -6},
        },
    ],
}

LOCATION_EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "San Jose": [
        {
            "id": "garage_landlord",
            "title": "The Garage Landlord",
            "description": "Your landlord noticed twelve people living in a two-bedroom. They want 'startup rent'.",
            "choices": [
                {"label": "Pay up", "outcome": "Quiet money solves loud problems.", "effects": {"cash": -4000}},
                {"label": "Negotiate", "outcome": "You buy a week.", "effects": {"morale": -10, "cash": -1500}},
                {
                    "label": "Host a demo day",
                    "outcome": "Investors might show... or not.",
                    "effects": {},
                    "risk_chance": 0.6,
                    "risk_effects": {"morale": -15, "hype": -10},
                    "success_effects": {"cash": 8000, "hype": 10},
                },
            ],
        },
        {
            "id": "angel_networking",
            "title": "Angel at the Coffee Shop",
            "description": "Someone with a dog-eared Zero to One offers warm intros.",
            "choices": [
                {"label": "Take the meeting", "outcome": "Warm-ish intro lands.", "effects": {"cash": 3000, "coffee": -5}},
                {"label": "Stay heads-down", "outcome": "Shipping > schmoozing.", "effects": {"bugs": -5}},
                {"label": "Ask for code review", "outcome": "They nitpick your architecture.", "effects": {"morale": -5}},
            ],
        },
    ],
    "Santa Clara": [
        {
            "id": "vc_pitch",
            "title": "VC Pitch Opportunity",
            "description": "A VC firm on Sand Hill Road wants to hear your pitch!",
            "choices": [
                {
                    "label": "Pitch unprepared",
                    "outcome": "Bold move...",
                    "effects": {},
                    "risk_chance": 0.5,
                    "risk_effects": {"morale": -20},
                    "success_effects": {"cash": 5000},
                },
                {
                    "label": "Decline politely",
                    "outcome": "You pass. Safe choice.",
                    "effects": {},
                },
                {
                    "label": "Ask for prep time",
                    "outcome": "You spend a day preparing.",
                    "effects": {"cash": -2000},
                    "risk_chance": 0.2,
                    "risk_effects": {"morale": -10},
                    "success_effects": {"cash": 3000},
                },
            ],
        },
        {
            "id": "chip_shortage",
            "title": "Hard-to-find parts",
            "description": "Tiny computer chips are in short supply. The gear you need for your product is backordered: the wait just got twice as long, and suppliers are charging more.",
            "choices": [
                {
                    "label": "Pay for rush shipping",
                    "outcome": "Expensive, but the parts show up fast and your build stays solid.",
                    "effects": {"cash": -3500, "bugs": -3},
                },
                {
                    "label": "Scrounge used or older parts",
                    "outcome": "You save money, but the setup is flaky and hard to keep working.",
                    "effects": {"bugs": 5, "morale": -5},
                },
                {
                    "label": "Give up on hardware for now",
                    "outcome": "Half the team loves it, half hates it. Long meeting.",
                    "effects": {"morale": -10, "hype": 5},
                },
            ],
        },
    ],
    "Sunnyvale": [
        {
            "id": "fab_tour",
            "title": "Cleanroom Fever",
            "description": "A semiconductor plant offers a tour if you sign an NDA thicker than your pitch deck.",
            "choices": [
                {"label": "Sign and learn", "outcome": "Inspo strikes.", "effects": {"morale": 10, "coffee": -5}},
                {"label": "Politely decline", "outcome": "You stay on roadmap.", "effects": {"bugs": -4}},
                {"label": "Ask about yield curves", "outcome": "Your PM feels seen.", "effects": {"hype": 5, "morale": 5}},
            ],
        },
        {
            "id": "meetup_pizza",
            "title": "Sunnyvale Meetup",
            "description": "Free pizza and recruiters fishing for senior talent.",
            "choices": [
                {"label": "Network hard", "outcome": "You leave with cards and indigestion.", "effects": {"hype": 10, "coffee": -3}},
                {"label": "Eat and leave", "outcome": "Carbs fuel the sprint.", "effects": {"morale": 5, "coffee": 5}},
                {
                    "label": "Give a lightning talk",
                    "outcome": "The crowd is polite.",
                    "effects": {"hype": 15},
                    "risk_chance": 0.35,
                    "risk_effects": {"bugs": 6},
                    "success_effects": {"cash": 2000},
                },
            ],
        },
    ],
    "Cupertino": [
        {
            "id": "apple_recruiter",
            "title": "Apple Recruiter",
            "description": "An Apple recruiter is targeting your lead developer.",
            "choices": [
                {"label": "Let them go", "outcome": "Dev leaves. Less tension though.", "effects": {"morale": 10, "bugs": 8}},
                {"label": "Counter-offer", "outcome": "You match Apple's offer. Expensive.", "effects": {"cash": -5000}},
                {
                    "label": "Ignore it",
                    "outcome": "You hope for the best...",
                    "effects": {},
                    "risk_chance": 0.5,
                    "risk_effects": {"bugs": 15, "morale": -15},
                },
            ],
        },
        {
            "id": "walled_garden",
            "title": "TestFlight Expired",
            "description": "Apple review flagged a harmless-sounding permission string.",
            "choices": [
                {"label": "Rewrite copy", "outcome": "Compliance calm returns.", "effects": {"morale": -5}},
                {"label": "Ship web PWA", "outcome": "Different bugs, same hustle.", "effects": {"bugs": 4, "hype": 5}},
                {"label": "Bribe with coffee", "outcome": "Your team rallies for a crunch.", "effects": {"coffee": -12, "bugs": -6}},
            ],
        },
    ],
    "Mountain View": [
        {
            "id": "google_food",
            "title": "Google Free Food",
            "description": "Googleplex opens its cafeteria to your team.",
            "choices": [
                {"label": "Feast", "outcome": "Team is energized!", "effects": {"morale": 20, "coffee": 10}},
                {"label": "Work through lunch", "outcome": "Productive but tired.", "effects": {"bugs": -5, "morale": 5}},
                {"label": "Decline, stay focused", "outcome": "Team respects the grind.", "effects": {"hype": 5}},
            ],
        },
        {
            "id": "search_quality",
            "title": "Your SEO Tanked",
            "description": "An algo update buried your landing page.",
            "choices": [
                {"label": "Hire an agency", "outcome": "Cash for clicks.", "effects": {"cash": -4000, "hype": 15}},
                {"label": "Write blog posts", "outcome": "Organic takes time.", "effects": {"morale": -5, "bugs": 2}},
                {"label": "Meme marketing", "outcome": "The timeline notices.", "effects": {"hype": 20, "morale": -5}},
            ],
        },
    ],
    "Palo Alto": [
        {
            "id": "techcrunch",
            "title": "TechCrunch Reporter",
            "description": "A journalist wants to write about your startup.",
            "choices": [
                {"label": "Give interview", "outcome": "Great coverage!", "effects": {"hype": 30, "cash": -1000}},
                {"label": "Decline", "outcome": "Stay under the radar.", "effects": {}},
                {"label": "Leak the roadmap", "outcome": "Massive hype, massive pressure.", "effects": {"hype": 50, "bugs": 10}},
            ],
        },
        {
            "id": "sand_hill_walk",
            "title": "Sand Hill Power Walk",
            "description": "Two VCs argue over whether you are 'AI' enough for the memo.",
            "choices": [
                {"label": "Say 'AI-powered'", "outcome": "It works until it doesn't.", "effects": {"hype": 10}},
                {"label": "Show metrics", "outcome": "Numbers talk.", "effects": {"cash": 2500}},
                {
                    "label": "Quote Paul Graham",
                    "outcome": "Wrong crowd, right vibes?",
                    "effects": {},
                    "risk_chance": 0.5,
                    "risk_effects": {"morale": -10},
                    "success_effects": {"hype": 15},
                },
            ],
        },
    ],
    "Menlo Park": [
        {
            "id": "meta_cafeteria",
            "title": "Meta Shuttle Energy",
            "description": "Employees complain about free snacks while you pay rent with blood.",
            "choices": [
                {"label": "Eat their snacks anyway", "outcome": "Petty fuel.", "effects": {"morale": 5, "coffee": 5}},
                {"label": "Focus on AR demos", "outcome": "Your engineer gets inspired.", "effects": {"bugs": -4, "morale": -5}},
                {"label": "Tweet hot takes", "outcome": "Engagement spikes.", "effects": {"hype": 12, "morale": -8}},
            ],
        },
        {
            "id": "quiet_money",
            "title": "Quiet Money Meeting",
            "description": "A family office wants 'founder-friendly' terms with a 3x liquidation preference.",
            "choices": [
                {"label": "Push back", "outcome": "They respect the spine.", "effects": {"cash": 4000, "morale": 5}},
                {"label": "Accept quickly", "outcome": "Cash now, paperwork later.", "effects": {"cash": 8000, "hype": -10}},
                {"label": "Ghost them", "outcome": "You live with the guilt.", "effects": {"morale": -10}},
            ],
        },
    ],
    "Redwood City": [
        {
            "id": "caltrain_disruption",
            "title": "Caltrain Delays",
            "description": "Your senior dev is stuck between stations with a laptop at 5% battery.",
            "choices": [
                {"label": "Uber them", "outcome": "You move money to move people.", "effects": {"cash": -600, "morale": 10}},
                {"label": "Reschedule stand-up", "outcome": "Async chaos.", "effects": {"bugs": 3, "morale": -5}},
                {"label": "Remote pair", "outcome": "Ships over Zoom.", "effects": {"morale": 5}},
            ],
        },
        {
            "id": "strip_mall_server",
            "title": "Sketchy Colo",
            "description": "A cheap colo in an unglamorous office park saves cash until the fans scream.",
            "choices": [
                {"label": "Migrate overnight", "outcome": "Pain now, uptime later.", "effects": {"coffee": -10, "bugs": -5}},
                {"label": "Buy more fans", "outcome": "MacGyver infrastructure.", "effects": {"cash": -2000, "bugs": 2}},
                {"label": "Do nothing", "outcome": "You sweat through pager duty.", "effects": {"morale": -15, "bugs": 8}},
            ],
        },
    ],
    "San Mateo": [
        {
            "id": "almost_sf_tolls",
            "title": "Bridge + Soul Tolls",
            "description": "Crossing costs money and patience. The fog lies.",
            "choices": [
                {"label": "Take 101", "outcome": "Standard pain.", "effects": {"cash": -800, "morale": -3}},
                {"label": "Carpool with hype", "outcome": "Podcasts play.", "effects": {"morale": 5, "hype": 5}},
                {
                    "label": "Bike the bay",
                    "outcome": "Legendary or foolish?",
                    "effects": {"coffee": -6},
                    "risk_chance": 0.4,
                    "risk_effects": {"morale": -12},
                    "success_effects": {"hype": 20, "morale": 10},
                },
            ],
        },
        {
            "id": "coffee_cart",
            "title": "Third-wave Pop-up",
            "description": "A coffee cart charges artisan prices near your coworking space.",
            "choices": [
                {"label": "Buy for the team", "outcome": "Hyper-focus unlocked.", "effects": {"cash": -1200, "coffee": 15, "morale": 5}},
                {"label": "BYO thermos", "outcome": "Discipline wins.", "effects": {"morale": -3}},
                {"label": "Negotiate beans", "outcome": "You become friends with the barista.", "effects": {"hype": 5, "coffee": 8}},
            ],
        },
    ],
}
# Note: San Francisco (index 9) never triggers events — the win condition fires
# immediately on arrival (see loop.py resolve_turn, new_idx < 9 guard).


def get_weather_event(weather: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a weather-tied event template, or None if this condition has no hook."""
    bucket = weather_api.condition_bucket(weather.get("condition"))
    if bucket == "rain":
        return copy.deepcopy(WEATHER_EVENT_RAIN)
    if bucket == "clear":
        return copy.deepcopy(WEATHER_EVENT_SUNNY)
    if bucket in ("fog", "clouds"):
        return copy.deepcopy(WEATHER_EVENT_FOG)
    return None


def pick_event(location_name: str, weather: Dict[str, Any], rng: Any = random) -> Dict[str, Any]:
    pool = LOCATION_EVENTS.get(location_name)
    if not pool:
        pool = LOCATION_EVENTS["San Jose"]
    bucket = weather_api.condition_bucket(weather.get("condition"))
    p_weather = 0.42 if bucket in ("rain", "fog", "clouds") else 0.24
    if rng.random() < p_weather:
        ev = get_weather_event(weather)
        if ev is not None:
            return ev
    return copy.deepcopy(rng.choice(pool))


def _apply_choice_outcome(
    state: Dict[str, Any], choice: Dict[str, Any], rng: Any = random
) -> Tuple[str, Optional[str]]:
    base = choice.get("effects") or {}
    resources.apply_effects(state, base)
    msg = choice.get("outcome", "Resolved.")
    risk = choice.get("risk_chance")
    if risk is not None:
        roll = rng.random()
        if roll < float(risk):
            risk_fx = choice.get("risk_effects") or {}
            resources.apply_effects(state, risk_fx)
            msg = f"{msg} Risk didn't pay off."
        else:
            ok_fx = choice.get("success_effects")
            if ok_fx:
                resources.apply_effects(state, ok_fx)
                msg = f"{msg} Risk paid off."
    return msg, None


def resolve_event_choice(state: Dict[str, Any], choice_num: int, rng: Any = random) -> str:
    ev = state.get("current_event")
    if not ev:
        raise ValueError("no_event")
    choices: List[Dict[str, Any]] = ev.get("choices") or []
    if choice_num < 1 or choice_num > len(choices):
        raise ValueError("bad_choice")
    choice = choices[choice_num - 1]
    before = resources.resource_snapshot(state)
    msg, _ = _apply_choice_outcome(state, choice, rng)
    resources.clamp_resources(state)
    after = resources.resource_snapshot(state)
    delta = resources.format_deltas(resources.delta_snapshots(before, after))
    if delta:
        msg = f"{msg} ({delta})"
    # Used to layer minigame outcomes on top of story choices (see bonus_narrative / minigames).
    state["last_event_choice"] = {
        "event_id": ev.get("id"),
        "event_title": ev.get("title"),
        "choice_label": choice.get("label", ""),
        "choice_index": choice_num,
        "outcome_line": choice.get("outcome", ""),
    }
    state["current_event"] = None
    return msg
