"""Deterministic rejection of listings that sell accessories instead of devices."""

from __future__ import annotations

import re


# These terms describe a sellable add-on rather than the target device.  The
# checker is deliberately conservative: it only rejects an accessory signal
# when the listing does not also claim to include a complete hardware unit.
ACCESSORY_ONLY_PATTERN = re.compile(
    r"\b(?:"
    r"box\s+only|empty\s+box|manual\s+only|"
    r"case|cover|skin|screen\s+protector|sleeve|pouch|bag|"
    r"charger|charging\s+cable|usb(?:-c)?\s+cable|adapter|"
    r"dock|stand|mount|replacement\s+battery|"
    r"joy[\s-]?con|controller|game(?:s)?|cartridge|game\s+card|"
    r"physical\s+copy|keyboard|mouse"
    r")\b",
    re.IGNORECASE,
)
COMPLETE_HARDWARE_PATTERN = re.compile(
    r"\b(?:"
    r"complete(?:\s+set)?|full\s+set|bundle|unit|console|"
    r"laptop|notebook|phone|tablet|headphones?|camera|"
    r"includes?|comes\s+with|with\s+(?:charger|box|case|controller|games?)"
    r")\b",
    re.IGNORECASE,
)


GAME_SUB_ACCESSORY_PATTERN = re.compile(
    r"\b(?:case\s+only|box\s+only|empty\s+(?:case|box)|manual\s+only|"
    r"cover\s+art(?:\s+only)?|poster|no\s+(?:game|cartridge)(?!\s+case))\b",
    re.IGNORECASE,
)


def is_accessory_only_listing(
    title: str, description: str = "", *, target_type: str = "Hardware"
) -> bool:
    """Return ``True`` when a listing is clearly for an accessory only.

    This gate rejects common marketplace false positives such as games,
    controllers, cases, cables, and empty boxes.  A listing that explicitly
    advertises a complete device bundle remains eligible for Gemini auditing.
    """
    text = " ".join(part for part in (title, description) if part).strip()
    if target_type == "Game":
        # Packaging for sale is not game software; a cartridge without its case is.
        return GAME_SUB_ACCESSORY_PATTERN.search(text) is not None
    if not text or ACCESSORY_ONLY_PATTERN.search(text) is None:
        return False
    return COMPLETE_HARDWARE_PATTERN.search(text) is None
