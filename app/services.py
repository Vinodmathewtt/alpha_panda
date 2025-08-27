# Base classes for stream processors and lifespan services
from abc import ABC, abstractmethod
from typing import Protocol


class LifespanService(Protocol):
    """Protocol for services that need startup/shutdown lifecycle management"""
    
    async def start(self) -> None:
        """Start the service"""
        ...
    
    async def stop(self) -> None:
        """Stop the service - MUST include producer.flush()"""
        ...