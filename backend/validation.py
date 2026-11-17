"""Validated application inputs shared by HTTP, backup import, and recipe operations."""

import re


class AppError(ValueError):
    def __init__(self, message, status=400, code="INVALID_INPUT", details=None):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details


def text(value, field, maximum=200, empty=False):
    if not isinstance(value, str):
        raise AppError(f"{field} must be text")
    value = value.strip()
    if (not empty and not value) or len(value) > maximum:
        raise AppError(
            f"{field} must contain {'0' if empty else '1'}–{maximum} characters"
        )
    return value


def object_value(value, field):
    if not isinstance(value, dict):
        raise AppError(f"{field} must be a JSON object")
    return value


def positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AppError(f"{field} must be a positive integer")
    return value


def context_value(value):
    value = object_value(value, "Context")
    if len(value) > 30:
        raise AppError("Context allows at most 30 dimensions")
    for key, item in value.items():
        text(key, "Context key", 80)
        if (
            not isinstance(item, (str, int, float, bool))
            or isinstance(item, str)
            and len(item) > 300
        ):
            raise AppError("Context values must be short strings, numbers, or booleans")
    return value


def operations_value(value):
    if not isinstance(value, list) or len(value) > 100:
        raise AppError("Recipe must be an array of at most 100 operations")
    result = []
    for index, item in enumerate(value):
        object_value(item, f"Operation {index + 1}")
        action = item.get("action")
        if action not in {"insert", "delete", "modify", "move"}:
            raise AppError(f"Operation {index + 1}: unknown action")
        op = {
            "action": action,
            "target": text(item.get("target"), f"Operation {index + 1} target", 200),
        }
        # Explicit operation IDs keep inserted activity references stable when recipes reorder.
        if item.get("id"):
            op["id"] = text(item["id"], "Operation ID", 80)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", op["id"]):
                raise AppError(
                    "Operation IDs must use letters, numbers and underscores"
                )
        if action in {"insert", "modify"}:
            op["name"] = text(item.get("name"), f"Operation {index + 1} name")
        if action == "move":
            op["after"] = text(
                item.get("after"), f"Operation {index + 1} destination", 200
            )
        if action == "insert":
            op["type"] = item.get("type", "userTask")
            if op["type"] not in {
                "task",
                "userTask",
                "serviceTask",
                "manualTask",
                "businessRuleTask",
                "sendTask",
                "receiveTask",
            }:
                raise AppError("Inserted activity type is unsupported")
            if item.get("role"):
                op["role"] = text(item["role"], "Activity role", 100)
        result.append(op)
    explicit = [op["id"] for op in result if "id" in op]
    if len(explicit) != len(set(explicit)):
        raise AppError("Recipe operation IDs must be unique")
    return result
