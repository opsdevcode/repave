"""repave-tf: the repave state and execution client (ADR 004).

Runs where cloud credentials already live. Speaks HTTP to the repave state store and
never opens a database connection.
"""

__version__ = "2.24.0"

__all__ = ["__version__"]
