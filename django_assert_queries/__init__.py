"""Django query assertion and instrumentation.

Version Added:
    1.0

This is the primary module for django-assert-queries. Projects should import
straight from this module.

The following functions are available:

.. autosummary::
   :nosignatures:

   ~django_assert_queries.query_catcher.ExecutedQueryInfo
   ~django_assert_queries.query_catcher.ExecutedQueryType
   ~django_assert_queries.query_catcher.ExecutedSubQueryInfo
   ~django_assert_queries.query_catcher.catch_queries
   ~django_assert_queries.query_comparator.ExpectedQueries
   ~django_assert_queries.query_comparator.ExpectedQuery
   ~django_assert_queries.query_comparator.QueryMismatch
   ~django_assert_queries.query_comparator.compare_queries
"""

from django_assert_queries._version import (
    VERSION,
    __version__,
    __version_info__,
    get_package_version,
    get_version_string,
    is_release,
)
from django_assert_queries.query_catcher import (
    ExecutedQueryInfo,
    ExecutedQueryType,
    ExecutedSubQueryInfo,
    catch_queries,
)
from django_assert_queries.query_comparator import (
    ExpectedQueries,
    ExpectedQuery,
    QueryMismatch,
    compare_queries,
)
from django_assert_queries.testing import assert_queries


__all__ = [
    'ExecutedQueryInfo',
    'ExecutedQueryType',
    'ExecutedSubQueryInfo',
    'ExpectedQueries',
    'ExpectedQuery',
    'QueryMismatch',
    'VERSION',
    '__version__',
    '__version_info__',
    'assert_queries',
    'catch_queries',
    'compare_queries',
    'get_package_version',
    'get_version_string',
    'is_release',
]

__autodoc_excludes__ = __all__
