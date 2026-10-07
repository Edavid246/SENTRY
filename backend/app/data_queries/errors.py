"""Data-pathway errors."""


class ToolParamError(ValueError):
    """Unknown tool, unknown/ill-typed parameter, or a unit outside the caller's scope.

    A safe refusal: raised before any SQL runs, and the message is written for
    the caller (it never echoes data). The registry audits it as a denial.
    """
