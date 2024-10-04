class ConfigError(Exception):
    """Error when parsing configuration spreadsheet."""

    pass


class CARTError(Exception):
    """Error in parsing CART output."""

    pass


class TreeError(Exception):
    """Error when building the typing tree from the CART."""

    pass


class FormError(Exception):
    """Error during form generation."""

    pass
