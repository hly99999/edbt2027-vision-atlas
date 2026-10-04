"""Classify machine-local path tokens without confusing scientific notation."""

from __future__ import annotations

import re
from typing import Final


# A path token starts at the beginning of a value or after a delimiter.  The
# excluded characters prevent matching inside URLs, DOI values, and ratios.
_TOKEN_PREFIX: Final = r"(?<![\w.:/\\-])"

_LOCAL_FILE_URI: Final = re.compile(rf"{_TOKEN_PREFIX}file://", re.IGNORECASE)
_WINDOWS_DRIVE_PATH: Final = re.compile(rf"{_TOKEN_PREFIX}[a-zA-Z]:[\\/]")
_FORWARD_UNC_PATH: Final = re.compile(
    rf"{_TOKEN_PREFIX}//[a-zA-Z0-9][a-zA-Z0-9.-]*/[a-zA-Z0-9$_.-]+"
)
_BACKSLASH_UNC_PATH: Final = re.compile(
    rf"{_TOKEN_PREFIX}\\\\[a-zA-Z0-9][a-zA-Z0-9.-]*\\[a-zA-Z0-9$_.-]+"
)
# One non-whitespace segment after a boundary-delimited slash is sufficient:
# it covers arbitrary and Unicode root names as well as the first segment of
# multi-component POSIX paths. The prefix guard keeps URL/DOI/ratio slashes
# out of this classification, while a spaced operator has no following token.
_POSIX_ABSOLUTE_PATH: Final = re.compile(rf"{_TOKEN_PREFIX}/[^\s/]+")
_LOCAL_PATH_PATTERNS: Final = (
    _LOCAL_FILE_URI,
    _WINDOWS_DRIVE_PATH,
    _FORWARD_UNC_PATH,
    _BACKSLASH_UNC_PATH,
    _POSIX_ABSOLUTE_PATH,
)


def contains_absolute_local_path(value: str) -> bool:
    """Return whether *value* has a boundary-delimited local path token.

    This recognizes file URIs, Windows drive paths, forward/backslash UNC
    paths, and Unix absolute paths. It intentionally ignores DOI/HTTP URL
    tokens, ratios, slash-based mathematical prose, and LaTeX commands.
    """

    return any(pattern.search(value) is not None for pattern in _LOCAL_PATH_PATTERNS)
