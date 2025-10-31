"""
WebSocket server for real-time job metrics updates
Provides live streaming of job metrics to GUI clients
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for job metrics"""
    
    def __init__(self):
        # job_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}")
        
    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove WebSocket connection"""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")
        
    async def send_metrics(self, job_id: str, metrics: dict):
        """Send metrics to all connected clients for a job"""
        if job_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(metrics)
                except Exception as e:
                    logger.error(f"Error sending metrics: {e}")
                    disconnected.append(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn, job_id)


# Global connection manager instance
manager = ConnectionManager()


async def metrics_stream_handler(websocket: WebSocket, job_id: str, get_metrics_func):
    """
    Handle WebSocket connection for job metrics streaming
    
    Args:
        websocket: FastAPI WebSocket connection
        job_id: ID of the job to stream metrics for
        get_metrics_func: Function to retrieve current metrics
    """
    await manager.connect(websocket, job_id)
    
    try:
        while True:
            # Send current metrics every second
            try:
                metrics = get_metrics_func(job_id)
                await websocket.send_json(metrics)
            except Exception as e:
                logger.error(f"Error retrieving metrics for job {job_id}: {e}")
                await websocket.send_json({
                    "error": "Failed to retrieve metrics",
                    "job_id": job_id
                })
            
            # Wait before next update
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
        logger.info(f"Client disconnected from job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, job_id)
