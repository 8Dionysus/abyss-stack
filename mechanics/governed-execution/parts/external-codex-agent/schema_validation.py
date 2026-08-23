"""Small, dependency-free validator for the runtime's local JSON schemas.

The installed lifecycle wrappers run from an immutable release and must not
depend on an ambient Python site.  This module deliberately implements only
the JSON Schema vocabulary used by the external-Codex observation and Goal
pause contracts; it is not a general-purpose schema implementation.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class SchemaValidationError(ValueError):
    """The schema could not be loaded or a local schema construct is invalid."""


_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})$"
)


def load_schema(path: Path) -> dict[str, Any]:
    """Read one local JSON schema as a fresh mapping."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaValidationError(f"cannot read schema: {path}") from exc
    if not isinstance(value, dict):
        raise SchemaValidationError(f"schema is not an object: {path}")
    return value


def errors(instance: object, schema: Mapping[str, Any]) -> list[str]:
    """Return deterministic validation messages for one JSON instance."""

    if not isinstance(schema, Mapping):
        raise SchemaValidationError("schema must be an object")
    return sorted(_validate(instance, schema, schema, "$"))


def first_error(instance: object, schema: Mapping[str, Any]) -> str | None:
    """Return the first deterministic validation message, if any."""

    messages = errors(instance, schema)
    return messages[0] if messages else None


def _path_member(path: str, member: object) -> str:
    if isinstance(member, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", member):
        return f"{path}.{member}"
    return f"{path}[{member!r}]"


def _path_index(path: str, index: int) -> str:
    return f"{path}[{index}]"


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_matches(value: object, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return _is_integer(value)
    if expected == "number":
        return _is_number(value)
    raise SchemaValidationError(f"unsupported JSON Schema type: {expected}")


def _json_equal(left: object, right: object) -> bool:
    """Compare JSON values without treating booleans as integers."""

    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _resolve_ref(root: Mapping[str, Any], reference: object) -> Mapping[str, Any]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise SchemaValidationError(f"unsupported schema reference: {reference!r}")
    value: object = root
    for raw_token in reference[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or token not in value:
            raise SchemaValidationError(f"unresolved schema reference: {reference}")
        value = value[token]
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"schema reference is not an object: {reference}")
    return value


def _format_date_time(value: object) -> bool:
    if not isinstance(value, str) or _DATE_TIME.fullmatch(value) is None:
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return True


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError("schema instance is not JSON data") from exc


def _validate(
    instance: object,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
) -> list[str]:
    messages: list[str] = []

    if "$ref" in schema:
        messages.extend(_validate(instance, _resolve_ref(root, schema["$ref"]), root, path))

    if "const" in schema and not _json_equal(instance, schema["const"]):
        messages.append(f"{path}: does not equal const")

    if "enum" in schema:
        choices = schema["enum"]
        if not isinstance(choices, list):
            raise SchemaValidationError(f"enum must be an array at {path}")
        if not any(_json_equal(instance, choice) for choice in choices):
            messages.append(f"{path}: is not an allowed enum value")

    if "type" in schema:
        expected = schema["type"]
        expected_types = expected if isinstance(expected, list) else [expected]
        if not isinstance(expected_types, list) or not all(
            isinstance(item, str) for item in expected_types
        ):
            raise SchemaValidationError(f"type must be a string or array at {path}")
        if not any(_type_matches(instance, item) for item in expected_types):
            messages.append(f"{path}: has the wrong type")
            return messages

    for subschema in schema.get("allOf", []):
        if not isinstance(subschema, Mapping):
            raise SchemaValidationError(f"allOf member is not an object at {path}")
        messages.extend(_validate(instance, subschema, root, path))

    for subschema in schema.get("anyOf", []):
        if not isinstance(subschema, Mapping):
            raise SchemaValidationError(f"anyOf member is not an object at {path}")
        if not _validate(instance, subschema, root, path):
            break
    else:
        if "anyOf" in schema:
            messages.append(f"{path}: must match at least one schema")

    if "oneOf" in schema:
        matches = 0
        for subschema in schema["oneOf"]:
            if not isinstance(subschema, Mapping):
                raise SchemaValidationError(f"oneOf member is not an object at {path}")
            if not _validate(instance, subschema, root, path):
                matches += 1
        if matches != 1:
            messages.append(f"{path}: must match exactly one schema")

    if "not" in schema:
        subschema = schema["not"]
        if not isinstance(subschema, Mapping):
            raise SchemaValidationError(f"not schema is not an object at {path}")
        if not _validate(instance, subschema, root, path):
            messages.append(f"{path}: must not match schema")

    if "if" in schema:
        condition = schema["if"]
        if not isinstance(condition, Mapping):
            raise SchemaValidationError(f"if schema is not an object at {path}")
        branch = schema.get("then") if not _validate(instance, condition, root, path) else schema.get("else")
        if branch is not None:
            if not isinstance(branch, Mapping):
                raise SchemaValidationError(f"conditional branch is not an object at {path}")
            messages.extend(_validate(instance, branch, root, path))

    if "pattern" in schema and isinstance(instance, str):
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise SchemaValidationError(f"pattern must be a string at {path}")
        try:
            matched = re.search(pattern, instance) is not None
        except re.error as exc:
            raise SchemaValidationError(f"invalid pattern at {path}") from exc
        if not matched:
            messages.append(f"{path}: does not match pattern")

    if schema.get("format") == "date-time" and isinstance(instance, str):
        if not _format_date_time(instance):
            messages.append(f"{path}: is not an RFC3339 date-time")

    if isinstance(instance, str):
        minimum = schema.get("minLength")
        if minimum is not None and len(instance) < minimum:
            messages.append(f"{path}: is shorter than minLength")
        maximum = schema.get("maxLength")
        if maximum is not None and len(instance) > maximum:
            messages.append(f"{path}: is longer than maxLength")

    if _is_number(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            messages.append(f"{path}: is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            messages.append(f"{path}: is above maximum")
        if "multipleOf" in schema:
            multiple = schema["multipleOf"]
            if not _is_number(multiple) or multiple <= 0:
                raise SchemaValidationError(f"multipleOf must be positive at {path}")
            quotient = instance / multiple
            if not math.isclose(quotient, round(quotient), rel_tol=0.0, abs_tol=1e-9):
                messages.append(f"{path}: is not a multipleOf value")

    if isinstance(instance, Mapping):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise SchemaValidationError(f"required must be an array of strings at {path}")
        for key in required:
            if key not in instance:
                messages.append(f"{_path_member(path, key)}: is required")

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise SchemaValidationError(f"properties must be an object at {path}")
        for key, subschema in properties.items():
            if key in instance:
                if not isinstance(subschema, Mapping):
                    raise SchemaValidationError(f"property schema is not an object at {path}")
                messages.extend(_validate(instance[key], subschema, root, _path_member(path, key)))

        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            messages.append(f"{path}: has fewer than minProperties")
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            messages.append(f"{path}: has more than maxProperties")

        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                continue
            if additional is False:
                messages.append(f"{_path_member(path, key)}: additional property")
            elif isinstance(additional, Mapping):
                messages.extend(_validate(value, additional, root, _path_member(path, key)))
            elif additional is not True:
                raise SchemaValidationError(f"additionalProperties must be a schema or boolean at {path}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            messages.append(f"{path}: has fewer than minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            messages.append(f"{path}: has more than maxItems")
        if schema.get("uniqueItems"):
            encoded = [_canonical_json(item) for item in instance]
            if len(encoded) != len(set(encoded)):
                messages.append(f"{path}: items are not unique")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(instance):
                messages.extend(_validate(item, items, root, _path_index(path, index)))
        elif items is not None and items is not False:
            raise SchemaValidationError(f"items must be a schema at {path}")
        if "contains" in schema:
            contains = schema["contains"]
            if not isinstance(contains, Mapping):
                raise SchemaValidationError(f"contains must be a schema at {path}")
            if not any(not _validate(item, contains, root, _path_index(path, index)) for index, item in enumerate(instance)):
                messages.append(f"{path}: contains no matching item")

    return messages
