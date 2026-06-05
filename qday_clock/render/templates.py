"""Jinja2 template renderer for the static site.

Loads templates from ``site/`` and renders ``index.html``,
``methodology.html``, ``about.html``. Forbidden-language linting is
not performed here (that's a separate test step).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

from qday_clock.core.schemas import ClockState
from qday_clock.render.svg_clock import render_svg

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "site"


def _env(template_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html", "htm"]),
        undefined=jinja2.StrictUndefined,  # fail-fast: undefined vars = error
    )


def render_index(
    state: ClockState,
    template_dir: Path | None = None,
) -> str:
    """Render the symbolic-clock landing page."""
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("index.tmpl.html")
    svg = render_svg(state)
    return tmpl.render(
        clock_svg=svg,
        state=state,
        hours=int(state.clock_hours),
        minutes=int((state.clock_hours - int(state.clock_hours)) * 60),
        verbal_reading=_verbal_reading(state),
    )


def render_methodology(
    methodology_md_text: str,
    template_dir: Path | None = None,
) -> str:
    """Render the methodology page from raw markdown text.

    Markdown is rendered into a <pre>-wrapped block by default to keep
    the MVP free of a markdown-to-HTML dependency. v0.2 can swap in
    a proper markdown renderer (e.g. ``mistune``).
    """
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("methodology.tmpl.html")
    return tmpl.render(methodology_text=methodology_md_text)


def render_about(
    pubkey_b64: str,
    template_dir: Path | None = None,
) -> str:
    """Render the About page; the public key is embedded so readers
    can re-verify ``clock_state.json`` independently."""
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("about.tmpl.html")
    return tmpl.render(pubkey_b64=pubkey_b64)


def _verbal_reading(state: ClockState) -> str:
    h = state.clock_hours
    hours = int(h)
    minutes = int((h - hours) * 60)
    return (
        f"As of {state.generated_at.strftime('%Y-%m-%d')}, public evidence reads "
        f"{hours:02d}:{minutes:02d} on a 24-hour Q-day clock, with the "
        f"GRI {state.gri_baseline_year} threat-timeline median anchored at "
        f"{state.gri_baseline_label.split('~')[-1].strip().rstrip('.')} and "
        f"NSA CNSA 2.0 mandatory at 2033."
    )
