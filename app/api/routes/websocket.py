"""
WebSocket route — real-time device status updates.
Devices connect and send heartbeats. Frontend subscribes for live updates.
"""
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.redis import set_device_online, is_device_online

router = APIRouter(tags=["WebSocket"])

# Connected frontend clients
_clients: set[WebSocket] = set()


@router.websocket("/ws/devices")
async def device_status_ws(websocket: WebSocket):
    """Frontend subscribes here for real-time device status updates."""
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            # Keep connection alive, receive pings
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _clients.discard(websocket)


@router.websocket("/ws/device/{device_id}")
async def device_heartbeat_ws(websocket: WebSocket, device_id: str):
    """
    Device connects here to report status in real-time.
    Sends heartbeat every 10s. Frontend clients get notified.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # Update Redis
            ip = msg.get("ip", "")
            await set_device_online(device_id, ip, ttl=30)

            # Broadcast to all frontend clients
            status_msg = json.dumps({
                "type": "device_status",
                "device_id": device_id,
                "online": True,
                "ip": ip,
            })
            disconnected = set()
            for client in _clients:
                try:
                    await client.send_text(status_msg)
                except:
                    disconnected.add(client)
            _clients -= disconnected

    except WebSocketDisconnect:
        # Mark device offline
        status_msg = json.dumps({
            "type": "device_status",
            "device_id": device_id,
            "online": False,
        })
        for client in _clients:
            try:
                await client.send_text(status_msg)
            except:
                pass
