"""Shared utility helpers used across agents."""

import json
from typing import Any


def extract_json_block(text: str) -> Any:
    """Extract and parse JSON from a markdown code fence or raw text.

    Handles responses wrapped in ```json ... ``` or ``` ... ``` fences,
    as well as plain JSON strings.
    """
    if "```json" in text:
        json_str = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        json_str = text.split("```")[1].split("```")[0].strip()
    else:
        json_str = text.strip()
    return json.loads(json_str)
