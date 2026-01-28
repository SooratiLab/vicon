"""
Data Broadcaster

Broadcasts tracking data (positions, orientations, markers, etc.) over TCP
to connected clients. Works with Vicon, TurtleBot localization, or any other
tracking system data.

Uses TCPServer from networking module for connection management.
"""

import json
import socket
import threading
import time
import logging
from typing import Dict, Optional, Any

from .networking import TCPServer

logger = logging.getLogger(__name__)


class DataBroadcaster:
    """
    TCP broadcaster for tracking data.
    
    Clients can connect to receive JSON-formatted data updates
    at a configurable rate. Built on top of TCPServer for connection handling.
    
    Compatible with any data format - Vicon segments, TurtleBot positions,
    markers, or custom tracking data.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5555,
        rate_hz: float = 20.0
    ):
        """
        Initialize the broadcaster.
        
        Args:
            host: Bind address (0.0.0.0 for all interfaces)
            port: TCP port to listen on
            rate_hz: Maximum broadcast rate in Hz
        """
        self.period = 1.0 / rate_hz
        
        self._server = TCPServer(
            host=host,
            port=port,
            max_clients=10,
            on_connect=self._on_client_connect,
            on_disconnect=self._on_client_disconnect
        )
        
        self._latest_payload: Optional[Dict] = None
        self._broadcast_thread: Optional[threading.Thread] = None
        self._running = False
        
        self._last_log_time = 0.0
        
        # Statistics
        self._messages_sent = 0
        self._bytes_sent = 0
    
    
    def start(self) -> bool:
        """
        Start the broadcaster.
        
        Returns:
            True if started successfully
        """
        if not self._server.start():
            return False
        
        self._running = True
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, 
            daemon=True
        )
        self._broadcast_thread.start()
        
        # Check for network IPs and log if available
        tailscale_ip = self._get_tailscale_ip()
        if tailscale_ip:
            logger.info(f"Broadcaster ready at {1.0/self.period:.1f} Hz (tailscale ip: {tailscale_ip})")
        else:
            wlan_ip = self._get_wlan_ip()
            if wlan_ip:
                logger.info(f"Broadcaster ready at {1.0/self.period:.1f} Hz (ip: {wlan_ip})")
            else:
                logger.info(f"Broadcaster ready at {1.0/self.period:.1f} Hz")
        
        return True
    
    def stop(self):
        """Stop the broadcaster and close all connections."""
        self._running = False
        self._server.stop()
        
        logger.info(
            f"Broadcaster stopped. Sent {self._messages_sent} messages, "
            f"{self._bytes_sent} bytes"
        )
    
    def update(self, payload: Dict[str, Any]):
        """
        Update the payload to broadcast.
        
        Args:
            payload: Dictionary to broadcast as JSON
        """
        self._latest_payload = payload
    
    def pause(self):
        """Pause broadcasting (keeps connections but stops sending)."""
        self._latest_payload = None
    
    def _on_client_connect(self, sock, addr):
        """Called when a client connects."""
        logger.info(f"Broadcast client connected: {addr[0]}:{addr[1]}")
    
    def _on_client_disconnect(self, sock, addr):
        """Called when a client disconnects."""
        logger.warning(f"Broadcast client disconnected: {addr[0]}:{addr[1]}")
    
    
    def _broadcast_loop(self):
        """Broadcast payload to all connected clients at configured rate."""
        last_broadcast = 0.0
        
        while self._running:
            now = time.monotonic()
            
            # Rate limiting
            if now - last_broadcast < self.period:
                time.sleep(0.001)
                continue
            
            if self._latest_payload is not None and self._server.client_count > 0:
                msg = json.dumps(self._latest_payload).encode() + b"\n"
                sent_count = self._server.broadcast(msg)
                
                if sent_count > 0:
                    self._messages_sent += 1
                    self._bytes_sent += len(msg) * sent_count
                
                last_broadcast = now
                
                # Throttled logging (once per second)
                if now - self._last_log_time >= 1.0:
                    # Log different data types based on payload content
                    if "subjects" in self._latest_payload:
                        count = len(self._latest_payload.get("subjects", []))
                        logger.debug(f"Broadcasted {count} subjects to {sent_count} clients")
                    elif "turtlebots" in self._latest_payload:
                        count = len(self._latest_payload.get("turtlebots", []))
                        logger.debug(f"Broadcasted {count} TurtleBots to {sent_count} clients")
                    else:
                        logger.debug(f"Broadcasted data to {sent_count} clients")
                    self._last_log_time = now
            else:
                last_broadcast = now
            
            time.sleep(self.period)

    def _get_tailscale_ip(self) -> Optional[str]:
        """Get Tailscale IP address if available."""
        try:
            # Tailscale uses CGNAT range 100.64.0.0/10
            hostname = socket.gethostname()
            addrs = socket.getaddrinfo(hostname, None)
            for addr in addrs:
                ip = addr[4][0]
                if ip.startswith('100.') and not ip.startswith('127.'):
                    return ip
        except Exception:
            pass
        return None
    
    def _get_wlan_ip(self) -> Optional[str]:
        """Get WLAN IP address if available."""
        try:
            # Try to get local IP by connecting to external address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            # Exclude loopback and Tailscale IPs
            if not ip.startswith('127.') and not ip.startswith('100.'):
                return ip
        except Exception:
            pass
        return None
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return self._server.client_count
    
    @property
    def is_running(self) -> bool:
        """Check if broadcaster is running."""
        return self._running and self._server.is_running
    
    @property
    def port(self) -> int:
        """Get the broadcast port."""
        return self._server.port
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get broadcaster statistics."""
        return {
            "messages_sent": self._messages_sent,
            "bytes_sent": self._bytes_sent,
            "client_count": self.client_count,
            "running": self.is_running
        }
