from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class BrokerOrderClient(Protocol):
    """Order execution client interface for a broker.

    Minimal surface for Phase 1 migration. Concrete implementations may
    accept additional kwargs but should satisfy this protocol.
    """

    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        ...


class PortfolioRepository(ABC):
    """Abstract portfolio persistence/access layer.

    Phase 1 defines the minimal abstraction; implementations can extend.
    """

    @abstractmethod
    async def get_positions(self, account_id: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def upsert_position(self, account_id: str, position: Dict[str, Any]) -> None:
        ...


class BrokerRisk(ABC):
    """Risk checks interface to validate orders per broker policies."""

    @abstractmethod
    async def validate(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        ...


class Reconciler(ABC):
    """Positions/orders reconciler interface."""

    @abstractmethod
    async def reconcile(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...

