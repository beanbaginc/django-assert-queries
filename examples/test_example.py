from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django_assert_queries import assert_queries
from django_assert_queries.tests.models import Author, Book


def populate_db():
    authors = Author.objects.bulk_create(
        Author(name=f'Author {i}')
        for i in range(10)
    )

    Book.objects.bulk_create(
        Book(author=authors[i],
             name=f'Book {i}')
        for i in range(10)
    )


def test_simple_query():
    populate_db()

    expected_queries = [
        {
            'model': Book,
            'select_related': {'author'},
        },
    ]

    with assert_queries(expected_queries):
        for book in Book.objects.select_related('author'):
            print(f'Book {book.name} by {book.author.name}')


def test_complex_query():
    populate_db()

    expected_queries = [
        {
            'model': Book,
            'limit': 2,
            'only_fields': {'author', 'name'},
            'select_related': {'author'},
        },
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
