"""Tolerant extraction of optional listing metadata without guessing missing values."""

from collections.abc import Mapping
from datetime import datetime, timezone
import math
import re
from typing import Any
from urllib.parse import urlsplit


def http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith('//'):
        value = 'https:' + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username:
            return value
    except ValueError:
        pass
    return None


def normalize_timestamp(value: Any) -> str | None:
    """Normalize ISO dates or Unix seconds/milliseconds to UTC; naive dates assume UTC."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r'\d+(?:\.\d+)?', str(value)):
            epoch = float(value)
            if abs(epoch) >= 100_000_000_000:
                epoch /= 1000
            stamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
        else:
            stamp = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _number(value: Any, *, integer: bool = False, maximum: float | None = None):
    try:
        number = float(value)
        if isinstance(value, bool) or not math.isfinite(number) or number < 0:
            return None
        if maximum is not None and number > maximum:
            return None
        return int(number) if integer and number.is_integer() else (None if integer else number)
    except (ValueError, TypeError, OverflowError):
        return None


def _image(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return next((url for key in ('thumbnailUrl', 'url', 'imageUrl', 'src', 'thumbnail', 'thumbnails')
                     if (url := _image(value.get(key)))), None)
    if isinstance(value, list):
        return next((url for item in value if (url := _image(item))), None)
    return http_url(value)


def _location(value: Any) -> str | None:
    if isinstance(value, str):
        return ' '.join(value.split()) or None
    if isinstance(value, Mapping):
        return next((text for key in ('name', 'displayName', 'address', 'location', 'title')
                     if (text := _location(value.get(key)))), None)
    if isinstance(value, list):
        places = list(dict.fromkeys(text for item in value if (text := _location(item))))
        return '; '.join(places) or None
    return None


def extract_metadata(card: Mapping[str, Any]) -> dict[str, Any]:
    sellers = [card[key] for key in ('seller', 'user', 'profile') if isinstance(card.get(key), Mapping)]
    containers = [card, *[card[key] for key in ('belowFold', 'below_fold', 'belowTheFold')
                         if isinstance(card.get(key), Mapping)]]

    def find(keys, converter, sources=containers):
        return next((result for source in sources for key in keys
                     if (result := converter(source.get(key))) is not None), None)

    return {
        'thumbnail_url': find(('thumbnailUrl', 'thumbnail_url', 'thumbnail', 'thumbnails', 'photos', 'images', 'image'), _image),
        'seller_rating': find(('rating', 'sellerRating'), lambda v: _number(v, maximum=5), [*sellers, card]),
        'seller_rating_count': find(('ratingCount', 'sellerRatingCount'), lambda v: _number(v, integer=True), [*sellers, card]),
        'like_count': find(('likeCount', 'likesCount'), lambda v: _number(v, integer=True)),
        'location': find(('meetupLocation', 'meetupLocations', 'meetUpLocation', 'meetUpLocations', 'location'), _location),
        'listing_timestamp': find(('timeCreated', 'createdAt', 'created_at', 'timestamp', 'listingTimestamp', 'postedAt'), normalize_timestamp),
    }
