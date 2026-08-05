"""`/api/state/v1` server routes (ADR 004).

Importing this package pulls in FastAPI. Clients want `repave_engine.state_contract`
instead, which is dependency-free.
"""

from repave_engine.api_state.router import build_state_router

__all__ = ["build_state_router"]
