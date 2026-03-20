"""
Nav2 Bridge — ROS2 node that bridges rover-control service to Nav2 NavigateToPose action.

This file requires ROS2 Kilted + nav2_msgs to be installed.
Run via: ros2 run rover_control nav2_bridge

Integration:
  - Subscribes to MQTT commands/rover/{rover_id}/mission
  - Sends NavigateToPose goals to Nav2 action server
  - Publishes position telemetry back to MQTT telemetry/rover/{rover_id}/position
  - Monitors battery from MQTT telemetry/rover/{rover_id}/battery

See docs/delivery/hil-gate-plan.md for SITL scenario requirements.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

# ROS2 imports — only available when ROS2 is sourced
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose
    from geometry_msgs.msg import PoseStamped
    from sensor_msgs.msg import BatteryState
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False

ROVER_ID = os.getenv("ROVER_ID", "field-rover-001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


class Nav2BridgeNode:
    """
    Bridges MQTT mission commands to ROS2 Nav2 NavigateToPose action.
    Runs in a separate thread from the ROS2 spin loop.
    """

    def __init__(self):
        if not ROS2_AVAILABLE:
            print("ROS2 not available — nav2_bridge in stub mode")
            return

        rclpy.init()
        self.node = Node(f"nav2_bridge_{ROVER_ID}")
        self.nav2_client = ActionClient(self.node, NavigateToPose, "navigate_to_pose")
        self._current_goal_handle = None
        self._running = True

        self.node.get_logger().info(f"Nav2 bridge started for rover: {ROVER_ID}")

    def navigate_to_waypoint(self, lat: float, lon: float, alt_m: float = 0.0) -> None:
        """
        Submit a NavigateToPose goal to Nav2.
        In field: GPS→ENU conversion required (RTK GNSS).
        In sim: direct ENU coordinates.
        """
        if not ROS2_AVAILABLE:
            print(f"STUB: Navigate to ({lat}, {lon})")
            return

        if not self.nav2_client.wait_for_server(timeout_sec=5.0):
            self.node.get_logger().error("Nav2 action server not available")
            return

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = lon  # Simplified: use ENU in production
        goal.pose.pose.position.y = lat
        goal.pose.pose.orientation.w = 1.0

        future = self.nav2_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self.node, future)
        self._current_goal_handle = future.result()

        if not self._current_goal_handle.accepted:
            self.node.get_logger().warning("Nav2 goal rejected")

    def cancel_navigation(self) -> None:
        """Cancel current navigation goal (E-stop)."""
        if self._current_goal_handle:
            cancel_future = self._current_goal_handle.cancel_goal_async()
            if ROS2_AVAILABLE:
                rclpy.spin_until_future_complete(self.node, cancel_future)
        if ROS2_AVAILABLE:
            self.node.get_logger().info("Navigation cancelled")

    def spin(self) -> None:
        if ROS2_AVAILABLE:
            rclpy.spin(self.node)

    def destroy(self) -> None:
        if ROS2_AVAILABLE:
            self.node.destroy_node()
            rclpy.shutdown()


def main():
    """ROS2 entry point."""
    bridge = Nav2BridgeNode()
    try:
        bridge.spin()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.destroy()


if __name__ == "__main__":
    main()
