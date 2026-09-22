"""Small dependency-free reader/validator for Astra release-lock.yml files.

The supported YAML subset is deliberately narrow: mappings, lists, quoted/plain
scalars and inline empty lists. Keeping the lock parser dependency-free makes
the bootstrap work on a plain Python 3.11 installation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class LockfileError(ValueError):
    pass


def _scalar(value: str) -> Any:
    value = value.strip()
    if value in ("[]", "{}"):
        return [] if value == "[]" else {}
    if value in ("true", "false"):
        return value == "true"
    if value in ("null", "~"):
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def load(path: Path) -> dict[str, Any]:
    """Load the restricted YAML grammar used by release locks."""
    source: list[tuple[int, str, int]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise LockfileError(f"{path}:{number}: tabs are not allowed")
        text = raw.strip()
        source.append((len(raw) - len(raw.lstrip(" ")), text, number))

    def block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(source) or source[index][0] < indent:
            return {}, index
        is_list = source[index][1].startswith("- ") or source[index][1] == "-"
        result: Any = [] if is_list else {}
        while index < len(source):
            current, text, line = source[index]
            if current < indent:
                break
            if current > indent:
                raise LockfileError(f"{path}:{line}: unexpected indentation")
            listed = text.startswith("- ") or text == "-"
            if listed != is_list:
                raise LockfileError(f"{path}:{line}: cannot mix list and mapping entries")
            if is_list:
                item = text[1:].strip()
                index += 1
                if not item:
                    if index >= len(source) or source[index][0] <= indent:
                        result.append(None)
                    else:
                        child, index = block(index, source[index][0])
                        result.append(child)
                    continue
                if ":" not in item:
                    result.append(_scalar(item))
                    continue
                key, value = item.split(":", 1)
                entry: dict[str, Any] = {key.strip(): _scalar(value)} if value.strip() else {key.strip(): None}
                if not value.strip() and index < len(source) and source[index][0] > indent:
                    entry[key.strip()], index = block(index, source[index][0])
                if index < len(source) and source[index][0] > indent:
                    extra, index = block(index, source[index][0])
                    if not isinstance(extra, dict):
                        raise LockfileError(f"{path}:{line}: list mapping continuation must be a mapping")
                    entry.update(extra)
                result.append(entry)
                continue
            if ":" not in text:
                raise LockfileError(f"{path}:{line}: expected 'key: value'")
            key, value = text.split(":", 1)
            key = key.strip()
            if not key:
                raise LockfileError(f"{path}:{line}: empty key")
            index += 1
            if value.strip():
                result[key] = _scalar(value)
            elif index < len(source) and source[index][0] > indent:
                result[key], index = block(index, source[index][0])
            else:
                result[key] = None
        return result, index

    if not source:
        raise LockfileError(f"{path}: lockfile is empty")
    data, consumed = block(0, source[0][0])
    if consumed != len(source) or not isinstance(data, dict):
        raise LockfileError(f"{path}: root must be a mapping")
    return data


def _require(mapping: dict[str, Any], key: str, location: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise LockfileError(f"{location}.{key} must be a non-empty string")
    return value


def validate(data: dict[str, Any]) -> None:
    if data.get("version") != "1":
        # The parser treats scalars as strings so this also avoids silent schema drift.
        raise LockfileError("version must be 1")
    package = data.get("package")
    if not isinstance(package, dict):
        raise LockfileError("package must be a mapping")
    for key in ("id", "assembly", "namespace"):
        _require(package, key, "package")
    source = package.get("source")
    if not isinstance(source, dict):
        raise LockfileError("package.source must be a mapping")
    entries = [("package.source", source)]
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise LockfileError("dependencies must be a list")
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            raise LockfileError(f"dependencies[{index}] must be a mapping")
        _require(dependency, "id", f"dependencies[{index}]")
        entries.append((f"dependencies[{index}]", dependency))
    for location, entry in entries:
        for key in ("repository", "path", "files", "ref"):
            _require(entry, key, location)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", entry["repository"]):
            raise LockfileError(f"{location}.repository must be OWNER/REPOSITORY")
        if entry["path"].startswith("/") or ".." in Path(entry["path"]).parts:
            raise LockfileError(f"{location}.path must be repository-relative")
        if not re.fullmatch(r"[A-Za-z0-9._/@-]+", entry["ref"]):
            raise LockfileError(f"{location}.ref contains unsupported characters")
    xref = data.get("xref")
    if not isinstance(xref, dict):
        raise LockfileError("xref must be a mapping")
    _require(xref, "unity", "xref")
    astra = xref.get("astra")
    if not isinstance(astra, list) or not all(isinstance(url, str) and url.startswith(("https://", "http://")) for url in astra):
        raise LockfileError("xref.astra must be a list of HTTP(S) URLs")


def load_and_validate(path: Path) -> dict[str, Any]:
    data = load(path)
    validate(data)
    return data


def as_pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
