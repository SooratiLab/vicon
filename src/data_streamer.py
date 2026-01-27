#!/usr/bin/env python3
"""
Vicon DataStream Broadcaster

Streams position, orientation, and other tracking data from a Vicon system
to connected clients over TCP. Supports different data modes:
    - pose: Position and orientation (segments)
    - all: All geometry data (segments, markers, quality)
    - frames: Camera frames from Vicon cameras (if available)

Usage:
    python data_streamer.py --host localhost:801 --pose
    python data_streamer.py --host localhost:801 --all --rate 100
    python data_streamer.py --host localhost:801 --pose --frames

Requirements:
    - vicon_dssdk (Vicon DataStream SDK)
    - numpy (for data handling)
"""

import argparse
import signal
import sys
import time
import json
import threading
from typing import Optional, Dict, List, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.core.broadcaster import DataBroadcaster
from utils.core.setup_logging import setup_logging, get_named_logger

try:
    from vicon_dssdk import ViconDataStream
except ImportError:
    print("ERROR: vicon_dssdk not found. Please install the Vicon DataStream SDK.")
    print("Install location: C:\\Program Files\\Vicon\\DataStream SDK\\Win64\\Python")
    sys.exit(1)

logger = get_named_logger("vicon_streamer", __name__)


class ViconStreamer:
    """
    Streams Vicon tracking data to connected clients.
    
    Connects to a Vicon DataStream server, captures tracking data at a
    specified rate, and broadcasts it to TCP clients.
    """
    
    def __init__(
        self,
        vicon_host: str = "localhost:801",
        broadcast_port: int = 5555,
        rate_hz: float = 100.0,
        stream_mode: str = "pose",
        include_frames: bool = False
    ):
        """
        Initialize the Vicon streamer.
        
        Args:
            vicon_host: Vicon server address (host:port format)
            broadcast_port: TCP port for broadcasting data
            rate_hz: Target streaming rate in Hz
            stream_mode: Data mode - "pose", "all"
            include_frames: Whether to stream camera frames
        """
        self.vicon_host = vicon_host
        self.stream_mode = stream_mode
        self.include_frames = include_frames
        self.rate_hz = rate_hz
        self.period = 1.0 / rate_hz
        
        # Vicon client
        self.client = ViconDataStream.Client()
        self._connected = False
        
        # Broadcaster
        self.broadcaster = DataBroadcaster(
            host="0.0.0.0",
            port=broadcast_port,
            rate_hz=rate_hz
        )
        
        # Control
        self._running = False
        self._stream_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._frames_captured = 0
        self._frames_broadcasted = 0
        self._start_time = 0.0
    
    def connect(self) -> bool:
        """Connect to the Vicon DataStream server."""
        logger.info(f"Connecting to Vicon at {self.vicon_host}...")
        
        try:
            self.client.Connect(self.vicon_host)
            
            if not self.client.IsConnected():
                logger.error("Failed to connect to Vicon server")
                return False
            
            # Get server version
            version = self.client.GetVersion()
            logger.info(f"Connected to Vicon DataStream SDK v{version[0]}.{version[1]}.{version[2]}")
            
            # Configure stream mode
            self.client.SetStreamMode(ViconDataStream.Client.StreamMode.EServerPush)
            
            # Set buffer size for low latency
            self.client.SetBufferSize(1)
            
            # Enable data types based on streaming mode
            self._enable_data_types()
            
            # Set axis mapping (Z-up, right-handed)
            self.client.SetAxisMapping(
                ViconDataStream.Client.AxisMapping.EForward,
                ViconDataStream.Client.AxisMapping.ELeft,
                ViconDataStream.Client.AxisMapping.EUp
            )
            
            # Wait for first frame
            logger.info("Waiting for first frame...")
            timeout = 50
            while timeout > 0:
                if self.client.GetFrame():
                    logger.info("First frame received")
                    break
                timeout -= 1
                time.sleep(0.1)
            
            if timeout <= 0:
                logger.error("Timeout waiting for first frame")
                return False
            
            # Get frame rate
            frame_rate = self.client.GetFrameRate()
            logger.info(f"Vicon frame rate: {frame_rate:.2f} Hz")
            
            # List available subjects
            subjects = self.client.GetSubjectNames()
            logger.info(f"Found {len(subjects)} subjects: {', '.join(subjects)}")
            
            self._connected = True
            return True
            
        except ViconDataStream.DataStreamException as e:
            logger.error(f"Vicon connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to Vicon: {e}")
            return False
    
    def _enable_data_types(self):
        """Enable appropriate data types based on stream mode."""
        if self.stream_mode in ["pose", "all"]:
            self.client.EnableSegmentData()
            logger.info("Enabled segment data")
        
        if self.stream_mode == "all":
            self.client.EnableMarkerData()
            self.client.EnableUnlabeledMarkerData()
            self.client.EnableDeviceData()
            logger.info("Enabled all geometry data (markers, devices)")
        
        if self.include_frames:
            self.client.EnableCentroidData()
            logger.info("Enabled centroid data for frames")
    
    def start(self):
        """Start streaming data."""
        if not self._connected:
            logger.error("Not connected to Vicon server")
            return
        
        logger.info(f"Starting Vicon data streamer (mode: {self.stream_mode}, rate: {self.rate_hz} Hz)")
        
        # Start broadcaster
        if not self.broadcaster.start():
            logger.error("Failed to start broadcaster")
            return
        
        self._running = True
        self._start_time = time.monotonic()
        
        # Start streaming thread
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        
        logger.info(f"Streaming on port {self.broadcaster.port}")
        
        # Keep main thread alive and print stats
        try:
            while self._running:
                time.sleep(5.0)
                self._print_stats()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            self.stop()
    
    def _stream_loop(self):
        """Main streaming loop - captures and broadcasts Vicon data."""
        last_capture_time = 0.0
        last_frame_number = -1
        
        while self._running:
            try:
                loop_start = time.monotonic()
                
                # Get new frame from Vicon
                if not self.client.GetFrame():
                    time.sleep(0.001)
                    continue
                
                frame_number = self.client.GetFrameNumber()
                
                # Skip duplicate frames
                if frame_number == last_frame_number:
                    time.sleep(0.001)
                    continue
                
                last_frame_number = frame_number
                self._frames_captured += 1
                
                # Rate limiting
                if loop_start - last_capture_time < self.period:
                    time.sleep(0.001)
                    continue
                
                last_capture_time = loop_start
                
                # Capture data based on mode
                payload = self._capture_data()
                
                # Broadcast to clients
                if payload and self.broadcaster.client_count > 0:
                    self.broadcaster.update(payload)
                    self._frames_broadcasted += 1
                
            except ViconDataStream.DataStreamException as e:
                logger.error(f"Vicon data error: {e}")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                time.sleep(0.1)
    
    def _capture_data(self) -> Dict[str, Any]:
        """Capture data from Vicon based on stream mode."""
        payload = {
            "timestamp": time.time(),
            "frame_number": self.client.GetFrameNumber(),
            "latency_ms": self.client.GetLatencyTotal() * 1000,
        }
        
        # Get all subjects
        subjects = self.client.GetSubjectNames()
        payload["subject_count"] = len(subjects)
        payload["subjects"] = []
        
        for subject_name in subjects:
            subject_data = {
                "name": subject_name,
            }
            
            # Get quality if available
            try:
                quality = self.client.GetObjectQuality(subject_name)
                subject_data["quality"] = quality
            except:
                pass
            
            # Get segment data (pose)
            if self.stream_mode in ["pose", "all"]:
                subject_data["segments"] = self._get_segment_data(subject_name)
            
            # Get marker data
            if self.stream_mode == "all":
                subject_data["markers"] = self._get_marker_data(subject_name)
            
            payload["subjects"].append(subject_data)
        
        # Get unlabeled markers
        if self.stream_mode == "all":
            payload["unlabeled_markers"] = self._get_unlabeled_markers()
        
        # Get camera frames (if enabled)
        if self.include_frames:
            payload["cameras"] = self._get_camera_data()
        
        return payload
    
    def _get_segment_data(self, subject_name: str) -> List[Dict[str, Any]]:
        """Get segment position and orientation data."""
        segments = []
        
        try:
            segment_names = self.client.GetSegmentNames(subject_name)
            
            for segment_name in segment_names:
                segment = {"name": segment_name}
                
                # Global translation (position)
                trans, occluded = self.client.GetSegmentGlobalTranslation(subject_name, segment_name)
                segment["position"] = {
                    "x": trans[0],
                    "y": trans[1],
                    "z": trans[2],
                    "occluded": occluded
                }
                
                # Global rotation (quaternion - most compact)
                rot, occluded = self.client.GetSegmentGlobalRotationQuaternion(subject_name, segment_name)
                segment["orientation"] = {
                    "x": rot[0],
                    "y": rot[1],
                    "z": rot[2],
                    "w": rot[3],
                    "occluded": occluded
                }
                
                # Also get Euler angles for convenience
                euler, occluded = self.client.GetSegmentGlobalRotationEulerXYZ(subject_name, segment_name)
                segment["euler_xyz"] = {
                    "x": euler[0],
                    "y": euler[1],
                    "z": euler[2],
                    "occluded": occluded
                }
                
                segments.append(segment)
                
        except ViconDataStream.DataStreamException:
            pass
        
        return segments
    
    def _get_marker_data(self, subject_name: str) -> List[Dict[str, Any]]:
        """Get marker position data."""
        markers = []
        
        try:
            marker_names = self.client.GetMarkerNames(subject_name)
            
            for marker_name, parent_segment in marker_names:
                trans, occluded = self.client.GetMarkerGlobalTranslation(subject_name, marker_name)
                
                markers.append({
                    "name": marker_name,
                    "parent_segment": parent_segment,
                    "position": {
                        "x": trans[0],
                        "y": trans[1],
                        "z": trans[2]
                    },
                    "occluded": occluded
                })
                
        except ViconDataStream.DataStreamException:
            pass
        
        return markers
    
    def _get_unlabeled_markers(self) -> List[Dict[str, Any]]:
        """Get unlabeled marker positions."""
        unlabeled = []
        
        try:
            unlabeled_markers = self.client.GetUnlabeledMarkers()
            
            for marker_pos, traj_id in unlabeled_markers:
                unlabeled.append({
                    "trajectory_id": traj_id,
                    "position": {
                        "x": marker_pos[0],
                        "y": marker_pos[1],
                        "z": marker_pos[2]
                    }
                })
                
        except ViconDataStream.DataStreamException:
            pass
        
        return unlabeled
    
    def _get_camera_data(self) -> List[Dict[str, Any]]:
        """Get camera metadata (frames not fully supported in SDK)."""
        cameras = []
        
        try:
            camera_names = self.client.GetCameraNames()
            
            for camera_name in camera_names:
                camera_info = {
                    "name": camera_name,
                    "id": self.client.GetCameraID(camera_name),
                    "display_name": self.client.GetCameraDisplayName(camera_name),
                }
                
                # Get camera resolution
                res_x, res_y = self.client.GetCameraResolution(camera_name)
                camera_info["resolution"] = {"width": res_x, "height": res_y}
                
                # Check if it's a video camera
                camera_info["is_video"] = self.client.GetIsVideoCamera(camera_name)
                
                # Get centroids (2D image features)
                centroids = self.client.GetCentroids(camera_name)
                camera_info["centroid_count"] = len(centroids)
                
                cameras.append(camera_info)
                
        except ViconDataStream.DataStreamException:
            pass
        
        return cameras
    
    def _print_stats(self):
        """Print streaming statistics."""
        if not self._running:
            return
        
        uptime = time.monotonic() - self._start_time
        capture_rate = self._frames_captured / uptime if uptime > 0 else 0
        broadcast_rate = self._frames_broadcasted / uptime if uptime > 0 else 0
        
        logger.info(
            f"Stats | Clients: {self.broadcaster.client_count} | "
            f"Captured: {self._frames_captured} ({capture_rate:.1f} Hz) | "
            f"Broadcasted: {self._frames_broadcasted} ({broadcast_rate:.1f} Hz) | "
            f"Uptime: {uptime:.1f}s"
        )
    
    def stop(self):
        """Stop streaming and disconnect."""
        logger.info("Stopping Vicon streamer...")
        self._running = False
        
        # Stop broadcaster
        self.broadcaster.stop()
        
        # Disconnect from Vicon
        if self._connected:
            try:
                self.client.Disconnect()
                logger.info("Disconnected from Vicon")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
        
        self._print_stats()
        logger.info("Vicon streamer stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Vicon DataStream Broadcaster",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Stream Modes:
    --pose      Position and orientation (segments only)
    --all       All geometry data (segments, markers, quality)
    
Additional Options:
    --frames    Include camera frame metadata (centroids)

Examples:
    # Stream pose data at 100 Hz
    python data_streamer.py --host localhost:801 --pose --rate 100
    
    # Stream all geometry data
    python data_streamer.py --host localhost:801 --all
    
    # Stream pose with camera metadata
    python data_streamer.py --host localhost:801 --pose --frames
    
    # Custom broadcast port
    python data_streamer.py --host 192.168.1.100:801 --pose --port 5556

Note:
    Clients can connect via TCP to receive JSON-formatted tracking data.
    Use data_listener.py or position_listener.py to receive the stream.
        """
    )
    
    parser.add_argument("--host", type=str, default="localhost:801",
                       help="Vicon server address (host:port, default: localhost:801)")
    parser.add_argument("--port", type=int, default=5555,
                       help="TCP broadcast port (default: 5555)")
    parser.add_argument("--rate", type=float, default=100.0,
                       help="Target streaming rate in Hz (default: 100)")
    
    # Stream modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--pose", action="store_true",
                           help="Stream position and orientation (segments)")
    mode_group.add_argument("--all", dest="all_data", action="store_true",
                           help="Stream all geometry data (segments, markers)")
    
    # Additional options
    parser.add_argument("--frames", action="store_true",
                       help="Include camera frame metadata")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(
        experiment_name="vicon_streamer",
        log_to_file=True,
        log_to_console=True
    )
    
    # Determine stream mode
    stream_mode = "all" if args.all_data else "pose"
    
    # Create streamer
    streamer = ViconStreamer(
        vicon_host=args.host,
        broadcast_port=args.port,
        rate_hz=args.rate,
        stream_mode=stream_mode,
        include_frames=args.frames
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        streamer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Connect and start streaming
    if streamer.connect():
        logger.info(f"Starting stream (mode: {stream_mode}, rate: {args.rate} Hz)")
        streamer.start()
    else:
        logger.error("Failed to connect to Vicon server")
        sys.exit(1)


if __name__ == "__main__":
    main()
