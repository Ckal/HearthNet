"""Test easter egg functionality in Gradio UI."""

from __future__ import annotations


def test_easter_egg_implementation():
    """Verify easter egg uses Gradio 6 js= approach and appends to body."""
    from hearthnet.ui.app import _EASTER_EGG_JS, _EASTER_EGG_RAW_CSS

    assert "#hn-egg-ticker" in _EASTER_EGG_RAW_CSS
    assert "#hn-egg-ticker.hn-active" in _EASTER_EGG_RAW_CSS
    assert "@keyframes hn-marquee" in _EASTER_EGG_RAW_CSS
    assert "#hn-egg-modal" in _EASTER_EGG_RAW_CSS
    assert "<style>" not in _EASTER_EGG_RAW_CSS

    assert "document.body.appendChild" in _EASTER_EGG_JS
    assert "'e'" in _EASTER_EGG_JS
    assert "'a'" in _EASTER_EGG_JS
    assert "Escape" in _EASTER_EGG_JS
    assert "INPUT" in _EASTER_EGG_JS
    assert "TEXTAREA" in _EASTER_EGG_JS
    assert "hn-egg-iframe" in _EASTER_EGG_JS
    assert "<script>" not in _EASTER_EGG_JS

    from hearthnet.ui.app import UiApp
    import inspect
    build_code = inspect.getsource(UiApp.build)
    assert "css=_EASTER_EGG_RAW_CSS" in build_code
    assert "js=_EASTER_EGG_JS" in build_code


def test_easter_egg_no_script_in_html():
    """No inline scripts or style tags in CSS/HTML constants."""
    from hearthnet.ui.app import _EASTER_EGG_HTML, _EASTER_EGG_RAW_CSS
    assert "<script>" not in _EASTER_EGG_HTML
    assert "<style>" not in _EASTER_EGG_HTML
    assert "<style>" not in _EASTER_EGG_RAW_CSS
