"""Shared input validation - the single source of truth for user-controlled
names that end up in file-system paths.

Both the Streamlit UI (code/) and the REST API (api/services.py) build
directories under UPLOAD_DIR from the username, so both must validate it the
same way. Keeping the pattern here avoids two definitions drifting apart.
"""

import re

# Usernames may be plain logins or e-mail addresses. The first character must
# be alphanumeric, which rules out '.', '..' and hidden names. Path separators
# and shell metacharacters are not in the character class, so neither path
# traversal nor command injection is possible when the name is used to build a
# directory path.
USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$"
_SAFE_USERNAME = re.compile(USERNAME_PATTERN)


def is_valid_username(username: str) -> bool:
    """True if the username is safe to use as a path component."""
    return bool(username) and _SAFE_USERNAME.match(username) is not None
