import pytest
import os


def pytest_ignore_collect(collection_path, config):
    return True
