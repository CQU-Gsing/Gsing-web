"""Reject sensitive-file probes before routes, static files and visit logging."""
import re
from urllib.parse import unquote

_PRIVATE_ROOTS = {"src", "data", "logs", "content", "tests", "__pycache__"}
_PRIVATE_FILES = {"main.py", "web.cmd", "requirements.txt", "pyproject.toml", "poetry.lock", "config.py", "settings.py"}
_SCAN_ROOTS = {"wp-admin", "wp-includes", "phpmyadmin", "pma", "cgi-bin"}
_PRIVATE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".sql", ".bak", ".ini", ".log", ".pyc")


def blocked_path_reason(path: str):
    # Flask decodes once; handle additional encoding without changing route semantics.
    for _ in range(8):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    else:
        return "excessive-encoding"
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return "invalid-path"
    path = path.replace("\\", "/").casefold()
    segments = [part for part in path.split("/") if part]
    if not segments:
        return None
    if any(part in {".", ".."} or ":" in part for part in segments):
        return "path-traversal"
    for index, part in enumerate(segments):
        if part.startswith(".") and not (index == 0 and part == ".well-known"):
            return "hidden-file"
    if segments[0] in _PRIVATE_ROOTS or segments[0] in _PRIVATE_FILES:
        return "private-project-file"
    if segments[:2] in [["docs", "private"], ["pages", "main.md"]]:
        return "private-source"
    if any(part.endswith(_PRIVATE_SUFFIXES) for part in segments):
        return "private-artifact"
    if segments[0] in _SCAN_ROOTS or any(re.search(r"\.(?:php[0-9]?|phtml|asp|aspx)(?:$|[;/])", part) for part in segments):
        return "unsupported-platform-probe"
    return None
