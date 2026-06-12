"""Test easter egg functionality in Gradio UI."""

from __future__ import annotations

import re


def test_easter_egg_implementation():
    """Verify easter egg ticker is properly implemented in app.py."""
    from hearthnet.ui.app import _EASTER_EGG_SCRIPT, _EASTER_EGG_RAW_CSS, _EASTER_EGG_HTML

    # Verify CSS contains the ticker styling (no <style> tags — goes to gr.Blocks css=)
    assert ".egg-ticker" in _EASTER_EGG_RAW_CSS, "CSS missing .egg-ticker class"
    assert ".egg-ticker.active" in _EASTER_EGG_RAW_CSS, "CSS missing .egg-ticker.active state"
    assert "@keyframes" in _EASTER_EGG_RAW_CSS, "CSS missing scroll animation"
    assert "<style>" not in _EASTER_EGG_RAW_CSS, "Raw CSS must not contain <style> tags (goes to gr.Blocks css=)"

    # Verify HTML contains the ticker element (no style tags)
    assert 'id="egg-ticker"' in _EASTER_EGG_HTML, "HTML missing egg-ticker id"
    assert "⚡ LIVE" in _EASTER_EGG_HTML, "HTML missing LIVE label"
    assert 'id="egg-track"' in _EASTER_EGG_HTML, "HTML missing egg-track id"
    assert "<style>" not in _EASTER_EGG_HTML, "HTML component must not contain <style> tags"

    # Verify script is injected via head parameter (must contain <script> tag)
    assert "<script>" in _EASTER_EGG_SCRIPT, "Script must be wrapped in <script> tag for head parameter"
    assert "</script>" in _EASTER_EGG_SCRIPT, "Script must have closing </script> tag"

    # Verify keydown listener
    assert "evt.key === 'e'" in _EASTER_EGG_SCRIPT, "Script missing 'e' key check"
    assert "evt.key === 'a'" in _EASTER_EGG_SCRIPT, "Script missing 'a' key check for modal"

    # Verify input guard
    assert "'INPUT'" in _EASTER_EGG_SCRIPT, "Script missing INPUT guard"
    assert "'TEXTAREA'" in _EASTER_EGG_SCRIPT, "Script missing TEXTAREA guard"

    # Verify toggle functions
    assert "toggleEasterEgg" in _EASTER_EGG_SCRIPT, "Script missing toggleEasterEgg function"
    assert "toggleAgentModal" in _EASTER_EGG_SCRIPT, "Script missing toggleAgentModal function"

    # Verify gr.Blocks uses css= parameter and gr.HTML uses HTML only
    from hearthnet.ui.app import UiApp
    import inspect
    build_code = inspect.getsource(UiApp.build)
    assert "css=_EASTER_EGG_RAW_CSS" in build_code, "Raw CSS not passed to gr.Blocks css= parameter"
    assert "head=_EASTER_EGG_SCRIPT" in build_code, "Script not injected via head parameter in Blocks"
    assert "gr.HTML(value=_EASTER_EGG_HTML)" in build_code, "HTML not injected via gr.HTML()"


def test_easter_egg_no_script_in_html():
    """Verify script and style are NOT in gr.HTML() to avoid Gradio/CSP issues."""
    from hearthnet.ui.app import _EASTER_EGG_HTML, _EASTER_EGG_RAW_CSS

    assert "<script>" not in _EASTER_EGG_HTML, "HTML component must not contain scripts"
    assert "<style>" not in _EASTER_EGG_HTML, "HTML component must not contain style tags (use gr.Blocks css=)"
    assert "<style>" not in _EASTER_EGG_RAW_CSS, "Raw CSS must not be wrapped in style tags"
