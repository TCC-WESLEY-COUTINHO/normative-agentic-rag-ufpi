"""Design tokens, the only place where visual values are defined; styles.css consumes them.

Institutional blue leads; the tassel's yellow appears only in small details. The page sits on a
neutral background, the sidebar directly on it, and the conversation in one raised panel.
"""

from pathlib import Path

LIGHT = {
    "c-app": "#F5F6F8",
    "c-bg": "#FFFFFF",
    "c-surface": "#F5F6F8",
    "c-raised": "#FFFFFF",
    "c-hover": "#E9EDF4",
    "c-selected": "#E3EAFF",
    "c-tint": "#EEF3FF",
    "c-text": "#172033",
    "c-muted": "#5D6880",
    "c-border": "#E1E7F0",
    "c-border-strong": "#8D94A8",
    "c-composer-border": "#A9BCF2",
    "c-brand": "#0033CC",
    "c-brand-deep": "#083897",
    "c-on-brand": "#FFFFFF",
    "c-link": "#0033CC",
    "c-interact": "#0033CC",
    "c-on-interact": "#FFFFFF",
    "c-accent": "#0033CC",
    "c-bubble": "#EEF3FF",
    "c-highlight": "#F3BD35",
    "c-warn": "#6F4B00",
    "c-warn-soft": "#FFF7DF",
    "c-danger": "#8C2A22",
    "c-danger-soft": "#F9EBE9",
    "grad-from": "#083897",
    "grad-mid": "#0033CC",
    "grad-to": "#4D7CFF",
    "panel-shadow": "0 1px 2px rgb(16 24 40 / 4%), 0 8px 28px rgb(16 24 40 / 6%)",
    "composer-shadow": "0 6px 24px rgb(0 51 204 / 8%)",
    "brand-shadow": "0 4px 12px rgb(0 51 204 / 18%)",
    "shimmer-base": "#4F5F86",
    "shimmer-light": "#2A5BFF",
    "control-shadow": "0 4px 14px rgb(16 24 40 / 14%)",
}

DARK = {
    "c-app": "#0D1016",
    "c-bg": "#151A24",
    "c-surface": "#0D1016",
    "c-raised": "#1B2130",
    "c-hover": "#222A3A",
    "c-selected": "#1E2A55",
    "c-tint": "#1A2442",
    "c-text": "#E9ECF4",
    "c-muted": "#A3ACC2",
    "c-border": "#273043",
    "c-border-strong": "#6E768B",
    "c-composer-border": "#3A4C80",
    "c-brand": "#2F5BE8",
    "c-brand-deep": "#9DB8FF",
    "c-on-brand": "#FFFFFF",
    "c-link": "#9DB8FF",
    "c-interact": "#7F9DFF",
    "c-on-interact": "#0D1016",
    "c-accent": "#9DB8FF",
    "c-bubble": "#1F2A4A",
    "c-highlight": "#F3BD35",
    "c-warn": "#E8C478",
    "c-warn-soft": "#2A2416",
    "c-danger": "#F2AAA2",
    "c-danger-soft": "#32201E",
    "grad-from": "#7FA0FF",
    "grad-mid": "#9DB8FF",
    "grad-to": "#C4D3FF",
    "panel-shadow": "0 1px 2px rgb(0 0 0 / 30%), 0 8px 28px rgb(0 0 0 / 30%)",
    "composer-shadow": "0 6px 24px rgb(0 0 0 / 25%)",
    "brand-shadow": "none",
    "shimmer-base": "#A3B1D6",
    "shimmer-light": "#E5F1FF",
    "control-shadow": "0 4px 14px rgb(0 0 0 / 45%)",
}

SHARED = {
    "font-ui": '"Google Sans", "Segoe UI", system-ui, -apple-system, sans-serif',
    "font-title": '"Google Sans", "Segoe UI", system-ui, sans-serif',
    "fs-xs": "0.8125rem",
    "fs-sm": "0.875rem",
    "fs-md": "0.9375rem",
    "fs-lg": "1.0625rem",
    "fs-title": "2.25rem",
    "s-1": "0.25rem",
    "s-2": "0.5rem",
    "s-3": "0.75rem",
    "s-4": "1rem",
    "s-5": "1.5rem",
    "s-6": "2rem",
    "s-7": "3rem",
    "r-sm": "0.5rem",
    "r-md": "0.75rem",
    "r-lg": "1.125rem",
    "r-xl": "1.25rem",
    "r-panel": "1.375rem",
    "gap-panel": "1rem",
    "w-read": "48rem",
    "w-sidebar": "18rem",
    "h-touch": "2.75rem",
    "h-avatar": "2rem",
    "face-light": "#EAF6FF",
    "face-glow": "#A6D8FF",
}

_STYLES = (Path(__file__).with_name("styles.css"), Path(__file__).with_name("character.css"))


def _declarations(tokens: dict[str, str]) -> str:
    return "".join(f"--{name}:{value};" for name, value in tokens.items())


def _palette(tokens: dict[str, str], scheme: str) -> str:
    """One palette plus the toggle that leads away from it: moon on light, sun on dark."""
    hidden = "theme_to_dark" if scheme == "dark" else "theme_to_light"
    shown = "theme_to_light" if scheme == "dark" else "theme_to_dark"
    return (
        f":root{{color-scheme:{scheme};{_declarations(tokens)}}}"
        f".st-key-{hidden}{{display:none}}.st-key-{shown}{{display:block}}"
    )


def stylesheet(mode: str = "system") -> str:
    """Return the page style; the mode only selects which palette is declared."""
    if mode == "dark":
        palettes = _palette(DARK, "dark")
    elif mode == "light":
        palettes = _palette(LIGHT, "light")
    else:
        palettes = (
            f"{_palette(LIGHT, 'light')}"
            f"@media (prefers-color-scheme: dark){{{_palette(DARK, 'dark')}}}"
        )
    shared = f":root{{{_declarations(SHARED)}}}"
    rules = "".join(path.read_text(encoding="utf-8") for path in _STYLES)
    return f"<style>{shared}{palettes}{rules}</style>"
