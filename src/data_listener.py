#!/usr/bin/env python3
"""
Vicon Data Listener

Receives and processes streaming Vicon tracking data from data_streamer.py.
Can save data to CSV, display real-time statistics, or forward to other systems.

Usage:
    python data_listener.py --host 192.168.1.100 --port 5555
    python data_listener.py --host localhost --port 5555 --save
    python data_listener.py --host localhost --port 5555 --verbose

Requirements:
    - None (uses only standard library)
"""

import argparse
import socket
import json
import time
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.core.setup_logging import setup_logging, get_named_logger

logger = get_named_logger("vicon_listener", __name__)


class ViconDataListener:
    """
    Listens to Vicon tracking data stream and processes it.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5555,
        save_to_csv: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the listener.
        
        Args:
            host: Vicon streamer host address
            port: TCP port to connect to
            save_to_csv: Whether to save data to CSV files
            verbose: Print detailed data information
        """
        self.host = host
        self.port = port
        self.save_to_csv = save_to_csv
        self.verbose = verbose
        
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._running = False
        
        # Statistics
        self._frames_received = 0
        self._bytes_received = 0
        self._start_time = 0.0
        self._last_frame_time = 0.0
        
        # CSV file handles
        self._csv_files = {}
    
    def connect(self) -> bool:
        """Connect to the Vicon streamer."""
        logger.info(f"Connecting to Vicon streamer at {self.host}:{self.port}...")
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((self.host, self.port))
            
            # Set socket to non-blocking after connection
            self._socket.settimeout(None)
            
            self._connected = True
            logger.info("Connected successfully")
            return True
            
        except socket.timeout:
            logger.error("Connection timeout")
            return False
        except ConnectionRefusedError:
            logger.error("Connection refused - is the streamer running?")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def start(self):
        """Start listening for data."""
        if not self._connected:
            logger.error("Not connected to streamer")
            return
        
        logger.info("Listening for Vicon data...")
        self._running = True
        self._start_time = time.monotonic()
        
        buffer = b""
        
        try:
            while self._running:
                # Receive data
                try:
                    chunk = self._socket.recv(4096)
                    if not chunk:
                        logger.warning("Connection closed by server")
                        break
                    
                    self._bytes_received += len(chunk)
                    buffer += chunk
                    
                    # Process complete messages (newline-delimited JSON)
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if line:
                            self._process_message(line)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Receive error: {e}")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()
    
    def _process_message(self, data: bytes):
        """Process a received message."""
        try:
            payload = json.loads(data.decode('utf-8'))
            self._frames_received += 1
            self._last_frame_time = time.monotonic()
            
            # Process the data
            self._handle_vicon_data(payload)
            
            # Print stats periodically
            if self._frames_received % 100 == 0:
                self._print_stats()
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def _handle_vicon_data(self, payload: Dict[str, Any]):
        """Handle received Vicon data."""
        frame_number = payload.get("frame_number", 0)
        timestamp = payload.get("timestamp", 0)
        latency_ms = payload.get("latency_ms", 0)
        subjects = payload.get("subjects", [])
        
        if self.verbose:
            logger.info(
                f"Frame {frame_number} | "
                f"Subjects: {len(subjects)} | "
                f"Latency: {latency_ms:.2f}ms"
            )
        
        # Process each subject
        for subject in subjects:
            subject_name = subject.get("name", "Unknown")
            quality = subject.get("quality", None)
            
            # Process segments (pose data)
            segments = subject.get("segments", [])
            for segment in segments:
                segment_name = segment.get("name", "Unknown")
                position = segment.get("position", {})
                orientation = segment.get("orientation", {})
                euler = segment.get("euler_xyz", {})
                
                if self.verbose:
                    logger.info(
                        f"  {subject_name}/{segment_name} | "
                        f"Pos: ({position.get('x', 0):.3f}, {position.get('y', 0):.3f}, {position.get('z', 0):.3f}) | "
                        f"Rot: ({euler.get('x', 0):.2f}, {euler.get('y', 0):.2f}, {euler.get('z', 0):.2f})°"
                    )
                
                if self.save_to_csv:
                    self._save_segment_to_csv(
                        timestamp, frame_number, subject_name, segment_name,
                        position, orientation, euler, quality
                    )
            
            # Process markers
            markers = subject.get("markers", [])
            if markers and self.verbose:
                logger.info(f"  {subject_name} has {len(markers)} markers")
        
        # Process unlabeled markers
        unlabeled = payload.get("unlabeled_markers", [])
        if unlabeled and self.verbose:
            logger.info(f"  {len(unlabeled)} unlabeled markers")
        
        # Process camera data
        cameras = payload.get("cameras", [])
        if cameras and self.verbose:
            logger.info(f"  {len(cameras)} cameras")
    
    def _save_segment_to_csv(
        self,
        timestamp: float,
        frame_number: int,
        subject_name: str,
        segment_name: str,
        position: Dict,
        orientation: Dict,
        euler: Dict,
        quality: Optional[float]
    ):
        """Save segment data to CSV file."""
        # Create CSV file for this subject/segment if not exists
        key = f"{subject_name}_{segment_name}"
        
        if key not in self._csv_files:
            filename = f"vicon_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            csv_path = Path("data") / filename
            csv_path.parent.mkdir(exist_ok=True)
            
            f = open(csv_path, 'w')
            f.write("timestamp,frame_number,pos_x,pos_y,pos_z,quat_x,quat_y,quat_z,quat_w,"
                   "euler_x,euler_y,euler_z,quality,pos_occluded,rot_occluded\n")
            self._csv_files[key] = f
            logger.info(f"Created CSV file: {csv_path}")
        
        # Write data
        f = self._csv_files[key]
        f.write(
            f"{timestamp},{frame_number},"
            f"{position.get('x', 0)},{position.get('y', 0)},{position.get('z', 0)},"
            f"{orientation.get('x', 0)},{orientation.get('y', 0)},"
            f"{orientation.get('z', 0)},{orientation.get('w', 1)},"
            f"{euler.get('x', 0)},{euler.get('y', 0)},{euler.get('z', 0)},"
            f"{quality if quality is not None else ''},"
            f"{1 if position.get('occluded', False) else 0},"
            f"{1 if orientation.get('occluded', False) else 0}\n"
        )
        f.flush()
    
    def _print_stats(self):
        """Print reception statistics."""
        if not self._running:
            return
        
        uptime = time.monotonic() - self._start_time
        receive_rate = self._frames_received / uptime if uptime > 0 else 0
        
        # Calculate latency (time since last frame)
        current_time = time.monotonic()
        frame_latency = (current_time - self._last_frame_time) * 1000 if self._last_frame_time > 0 else 0
        
        logger.info(
            f"Stats | Frames: {self._frames_received} ({receive_rate:.1f} Hz) | "
            f"Data: {self._bytes_received / 1024:.1f} KB | "
            f"Latency: {frame_latency:.1f}ms | "
            f"Uptime: {uptime:.1f}s"
        )
    
    def stop(self):
        """Stop listening and cleanup."""
        logger.info("Stopping listener...")
        self._running = False
        
        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        
        # Close CSV files
        for f in self._csv_files.values():
            try:
                f.close()
            except:
                pass
        
        self._print_stats()
        logger.info("Listener stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Vicon Data Listener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Listen and display data
    python data_listener.py --host localhost --port 5555
    
    # Save data to CSV files
    python data_listener.py --host localhost --port 5555 --save
    
    # Verbose output with detailed position data
    python data_listener.py --host localhost --port 5555 --verbose
    
    # Remote streamer
    python data_listener.py --host 192.168.1.100 --port 5555 --save

Note:
    Requires data_streamer.py to be running on the specified host.
        """
    )
    
    parser.add_argument("--host", type=str, default="localhost",
                       help="Vicon streamer host address (default: localhost)")
    parser.add_argument("--port", type=int, default=5555,
                       help="TCP port to connect to (default: 5555)")
    parser.add_argument("--save", action="store_true",
                       help="Save data to CSV files")
    parser.add_argument("--verbose", action="store_true",
                       help="Print detailed data information")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(
        experiment_name="vicon_listener",
        log_to_file=True,
        log_to_console=True
    )
    
    # Create listener
    listener = ViconDataListener(
        host=args.host,
        port=args.port,
        save_to_csv=args.save,
        verbose=args.verbose
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        listener.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Connect and start listening
    if listener.connect():
        listener.start()
    else:
        logger.error("Failed to connect to streamer")
        sys.exit(1)


if __name__ == "__main__":
    main()
