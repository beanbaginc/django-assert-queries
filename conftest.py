"""Configures pytest and Django environment setup.

.. important::

   Do not define plugins in this file! Plugins must be in a different
   package (such as in tests/). pytest overrides importers for plugins and
   all modules descending from that module level, which will cause extension
   importers to fail, breaking unit tests.

Version Added:
    1.0
"""

import os
import sys

import django
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(django_db_reset_sequences):
    """Enable database access for all unit tests.

    This is applied to all test functions, ensuring database access isn't
    blocked.
    """
    pass


def pytest_report_header(config):
    """Return information for the report header.

    This will log the version of Django.

    Args:
        config (object):
            The pytest configuration object.

    Returns:
        list of unicode:
        The report header entries to log.
    """
    return [
        'django version: %s' % django.get_version(),
    ]
