"""Bisco: the hand-drawn 2D character, rendered from its layered raster rig.

Every figure is first drawn as a still SVG, in the rig's 1024 x 1024 canvas: the scribble base, the
eye whites and the five parts of one expression (brows, eyes, mouth), each placed at its measured
box. That still picture is complete on its own: older chat avatars and the sidebar card stay like
that. The page script (character.js) brings the live figures (home, loading, newest answer) to life
with the same rig through bisco.js, and keeps this still picture underneath until the live one has
loaded, so nothing ever flashes.

The wrapper keeps the structural classes the page relies on for sizing and for the shared-element
transition (`ufpinho-home|loading|chat`, `data-ufpinho-lead`); they are internal names only.
"""

import json
from html import escape
from pathlib import Path

RIG = json.loads((Path(__file__).with_name("bisco_rig.json")).read_text(encoding="utf-8"))
ASSETS_URL = "app/static/bisco"
VARIANTS = frozenset({"home", "loading", "chat"})
EXPRESSIONS = tuple(RIG["expressions"])  # neutral, happy, thinking, ... looking (10)
# Still pictures use the resolution tier that matches their size on a high-density screen.
TIER = {"home": "md", "loading": "sm", "chat": "sm"}
_SLOTS = ("eye_left", "eye_right", "brow_left", "brow_right", "mouth")


def _image(entry: dict, tier: str) -> str:
    x, y, w, h = entry["box"]
    return (
        f'<image href="{ASSETS_URL}/{entry["files"][tier]}" x="{x}" y="{y}" width="{w}" '
        f'height="{h}" preserveAspectRatio="none"/>'
    )


def still_svg(state: str, tier: str) -> str:
    """Base, eye whites (absent when the eyes are fully closed) and one expression, in order."""
    layers = [_image(RIG["v3"]["base"], tier)]
    if state != "blink":
        layers.append(_image(RIG["body"]["eye_whites"], tier))
    parts = RIG["expressions"][state]["parts"]
    layers += [_image(parts[slot], tier) for slot in _SLOTS]
    return (
        '<svg class="bisco-still" viewBox="0 0 1024 1024" aria-hidden="true" focusable="false">'
        + "".join(layers)
        + "</svg>"
    )


def character_markup(
    state: str = "neutral",
    *,
    variant: str = "chat",
    uid: str = "0",
    label: str | None = None,
    lead: str | None = None,
    interactive: bool = False,
) -> str:
    """One line of HTML.

    `lead` marks the one figure the page follows from screen to screen (home, loading, newest
    answer); the browser moves Bisco between successive leads.

    `interactive` makes the figure a button that plays a short reaction: it needs a label, which
    becomes its accessible name. `uid` is kept for callers; the still picture has no ids.
    """
    if state not in RIG["expressions"]:
        raise ValueError(f"Unknown expression: {state}")
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    if interactive and not label:
        raise ValueError("An interactive figure needs a label")
    del uid  # the still picture carries no ids, so no two figures can clash
    if interactive:
        accessible = f'role="button" tabindex="0" aria-label="{escape(label)}"'
    elif label:
        accessible = f'role="img" aria-label="{escape(label)}"'
    else:
        accessible = 'aria-hidden="true"'
    lead_attribute = f' data-ufpinho-lead="{escape(lead)}"' if lead else ""
    classes = f"ufpinho ufpinho-{variant} bisco-figure" + (
        " ufpinho-interactive" if interactive else ""
    )
    return (
        f'<div class="{classes}" data-state="{state}"{lead_attribute} {accessible}>'
        f'<div class="bisco-host">{still_svg(state, TIER[variant])}</div></div>'
    )
