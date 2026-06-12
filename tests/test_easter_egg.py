"""Test easter egg - Gradio 6 html_template/js_on_load API."""

from __future__ import annotations


def test_easter_egg_implementation():
    from hearthnet.ui.app import _EGG_JS, _EGG_HTML

    # CSS is now injected via js_on_load (document.head.appendChild)
    assert ".hn-ticker" in _EGG_JS
    assert ".hn-ticker.hn-on" in _EGG_JS
    assert "@keyframes hn-scroll" in _EGG_JS
    assert ".hn-modal" in _EGG_JS
    assert "hn-egg-styles" in _EGG_JS  # idempotent guard

    assert "hn-ticker" in _EGG_HTML
    assert "hn-modal" in _EGG_HTML
    assert "hn-iframe" in _EGG_HTML
    assert "/webagent/index.html" in _EGG_HTML  # served via FastAPI StaticFiles
    assert "file=" not in _EGG_HTML  # NOT using file= (blocked by HF proxy)
    assert "<script>" not in _EGG_HTML

    assert "document.body.appendChild" in _EGG_JS
    assert "document.head.appendChild" in _EGG_JS
    assert "'e'" in _EGG_JS
    assert "'a'" in _EGG_JS
    assert "Escape" in _EGG_JS
    assert "INPUT" in _EGG_JS
    assert "hacker-news.firebaseio.com" in _EGG_JS  # real news fetch
    assert "allorigins.win" in _EGG_JS  # BBC via CORS proxy
    assert "_hnFetchNews" in _EGG_JS

    from hearthnet.ui.app import UiApp
    import inspect

    build_code = inspect.getsource(UiApp.build)
    assert "html_template=_EGG_HTML" in build_code
    assert "js_on_load=_EGG_JS" in build_code


def test_easter_egg_no_inline_scripts():
    from hearthnet.ui.app import _EGG_HTML

    assert "<script>" not in _EGG_HTML
    assert "<style>" not in _EGG_HTML
