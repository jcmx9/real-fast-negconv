"""Exception hierarchy for real-fast-filmlab."""


class RfFilmlabError(Exception):
    """Base class for expected, user-reportable errors."""


class ConfigError(RfFilmlabError):
    """Invalid or incomplete configuration."""


class FolderError(RfFilmlabError):
    """A configured folder is unreachable, not writable or full."""


class RawLoadError(RfFilmlabError):
    """A RAW file could not be decoded."""


class UnsupportedRawError(RawLoadError):
    """A RAW that decodes, but not into the three colour channels needed."""


class EncodeError(RfFilmlabError):
    """An output image could not be encoded from this file's data."""


class ServiceError(RfFilmlabError):
    """Installing or controlling the background service failed."""
