"""CSV Writer for Vicon Tracking Data

Writes Vicon position and orientation data to CSV files with throttled rate support.
Handles segments (rigid bodies), markers, and quality metrics.
"""

import csv
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ViconCSVWriter:
    """
    CSV writer for Vicon tracking data.
    
    Writes segment pose data (position + orientation) at a configurable rate
    with proper timestamping for later analysis.
    """
    
    def __init__(
        self,
        output_path: Path,
        rate_hz: float = 10.0,
        append: bool = False
    ):
        """
        Initialize the CSV writer.
        
        Args:
            output_path: Path to output CSV file
            rate_hz: Maximum write rate in Hz
            append: Whether to append to existing file
        """
        self._output_path = Path(output_path)
        self._period = 1.0 / rate_hz
        self._last_write_time = 0.0
        
        # Create parent directories if needed
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open file
        mode = "a" if append else "w"
        self._file = self._output_path.open(mode, newline="")
        self._writer = csv.writer(self._file)
        
        # Write header if new file
        if not append or self._output_path.stat().st_size == 0:
            self._writer.writerow([
                "ts_write",        # Wall clock time when written
                "timestamp",       # Vicon timestamp
                "frame_number",    # Vicon frame number
                "latency_ms",      # Vicon system latency
                "subject_name",    # Subject name
                "segment_name",    # Segment name
                "pos_x",           # Position X (mm)
                "pos_y",           # Position Y (mm)
                "pos_z",           # Position Z (mm)
                "quat_x",          # Quaternion X
                "quat_y",          # Quaternion Y
                "quat_z",          # Quaternion Z
                "quat_w",          # Quaternion W
                "euler_x",         # Euler angle X (degrees)
                "euler_y",         # Euler angle Y (degrees)
                "euler_z",         # Euler angle Z (degrees)
                "quality",         # Object quality (if available)
                "occluded"         # Whether object is occluded
            ])
            self._file.flush()
        
        # Statistics
        self._rows_written = 0
        self._snapshots_written = 0
        
        logger.info(
            f"CSV writer opened at {output_path} (rate {rate_hz:.1f} Hz)"
        )
    
    def write_snapshot(
        self,
        vicon_data: Dict[str, Any]
    ) -> bool:
        """
        Write a Vicon data snapshot.
        
        Args:
            vicon_data: Dictionary containing Vicon frame data with structure:
                {
                    "timestamp": float,
                    "frame_number": int,
                    "latency_ms": float,
                    "subjects": [
                        {
                            "name": str,
                            "quality": float,
                            "segments": [
                                {
                                    "name": str,
                                    "position": {"x": float, "y": float, "z": float, "occluded": bool},
                                    "orientation": {"x": float, "y": float, "z": float, "w": float, "occluded": bool},
                                    "euler_xyz": {"x": float, "y": float, "z": float, "occluded": bool}
                                }
                            ]
                        }
                    ]
                }
            
        Returns:
            True if written, False if throttled
        """
        now = time.monotonic()
        
        # Rate limiting
        if now - self._last_write_time < self._period:
            return False
        
        ts_write = time.time()
        timestamp = vicon_data.get("timestamp", ts_write)
        frame_number = vicon_data.get("frame_number", 0)
        latency_ms = vicon_data.get("latency_ms", 0)
        subjects = vicon_data.get("subjects", [])
        
        rows = []
        for subject in subjects:
            subject_name = subject.get("name", "Unknown")
            quality = subject.get("quality", None)
            
            segments = subject.get("segments", [])
            for segment in segments:
                segment_name = segment.get("name", "Unknown")
                position = segment.get("position", {})
                orientation = segment.get("orientation", {})
                euler = segment.get("euler_xyz", {})
                
                occluded = position.get("occluded", False) or orientation.get("occluded", False)
                
                rows.append([
                    f"{ts_write:.6f}",
                    f"{timestamp:.6f}",
                    frame_number,
                    f"{latency_ms:.3f}",
                    subject_name,
                    segment_name,
                    f"{position.get('x', 0):.6f}",
                    f"{position.get('y', 0):.6f}",
                    f"{position.get('z', 0):.6f}",
                    f"{orientation.get('x', 0):.6f}",
                    f"{orientation.get('y', 0):.6f}",
                    f"{orientation.get('z', 0):.6f}",
                    f"{orientation.get('w', 1):.6f}",
                    f"{euler.get('x', 0):.6f}",
                    f"{euler.get('y', 0):.6f}",
                    f"{euler.get('z', 0):.6f}",
                    f"{quality:.4f}" if quality is not None else "",
                    1 if occluded else 0
                ])
        
        if not rows:
            return False
        
        self._writer.writerows(rows)
        self._file.flush()
        
        self._last_write_time = now
        self._rows_written += len(rows)
        self._snapshots_written += 1
        
        logger.debug(
            f"CSV snapshot written: {len(subjects)} subjects, {len(rows)} segments at frame {frame_number}"
        )
        
        return True
    
    def close(self):
        """Close the CSV file."""
        logger.info(
            f"Closing CSV writer. Wrote {self._rows_written} rows in "
            f"{self._snapshots_written} snapshots"
        )
        self._file.close()
    
    @property
    def rows_written(self) -> int:
        """Get total rows written."""
        return self._rows_written
    
    @property
    def snapshots_written(self) -> int:
        """Get total snapshots written."""
        return self._snapshots_written
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
