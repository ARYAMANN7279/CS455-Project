"""Common role and status enums."""
from __future__ import annotations

import enum

class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class Role(str, enum.Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    DEBUGGER = "debugger"
    OWNER = "owner"


ROLE_RANK = {Role.VIEWER: 0, Role.EDITOR: 1, Role.DEBUGGER: 2, Role.OWNER: 3}
