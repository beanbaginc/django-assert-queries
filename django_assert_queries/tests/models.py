"""Models for unit tests.

Version Added:
    1.0
"""

from django.contrib.auth.models import User
from django.db import models


class TestModel(models.Model):
    name = models.CharField(max_length=10)
    flag = models.BooleanField(default=True)
    user = models.OneToOneField(
        User,
        null=True,
        on_delete=models.SET_NULL)


class RelTestModel(models.Model):
    # Set up a relation, but don't do anything if the test model deletes.
    # We don't want this interfering with our query tests.
    test = models.ForeignKey(
        TestModel,
        on_delete=models.DO_NOTHING)


class Author(models.Model):
    name = models.CharField(max_length=128)


class Book(models.Model):
    name = models.CharField(max_length=128)
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name='books')
