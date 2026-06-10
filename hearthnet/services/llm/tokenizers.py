from __future__ import annotations


def count_tokens_approx(model_family: str, text: str) -> int:
    """Fast heuristic: chars/3.5 for Latin scripts, /2 for CJK."""
    cjk_count = sum(
        1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f"
    )
    latin_count = len(text) - cjk_count
    return int(latin_count / 3.5 + cjk_count / 2)


def model_family(model_name: str) -> str:
    """'qwen2.5-7b-instruct' → 'qwen', 'llama-3-8b' → 'llama', etc."""
    name = model_name.lower()
    for family in ["llama", "qwen", "mistral", "gemma", "phi", "falcon", "gpt", "claude"]:
        if family in name:
            return family
    return "unknown"
