"""Pytest coverage for Silicon Valley Trail core logic and API."""

from __future__ import annotations

import copy

from api import weather as weather_api
from app import app as flask_app
from game import actions
from game import loop
from game import minigames as game_minigames
from game import state as game_state
from game.conditions import check_lose
from game.events import LOCATION_EVENTS, resolve_event_choice
from game.state import DAILY_OVERHEAD_CASH, create_initial_state


def _clear_cache():
    w = {loc["name"]: {"condition": "Clear", "temp": 72} for loc in game_state.LOCATIONS}
    return w


def test_travel_decreases_cash_and_advances():
    st = create_initial_state("test-travel", _clear_cache())
    st["resources"]["cash"] = 50000
    loop.resolve_turn(st, "travel")
    assert st["current_location_index"] == 1
    # Travel cost + daily overhead (Clear weather: small morale bump, no extra cash hit).
    assert st["resources"]["cash"] == 50000 - 1500 - DAILY_OVERHEAD_CASH


def test_travel_cloudy_applies_weather_penalty():
    """Cloudy / Clouds must hit travel rules (previously unmatched, so weather felt absent)."""
    st = create_initial_state("test-cloud", _clear_cache())
    st["resources"]["cash"] = 50000
    st["weather_cache"]["Santa Clara"] = {"condition": "Cloudy", "temp": 68}
    loop.resolve_turn(st, "travel")
    assert st["current_location_index"] == 1
    assert st["resources"]["cash"] == 50000 - 1500 - 200 - DAILY_OVERHEAD_CASH


def test_travel_weather_type_changes_action_travel_result():
    """Same base travel; destination forecast alone must change resources and the weather line."""
    base = create_initial_state("test-weather-diff", _clear_cache())
    base["resources"] = {
        "cash": 50000,
        "morale": 75,
        "coffee": 28,
        "hype": 40,
        "bugs": 0,
    }
    st_clear = copy.deepcopy(base)
    st_rain = copy.deepcopy(base)
    st_clear["weather_cache"]["Santa Clara"] = {"condition": "Clear", "temp": 72}
    st_rain["weather_cache"]["Santa Clara"] = {"condition": "Rain", "temp": 58}

    msg_clear = actions.action_travel(st_clear)
    msg_rain = actions.action_travel(st_rain)

    # apply_weather_modifiers: clear → +5 morale; rain → -500 cash, -5 morale (vs no weather cash hit for clear).
    assert st_clear["resources"]["cash"] == 50000 - 1500
    assert st_rain["resources"]["cash"] == 50000 - 1500 - 500
    assert st_clear["resources"]["morale"] == 75 - 5 + 5
    assert st_rain["resources"]["morale"] == 75 - 5 - 5
    assert st_clear["resources"] != st_rain["resources"]

    assert "Clear" in msg_clear
    assert "Rain" in msg_rain
    assert msg_clear != msg_rain


def test_passive_coffee_decay_per_turn():
    st = create_initial_state("test-decay", _clear_cache())
    st["resources"]["coffee"] = 100
    loop.resolve_turn(st, "marketing_push")
    assert st["resources"]["coffee"] == 100 - 3


def test_coffee_zero_increments_emergency_turns():
    st = create_initial_state("test-em", _clear_cache())
    st["resources"]["coffee"] = 5
    loop.resolve_turn(st, "rest")
    assert st["coffee_emergency_turns"] == 1


def test_coffee_emergency_three_turns_at_zero_loses():
    st = create_initial_state("test-em2", _clear_cache())
    st["resources"]["coffee"] = 5
    loop.resolve_turn(st, "rest")
    assert st["status"] == "playing"
    assert st["coffee_emergency_turns"] == 1
    loop.resolve_turn(st, "rest")
    assert st["status"] == "playing"
    assert st["coffee_emergency_turns"] == 2
    loop.resolve_turn(st, "rest")
    assert st["status"] == "lost"
    assert "coffee" in (st.get("lost_reason") or "").lower()


def test_morale_capped_after_rest():
    st = create_initial_state("test-morale", _clear_cache())
    st["resources"]["morale"] = 95
    loop.resolve_turn(st, "rest")
    assert st["resources"]["morale"] == 100


def test_bugs_above_threshold_loses():
    st = create_initial_state("test-bugs", _clear_cache())
    st["resources"]["bugs"] = 21
    assert check_lose(st) is True


def test_bugs_at_threshold_still_playing():
    st = create_initial_state("test-bugs-edge", _clear_cache())
    st["resources"]["bugs"] = 20
    assert check_lose(st) is False


def test_calendar_runway_exceeded_loses():
    st = create_initial_state("test-runway", _clear_cache())
    st["day"] = 20
    st["max_days"] = 20
    loop.resolve_turn(st, "rest")
    assert st["status"] == "lost"
    assert "calendar" in (st.get("lost_reason") or "").lower()


def test_fetch_weather_offline_uses_fallback(monkeypatch):
    monkeypatch.setenv("WEATHER_OFFLINE", "1")
    out = weather_api.fetch_weather("San Jose")
    fb = weather_api.WEATHER_FALLBACK["San Jose"]
    assert out["condition"] == fb["condition"]
    assert out["temp"] == fb["temp"]


def test_fetch_weather_open_meteo_response_parsed(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"current": {"temperature_2m": 65.4, "weather_code": 0}}

    monkeypatch.delenv("WEATHER_OFFLINE", raising=False)
    monkeypatch.setattr("api.weather.requests.get", lambda *a, **k: FakeResp())
    out = weather_api.fetch_weather("San Jose")
    assert out["condition"] == "Clear"
    assert out["temp"] == 65


def test_fetch_weather_network_error_uses_fallback(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.delenv("WEATHER_OFFLINE", raising=False)
    monkeypatch.setattr("api.weather.requests.get", boom)
    out = weather_api.fetch_weather("Mountain View")
    fb = weather_api.WEATHER_FALLBACK["Mountain View"]
    assert out["condition"] == fb["condition"]


def test_event_effects_modify_resources():
    st = create_initial_state("test-ev", _clear_cache())
    ev = copy.deepcopy(LOCATION_EVENTS["Mountain View"][0])
    st["current_event"] = ev
    before = copy.deepcopy(st["resources"])
    resolve_event_choice(st, 1)
    assert st["current_event"] is None
    assert st["resources"] != before


def test_event_turn_may_offer_bonus_minigame(monkeypatch):
    monkeypatch.setattr("game.loop.random.random", lambda: 0.1)
    st = create_initial_state("test-bonus", _clear_cache())
    st["first_event_bonus_pending"] = False
    ev = copy.deepcopy(LOCATION_EVENTS["Mountain View"][0])
    st["current_event"] = ev
    loop.resolve_event_turn(st, 1)
    assert st["mining_eligible"] is True
    assert st["minigame_type"] in ("mining", "typing", "coffee_hunt")


def test_event_turn_skips_bonus_when_roll_high(monkeypatch):
    monkeypatch.setattr("game.loop.random.random", lambda: 0.99)
    st = create_initial_state("test-bonus-skip", _clear_cache())
    st["first_event_bonus_pending"] = False
    ev = copy.deepcopy(LOCATION_EVENTS["Mountain View"][0])
    st["current_event"] = ev
    loop.resolve_event_turn(st, 1)
    assert st["mining_eligible"] is False
    assert st["minigame_type"] is None
    assert st["events_since_bonus"] == 1


def test_first_resolved_event_always_offers_bonus(monkeypatch):
    """New runs guarantee a minigame on the first event choice (even if RNG is bad)."""
    monkeypatch.setattr("game.loop.random.random", lambda: 0.99)
    st = create_initial_state("test-first-bonus", _clear_cache())
    assert st["first_event_bonus_pending"] is True
    ev = copy.deepcopy(LOCATION_EVENTS["Mountain View"][0])
    st["current_event"] = ev
    loop.resolve_event_turn(st, 1)
    assert st["mining_eligible"] is True
    assert st["minigame_type"] in ("mining", "typing", "coffee_hunt")
    assert st["first_event_bonus_pending"] is False


def test_bonus_forced_after_two_misses(monkeypatch):
    monkeypatch.setattr("game.loop.random.random", lambda: 0.99)
    st = create_initial_state("test-pity", _clear_cache())
    st["first_event_bonus_pending"] = False
    st["resources"]["cash"] = 100000
    ev = copy.deepcopy(LOCATION_EVENTS["Mountain View"][0])
    for i in range(2):
        st["current_event"] = copy.deepcopy(ev)
        loop.resolve_event_turn(st, 1)
        assert st["mining_eligible"] is False
        assert st["events_since_bonus"] == i + 1
    st["current_event"] = copy.deepcopy(ev)
    loop.resolve_event_turn(st, 1)
    assert st["mining_eligible"] is True
    assert st["events_since_bonus"] == 0


def test_win_at_san_francisco_index():
    st = create_initial_state("test-win", _clear_cache())
    st["current_location_index"] = 8
    loop.resolve_turn(st, "travel")
    assert st["current_location_index"] == 9
    assert st["status"] == "won"


def test_bonus_narrative_vc_pitch_decline_polite_mining():
    st = create_initial_state("test-layer", _clear_cache())
    st["mining_eligible"] = True
    st["minigame_type"] = "mining"
    st["last_event_choice"] = {
        "event_id": "vc_pitch",
        "event_title": "VC Pitch Opportunity",
        "choice_label": "Decline politely",
        "choice_index": 2,
        "outcome_line": "You pass. Safe choice.",
    }
    hype_before = st["resources"]["hype"]
    st2, msg = game_minigames.apply_mining_result(st, False)
    assert "bonus lost" in msg.lower()
    assert "declined politely" in msg.lower()
    assert "mining sprint collapsed" in msg.lower()
    assert str(game_minigames.MINING_FAIL_MORALE) in msg
    assert str(game_minigames.MINING_FAIL_HYPE) in msg
    assert st2["resources"]["hype"] == max(0, hype_before - game_minigames.MINING_FAIL_HYPE)
    assert st2["mining_eligible"] is False


def test_bonus_narrative_generic_fallback_uses_choice_label():
    st = create_initial_state("test-fallback", _clear_cache())
    st["mining_eligible"] = True
    st["minigame_type"] = "mining"
    st["last_event_choice"] = {
        "event_id": "vc_pitch",
        "choice_label": "Pitch unprepared",
        "choice_index": 1,
        "outcome_line": "Bold move...",
    }
    st2, msg = game_minigames.apply_mining_result(st, True)
    assert "Pitch unprepared" in msg
    assert "bonus won" in msg.lower()
    assert "mining haul" in msg.lower() or "cash" in msg.lower()
    assert st2["mining_eligible"] is False


def test_pitch_vc_allowed_from_starting_location():
    """Pitch VC is available in every city (not only Palo Alto / Menlo Park)."""
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    created = client.post("/api/games")
    gid = created.get_json()["game_id"]
    res = client.post(f"/api/games/{gid}/moves", json={"action": "pitch_vc"})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("status") == "playing"
    out = data.get("outcome") or ""
    assert "San Jose" in out or "Great pitch" in out or "flopped" in out.lower()


def test_save_with_display_name_writes_slug_file(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    res = client.put(f"/api/games/{gid}/saves", json={"save_name": " Claire "})
    assert res.status_code == 200
    body = res.get_json()
    assert body.get("save_name") == "Claire"
    assert (tmp_path / "claire.json").is_file()
    assert (tmp_path / f"{gid}.json").is_file()


def test_restore_save_by_name_round_trip(tmp_path, monkeypatch):
    import game.state as game_state
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "alpha"}).status_code == 200

    game_state._games.clear()
    res = client.post("/api/games/restore-save", json={"save_name": "alpha"})
    assert res.status_code == 200
    loaded = res.get_json()
    assert loaded.get("game_id") == gid
    assert loaded.get("save_name") == "alpha"
    assert game_state.get_game(gid) is not None


def test_save_rejects_unusable_display_name(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    res = client.put(f"/api/games/{gid}/saves", json={"save_name": "###"})
    assert res.status_code == 400


def test_save_requires_display_name(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    assert client.put(f"/api/games/{gid}/saves", json={}).status_code == 400
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "  "}).status_code == 400


def test_save_rejects_name_claimed_by_another_game(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid_a = client.post("/api/games").get_json()["game_id"]
    assert client.put(f"/api/games/{gid_a}/saves", json={"save_name": "claire"}).status_code == 200
    gid_b = client.post("/api/games").get_json()["game_id"]
    res = client.put(f"/api/games/{gid_b}/saves", json={"save_name": "claire"})
    assert res.status_code == 409
    assert "already used" in (res.get_json().get("error") or "").lower()


def test_save_same_display_name_ok_when_same_game(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "claire"}).status_code == 200
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "claire"}).status_code == 200


def test_save_new_name_removes_previous_slug_file(tmp_path, monkeypatch):
    import routes.game as game_routes

    monkeypatch.setattr(game_routes, "_GAMES_DIR", tmp_path)
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    gid = client.post("/api/games").get_json()["game_id"]
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "claire"}).status_code == 200
    assert (tmp_path / "claire.json").is_file()
    assert client.put(f"/api/games/{gid}/saves", json={"save_name": "bryan"}).status_code == 200
    assert not (tmp_path / "claire.json").exists()
    assert (tmp_path / "bryan.json").is_file()
    assert (tmp_path / f"{gid}.json").is_file()
