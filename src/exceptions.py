class YeteeError(Exception):
    """Base exception for all Types Editor errors."""


class ParseError(YeteeError):
    """Raised when XML parsing fails."""


class NetworkError(YeteeError):
    """Raised when a network operation fails."""


class RemoteConnectionError(NetworkError):
    """Raised when a remote connection or transfer fails."""


class RemoteAuthError(NetworkError):
    """Raised when remote authentication fails."""


class RemoteTimeoutError(NetworkError):
    """Raised when a remote operation times out."""


class AccessError(YeteeError):
    """Raised when file access fails (missing, permissions, etc)."""
