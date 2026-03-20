from setuptools import find_packages, setup

package_name = "rover_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/rover.launch.py"]),
        (f"share/{package_name}/config", ["config/nav2_params.yaml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Computer Project",
    maintainer_email="founder@computer.local",
    description="Rover control ROS2 package",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            f"nav2_bridge = {package_name}.nav2_bridge:main",
        ],
    },
)
