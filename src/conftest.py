"""Cross-module test fixtures.

Qt owns process-global native state.  Every view test module historically
created its own ``QApplication`` wrapper; once that module finished, the wrapper
could be garbage-collected while later modules still used Qt, causing native
heap corruption on Windows.  Hold one application for the whole pytest session.
"""
import os

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application
