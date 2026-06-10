"""M08 — Gradio theme definitions.

Spec: docs/M08-ui.md §7

Two themes:
  hearthnet_theme — default purple/dark theme used at all times
  emergency_theme — red-accent override shown in emergency mode
"""

from __future__ import annotations

try:
    import gradio as gr

    hearthnet_theme = gr.themes.Soft(
        primary_hue="purple",
        secondary_hue="violet",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    ).set(
        # CSS variable overrides (spec §7)
        body_background_fill="#1a1a2e",
        body_background_fill_dark="#0f0f1a",
        block_background_fill="#16213e",
        block_border_color="#7c3aed",
        button_primary_background_fill="#7c3aed",
        button_primary_background_fill_hover="#6d28d9",
        button_primary_text_color="#ffffff",
        input_background_fill="#0f3460",
    )

    emergency_theme = gr.themes.Soft(
        primary_hue="red",
        secondary_hue="orange",
        neutral_hue="zinc",
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    ).set(
        body_background_fill="#1a0a0a",
        body_background_fill_dark="#0f0505",
        block_background_fill="#2d0000",
        block_border_color="#dc2626",
        button_primary_background_fill="#dc2626",
        button_primary_background_fill_hover="#b91c1c",
        button_primary_text_color="#ffffff",
        input_background_fill="#1f0000",
    )

except ImportError:
    # Gradio not installed — provide None sentinels so imports don't fail
    hearthnet_theme = None  # type: ignore[assignment]
    emergency_theme = None  # type: ignore[assignment]

__all__ = ["hearthnet_theme", "emergency_theme"]
