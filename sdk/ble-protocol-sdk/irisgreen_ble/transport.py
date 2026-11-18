"""Platform-independent BLE transport interface.

The SDK speaks the IrisGreen protocol on top of this interface; each platform
(Python + Bleak, Flutter, ...) only has to implement these few primitives.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

NotifyCallback = Callable[[bytes], None]


class Transport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @property
    def is_connected(self) -> bool:
        """False once the link has dropped. Transports that cannot tell may keep the default."""
        return True

    @property
    @abstractmethod
    def mtu(self) -> int:
        """Negotiated ATT MTU, or 0 if unknown."""

    @abstractmethod
    async def write(self, uuid: str, data: bytes, response: bool) -> None: ...

    @abstractmethod
    async def read(self, uuid: str) -> bytes: ...

    @abstractmethod
    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        """Subscribe to notifications or indications on a characteristic."""

    @abstractmethod
    async def stop_notify(self, uuid: str) -> None: ...
