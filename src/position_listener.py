#!/usr/bin/env python3
"""
Vicon Position Listener - Simple wrapper for TB3Manager compatibility.

Connects directly to Vicon data streamer and provides position data.
"""

import json
import socket
import threading
import time
from typing import Dict, Tuple, Optional

class ListenerConnectionError(Exception):
    """Raised when connection to Vicon streamer is lost."""
    pass


class ViconPositionListener:
    """
    Simple Vicon position listener compatible with TB3Manager.
    Connects to data_streamer.py TCP stream.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5555,
        verbose: bool = False,
        stale_data_timeout: float = 3.0,
        reconnect_delay: float = 2.0,
        convert_to_meters: bool = True,
    ):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.stale_data_timeout = stale_data_timeout
        self.reconnect_delay = reconnect_delay
        self.convert_to_meters = convert_to_meters
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        
        # Latest positions: key = subject_name (e.g., "TB10"), value = (x, y, z) in meters or mm
        self._positions: Dict[str, Tuple[float, float, float]] = {}
        self._last_data_time: float = 0.0
        self._lock = threading.Lock()
        
        self._connection_error: Optional[Exception] = None
        self._connection_error_lock = threading.Lock()
    
    def start(self):
        """Start listener thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop listener thread."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
    
    @property
    def connected(self) -> bool:
        """Check if connected and data is fresh."""
        if self._last_data_time == 0:
            return False
        return (time.time() - self._last_data_time) < self.stale_data_timeout
    
    def get_latest(self, check_connection: bool = False) -> Dict[str, Tuple[float, float, float]]:
        """
        Get latest positions for all tracked objects.
        
        Returns:
            Dict mapping subject name to (x, y, z).
            Units: meters if convert_to_meters=True, millimeters otherwise.
            Example: {"TB10": (1.2005, 2.3001, 0.050), "REF1": (0.0, 0.0, 0.0)}
        """
        if check_connection:
            with self._connection_error_lock:
                if self._connection_error:
                    error = self._connection_error
                    self._connection_error = None
                    raise error
            
            if not self.connected:
                raise ListenerConnectionError(
                    f"Vicon data stale (last update {time.time() - self._last_data_time:.1f}s ago)"
                )
        
        with self._lock:
            return dict(self._positions)
    
    def _listen_loop(self):
        """Main listener loop."""
        while self._running:
            try:
                self._connect()
                self._receive_loop()
            except Exception as e:
                with self._connection_error_lock:
                    self._connection_error = ListenerConnectionError(str(e))
                
                if self._socket:
                    try:
                        self._socket.close()
                    except:
                        pass
                    self._socket = None
                
                if self._running:
                    time.sleep(self.reconnect_delay)
    
    def _connect(self):
        """Connect to Vicon streamer."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(5.0)
        self._socket.connect((self.host, self.port))
        self._socket.settimeout(None)
    
    def _receive_loop(self):
        """Receive and process data."""
        buffer = b""
        
        while self._running:
            chunk = self._socket.recv(4096)
            if not chunk:
                break
            
            buffer += chunk
            
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line:
                    self._process_message(line)
    
    def _process_message(self, data: bytes):
        """Process received message."""
        try:
            payload = json.loads(data.decode('utf-8'))
            self._update_positions(payload)
        except:
            pass
    
    def _update_positions(self, payload: Dict):
        """Update positions from payload."""
        subjects = payload.get("subjects", [])
        
        with self._lock:
            self._positions.clear()
            
            for subject in subjects:
                subject_name = subject.get("name", "Unknown")
                segments = subject.get("segments", [])
                
                for segment in segments:
                    position = segment.get("position", {})
                    
                    if position.get("occluded", False):
                        continue
                    
                    x = position.get("x", 0.0)
                    y = position.get("y", 0.0)
                    z = position.get("z", 0.0)
                    
                    # Convert from millimeters to meters if requested
                    if self.convert_to_meters:
                        x = x / 1000.0
                        y = y / 1000.0
                        z = z / 1000.0
                    
                    # Use subject name as key
                    if subject_name not in self._positions:
                        self._positions[subject_name] = (x, y, z)
            
            self._last_data_time = time.time()
