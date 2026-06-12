"""Test easter egg functionality in Gradio UI."""

from __future__ import annotations

import re


def test_easter_egg_implementation():
    """Verify easter egg ticker is properly implemented in app.py.
    
    Tests that:
    1. Script is injected via head parameter (not innerHTML)
    2. HTML/CSS is in gr.HTML() component
    3. Event listener checks for 'e' key
    4. Guards against INPUT/TEXTAREA elements
    """
    from hearthnet.ui.app import _EASTER_EGG_SCRIPT, _EASTER_EGG_CSS
    
    # Verify CSS contains the ticker styling
    assert ".egg-ticker" in _EASTER_EGG_CSS, "CSS missing .egg-ticker class"
    assert ".egg-ticker.active" in _EASTER_EGG_CSS, "CSS missing .egg-ticker.active state"
    assert "@keyframes scroll" in _EASTER_EGG_CSS, "CSS missing scroll animation"
    
    # Verify HTML contains the ticker element
    assert 'id="egg-ticker"' in _EASTER_EGG_CSS, "HTML missing egg-ticker id"
    assert "⚡ LIVE" in _EASTER_EGG_CSS, "HTML missing LIVE label"
    assert 'id="egg-track"' in _EASTER_EGG_CSS, "HTML missing egg-track id"
    
    # Verify script is injected via head parameter (must contain <script> tag)
    assert "<script>" in _EASTER_EGG_SCRIPT, "Script must be wrapped in <script> tag for head parameter"
    assert "</script>" in _EASTER_EGG_SCRIPT, "Script must have closing </script> tag"
    
    # Verify keydown listener
    assert "evt.key === 'e'" in _EASTER_EGG_SCRIPT, "Script missing 'e' key check (lowercase)"
    assert "evt.key === 'E'" in _EASTER_EGG_SCRIPT, "Script missing 'E' key check (uppercase)"
    
    # Verify input guard
    assert "'INPUT'" in _EASTER_EGG_SCRIPT, "Script missing INPUT guard"
    assert "'TEXTAREA'" in _EASTER_EGG_SCRIPT, "Script missing TEXTAREA guard"
    
    # Verify toggle function
    assert "toggleEasterEgg" in _EASTER_EGG_SCRIPT, "Script missing toggleEasterEgg function"
    assert ".active" in _EASTER_EGG_SCRIPT, "Script not toggling .active class"
    
    # Verify retry logic for DOM element
    assert "initEasterEgg" in _EASTER_EGG_SCRIPT, "Script missing initEasterEgg function"
    assert "setTimeout(initEasterEgg" in _EASTER_EGG_SCRIPT, "Script missing retry logic for DOM"
    
    # Verify script is injected in Blocks head parameter
    from hearthnet.ui.app import UiApp
    import inspect
    
    build_code = inspect.getsource(UiApp.build)
    assert "head=_EASTER_EGG_SCRIPT" in build_code, "Script not injected via head parameter in Blocks"
    assert "gr.HTML(value=_EASTER_EGG_CSS)" in build_code, "CSS not injected via gr.HTML()"


def test_easter_egg_no_script_in_html():
    """Verify script is NOT embedded in gr.HTML() to avoid Gradio warning."""
    from hearthnet.ui.app import _EASTER_EGG_CSS, _EASTER_EGG_SCRIPT
    
    # CSS should NOT contain script tags (they go to head parameter)
    assert "<script>" not in _EASTER_EGG_CSS, "CSS component should not contain script (goes to head parameter)"
    
    # Script should be separate
    assert len(_EASTER_EGG_SCRIPT) > 0, "Script must exist"
    assert "<script>" in _EASTER_EGG_SCRIPT, "Script must be in _EASTER_EGG_SCRIPT constant"
