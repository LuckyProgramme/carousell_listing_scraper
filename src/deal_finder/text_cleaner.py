"""Text pre-cleaning, alias expansion, noise stripping, and in-text price recovery."""

from __future__ import annotations

import re
from html import escape as xml_escape
from typing import Final

# Target brand & model aliases for high-recall candidate matching
TARGET_ALIASES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bbotw\b", re.IGNORECASE), "the legend of zelda breath of the wild"),
    (re.compile(r"\btotk\b", re.IGNORECASE), "the legend of zelda tears of the kingdom"),
    (re.compile(r"\bsmo\b", re.IGNORECASE), "super mario odyssey"),
    (re.compile(r"\bns2\b", re.IGNORECASE), "nintendo switch 2"),
    (re.compile(r"\bplay\s*station\s*5\b", re.IGNORECASE), "ps5 playstation 5"),
    (re.compile(r"\bps5\s*disc\b", re.IGNORECASE), "ps5 slim disc"),
    (re.compile(r"\bps5\s*digi(?:tal)?\b", re.IGNORECASE), "ps5 slim digital"),
    (re.compile(r"\bps5\b", re.IGNORECASE), "ps5 playstation 5"),
    (re.compile(r"\b(?:switch\s*oled|oled\s*(?:v\d\s*)?console)\b", re.IGNORECASE), "nintendo switch oled"),
    (re.compile(r"\b(?:nsw|switch)\b", re.IGNORECASE), "nintendo switch"),
    (re.compile(r"\b(?:ip15pm|15pm|iphone\s*15\s*pm|15\s*pro\s*max)\b", re.IGNORECASE), "iphone 15 pro max"),
    (re.compile(r"\b(?:ip15p|15p|iphone\s*15\s*pro)\b", re.IGNORECASE), "iphone 15 pro"),
    (re.compile(r"\b(?:ip15|iphone15)\b", re.IGNORECASE), "iphone 15"),
    (re.compile(r"\b(?:wh-?1000xm5|xm5)\b", re.IGNORECASE), "sony wh-1000xm5"),
    (re.compile(r"\b(?:mba\s*m1|m1\s*mba|macbook\s*m1)\b", re.IGNORECASE), "m1 macbook air"),
    (re.compile(r"\b(?:ipad\s*air\s*5|air\s*5)\b", re.IGNORECASE), "ipad air 5"),
)

# Common marketplace payment and logistics noise patterns
NOISE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"#\w+", re.UNICODE),  # Hashtags
    re.compile(
        r"\b(?:gcash|maya|bpi|bdo|bank\s*transfer|cod|meet\s*up|lalamove|grab|j&t|shipping)\b.*?(?=[,.\n]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:rfs|reason\s*for\s*selling)\b.*?(?=[,.\n]|$)", re.IGNORECASE),
)

# In-text price regexes (e.g. 15k, 15.5k, PHP 15,000, price: 14000)
K_PRICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:price|selling\s*for|asking|only|for)?\s*[:=-]?\s*(?:php|₱)?\s*(\d{1,3}(?:\.\d+)?)\s*k\b",
    re.IGNORECASE,
)
STANDARD_PRICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:price|selling\s*for|take\s*all\s*for|fixed\s*at|only)?\s*[:=-]?\s*(?:php|₱)\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,6}(?:\.\d+)?)",
    re.IGNORECASE,
)

# PII Minimization Patterns (Philippine/International Mobile, Email, Payment Accounts)
PHONE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?:\+?63\s*|0)9\d{2}[-\s.]?\d{3}[-\s.]?\d{4}\b"),
    re.compile(r"\b09\d{9}\b"),
    re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PAYMENT_ACCOUNT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:gcash|maya|bpi|bdo|acct|acc#|account)[\s:#-]*(\d{10,16})\b", re.IGNORECASE),
    re.compile(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}(?:[-\s]\d{4})?\b"),
)

# Structural and Prompt Injection Defanging
INJECTION_TAGS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<\/?(?:listing_untrusted_data|system|instruction|prompt|context|admin|script|style|iframe|embed)\b[^>]*>",
    re.IGNORECASE,
)
CONTROL_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def expand_aliases(text: str) -> str:
    """Expand colloquial model abbreviations and aliases for candidate recall."""
    if not text:
        return ""
    result = text
    for pattern, replacement in TARGET_ALIASES:
        result = pattern.sub(replacement, result)
    return result


def compress_description(text: str, max_chars: int = 250) -> str:
    """Compress and truncate description to token-dense prefix."""
    if not text:
        return ""
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    # Truncate at last whitespace before max_chars
    truncated = cleaned[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > int(max_chars * 0.7):
        return truncated[:last_space].rstrip(" ,.-") + "..."
    return truncated.rstrip(" ,.-") + "..."


def strip_marketplace_noise(text: str) -> str:
    """Strip hashtags, payment spam, and delivery/meetup clutter."""
    if not text:
        return ""
    result = text
    for pattern in NOISE_PATTERNS:
        result = pattern.sub("", result)
    return " ".join(result.split()).strip()


def recover_price_from_text(
    title: str,
    description: str,
    deal_price: float | None = None,
) -> tuple[float | None, str]:
    """Attempt to recover actual asking price from listing text.

    Returns:
        (recovered_price, source_description)
    """
    combined = f"{title} \n {description}"

    # 1. Check for 'k' notation: e.g. "15k", "15.5k"
    for match in K_PRICE_PATTERN.finditer(combined):
        try:
            val = float(match.group(1)) * 1000.0
            if deal_price is None or (deal_price * 0.10 <= val <= deal_price * 1.5):
                return val, "k_notation"
        except (ValueError, TypeError):
            continue

    # 2. Check for explicit currency notation: e.g. "PHP 15,000"
    for match in STANDARD_PRICE_PATTERN.finditer(combined):
        try:
            raw = match.group(1).replace(",", "")
            val = float(raw)
            if deal_price is None or (deal_price * 0.10 <= val <= deal_price * 1.5):
                return val, "currency_notation"
        except (ValueError, TypeError):
            continue

    return None, "none"


def redact_pii(text: str) -> str:
    """Redact personal identifiable information (phone numbers, emails, payment accounts)."""
    if not text:
        return ""
    result = text
    # 1. Redact emails
    result = EMAIL_PATTERN.sub("[EMAIL REDACTED]", result)
    # 2. Redact payment account details
    for pattern in PAYMENT_ACCOUNT_PATTERNS:
        result = pattern.sub("[PAYMENT REDACTED]", result)
    # 3. Redact phone numbers
    for pattern in PHONE_PATTERNS:
        result = pattern.sub("[PHONE REDACTED]", result)
    return result


def sanitize_untrusted_text(text: str) -> str:
    """Defang prompt-injection vectors, strip control characters, and disarm code fences."""
    if not text:
        return ""
    # Strip null bytes and non-printable control characters
    cleaned = CONTROL_CHARS_PATTERN.sub("", text)
    # Defang structural XML injection tags
    cleaned = INJECTION_TAGS_PATTERN.sub("[TAG DISARMED]", cleaned)
    # Disarm markdown code fences that could attempt to trick LLM parsers
    cleaned = cleaned.replace("```", "'''")
    return cleaned


def clean_description_for_audit(text: str, max_chars: int = 800) -> str:
    """Clean, minimize PII, disarm injections, and compress description for Gemini audit."""
    if not text:
        return ""
    # Redact before line processing; keep seller price lines associated with items.
    cleaned = sanitize_untrusted_text(redact_pii(text))
    lines = [strip_marketplace_noise(line) for line in cleaned.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    if len(cleaned) <= max_chars:
        return cleaned
    prefix = cleaned[:max_chars]
    # Never turn a partially truncated asking price (1000 -> 100) into evidence.
    if cleaned[max_chars:max_chars + 1] and not cleaned[max_chars].isspace():
        prefix = re.sub(r"\S+$", "", prefix)
    return prefix.rstrip()


def format_listing_data_block(
    listing_id: str,
    title: str,
    price: float | None,
    description: str,
    max_desc_chars: int = 800,
) -> str:
    """Format untrusted listing data inside structural XML boundaries."""
    clean_id = xml_escape(sanitize_untrusted_text(str(listing_id)), quote=True)
    clean_title = xml_escape(
        sanitize_untrusted_text(redact_pii(title.strip())), quote=False
    )
    clean_desc = xml_escape(
        clean_description_for_audit(description, max_chars=max_desc_chars), quote=False
    )
    price_str = f"{price:.2f}" if price is not None else "0.00"
    return (
        f'<listing_untrusted_data id="{clean_id}">\n'
        f"  <title>{clean_title}</title>\n"
        f"  <price>{price_str}</price>\n"
        f"  <description>{clean_desc}</description>\n"
        f"</listing_untrusted_data>"
    )
