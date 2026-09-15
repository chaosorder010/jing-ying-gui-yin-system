from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, conversation_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[conversation_id].add(websocket)

    async def disconnect(self, conversation_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms[conversation_id].discard(websocket)
            if not self._rooms[conversation_id]:
                del self._rooms[conversation_id]

    async def broadcast(self, conversation_id: int, message: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._rooms.get(conversation_id, set()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(conversation_id, ws)


manager = ConnectionManager()
