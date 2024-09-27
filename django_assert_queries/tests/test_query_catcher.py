"""Unit tests for djblets.db.query_catcher.

Version Added:
    1.0
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, TYPE_CHECKING, Type

from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery, Sum
from django.db.models.sql.subqueries import AggregateQuery
from django.test.testcases import TestCase

from django_assert_queries.query_catcher import (ExecutedQueryType,
                                                 catch_queries)
from django_assert_queries.tests.models import (TestModel,
                                                RelTestModel)

if TYPE_CHECKING:
    from djblets.db.query_catcher import (CatchQueriesContext,
                                          ExecutedQueryInfo,
                                          ExecutedSubQueryInfo)


class CaptureQueriesTests(TestCase):
    """Unit tests for djblets.db.query_catcher.catch_queries."""

    tests_app = 'djblets.db.tests'

    maxDiff = None

    _extra_ws_re = re.compile(r'\s{2,}')

    def test_with_select(self) -> None:
        """Testing capture_queries with SELECT"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        with catch_queries() as ctx:
            objs = list(
                TestModel.objects
                .filter(Q(name__startswith='test') &
                        Q(flag=True))
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag",'
                ' "tests_testmodel"."user_id" '
                ' FROM "tests_testmodel"'
                ' WHERE'
                '  ("tests_testmodel"."name"'
                '   LIKE test% ESCAPE \'\\\''
                '   AND "tests_testmodel"."flag")',
            ],
            q=(
                Q(Q(name__startswith='test') &
                  Q(flag=True))
            ))

        self.assertEqual(len(objs), 2)
        self.assertEqual(objs[0].name, 'test1')
        self.assertEqual(objs[1].name, 'test2')

    def test_with_insert(self) -> None:
        """Testing capture_queries with SELECT"""
        with catch_queries() as ctx:
            TestModel.objects.bulk_create([
                TestModel(name='test1'),
                TestModel(name='test2'),
            ])

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            query_type=ExecutedQueryType.INSERT,
            sql=[
                'INSERT INTO "tests_testmodel"'
                ' ("name", "flag", "user_id")'
                ' VALUES (test1, True, None), (test2, True, None)',
            ])

    def test_with_delete(self) -> None:
        """Testing capture_queries with DELETE"""
        obj = TestModel.objects.create(name='test')
        obj_id = obj.pk

        with catch_queries() as ctx:
            obj.delete()

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            query_type=ExecutedQueryType.DELETE,
            sql=[
                'DELETE FROM "tests_testmodel"'
                ' WHERE "tests_testmodel"."id" IN (1)',
            ],
            q=Q(id__in=[obj_id]))

    def test_with_update(self) -> None:
        """Testing capture_queries with UPDATE"""
        obj = TestModel.objects.create(name='test')

        with catch_queries() as ctx:
            obj.flag = False
            obj.save(update_fields=('flag',))

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            query_type=ExecutedQueryType.UPDATE,
            sql=[
                'UPDATE "tests_testmodel"'
                ' SET "flag" = False'
                ' WHERE "tests_testmodel"."id" = 1',
            ],
            q=Q(pk=obj.pk))

    def test_with_multiple(self) -> None:
        """Testing capture_queries with multiple queries"""
        with catch_queries() as ctx:
            obj = TestModel.objects.create(name='test')
            obj.flag = False
            obj.save(update_fields=('flag',))

            list(TestModel.objects.all())

            obj.delete()

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 4)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            query_type=ExecutedQueryType.INSERT,
            sql=[
                'INSERT INTO "tests_testmodel"'
                ' ("name", "flag", "user_id")'
                ' VALUES (test, True, None)',
            ])

        self._check_query(
            executed_queries[1],
            ctx=ctx,
            query_type=ExecutedQueryType.UPDATE,
            sql=[
                'UPDATE "tests_testmodel"'
                ' SET "flag" = False'
                ' WHERE "tests_testmodel"."id" = 1',
            ],
            q=Q(pk=1))

        self._check_query(
            executed_queries[2],
            ctx=ctx,
            query_type=ExecutedQueryType.SELECT,
            sql=[
                'SELECT "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag",'
                ' "tests_testmodel"."user_id"'
                ' FROM "tests_testmodel"',
            ])

        self._check_query(
            executed_queries[3],
            ctx=ctx,
            query_type=ExecutedQueryType.DELETE,
            sql=[
                'DELETE FROM "tests_testmodel"'
                ' WHERE "tests_testmodel"."id" IN (1)',
            ],
            q=Q(id__in=[1]))

    def test_with_annotation_subquery(self) -> None:
        """Testing capture_queries with annotation and Subquery"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            objs = list(
                TestModel.objects
                .filter(Q(name__startswith='test'))
                .annotate(sub=Subquery(
                    RelTestModel.objects
                    .filter(test=OuterRef('pk'))
                    .values('pk')
                ))
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag", '
                ' "tests_testmodel"."user_id", '
                ' (SELECT U0."id"'
                '   FROM "tests_reltestmodel" U0'
                '   WHERE'
                '    U0."test_id" ='
                '    ("tests_testmodel"."id")) AS "sub"'
                ' FROM "tests_testmodel" '
                ' WHERE'
                '  "tests_testmodel"."name"'
                '   LIKE test% ESCAPE \'\\\''
            ],

            # NOTE: Subquery() cannot be compared through equality checks.
            can_compare_q=False)

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=Subquery,
            q=Q(test=OuterRef('pk')))

        # Check the fetched objects from the query.
        self.assertEqual(len(objs), 2)
        self.assertEqual(objs[0].name, 'test1')
        self.assertEqual(objs[1].name, 'test2')

    def test_with_annotation_exists(self) -> None:
        """Testing capture_queries with annotation and Exists"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            objs = list(
                TestModel.objects
                .filter(Q(name__startswith='test'))
                .annotate(sub=Exists(
                    RelTestModel.objects
                    .filter(test=OuterRef('pk'))
                ))
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag", '
                ' "tests_testmodel"."user_id", '
                ' EXISTS(SELECT 1 AS "a"'
                '  FROM "tests_reltestmodel" U0'
                '  WHERE'
                '   U0."test_id" ='
                '   ("tests_testmodel"."id")'
                '  LIMIT 1) AS "sub"'
                ' FROM "tests_testmodel" '
                ' WHERE'
                '  "tests_testmodel"."name"'
                '   LIKE test% ESCAPE \'\\\''
            ],

            # NOTE: Exists() cannot be compared through equality checks.
            can_compare_q=False)

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=Exists,
            q=Q(test=OuterRef('pk')))

        # Check the fetched objects from the query.
        self.assertEqual(len(objs), 2)
        self.assertEqual(objs[0].name, 'test1')
        self.assertEqual(objs[1].name, 'test2')

    def test_with_aggregate_subquery(self) -> None:
        """Testing capture_queries with aggregates and Subquery"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[1]),
            RelTestModel(test=test_models[1]),
        ])

        with catch_queries() as ctx:
            # This query is a particular amount of nonsense. Don't worry
            # about it.
            list(
                TestModel.objects
                .filter(
                    Q(name__startswith='test') &
                    Q(pk__gt=Subquery(
                        RelTestModel.objects
                        .filter(test=OuterRef('pk'))
                        .annotate(some_value=Sum('pk') + 1)
                        .values('some_value')
                    ))
                )
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag",'
                ' "tests_testmodel"."user_id"'
                ' FROM "tests_testmodel" '
                ' WHERE'
                '  ("tests_testmodel"."name"'
                '    LIKE test% ESCAPE \'\\\' AND'
                '   "tests_testmodel"."id" > '
                '    (SELECT (SUM(U0."id") + 1) AS "some_value"'
                '      FROM "tests_reltestmodel" U0'
                '      WHERE U0."test_id" ='
                '       ("tests_testmodel"."id")'
                '      GROUP BY U0."id", U0."test_id"))'
            ],

            # NOTE: Subquery() cannot be compared through equality checks.
            can_compare_q=False)

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=Subquery,
            q=Q(test=OuterRef('pk')))

    def test_with_filter_subquery_exists(self) -> None:
        """Testing capture_queries with filtering using Exists subqueries"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            objs = list(
                TestModel.objects
                .filter(
                    Q(name__startswith='test') &
                    Exists(
                        RelTestModel.objects
                        .filter(test=OuterRef('pk'))
                    )
                )
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag",'
                ' "tests_testmodel"."user_id"'
                ' FROM "tests_testmodel" '
                ' WHERE'
                '  ("tests_testmodel"."name"'
                '    LIKE test% ESCAPE \'\\\' AND'
                '   EXISTS(SELECT 1 AS "a"'
                '    FROM "tests_reltestmodel" U0'
                '    WHERE U0."test_id" ='
                '     ("tests_testmodel"."id")'
                '    LIMIT 1))',
            ],

            # NOTE: Exists() cannot be compared through equality checks.
            can_compare_q=False)

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=Exists,
            q=Q(test=OuterRef('pk')))

        # Check the fetched objects from the query.
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].name, 'test1')

    def test_with_filter_subquery_q(self) -> None:
        """Testing capture_queries with filtering using Q subqueries"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            objs = list(
                TestModel.objects
                .filter(
                    Q(name__startswith='test') &
                    Q(pk__in=(
                        RelTestModel.objects
                        .values_list('pk', flat=True)
                    ))
                )
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT'
                ' "tests_testmodel"."id",'
                ' "tests_testmodel"."name",'
                ' "tests_testmodel"."flag",'
                ' "tests_testmodel"."user_id"'
                ' FROM "tests_testmodel" '
                ' WHERE'
                '  ("tests_testmodel"."name"'
                '    LIKE test% ESCAPE \'\\\' AND'
                '   "tests_testmodel"."id" IN'
                '    (SELECT U0."id" FROM'
                '      "tests_reltestmodel" U0))',
            ],

            # NOTE: QuerySet() cannot be compared consistently through
            #       equality checks.
            can_compare_q=False)

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=QuerySet)

        # Check the fetched objects from the query.
        self.assertEqual(len(objs), 2)
        self.assertEqual(objs[0].name, 'test1')
        self.assertEqual(objs[1].name, 'test2')

    def test_with_distinct_count(self) -> None:
        """Testing capture_queries with distinct() and count()"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            count = (
                TestModel.objects
                .filter(name__startswith='test')
                .distinct()
                .count()
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT COUNT(*)'
                ' FROM'
                ' (SELECT DISTINCT'
                '   "tests_testmodel"."id" AS "col1",'
                '   "tests_testmodel"."name" AS "col2",'
                '   "tests_testmodel"."flag" AS "col3",'
                '   "tests_testmodel"."user_id" AS "col4"'
                '  FROM "tests_testmodel"'
                '  WHERE "tests_testmodel"."name"'
                '   LIKE test% ESCAPE \'\\\') subquery'
            ])

        # Check the subqueries.
        self._check_subquery(
            executed_queries[0]['subqueries'][0],
            ctx=ctx,
            subquery_class=AggregateQuery,
            q=Q(name__startswith='test'))

        # Check the fetched count.
        self.assertEqual(count, 2)

    def test_with_subqueries_complex(self) -> None:
        """Testing capture_queries with complex subqueries"""
        TestModel.objects.bulk_create([
            TestModel(name='test1'),
            TestModel(name='test2'),
        ])

        # Re-fetch to guarantee IDs.
        test_models = list(TestModel.objects.all())

        RelTestModel.objects.bulk_create([
            RelTestModel(test=test_models[0]),
            RelTestModel(test=test_models[0]),
        ])

        with catch_queries() as ctx:
            count = (
                TestModel.objects
                .filter(
                    Q(name__startswith='test') &
                    Exists(
                        RelTestModel.objects
                        .filter(
                            Q(test=OuterRef('pk')) &
                            ~Exists(
                                RelTestModel.objects
                                .filter(test=2)
                            )
                        )
                    )
                )
                .annotate(
                    sub1=Subquery(
                        RelTestModel.objects
                        .filter(
                            Q(test=OuterRef('pk')) &
                            Q(test__gt=Subquery(
                                RelTestModel.objects
                                .filter(test=OuterRef('pk'))
                                .annotate(some_value=Sum('pk') + 1)
                                .values('some_value')
                            ))
                        )
                        .values('pk')
                    ),
                )
                .distinct()
                .count()
            )

        executed_queries = ctx.executed_queries
        self.assertEqual(len(executed_queries), 1)

        self._check_query(
            executed_queries[0],
            ctx=ctx,
            num_subqueries=1,
            sql=[
                'SELECT COUNT(*) FROM'
                ' (SELECT DISTINCT'
                '  "tests_testmodel"."id" AS "col1",'
                '  "tests_testmodel"."name" AS "col2",'
                '  "tests_testmodel"."flag" AS "col3",'
                '  "tests_testmodel"."user_id" AS "col4",'
                '  (SELECT V0."id"'
                '    FROM "tests_reltestmodel" V0'
                '    WHERE (V0."test_id" ='
                '     ("tests_testmodel"."id") AND'
                '     V0."test_id" >'
                '     (SELECT (SUM(U0."id") + 1) AS "some_value"'
                '       FROM "tests_reltestmodel" U0'
                '       WHERE U0."test_id" = (V0."id")'
                '       GROUP BY U0."id", U0."test_id"))) AS "sub1"'
                '  FROM "tests_testmodel"'
                '  WHERE'
                '   ("tests_testmodel"."name"'
                '     LIKE test% ESCAPE \'\\\' AND'
                '    EXISTS(SELECT 1 AS "a"'
                '     FROM "tests_reltestmodel" V0'
                '     WHERE'
                '      (V0."test_id" ='
                '       ("tests_testmodel"."id")'
                '       AND NOT EXISTS(SELECT 1 AS "a"'
                '        FROM "tests_reltestmodel" U0'
                '        WHERE U0."test_id" = 2'
                '        LIMIT 1))'
                '     LIMIT 1))) subquery',
            ])

        # Check the distinct subquery.
        distinct_subquery = executed_queries[0]['subqueries'][0]

        self._check_subquery(distinct_subquery,
                             ctx=ctx,
                             subquery_class=AggregateQuery,
                             num_subqueries=2,
                             can_compare_q=False)

        subqueries = distinct_subquery['subqueries']

        # Check annotate subquery 1.
        self._check_subquery(subqueries[0],
                             ctx=ctx,
                             subquery_class=Subquery,
                             num_subqueries=1,
                             can_compare_q=False)  # Subquery() again.
        self._check_subquery(subqueries[0]['subqueries'][0],
                             ctx=ctx,
                             subquery_class=Subquery,
                             can_compare_q=False)  # Subquery() again.

        # Check filter subquery 1.
        self._check_subquery(subqueries[1],
                             ctx=ctx,
                             subquery_class=Exists,
                             num_subqueries=1,
                             can_compare_q=False)   # Exists() again.
        self._check_subquery(subqueries[1]['subqueries'][0],
                             subquery_class=Exists,
                             ctx=ctx,
                             q=Q(test=2))

        # Check the fetched count.
        self.assertEqual(count, 1)

    def _check_query(
        self,
        executed_query: ExecutedQueryInfo,
        *,
        ctx: CatchQueriesContext,
        sql: List[str],
        num_subqueries: int = 0,
        query_type: ExecutedQueryType = ExecutedQueryType.SELECT,
        q: Optional[Q] = None,
        can_compare_q: bool = True,
    ) -> None:
        """Check the recorded information on a query.

        This will perform stanadrd checks on query state, and compare the
        provided attributes.

        Args:
            executed_query (dict):
                Information on the query that was executed.

            ctx (dict):
                The context information from catching the queries.

            sql (list of str):
                The expected list of SQL statements for the query.

            num_subqueries (int, optional):
                The expected number of subqueries within this query.

            query_type (djblets.db.query_catcher.ExecutedQueryType, optional):
                The expected query type.

                This defaults to ``SELECT`` queries.

            q (django.db.models.Q, optional):
                The Q object for the query, if any.

                This can be omitted if passing ``can_compare_q=False`` or
                for queries that lack filtering.

            can_compare_q (bool, optional):
                Whether ``q`` can be compared.

                If ``False``, this will merely check for the presence of a
                recorded Q object.

        Raises:
            AssertionError:
                One or more checks failed.
        """
        self.assertEqual(executed_query['result_type'], 'query')
        self.assertEqual(executed_query['type'], query_type)
        self._assert_sql(executed_query['sql'], sql)
        self.assertEqual(len(executed_query['subqueries']), num_subqueries)
        self.assertGreaterEqual(len(executed_query['traceback']), 1)

        query = executed_query['query']
        self.assertIsNotNone(query)

        if q is None and can_compare_q:
            self.assertNotIn(query, ctx.queries_to_qs)
        else:
            self.assertIn(query, ctx.queries_to_qs)

            if can_compare_q:
                self.assertEqual(ctx.queries_to_qs[query], q)

    def _check_subquery(
        self,
        executed_subquery: ExecutedSubQueryInfo,
        *,
        ctx: CatchQueriesContext,
        subquery_class: Type[Any],
        num_subqueries: int = 0,
        q: Optional[Q] = None,
        can_compare_q: bool = True,
    ) -> None:
        """Check the recorded information on a subquery.

        This will perform stanadrd checks on subquery state, and compare the
        provided attributes.

        Args:
            executed_subquery (dict):
                Information on the subquery that was executed.

            ctx (dict):
                The context information from catching the queries.

            subquery_class (type):
                The expected class for the subquery.

            num_subqueries (int, optional):
                The expected number of subqueries within this subquery.

            q (django.db.models.Q, optional):
                The Q object for the subquery, if any.

                This can be omitted if passing ``can_compare_q=False`` or
                for queries that lack filtering.

            can_compare_q (bool, optional):
                Whether ``q`` can be compared.

                If ``False``, this will merely check for the presence of a
                recorded Q object.

        Raises:
            AssertionError:
                One or more checks failed.
        """
        self.assertEqual(executed_subquery['result_type'], 'subquery')
        self.assertEqual(executed_subquery['type'], ExecutedQueryType.SELECT)
        self.assertIs(executed_subquery['cls'], subquery_class)
        self.assertEqual(len(executed_subquery['subqueries']), num_subqueries)

        query = executed_subquery['query']
        self.assertIsNotNone(query)

        if q is None and can_compare_q:
            self.assertNotIn(query, ctx.queries_to_qs)
        else:
            self.assertIn(query, ctx.queries_to_qs)

            if can_compare_q:
                self.assertEqual(ctx.queries_to_qs[query], q)

    def _assert_sql(
        self,
        sql1: List[str],
        sql2: List[str],
    ) -> None:
        """Assert that two lists of SQL statements are equal.

        This will normalize the lists, removing any extra whitespace that may
        be added to help format the SQL for editing and display.

        Args:
            sql1 (list of str):
                The first list of SQL statements.

            sql1 (list of str):
                The second list of SQL statements.

        Raises:
            AssertionError:
                The SQL statements are not equal.
        """
        extra_ws_re = self._extra_ws_re
        self.assertEqual(
            '\n'.join(
                extra_ws_re.sub(' ', _line)
                for _line in sql1
            ),
            '\n'.join(
                extra_ws_re.sub(' ', _line)
                for _line in sql2
            ))
