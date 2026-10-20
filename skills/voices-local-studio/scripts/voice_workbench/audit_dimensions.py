"""Voice-dimension and purpose text rules."""

from __future__ import annotations

from .contracts import DIMENSION_TERMS, PURPOSE_TERMS, VAGUE_PATTERNS, VAGUE_TOKENS, WORD_PATTERN


def contains_vague_language(normalized_text: str) -> bool:
    """Return whether the prompt relies on vague praise language."""
    words = set(WORD_PATTERN.findall(normalized_text))
    vague_token = any(token in words for token in VAGUE_TOKENS)
    vague_pattern = any(pattern in normalized_text for pattern in VAGUE_PATTERNS)
    return vague_pattern or (vague_token and populated_dimension_count_from_text(normalized_text) < 4)


def contains_purpose(normalized_text: str) -> bool:
    """Return whether the prompt names a role or use case."""
    words = set(WORD_PATTERN.findall(normalized_text))
    for term in PURPOSE_TERMS:
        phrase_match = " " in term and term in normalized_text
        word_match = " " not in term and term in words
        if phrase_match or word_match:
            return True
    return False


def populated_dimension_count_from_text(normalized_text: str) -> int:
    """Count the number of voice dimensions explicitly covered in prose."""
    count = sum(1 for terms in DIMENSION_TERMS.values() if any(term in normalized_text for term in terms))
    return count + (1 if contains_purpose(normalized_text) else 0)
