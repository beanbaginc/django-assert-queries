"""Utilities for capturing and inspecting database queries.

Version Added:
    1.0
"""

from __future__ import annotations

import inspect
import os
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any, Dict, Iterator, List, Mapping, Optional, Sequence, Type, Union
)

import kgb
from django.core.exceptions import EmptyResultSet
from django.db.models import Model, Q, QuerySet, Subquery
from django.db.models.deletion import Collector as DeleteCollector
from django.db.models.expressions import ExpressionWrapper
from django.db.models.signals import pre_delete
from django.db.models.sql.compiler import (SQLCompiler,
                                           SQLDeleteCompiler,
                                           SQLInsertCompiler,
                                           SQLUpdateCompiler)
from django.db.models.sql.query import Query as SQLQuery
from django.db.models.sql.subqueries import AggregateQuery
from django.utils.tree import Node
from typing_extensions import Literal, NotRequired, TypedDict


# Template debugging now uses Django's own infrastructure via stack inspection
# No global state needed - we inspect the call stack during query execution


class TemplateInfo(TypedDict):
    """Information about the template where a query was executed.

    Version Added:
        2.1
    """

    #: The name of the template file.
    name: str

    #: The origin/path of the template.
    origin: str

    #: The line number in the template (if available).
    line_number: NotRequired[int]

    #: The line content where the query occurred (if available).
    line_content: NotRequired[str]


class ExecutedQueryType(str, Enum):
    """A type of executed query that can be inspected.

    Version Added:
        1.0
    """

    #: A DELETE query.
    DELETE = 'DELETE'

    #: An INSERT query.
    INSERT = 'INSERT'

    #: A SELECT query.
    SELECT = 'SELECT'

    #: An UPDATE query.
    UPDATE = 'UPDATE'


class ExecutedQueryInfo(TypedDict):
    """Information on an executed query.

    This contains information seen at execution time that can be used for
    inspection of the queries.

    This should not be populated by consumers, only by this library.

    Version Added:
        1.0
    """

    #: The query that was executed.
    query: SQLQuery

    #: The type of result information.
    #:
    #: This is used to distinguish between query and subquery information.
    result_type: Literal['query']

    #: The list of lines of SQL that was executed.
    sql: List[str]

    #: Any subqueries within this query, in the orders found.
    subqueries: List[ExecutedSubQueryInfo]

    #: The lines of traceback showing where the query was executed.
    traceback: List[str]

    #: Information about the template where the query was executed (if any).
    template_info: NotRequired[TemplateInfo]

    #: The type of executed query.
    type: ExecutedQueryType


class ExecutedSubQueryInfo(TypedDict):
    """Information on a subquery within an executed query.

    This contains information seen at execution time that can be used for
    inspection of the queries.

    This should not be populated by consumers, only by this library.

    Version Added:
        1.0
    """

    #: The type of class managing the subquery.
    cls: Type[Union[AggregateQuery, QuerySet, Subquery]]

    #: The instance of the subquery class.
    instance: Union[AggregateQuery, QuerySet, Subquery]

    #: The query that was executed.
    query: SQLQuery

    #: The type of result information.
    #:
    #: This is used to distinguish between query and subquery information.
    result_type: Literal['subquery']

    #: Any subqueries within this query, in the orders found.
    subqueries: List[ExecutedSubQueryInfo]

    #: The type of executed query.
    type: Literal[ExecutedQueryType.SELECT]


@dataclass
class CatchQueriesContext:
    """Context for captured query information.

    This is provided and populated when using :py:func:`catch_queries`.

    This should not be populated by consumers, only by this library.

    Version Added:
        1.0
    """

    #: A mapping of deleted instance IDs to their original primary keys.
    #:
    #: Version Added:
    #:     2.0
    deleted_objects: Mapping[int, Any]

    #: Information on the queries that were executed.
    executed_queries: Sequence[ExecutedQueryInfo]

    #: A mapping of SQL queries to their Q expressions.
    queries_to_qs: Dict[SQLQuery, Q]


def _get_template_info_manual_fallback(template, node) -> TemplateInfo:
    """Manual fallback when Django's get_exception_info can't work."""
    template_info = {
        'name': template.name or 'unknown',
        'origin': template.origin.name if template.origin else 'unknown'
    }

    # Try to find line number by parsing template source manually
    if (hasattr(template, 'source') and hasattr(node.token, 'contents') and
            template.source and node.token.contents):
        token_content = node.token.contents.strip()
        for i, line in enumerate(template.source.split('\n'), 1):
            if token_content in line:
                template_info.update({
                    'line_number': i,
                    'line_content': line.strip()
                })
                break

    return template_info


def _get_line_info_from_node_origin(node) -> dict:
    """Extract line information from the node's origin template."""
    if not (hasattr(node, 'origin') and node.origin and
            hasattr(node.token, 'position') and node.token.position):
        return {}

    origin_path = (node.origin.name if hasattr(node.origin, 'name')
                   else str(node.origin))
    if not os.path.isfile(origin_path):
        return {}

    with open(origin_path, 'r', encoding='utf-8') as f:
        source_lines = f.readlines()

    # Extract line number from token position
    line_number = (node.token.position[0]
                   if isinstance(node.token.position, tuple)
                   else int(node.token.position))

    if 1 <= line_number <= len(source_lines):
        return {
            'line_number': line_number,
            'line_content': source_lines[line_number - 1].strip()
        }

    # Fallback: search for token content in source
    if hasattr(node.token, 'contents') and node.token.contents:
        token_content = node.token.contents.strip()
        for i, line in enumerate(source_lines, 1):
            if token_content in line:
                return {
                    'line_number': i,
                    'line_content': line.strip()
                }

    return {}


@contextmanager
def catch_queries(
    *,
    _check_subqueries: bool = True,
) -> Iterator[CatchQueriesContext]:
    """Catch queries and provide information for further inspection.

    Any database queries executed during this context will be captured and
    provided in the context. For each query, this will capture:

    1. The type of query.
    2. The :py:class:`SQL Query objects <django.db.models.query.sql.Query>`
    3. The generated SQL statements
    4. Tracebacks showing where the SQL was executed.

    It will also provide a mapping of the Query objects to their Q
    expressions.

    Version Added:
        1.0

    Args:
        _check_subqueries (bool, optional):
            Whether to check subqueries.

            This is internal for compatibility with the old behavior for
            :py:meth:`~django_assert_queries.testing.assert_queries>` and will
            be removed in a future release without a deprecation period.

    Context:
        CatchQueriesContext:
        The context populated with query information.
    """
    spy_agency = kgb.SpyAgency()

    deleted_objects: dict[int, Any] = {}
    executed_queries: List[ExecutedQueryInfo] = []
    queries_to_qs: Dict[SQLQuery, Q] = {}

    def _get_template_info_for_query(_self) -> Optional[List[TemplateInfo]]:
        """Extract template debugging info showing the entire inheritance
        chain."""
        template_chain = []
        seen_templates = set()

        for frame_info in inspect.stack():
            frame = frame_info.frame

            # Quick validation of frame locals
            if not all(key in frame.f_locals
                       for key in ('context', 'self')):
                continue

            context = frame.f_locals['context']
            node = frame.f_locals['self']

            # Validate template context
            if not (hasattr(context, 'render_context') and
                    hasattr(node, 'token') and hasattr(node, 'render') and
                    node.token is not None):
                continue

            template = context.render_context.template
            if not hasattr(template, 'get_exception_info'):
                continue

            # Extract template info for this frame
            if not (hasattr(node.token, 'position') and node.token.position):
                template_info = _get_template_info_manual_fallback(
                    template, node)
            elif hasattr(node, 'origin') and node.origin:
                # Use node's origin (inheritance scenario)
                node_origin_name = (node.origin.name
                                    if hasattr(node.origin, 'name')
                                    else str(node.origin))
                template_info = {
                    'name': os.path.basename(node_origin_name),
                    'origin': node_origin_name
                }
                template_info.update(_get_line_info_from_node_origin(node))
            else:
                # Use Django's debugging
                debug_info = template.get_exception_info(
                    Exception("Template debugging probe"), node.token)
                template_info = {
                    'name': template.name or 'unknown',
                    'origin': (template.origin.name if template.origin
                               else 'unknown')
                }

                if debug_info.get('line', 0) > 0:
                    template_info['line_number'] = debug_info['line']
                if debug_info.get('during', '').strip():
                    template_info['line_content'] = (
                        debug_info['during'].strip())

            # Add to chain if we have valid info and haven't seen this
            # template+line combo
            if template_info:
                template_key = (template_info['origin'],
                                template_info.get('line_number', 0))
                if template_key not in seen_templates:
                    seen_templates.add(template_key)
                    template_chain.append(template_info)

        return list(reversed(template_chain)) if template_chain else None

    def _add_query_info(query, query_type, subqueries=None):
        """Helper to add query info with template debugging."""
        sql = _serialize_caught_sql(query)
        if not sql:
            return

        query_info = {
            'query': query,
            'result_type': 'query',
            'sql': sql,
            'subqueries': subqueries or [],
            'traceback': traceback.format_stack(),
            'type': query_type,
        }

        # Add template debugging information if available
        template_chain = _get_template_info_for_query(None)
        if template_chain:
            query_info['template_info'] = template_chain

        executed_queries.append(query_info)

    def _call_original_execute_sql(compiler_class, _self, *args, **kwargs):
        """Helper to call original execute_sql method, handling library
        conflicts."""
        execute_sql_method = getattr(compiler_class, 'execute_sql')

        if hasattr(execute_sql_method, 'call_original'):
            return execute_sql_method.call_original(_self, *args, **kwargs)
        else:
            # Fallback for libraries like cachalot that also patch execute_sql
            method = execute_sql_method
            while hasattr(method, '__wrapped__'):
                method = method.__wrapped__
            return method(_self, *args, **kwargs)

    # Track Query objects any time a compiler is executing SQL.
    @spy_agency.spy_for(SQLCompiler.execute_sql,
                        owner=SQLCompiler)
    def _sql_compiler_execute_sql(
        _self: SQLCompiler,
        *args,
        **kwargs,
    ) -> Any:
        if isinstance(_self, SQLDeleteCompiler):
            query_type = ExecutedQueryType.DELETE
        elif isinstance(_self, SQLUpdateCompiler):
            query_type = ExecutedQueryType.UPDATE
        else:
            query_type = ExecutedQueryType.SELECT

        query = _self.query
        subqueries: List[ExecutedSubQueryInfo] = []

        if _check_subqueries:
            _scan_subqueries(node=query,
                             result=subqueries,
                             queries_to_qs=queries_to_qs,
                             _check_subqueries=_check_subqueries)

        _add_query_info(query, query_type, subqueries)
        return _call_original_execute_sql(
            SQLCompiler, _self, *args, **kwargs)

    @spy_agency.spy_for(SQLInsertCompiler.execute_sql,
                        owner=SQLInsertCompiler)
    def _sql_insert_compiler_execute_sql(
        _self: SQLInsertCompiler,
        *args,
        **kwargs,
    ) -> Any:
        _add_query_info(_self.query, ExecutedQueryType.INSERT)
        return _call_original_execute_sql(
            SQLInsertCompiler, _self, *args, **kwargs)

    # Build and track Q() objects any time they're added to a Query.
    @spy_agency.spy_for(SQLQuery.add_q, owner=SQLQuery)
    def _query_add_q(
        _self: SQLQuery,
        q_object: Q,
        *args,
        **kwargs
    ) -> Any:
        try:
            queries_to_qs[_self] &= q_object
        except KeyError:
            queries_to_qs[_self] = q_object

        return SQLQuery.add_q.call_original(_self, q_object, *args, **kwargs)

    # Copy Q() objects any time a Query is cloned.
    @spy_agency.spy_for(SQLQuery.clone, owner=SQLQuery)
    def _query_clone(
        _self: SQLQuery,
        *args,
        **kwargs,
    ) -> Any:
        result = SQLQuery.clone.call_original(_self, *args, **kwargs)

        try:
            queries_to_qs[result] = queries_to_qs[_self]
        except KeyError:
            pass

        return result

    # Template debugging now uses Django's stack inspection approach
    # No spies needed - we inspect the call stack during query execution

    # Listen for any deletions and record their primary keys before they're
    # unset.
    @spy_agency.spy_for(DeleteCollector.collect, owner=DeleteCollector)
    def _delete_collector_collect(
        _self: DeleteCollector,
        objs: Sequence[Model],
        *args,
        **kwargs,
    ) -> None:
        DeleteCollector.collect.call_original(_self, objs, *args, **kwargs)

        for obj in objs:
            deleted_objects[id(obj)] = obj.pk

    # Set up an explicit pre_delete signal. During deletion, Django
    # attempts to determine if it can fast-delete (which can be done if,
    # amongst other things, signals don't need to be emitted for each
    # object).
    #
    # This can lead to inconsistencies in test runs, if registration of
    # pre_delete or post_delete signals is conditional on that run. We
    # want to ensure a stable query count and information for DELETEs,
    # so we deny fast-deletion by setting up a model-global signal handler
    # during capture of queries.
    def _on_pre_delete(**kwargs):
        pass

    pre_delete.connect(_on_pre_delete)

    # Let the caller execute SQL. Results will be stored in the context.
    try:
        yield CatchQueriesContext(deleted_objects=deleted_objects,
                                  executed_queries=executed_queries,
                                  queries_to_qs=queries_to_qs)
    finally:
        # We no longer need to track anything in the compiler of Query.
        spy_agency.unspy_all()
        pre_delete.disconnect(_on_pre_delete)


def _scan_subqueries(
    *,
    node: Union[Node, SQLQuery],
    result: List[ExecutedSubQueryInfo],
    queries_to_qs: Dict[SQLQuery, Q],
    _check_subqueries: bool,
) -> None:
    """Scan for subqueries in a level of a query tree.

    This recursively walks a query tree, looking for any subqueries and
    recording them in the list within the nearest top-level query or subquery.

    Version Added:
        1.0

    Args:
        node (django.utils.tree.Node or django.db.models.sql.Query):
            The level of the tree to process.

        result (list of dict):
            The list of queries to append any new subquery information to.

        queries_to_qs (dict):
            A dictionary containing recording mappings of queries to Q objects.
    """
    child_subqueries: List[ExecutedSubQueryInfo]
    children: List[Any] = []

    if isinstance(node, SQLQuery):
        if isinstance(node, AggregateQuery):
            inner_query = node.inner_query  # type: ignore
            assert isinstance(inner_query, SQLQuery)

            child_subqueries = []
            _scan_subqueries(node=inner_query,
                             result=child_subqueries,
                             queries_to_qs=queries_to_qs,
                             _check_subqueries=_check_subqueries)

            result.append({
                'cls': type(node),
                'instance': node,
                'query': inner_query,
                'result_type': 'subquery',
                'subqueries': child_subqueries,
                'type': ExecutedQueryType.SELECT,
            })

            # We won't have any children to process, so we'll effectively
            # bail at this point.
        else:
            # Process the annotations.
            children = list(node.annotations.values())

            # Continue on by processing the Q filters within it.
            try:
                children += queries_to_qs[node].children
            except KeyError:
                # There are no Q objects for this query. Nothing to scan
                # through.
                pass
    else:
        children = node.children

    for child in children:
        if child:
            if isinstance(child, tuple):
                child = child[1]

            if isinstance(child, Node):
                _scan_subqueries(node=child,
                                 result=result,
                                 queries_to_qs=queries_to_qs,
                                 _check_subqueries=_check_subqueries)
            elif _check_subqueries:
                if isinstance(child, ExpressionWrapper):
                    # NOTE: As of November 28, 2023, django-stubs doesn't have
                    #       type hints for `ExpressionWrapper.expression`.
                    child = child.expression  # type: ignore

                if isinstance(child, (QuerySet, Subquery)):
                    child_subqueries = []
                    _scan_subqueries(node=child.query,
                                     result=child_subqueries,
                                     queries_to_qs=queries_to_qs,
                                     _check_subqueries=_check_subqueries)

                    result.append({
                        'cls': type(child),
                        'instance': child,
                        'query': child.query,
                        'result_type': 'subquery',
                        'subqueries': child_subqueries,
                        'type': ExecutedQueryType.SELECT,
                    })


def _serialize_caught_sql(
    query: SQLQuery,
) -> List[str]:
    """Serialize a caught SQL Query to SQL.

    Version Added:
        1.0

    Args:
        query (django.db.models.query.sql.Query):
            The SQL query to serialize.

    Returns:
        list of str:
        The list of SQL statements executed.
    """
    sql: List[str]

    # Grab the SQL. from the query. This may fail, and if it does, it
    # represents a query that we've caught that isn't actually going to be
    # executed (likely a component of another).
    try:
        try:
            sql = [str(query)]
        except ValueError:
            # When doing an INSERT OR IGNORE (SQLite), the SQL can be a list
            # rather than a string. Query.__str__ doesn't know how to handle
            # this, and will crash. We'll deal with it ourselves.
            sql_statements = query.sql_with_params()
            assert isinstance(sql_statements, list)

            sql = [
                _sql % _sql_params
                for _sql, _sql_params in sql_statements
            ]
    except EmptyResultSet:
        # This will be skipped.
        sql = []

    return sql
