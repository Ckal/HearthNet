"""Sponsor LLM backends are wired when their env vars are set (prize tracks)."""

from __future__ import annotations

from hearthnet.node import HearthNode


def _llm_models(node: HearthNode) -> set[str]:
    """Collect every model name served by registered llm.chat capabilities.

    LlmService registers a single llm.chat that advertises its full model
    catalogue in params["models"], dispatching to the owning backend by model.
    """
    models: set[str] = set()
    for e in node.bus.registry.all_local():
        if e.descriptor.name != "llm.chat":
            continue
        primary = e.descriptor.params.get("model")
        if primary:
            models.add(str(primary))
        models.update(str(m) for m in e.descriptor.params.get("models", []))
    return models


def _nemotron_models() -> set[str]:
    from hearthnet.services.llm.backends.nemotron import NemotronBackend

    backend = NemotronBackend(api_key_env="NVIDIA_API_KEY")
    return {bm.name for bm in backend.models}


def test_nemotron_wired_when_key_set(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    monkeypatch.delenv("MODAL_ENDPOINT", raising=False)
    node = HearthNode("ed25519:nv", "NV", "ed25519:test-community")
    node.install_services(corpus="t")
    # At least one of Nemotron's models must now be served via llm.chat.
    assert _llm_models(node) & _nemotron_models()


def test_no_sponsor_backend_without_env(monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NEMOTRON_URL", raising=False)
    monkeypatch.delenv("MODAL_ENDPOINT", raising=False)
    monkeypatch.delenv("MINICPM_URL", raising=False)
    node = HearthNode("ed25519:none", "None", "ed25519:test-community")
    node.install_services(corpus="t")
    # Without the key, none of Nemotron's models should be registered.
    assert not (_llm_models(node) & _nemotron_models())


def test_nemotron_backend_constructs() -> None:
    from hearthnet.services.llm.backends.nemotron import NemotronBackend

    backend = NemotronBackend(api_key_env="NVIDIA_API_KEY")
    assert backend.name == "nemotron"
