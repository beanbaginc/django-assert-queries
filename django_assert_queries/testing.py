"""Utilities for capturing queries during unit tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import (Any, Dict, Iterator, List, Optional, Sequence,
                    TYPE_CHECKING, Union)

from django_assert_queries.query_comparator import compare_queries

if TYPE_CHECKING:
    from djagno_assert_queries.query_comparator import (CompareQueriesContext,
                                                        ExpectedQuery,
                                                        QueryMismatchedAttr)


@contextmanager
def assert_queries(
    queries: Sequence[Union[ExpectedQuery,
                            Dict[str, Any]]],
    num_statements: Optional[int] = None,
    *,
    with_tracebacks: bool = False,
    traceback_size: int = 15,
    check_join_types: Optional[bool] = None,
    check_subqueries: Optional[bool] = None,
) -> Iterator[None]:
    """Assert the number and complexity of queries.

    This provides advanced checking of queries, allowing the caller to
    match filtering, JOINs, ordering, selected fields, and more.

    This takes a list of dictionaries with query information. Each
    contains the keys in :py:class:`ExpectedQuery`.

    Args:
        queries (list of django_equery.query_comparator.ExpectedQuery):
            The list of query dictionaries to compare executed queries
            against.

        num_statements (int, optional):
            The numbre of SQL statements executed.

            This defaults to the length of ``queries``, but callers may
            need to provide an explicit number, as some operations may add
            additional database-specific statements (such as
            transaction-related SQL) that won't be covered in ``queries``.

        with_tracebacks (bool, optional):
            If enabled, tracebacks for queries will be included in
            results.

        tracebacks_size (int, optional):
            The size of any tracebacks, in number of lines.

            The default is 15.

    Raises:
        AssertionError:
            The parameters passed, or the queries compared, failed
            expectations.
    """
    def _serialize_mismatched_attrs(
        failures: List[QueryMismatchedAttr],
        *,
        indent: str,
    ) -> List[str]:
        error_lines: List[str] = []

        for mismatched_attr in sorted(failures,
                                      key=lambda attr: attr['name']):
            name = mismatched_attr['name']

            executed_value = mismatched_attr.get('executed_value')
            expected_value = mismatched_attr.get('expected_value')

            assert executed_value is not None
            assert expected_value is not None

            # If we're formatting multi-line output, make sure to
            # indent it properly.
            if '\n' in executed_value or '\n' in expected_value:
                executed_value = f'\n%s\n{indent}' % '\n'.join(
                    f'{indent}  {line}'
                    for line in executed_value.splitlines()
                )
                expected_value = '\n%s' % '\n'.join(
                    f'{indent}  {line}'
                    for line in expected_value.splitlines()
                )

            error_lines.append(
                f'{indent}{name}: '
                f'{executed_value} != {expected_value}')

        return error_lines

    def _serialize_results(
        results: CompareQueriesContext,
        *,
        indent: str = '',
    ) -> List[str]:
        mismatches = results['query_mismatches']
        num_queries = results['num_expected_queries']
        num_executed_queries = results['num_executed_queries']
        inner_indent = f'{indent}  '

        # Check if we found any failures, and include them in an assertion.
        error_lines: List[str] = []

        if num_queries != num_executed_queries:
            error_lines += [
                f'{indent}Expected {num_queries} queries, but got '
                f'{num_executed_queries}',

                '',
            ]

        if results['has_mismatches']:
            num_mismatches = len(mismatches)

            if num_mismatches == 1:
                error_lines.append(
                    f'{indent}1 query failed to meet expectations.')
            else:
                error_lines.append(
                    f'{indent}{num_mismatches} queries failed to meet '
                    f'expectations.'
                )

            for mismatch_info in mismatches:
                mismatched_attrs = mismatch_info['mismatched_attrs']
                subqueries = mismatch_info['subqueries']
                has_mismatched_subqueries = (check_subqueries and
                                             subqueries is not None and
                                             subqueries['has_mismatches'])

                if mismatched_attrs or has_mismatched_subqueries:
                    i = mismatch_info['index']
                    note = mismatch_info['note']
                    traceback = mismatch_info.get('traceback')
                    query_sql = mismatch_info.get('query_sql') or []

                    if note:
                        title = f'{indent}Query {i + 1} ({note}):'
                    else:
                        title = f'{indent}Query {i + 1}:'

                    error_lines += [
                        '',
                        title,
                    ] + _serialize_mismatched_attrs(mismatched_attrs,
                                                    indent=inner_indent)

                    if has_mismatched_subqueries:
                        assert subqueries is not None

                        if mismatched_attrs:
                            error_lines.append('')

                        error_lines += [
                            f'{inner_indent}Subqueries:',
                        ] + _serialize_results(
                            subqueries,
                            indent=f'{inner_indent}  ')

                    if query_sql:
                        error_lines += [
                            f'{indent}  SQL: {_sql}'
                            for _sql in query_sql
                        ]

                    if with_tracebacks and traceback:
                        traceback_str = \
                            ''.join(traceback[-traceback_size:])
                        error_lines.append(
                            f'{indent}Trace: {traceback_str}')

        return error_lines

    # Run the query comparisons.
    with compare_queries(_check_join_types=bool(check_join_types),
                         _check_subqueries=bool(check_subqueries),
                         queries=queries) as results:
        yield

    if results['has_mismatches']:
        raise AssertionError('\n'.join(_serialize_results(results)))
