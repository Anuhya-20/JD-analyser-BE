"""
Token optimisation utilities.

trim_text()        — strips noise and truncates to a character budget
trim_list()        — caps a list at N items and joins to a compact string
estimate_tokens()  — rough token count (1 token ≈ 4 chars for English)
coerce_llm_output()— normalise DeepSeek null quirks before Pydantic validation
"""
from __future__ import annotations
import re
from typing import List, Union, get_args, get_origin


def trim_text(text: str, max_chars: int = 3500) -> str:
    """
    Clean and truncate text to max_chars.

    Steps:
    1. Collapse runs of whitespace / blank lines
    2. Remove repeated separator lines (----, ====, ....)
    3. Keep the first max_chars characters
       (resume headers + first jobs carry the most signal)
    """
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ blank lines → 1
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove pure separator lines
    text = re.sub(r"\n[-=_.]{4,}\n", "\n", text)
    # Collapse runs of spaces/tabs
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    return text[:max_chars]


def trim_list(items: List[str], max_items: int = 8, sep: str = ", ") -> str:
    """Return the first max_items joined as a single string."""
    return sep.join(items[:max_items]) if items else "None"


def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 English characters."""
    return max(1, len(text) // 4)


def coerce_llm_output(model_cls, data: dict) -> dict:
    """
    Normalise LLM JSON quirks before Pydantic validation.

    DeepSeek (and other LLMs) sometimes returns:
    - null  for Optional List fields  → coerce to []
    - null  for required str fields   → coerce to ""
    - [] / {} for Optional scalar fields → coerce to None

    Pass the Pydantic model class and the raw dict from the LLM.
    """
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        fi = model_cls.model_fields.get(k)
        if fi is None:
            result[k] = v
            continue
        ann = fi.annotation
        origin = get_origin(ann)
        args = get_args(ann)
        if origin is list:
            # List[X] — null → []; bare string → wrap in list
            if isinstance(v, list):
                result[k] = v
            elif isinstance(v, str) and v:
                result[k] = [v]
            else:
                result[k] = []
        elif origin is Union and type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            inner_origin = get_origin(non_none[0]) if non_none else None
            if inner_origin is list:
                # Optional[List[X]] — null → []
                result[k] = [] if v is None else v
            else:
                # Optional[scalar] — [] / {} → None
                result[k] = None if isinstance(v, (list, dict)) and not v else v
        elif ann is str or ann == "str":
            # plain str — null → ""
            result[k] = v if v is not None else ""
        else:
            result[k] = v
    return result
