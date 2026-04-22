"""Resource update helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

RESOURCE_LABELS = {
    "cash": "cash",
    "morale": "morale",
    "hype": "hype",
    "coffee": "coffee",
    "bugs": "bugs",
}


def resource_snapshot(state: Dict[str, Any]) -> Dict[str, int]:
    r = state["resources"]
    return {k: int(r[k]) for k in RESOURCE_LABELS}


def delta_snapshots(
    before: Mapping[str, int], after: Mapping[str, int]
) -> Dict[str, int]:
    return {k: int(after[k]) - int(before[k]) for k in RESOURCE_LABELS}


def format_deltas(delta: Mapping[str, int]) -> str:
    parts: List[str] = []
    for key in ("cash", "morale", "hype", "coffee", "bugs"):
        d = int(delta.get(key, 0))
        if d == 0:
            continue
        label = RESOURCE_LABELS[key]
        if key == "cash":
            sign = "+" if d > 0 else "-"
            parts.append(f"{sign}${abs(d):,} {label}")
        elif key == "bugs":
            # Fewer bugs is good — avoid "-10 bugs" reading like a penalty.
            if d < 0:
                parts.append(f"{abs(d)} bugs fixed")
            else:
                parts.append(f"+{d} bugs")
        else:
            sign = "+" if d > 0 else "-"
            parts.append(f"{sign}{abs(d)} {label}")
    return ", ".join(parts)


def apply_effects(state: Dict[str, Any], effects: Optional[Mapping[str, int]]) -> None:
    if not effects:
        return
    r = state["resources"]
    for key, delta in effects.items():
        if key not in r:
            continue
        r[key] += int(delta)
    clamp_resources(state)


def clamp_resources(state: Dict[str, Any]) -> None:
    r = state["resources"]
    r["morale"] = max(0, min(100, r["morale"]))
    r["hype"] = max(0, min(100, r["hype"]))
    r["coffee"] = max(0, r["coffee"])
    r["bugs"] = max(0, r["bugs"])
    # cash has no upper cap
