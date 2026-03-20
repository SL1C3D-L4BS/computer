"""
Integration test configuration.
These tests require all core services to be running.
Use `task bootstrap` or `task dev` to start services before running.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require running services)",
    )
