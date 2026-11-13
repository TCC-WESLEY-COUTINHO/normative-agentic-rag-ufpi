"""UFpinho: the original 3D head with expressions drawn on its visor in SVG.

The head PNG is served untouched. The face lives in the same 512 x 512 coordinate system as the
image, so it stays aligned at any size. Each kind of motion owns one layer, so no two animations
ever compete for the same transform:

    .ufpinho          size, the quiet entrance, the transition ghost
    .ufpinho-motion   idle float
    .ufpinho-pose     tilts: welcome nod, thinking sway, greeting
    .ufpinho-look     ambient gaze (CSS)
    .ufpinho-track    eyes following the pointer (set from the page script, home only)
"""

from html import escape

HEAD_URL = "app/static/ufpinho/head_front.png"
VARIANTS = frozenset({"home", "loading", "chat"})

# Measured on 01_frente.png: the dark visor spans x 107-424 and y 214-424 with corners of about
# 95 px. The specular highlight sits at x 322-419, y 215-272, so the face stays below it.
VISOR = {"x": 107, "y": 214, "width": 318, "height": 210, "radius": 95}
_CX = 265.5
_EYE_Y = 300
_LEFT, _RIGHT = 214, 317
_MOUTH_Y = 357


def _eye(cx: float, cy: float, rx: float, ry: float) -> str:
    return f'<ellipse class="ufpinho-eye" cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"/>'


def _arc_eye(cx: float, cy: float) -> str:
    return (
        f'<path class="ufpinho-stroke ufpinho-eye" '
        f'd="M{cx - 19} {cy + 6} Q{cx} {cy - 20} {cx + 19} {cy + 6}"/>'
    )


def _closed_eye(cx: float, cy: float) -> str:
    return (
        f'<path class="ufpinho-stroke ufpinho-eye" '
        f'd="M{cx - 18} {cy} Q{cx} {cy + 9} {cx + 18} {cy}"/>'
    )


def _mouth(d: str) -> str:
    return f'<path class="ufpinho-stroke ufpinho-mouth" d="{d}"/>'


_SMILE = _mouth(f"M{_CX - 20} {_MOUTH_Y} Q{_CX} {_MOUTH_Y + 12} {_CX + 20} {_MOUTH_Y}")

EXPRESSIONS = {
    "neutral": (_eye(_LEFT, _EYE_Y, 15, 25) + _eye(_RIGHT, _EYE_Y, 15, 25), _SMILE),
    "happy": (
        _arc_eye(_LEFT, _EYE_Y) + _arc_eye(_RIGHT, _EYE_Y),
        _mouth(f"M{_CX - 30} {_MOUTH_Y - 5} Q{_CX} {_MOUTH_Y + 22} {_CX + 30} {_MOUTH_Y - 5}"),
    ),
    "thinking": (
        _eye(_LEFT + 7, _EYE_Y - 5, 14, 21) + _eye(_RIGHT + 7, _EYE_Y - 5, 14, 21),
        _mouth(f"M{_CX - 10} {_MOUTH_Y + 2} L{_CX + 14} {_MOUTH_Y}"),
    ),
    "clarification": (
        _eye(_LEFT, _EYE_Y, 15, 25) + _eye(_RIGHT, _EYE_Y - 5, 14, 19),
        _mouth(f"M{_CX - 16} {_MOUTH_Y + 4} Q{_CX + 2} {_MOUTH_Y + 6} {_CX + 18} {_MOUTH_Y - 4}"),
    ),
    "explaining": (
        _eye(_LEFT, _EYE_Y, 16, 26) + _eye(_RIGHT, _EYE_Y, 16, 26),
        _mouth(f"M{_CX - 23} {_MOUTH_Y - 3} Q{_CX} {_MOUTH_Y + 15} {_CX + 23} {_MOUTH_Y - 3}"),
    ),
    "abstained": (
        _eye(_LEFT, _EYE_Y + 3, 15, 21) + _eye(_RIGHT, _EYE_Y + 3, 15, 21),
        _mouth(f"M{_CX - 15} {_MOUTH_Y + 3} L{_CX + 15} {_MOUTH_Y + 3}"),
    ),
    "error": (
        _eye(_LEFT, _EYE_Y, 16, 20) + _eye(_RIGHT, _EYE_Y, 16, 20),
        f'<ellipse class="ufpinho-stroke ufpinho-mouth" cx="{_CX}" cy="{_MOUTH_Y + 2}" '
        'rx="7" ry="8"/>',
    ),
    "blink": (_closed_eye(_LEFT, _EYE_Y) + _closed_eye(_RIGHT, _EYE_Y), _SMILE),
}


def character_markup(
    state: str = "neutral",
    *,
    variant: str = "chat",
    uid: str = "0",
    label: str | None = None,
    lead: str | None = None,
    interactive: bool = False,
) -> str:
    """One line of HTML. Every expression is present; the state only selects which one shows,
    so a later state change becomes a transition instead of a rebuilt picture.

    `lead` marks the one figure the page follows from screen to screen (home, loading, newest
    answer); the browser moves the head between successive leads.

    `interactive` makes the figure a button that only plays a short greeting: it needs a label,
    which becomes its accessible name.
    """
    if state not in EXPRESSIONS:
        raise ValueError(f"Unknown expression: {state}")
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    if interactive and not label:
        raise ValueError("An interactive figure needs a label")
    clip, glow = f"ufpinho-visor-{uid}", f"ufpinho-glow-{uid}"
    faces = "".join(
        f'<g class="ufpinho-expr ufpinho-expr-{name}"><g class="ufpinho-eyes">{eyes}</g>{mouth}</g>'
        for name, (eyes, mouth) in EXPRESSIONS.items()
    )
    v = VISOR
    if interactive:
        accessible = f'role="button" tabindex="0" aria-label="{escape(label)}"'
    elif label:
        accessible = f'role="img" aria-label="{escape(label)}"'
    else:
        accessible = 'aria-hidden="true"'
    lead_attribute = f' data-ufpinho-lead="{escape(lead)}"' if lead else ""
    classes = f"ufpinho ufpinho-{variant}" + (" ufpinho-interactive" if interactive else "")
    return (
        f'<div class="{classes}" data-state="{state}"{lead_attribute} {accessible}>'
        '<div class="ufpinho-motion"><div class="ufpinho-pose">'
        f'<img class="ufpinho-head" src="{HEAD_URL}" alt="" width="512" height="512" '
        'draggable="false">'
        '<svg class="ufpinho-face" viewBox="0 0 512 512" aria-hidden="true" focusable="false">'
        f'<defs><clipPath id="{clip}"><rect x="{v["x"]}" y="{v["y"]}" width="{v["width"]}" '
        f'height="{v["height"]}" rx="{v["radius"]}"/></clipPath>'
        f'<filter id="{glow}" x="-20%" y="-20%" width="140%" height="140%">'
        '<feGaussianBlur stdDeviation="3.5" result="soft"/>'
        '<feMerge><feMergeNode in="soft"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
        f'<g clip-path="url(#{clip})" filter="url(#{glow})"><g class="ufpinho-look">'
        f'<g class="ufpinho-track">{faces}</g></g></g>'
        "</svg></div></div></div>"
    )
