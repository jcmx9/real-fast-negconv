"""Exception hierarchy for real-fast-negconv."""


class RfNegconvError(Exception):
    """Base class for expected, user-reportable errors."""


class ConfigError(RfNegconvError):
    """Invalid or incomplete configuration."""


class FolderError(RfNegconvError):
    """A configured folder is unreachable, not writable or full."""


class RawLoadError(RfNegconvError):
    """A RAW file could not be decoded."""


class EncodeError(RfNegconvError):
    """An output image could not be encoded from this file's data."""


class ServiceError(RfNegconvError):
    """Installing or controlling the background service failed."""
