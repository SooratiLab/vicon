"""
Position Plotter for Vicon and TurtleBot Tracking

Real-time matplotlib visualization of tracked object positions with trails and velocity vectors.
Works with both Vicon segments and TurtleBot localization data.
"""

import time
import math
from collections import deque
from typing import Dict, Tuple

import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt

from utils.core.setup_logging import get_named_logger

logger = get_named_logger("plotter", __name__)


class PositionPlotter:
    """
    Real-time position plotter with trails and velocity vectors.
    
    Works with both Vicon tracking data and TurtleBot localization data.
    
    Args:
        decay_seconds: Remove points not updated for this long
        trail_seconds: Show trail for this duration
        refresh_interval: Minimum time between redraws
        velocity_scale: Scale factor for velocity arrows
        show_pos: Show position coordinates in labels
        coord_scale: Scale factor for coordinates (1.0 = meters, 0.001 = mm to meters)
    """
    
    def __init__(
        self,
        decay_seconds: float = 15.0,
        trail_seconds: float = 10.0,
        refresh_interval: float = 0.2,
        velocity_scale: float = 1.0,
        show_pos: bool = False,
        coord_scale: float = 0.001,  # Default: convert mm to meters
    ):
        self.decay_seconds = decay_seconds
        self.trail_seconds = trail_seconds
        self.refresh_interval = refresh_interval
        self.velocity_scale = velocity_scale
        self.show_pos = show_pos
        self.coord_scale = coord_scale

        self._points: Dict[Tuple[str, int], deque] = {}
        self._last_draw = 0.0
        self._running = True

        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self._setup_axes()
        plt.show(block=False)
        logger.info("Plotter initialized")

        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _on_key(self, event):
        """Handle key press events."""
        if event.key == "p":
            self.show_pos = not self.show_pos
            logger.info(f"Show positions: {self.show_pos}")
        elif event.key == "c":
            # Clear all trails
            self._points.clear()
            logger.info("Cleared all trails")

    def _setup_axes(self):
        """Setup the plot axes."""
        self.ax.set_xlabel("X (m)")
        self.ax.set_ylabel("Y (m)")
        self.ax.set_title("Vicon Tracking Visualization")
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.grid(True, alpha=0.3)
        
        # Set initial limits (will auto-adjust)
        # Default for Vicon in meters (assuming mm to m conversion)
        self.ax.set_xlim(-2, 6)
        self.ax.set_ylim(-2, 6)

    def update(self, label: str, beacon_id: int, x: float, y: float, z: float):
        """
        Update position for a tracked object.
        
        Args:
            label: Object type 
                - "VICON" or "SEG" for Vicon segments
                - "BOT" for TurtleBots (backward compatibility)
                - "REF" for reference markers
            beacon_id: Unique ID for the object
            x: X position (will be scaled by coord_scale)
            y: Y position (will be scaled by coord_scale)
            z: Z position (will be scaled by coord_scale)
        """
        if not self._running:
            return

        # Apply coordinate scaling (e.g., mm to meters)
        x_scaled = x * self.coord_scale
        y_scaled = y * self.coord_scale
        z_scaled = z * self.coord_scale

        now = time.monotonic()
        key = (label, beacon_id)

        if key not in self._points:
            self._points[key] = deque()

        self._points[key].append((x_scaled, y_scaled, z_scaled, now))

        # Remove old points from trail
        while self._points[key] and now - self._points[key][0][3] > self.trail_seconds:
            self._points[key].popleft()

        # Redraw if enough time has passed
        if now - self._last_draw >= self.refresh_interval:
            self._redraw(now)

    def _label_alignment(self, x: float, y: float):
        """Calculate label alignment based on position."""
        xmin, xmax = self.ax.get_xlim()
        ymin, ymax = self.ax.get_ylim()

        x_mid = (xmin + xmax) * 0.5
        y_mid = (ymin + ymax) * 0.5

        ha = "left" if x < x_mid else "right"
        va = "bottom" if y < y_mid else "top"

        dx = 8 if ha == "left" else -8
        dy = 8 if va == "bottom" else -8

        return ha, va, dx, dy

    def _redraw(self, now: float):
        """Redraw the plot."""
        try:
            self.ax.clear()
            self._setup_axes()

            expired = []

            for (label, bid), samples in self._points.items():
                if not samples:
                    expired.append((label, bid))
                    continue

                last_x, last_y, last_z, last_ts = samples[-1]

                # Check if this object has timed out
                if now - last_ts > self.decay_seconds:
                    expired.append((label, bid))
                    continue

                xs = [p[0] for p in samples]
                ys = [p[1] for p in samples]

                # Determine object type and styling
                is_vicon = label in ["VICON", "SEG"]
                is_bot = label == "BOT"
                is_ref = label == "REF"
                
                if is_vicon:
                    color = "green"
                    marker = "D"  # Diamond for Vicon segments
                    size = 120
                elif is_bot:
                    color = "red"
                    marker = "o"
                    size = 100
                else:  # Reference marker
                    color = "blue"
                    marker = "s"
                    size = 80

                # Draw trail (only for moving objects)
                if len(xs) > 1 and (is_vicon or is_bot):
                    self.ax.plot(xs, ys, color=color, alpha=0.4, linewidth=2)

                # Draw current position
                self.ax.scatter(last_x, last_y, c=color, marker=marker, s=size, zorder=5)

                # Label rendering
                if is_vicon:
                    name = f"V{bid}"  # Vicon segment
                elif is_bot:
                    name = f"M{bid}"  # Mobile robot
                else:
                    name = f"R{bid}"  # Reference marker
                
                if self.show_pos:
                    ha, va, dx, dy = self._label_alignment(last_x, last_y)
                    text = f"{name} ({last_x:.2f}, {last_y:.2f})"
                    self.ax.annotate(
                        text,
                        (last_x, last_y),
                        xytext=(dx, dy),
                        textcoords="offset points",
                        ha=ha,
                        va=va,
                        fontsize=9,
                        color=color,
                        alpha=0.9,
                        fontweight="bold"
                    )
                else:
                    self.ax.annotate(
                        name,
                        (last_x, last_y),
                        xytext=(5, 5),
                        textcoords="offset points",
                        fontsize=10,
                        color=color,
                        fontweight="bold"
                    )

                # Velocity vector (only for moving objects)
                if (is_vicon or is_bot) and len(samples) >= 2:
                    x0, y0, _, t0 = samples[-2]
                    dt = last_ts - t0
                    if dt > 0:
                        vx = (last_x - x0) / dt
                        vy = (last_y - y0) / dt
                        speed = math.hypot(vx, vy)
                        if speed > 0.01:  # Only show if moving
                            self.ax.arrow(
                                last_x,
                                last_y,
                                vx * self.velocity_scale,
                                vy * self.velocity_scale,
                                head_width=0.08,
                                head_length=0.1,
                                fc=color,
                                ec=color,
                                alpha=0.7,
                                zorder=4
                            )

            # Remove expired entries
            for key in expired:
                del self._points[key]

            self.fig.canvas.draw_idle()
            plt.pause(0.001)
            self._last_draw = now

        except KeyboardInterrupt:
            self.close()
        except Exception as e:
            # Don't crash on plotting errors
            logger.debug(f"Plot error: {e}")

    def close(self):
        """Close the plotter."""
        self._running = False
        try:
            plt.close(self.fig)
            logger.info("Plotter closed")
        except Exception:
            pass
