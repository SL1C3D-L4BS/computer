"""Rover launch file — starts Nav2 bridge + lifecycle manager."""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument


def generate_launch_description():
    rover_id_arg = DeclareLaunchArgument(
        "rover_id",
        default_value="field-rover-001",
        description="Rover identifier for MQTT topics",
    )

    nav2_bridge = Node(
        package="rover_control",
        executable="nav2_bridge",
        name="nav2_bridge",
        parameters=[
            {"rover_id": LaunchConfiguration("rover_id")},
        ],
        output="screen",
    )

    return LaunchDescription([rover_id_arg, nav2_bridge])
