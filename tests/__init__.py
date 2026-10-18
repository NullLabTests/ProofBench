"""Test package marker.

Makes ``tests`` importable so ``from tests.conftest import ...`` works
whether pytest is invoked as ``pytest`` (CI) or ``python -m pytest``.
"""
