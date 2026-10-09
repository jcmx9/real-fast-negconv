"""Exception hierarchy for real-fast-negconv."""


class RfNegconvError(Exception):
    """Base class for expected, user-reportable errors."""


class ConfigError(RfNegconvError):
    """Invalid or incomplete configuration."""


class RawLoadError(RfNegconvError):
    """A RAW file could not be decoded."""


class OutputError(RfNegconvError):
    """An output file could not be written."""


class ServiceError(RfNegconvError):
    """Installing or controlling the background service failed."""
