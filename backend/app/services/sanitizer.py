"""Apply sanitizer transformation rules to extracted data."""

import logging
import re
from typing import Any

from app.models.enums import TransformType
from app.schemas.sanitizer_config import FieldSanitizer

logger = logging.getLogger(__name__)


def apply_sanitizer(data: dict, rules: list[FieldSanitizer]) -> dict:
    """Apply sanitizer rules to extracted data dict. Returns a new dict."""
    result = dict(data)
    for rule in rules:
        if rule.field not in result or result[rule.field] is None:
            continue
        value = result[rule.field]
        for transform in rule.transforms:
            value = _apply_transform(value, transform.type, transform)
            if value is None:
                break
        result[rule.field] = value
    return result


def _apply_transform(
    value: Any,
    transform_type: TransformType,
    rule: Any,
) -> Any:
    """Apply a single transform to a value."""
    try:
        if transform_type == TransformType.STRIP:
            return str(value).strip()

        if transform_type == TransformType.TO_LOWER:
            return str(value).lower()

        if transform_type == TransformType.TO_UPPER:
            return str(value).upper()

        if transform_type == TransformType.TO_NUMBER:
            cleaned = re.sub(r"[^0-9.\-]", "", str(value))
            if not cleaned or cleaned in (".", "-", "-."):
                return value
            return float(cleaned)

        if transform_type == TransformType.TO_INT:
            cleaned = re.sub(r"[^0-9\-]", "", str(value))
            if not cleaned or cleaned == "-":
                return value
            return int(cleaned)

        if transform_type == TransformType.REGEX_REPLACE:
            if rule.pattern is None:
                return value
            return re.sub(rule.pattern, rule.replacement or "", str(value))

        if transform_type == TransformType.EXTRACT_NUMBER:
            match = re.search(r"[-+]?\d*\.?\d+", str(value))
            if match:
                num_str = match.group()
                return float(num_str) if "." in num_str else int(num_str)
            return value

        if transform_type == TransformType.TRIM_PREFIX:
            prefix = rule.value or ""
            s = str(value)
            if s.startswith(prefix):
                return s[len(prefix):]
            return s

        if transform_type == TransformType.TRIM_SUFFIX:
            suffix = rule.value or ""
            s = str(value)
            if s.endswith(suffix):
                return s[: -len(suffix)]
            return s

        if transform_type == TransformType.DEFAULT:
            if value is None or (isinstance(value, str) and value.strip() == ""):
                return rule.value
            return value

        if transform_type == TransformType.SPLIT_TAKE:
            separator = rule.pattern or ","
            idx = rule.index if rule.index is not None else 0
            parts = str(value).split(separator)
            if 0 <= idx < len(parts):
                return parts[idx].strip()
            return value

    except Exception:
        logger.warning("Transform %s failed for value %r", transform_type.value, value)

    return value