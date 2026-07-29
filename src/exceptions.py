class YeteeError(Exception):
    """Base exception for all Types Editor errors."""


class ParseError(YeteeError):
    """Raised when XML parsing fails."""


class NetworkError(YeteeError):
    """Raised when a network operation fails."""


class AccessError(YeteeError):
    """Raised when file access fails (missing, permissions, etc)."""
