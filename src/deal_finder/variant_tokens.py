"""Variant-aware candidate filtering for similarly named reference items."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from rapidfuzz import fuzz


GENERIC_PRODUCT_TOKENS = frozenset(
    {
        "apple", "mac", "macbook", "iphone", "ipad", "samsung", "sony",
        "nintendo", "switch", "playstation", "ps5", "xbox", "microsoft",
    }
)

def tokenize(value: str) -> set[str]:
    """Return case-insensitive alphanumeric tokens suitable for item matching."""
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def group_families(item_names: Sequence[str], threshold: float = 55) -> list[list[str]]:
    """Cluster fuzzy-similar reference item names into variant families."""
    names = [name for name in item_names if name and name.strip()]
    families: list[list[str]] = []
    used: set[str] = set()
    for index, name in enumerate(names):
        if name in used:
            continue
        family = [name]
        used.add(name)
        for other in names[index + 1 :]:
            if other in used:
                continue
            if fuzz.token_sort_ratio(name.lower(), other.lower()) >= threshold:
                family.append(other)
                used.add(other)
        families.append(family)
    return families


def build_family_lookup(
    item_names: Sequence[str],
    threshold: float = 55,
) -> dict[str, list[str]]:
    """Precompute family grouping lookup map once per run for O(1) variant checks."""
    families = group_families(item_names, threshold=threshold)
    lookup: dict[str, list[str]] = {}
    for family in families:
        for name in family:
            lookup[name] = family
    return lookup


def build_variant_token_map(item_names: Sequence[str]) -> dict[str, set[str]]:
    """Map each reference item to tokens that distinguish it within its family."""
    token_map: dict[str, set[str]] = {}
    for family in group_families(item_names):
        family_tokens = {name: tokenize(name) for name in family}
        shared_tokens = (
            set.intersection(*family_tokens.values()) if family_tokens else set()
        )
        for name, tokens in family_tokens.items():
            token_map[name] = tokens - shared_tokens
    return token_map


def _family_for(
    item_name: str,
    item_names: Sequence[str],
    family_lookup: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Return the variant family for item_name, using precomputed lookup if provided."""
    if family_lookup is not None:
        return list(family_lookup.get(item_name, []))
    return next(
        (family for family in group_families(item_names) if item_name in family),
        [],
    )


def filter_candidates(
    listing_title: str,
    item_name: str,
    variant_map: dict[str, set[str]],
    reference_items: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
    *,
    family_lookup: Mapping[str, Sequence[str]] | None = None,
) -> bool:
    """Return whether a listing title is compatible with a reference variant.

    A base variant (for example, ``PS5 Slim``) has no exclusive tokens.  It is
    still rejected when a listing explicitly contains a sibling qualifier such
    as ``digital``; this is the safeguard that prevents cross-matching.
    """
    if family_lookup is not None:
        family = list(family_lookup.get(item_name, []))
    elif isinstance(reference_items, Mapping):
        family = list(reference_items.get(item_name, []))
    elif reference_items is not None:
        family = _family_for(item_name, reference_items)
    else:
        return False

    if not family:
        return False

    title_tokens = tokenize(listing_title)
    # A single catalog target has no sibling from which to derive exclusive
    # tokens.  Still require its explicit model/edition tokens for local
    # fallback: ``MacBook M4`` must never accept ``MacBook Air 2020`` merely
    # because both contain the generic word "MacBook".
    required_model_tokens = tokenize(item_name) - GENERIC_PRODUCT_TOKENS
    if required_model_tokens and not required_model_tokens.issubset(title_tokens):
        return False
    my_tokens = variant_map.get(item_name, set())
    sibling_tokens = set().union(
        *(variant_map.get(other, set()) for other in family if other != item_name)
    )
    if not my_tokens:
        return not bool(title_tokens & sibling_tokens)
    return my_tokens.issubset(title_tokens) and not bool(
        title_tokens & (sibling_tokens - my_tokens)
    )
