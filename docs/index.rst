.. _django-assert-queries-docs:

==============================================================
django-assert-queries: Keep your Django queries from exploding
==============================================================

ORMs. Love 'em or hate 'em, they're often part of the job, and a core part of
writing Django_ webapps. They can make it easy to write queries that work
across databases, but the trade-off is your queries might explode in number
and in complexity.

Who hasn't made this mistake?

.. code-block:: python

   for book in Book.objects.all():
       print(f'Author: {book.author.name}')

Spot the error? We're fetching the associated author once for every book. For
100 books, that's 101 queries!

And that's just a really basic query.

These mistakes happen all the time, and they're not always easy to catch in
unit tests.

That's what the clear-but-unimaginatively-named django-assert-queries_ is here
to solve. With proper use, this can save companies from costly mistakes.
`We've <https://www.reviewboard.org>`_ found it to be an invaluable tool in
our arsenal.

We'll explore how it does that, but first, let's get things installed.


.. _Django: https://djangoproject.com
.. _django-assert-queries: https://pypi.org/project/django-assert-queries


Installation
============

.. code-block:: console

   $ pip install django-assert-queries


``django-assert-queries`` follows `semantic versioning`_, meaning no surprises
when you upgrade.


.. _semantic versioning: https://semver.org/


Let's see it in action
======================

We're going to catch the bug above.

.. code-block:: python

   from django_assert_queries import assert_queries


   def test():
       expected_queries = [
           {
               'model': Book,
           },
       ]

       with assert_queries(expected_queries):
           for book in Book.objects.all():
               print(f'Book {book.name} by {book.author.name}')

When we run that, we get:

.. code-block:: text

   E AssertionError: Expected 1 queries, but got 101
   E
   E 100 queries failed to meet expectations.
   E
   E Query 2:
   E   model: <class 'django_assert_queries.tests.models.Author'> != None
   E   tables: {'tests_author'} != {}
   E   where: Q(id=1) != Q()
   E   SQL: SELECT "tests_author"."id", "tests_author"."name" FROM "tests_author" WHERE "tests_author"."id" = 1 LIMIT 21
   E
   E Query 3:
   E   model: <class 'django_assert_queries.tests.models.Author'> != None
   E   tables: {'tests_author'} != {}
   E   where: Q(id=2) != Q()
   E   SQL: SELECT "tests_author"."id", "tests_author"."name" FROM "tests_author" WHERE "tests_author"."id" = 2 LIMIT 21
   E
   E Query 4:
   E   model: <class 'django_assert_queries.tests.models.Author'> != None
   E   tables: {'tests_author'} != {}
   E   where: Q(id=3) != Q()
   E   SQL: SELECT "tests_author"."id", "tests_author"."name" FROM "tests_author" WHERE "tests_author"."id" = 3 LIMIT 21
   E

   [...]

That problem just became a lot more clear. Let's fix this.

.. code-block:: python

   from django_assert_queries import assert_queries


   def test():
       # We'll select-related the authors.
       expected_queries = [
           {
               'model': Book,
               'select_related' ('author',),
           },
       ]

       with assert_queries(expected_queries):
           for book in Book.objects.select_related('author'):
               print(f'Book {book.name} by {book.author.name}')

These can be a lot more thorough:

.. code-block:: python

   def test_complex_query():
       expected_queries = [
           # Initial query for the books.
           {
               'model': Book,
               'limit': 2,
               'only_fields': {'author', 'name'},
               'select_related': {'author'},
           },

           # Initial query for the authors.
           {
               'model': Author,
               'annotations': {
                   'book_count': Count('books'),
               },
               'group_by': True,
               'num_joins': 1,
               'tables': {
                   'tests_author',
                   'tests_book',
               },
           },

           # The prefetch-related for all the authors' books.
           {
               'model': Book,
               'where': Q(author__in=list(Author.objects.all())),
           },
       ]

       books_queryset = (
           Book.objects
           .filter(name__in=['Book 1', 'Book 9'])
           .only('author', 'name')
           .select_related('author')
           [:2]
       )

       authors_queryset = (
           Author.objects
           .annotate(book_count=Count('books'))
           .prefetch_related('books')
       )

       with assert_queries(expected_queries):
           for book in books_queryset:
               print(f'Book {book.name} by {book.author.name}')

           for author in authors_queryset:
               print(f'Author {author.name} published {author.book_count} books:')

               for book in author.books.all():
                   print(f'    {book.name}')

Here we've got filtering, annotations, field limiting, filtering, joins,
and prefetch-related.

These cover just about everything that Django queries can do, and when used
correctly your unit tests can account for just about every query your
application makes.


Crafting expected queries
=========================

Your ``expected_queries`` list are dictionaries, documented by
:py:class:`~django_assert_queries.query_comparator.ExpectedQuery`.

This is then passed to
:py:func:`~django_assert_queries.testing.assert_queries`.

If your list fails to match the executed queries at all, you'll get detailed
information on what failed to match. This means it's easy to start with an
empty list and see what the final list should be. That's also a great time to
inspect your queries and optimize them!

Need something more involved? You can use
:py:func:`~django_assert_queries.query_catcher.catch_queries` to perform your
own query-catching and inspection! Unit test comparisons are just one usage.


Brought to you by Beanbag
=========================

At Beanbag_, we're all about building better software development tools.

Our flagship product is `Review Board`_, one of the first-ever code review
products on the market, and originator for most now-standard code review
features.

We also build these lovely Python packages:

* `beanbag-docutils <https://github.com/beanbaginc/beanbag-docutils/>`_ -
  Multi-DPI images, enhanced syntax, and many more add-ons for Sphinx
  documentation writers.

* `Djblets <https://github.com/djblets/djblets/>`_ -
  Our pack of Django utilities for datagrids, API, privacy, extensions, and
  more. Used by Review Board.

* `Grumble <https://github.com/beanbaginc/grumble/>`_ -
  For Python print debuggers drowning in print statements.

* `Housekeeping <https://github.com/beanbaginc/housekeeping/>`_ -
  Deprecation management for Python codebases of all sizes.

* `kgb <https://github.com/beanbaginc/kgb/>`_ -
  Function spies for Python unit tests, a major upgrade from mocks.

* `registries <https://github.com/beanbaginc/registries/>`_ -
  Registration management and lookup of objects, for extensible Python
  applications.

* `typelets <https://github.com/beanbaginc/typelets/>`_ -
  Python typing additions, including comprehensive JSON and JSON-compatible
  data structures, symbols, and Django add-ons.

You can see more on `github.com/beanbaginc <https://github.com/beanbaginc>`_
and `github.com/reviewboard <https://github.com/reviewboard>`_.


.. _Beanbag: https://www.beanbaginc.com
.. _Review Board: https://www.reviewboard.org


Documentation
=============

.. toctree::
   :maxdepth: 3

   coderef/index
   releasenotes/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
