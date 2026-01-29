"""
Position Plotter for Vicon Tracking

Real-time matplotlib visualization of tracked object positions with trails and velocity vectors.
Works with Vicon segments.
"""

import time
import math
from collections import deque
from typing import Dict, Tuple

import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt

from utils.core.setup_logging import get_named_logger


class PositionPlotter:
    """
    Real-time position plotter with trails and velocity vectors.
    
    Works with Vicon tracking data.
    
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
        show_pos: bool = True,
        coord_scale: float = 0.001,  # Default: convert mm to meters
    ):
        self.decay_seconds = decay_seconds
        self.trail_seconds = trail_seconds
        self.refresh_interval = refresh_interval
        self.velocity_scale = velocity_scale
        self.show_pos = show_pos
        self.coord_scale = coord_scale
        self.min_limit = 2.0  # Minimum ±2m from origin

        self._points: Dict[Tuple[str, str], deque] = {}
        self._last_draw = 0.0
        self._running = True

        self.logger = get_named_logger("plotter", __name__)

        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self._setup_axes()
        plt.show(block=False)
        self.logger.info("Plotter initialized")

        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _on_key(self, event):
        """Handle key press events."""
        if event.key == "p":
            self.show_pos = not self.show_pos
            self.logger.info(f"Show positions: {self.show_pos}")
        elif event.key == "c":
            # Clear all trails
            self._points.clear()
            self.logger.info("Cleared all trails")

    def _setup_axes(self):
        """Setup the plot axes."""
        self.ax.set_xlabel("X (m)")
        self.ax.set_ylabel("Y (m)")
        self.ax.set_title("Vicon Tracking Visualization")
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.grid(True, alpha=0.3)
        
        # Center plot at origin with minimum size
        self.ax.set_xlim(-self.min_limit, self.min_limit)
        self.ax.set_ylim(-self.min_limit, self.min_limit)
        
        # Draw crosshairs at origin
        self.ax.axhline(y=0, color='k', linewidth=0.5, alpha=0.3)
        self.ax.axvline(x=0, color='k', linewidth=0.5, alpha=0.3)

    def update(self, subject_name: str, x: float, y: float, z: float, segment_name: str = None):
        """
        Update position for a tracked object.
        
        Object type is automatically determined from subject_name:
        - Names starting with 'tb' or 'TB' -> Robot (red circle)
        - Names starting with 'ref' or 'REF' -> Reference (blue square)
        - All others -> Vicon segment (green diamond)
        
        Args:
            subject_name: Name of the subject (e.g., "TB10", "REF1", "Subject1")
            x: X position (will be scaled by coord_scale)
            y: Y position (will be scaled by coord_scale)
            z: Z position (will be scaled by coord_scale)
            segment_name: Optional segment name (only if different from subject_name)
        """
        if not self._running:
            return

        # Determine object type from name
        name_lower = subject_name.lower()
        if name_lower.startswith('tb'):
            obj_type = 'robot'
        elif name_lower.startswith('ref'):
            obj_type = 'reference'
        else:
            obj_type = 'vicon'

        # Apply coordinate scaling (e.g., mm to meters)
        x_scaled = x * self.coord_scale
        y_scaled = y * self.coord_scale
        z_scaled = z * self.coord_scale

        now = time.monotonic()
        # Use segment name if provided, otherwise just subject name
        display_name = f"{subject_name}/{segment_name}" if segment_name else subject_name
        key = (obj_type, display_name)

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

            # Calculate required limits based on all points
            max_extent = self.min_limit
            for samples in self._points.values():
                if samples:
                    for x, y, z, ts in samples:
                        extent = max(abs(x), abs(y))
                        max_extent = max(max_extent, extent)
            
            # Add 10% margin and ensure never smaller than min_limit
            plot_limit = max(self.min_limit, max_extent * 1.1)
            self.ax.set_xlim(-plot_limit, plot_limit)
            self.ax.set_ylim(-plot_limit, plot_limit)

            expired = []

            for (obj_type, name), samples in self._points.items():
                if not samples:
                    expired.append((obj_type, name))
                    continue

                last_x, last_y, last_z, last_ts = samples[-1]

                # Check if this object has timed out
                if now - last_ts > self.decay_seconds:
                    expired.append((obj_type, name))
                    continue

                xs = [p[0] for p in samples]
                ys = [p[1] for p in samples]

                # Determine styling based on object type
                if obj_type == 'robot':
                    color = "red"
                    marker = "o"  # Circle for robots (TB)
                    size = 100
                elif obj_type == 'reference':
                    color = "blue"
                    marker = "s"  # Square for references (REF)
                    size = 80
                else:  # vicon
                    color = "green"
                    marker = "D"  # Diamond for Vicon segments
                    size = 120

                # Draw trail
                if len(xs) > 1:
                    self.ax.plot(xs, ys, color=color, alpha=0.4, linewidth=2)

                # Draw current position
                self.ax.scatter(last_x, last_y, c=color, marker=marker, s=size, zorder=5)

                # Render label - name with position if enabled
                if self.show_pos:
                    text = f"{name} ({last_x:.2f}, {last_y:.2f})"
                else:
                    text = name
                self.ax.annotate(
                    text,
                    (last_x, last_y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=9,
                    color=color,
                    alpha=0.9,
                    fontweight="bold"
                )

                # Velocity vector
                if len(samples) >= 2:
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
            self.logger.debug(f"Plot error: {e}")

    def close(self):
        """Close the plotter."""
        self._running = False
        try:
            plt.close(self.fig)
            self.logger.info("Plotter closed")
        except Exception:
            pass
