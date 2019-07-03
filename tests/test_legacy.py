# -*- coding: utf-8 -*-

import unittest

from flask import Flask
from mongoengine import Document, ReferenceField, SafeReferenceListField

from flask_mongoengine import MongoEngine
from flask_common.utils import apply_recursively, slugify, uniqify


app = Flask(__name__)

app.config.update(
    DEBUG=True,
    TESTING=True,
    MONGODB_HOST='localhost',
    MONGODB_PORT='27017',
    MONGODB_DB='common_example_app',
)

db = MongoEngine(app)


class SafeReferenceListFieldTestCase(unittest.TestCase):
    # TODO this is a mongoengine field and it should be tested in that package,
    # not here.

    def test_safe_reference_list_field(self):
        class Book(Document):
            pass

        class Author(Document):
            books = SafeReferenceListField(ReferenceField(Book))

        Author.drop_collection()
        Book.drop_collection()

        b1 = Book.objects.create()
        b2 = Book.objects.create()

        a = Author.objects.create(books=[b1, b2])
        a.reload()
        self.assertEqual(a.books, [b1, b2])

        b1.delete()
        a.reload()
        self.assertEqual(a.books, [b2])

        b3 = Book.objects.create()
        a.books.append(b3)
        a.save()
        a.reload()
        self.assertEqual(a.books, [b2, b3])

        b2.delete()
        b3.delete()
        a.reload()
        self.assertEqual(a.books, [])


class ApplyRecursivelyTestCase(unittest.TestCase):
    def test_none(self):
        self.assertEqual(apply_recursively(None, lambda n: n + 1), None)

    def test_list(self):
        self.assertEqual(
            apply_recursively([1, 2, 3], lambda n: n + 1), [2, 3, 4]
        )

    def test_nested_tuple(self):
        self.assertEqual(
            apply_recursively([(1, 2), (3, 4)], lambda n: n + 1),
            [[2, 3], [4, 5]],
        )

    def test_nested_dict(self):
        self.assertEqual(
            apply_recursively(
                [{'a': 1, 'b': [2, 3], 'c': {'d': 4, 'e': None}}, 5],
                lambda n: n + 1,
            ),
            [{'a': 2, 'b': [3, 4], 'c': {'d': 5, 'e': None}}, 6],
        )


class SlugifyTestCase(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify('  Foo  ???BAR\t\n\r'), 'foo_bar')
        self.assertEqual(slugify(u'äąé öóü', '-'), 'aae-oou')


class UtilsTestCase(unittest.TestCase):
    def test_uniqify(self):
        self.assertEqual(
            uniqify([1, 2, 3, 1, 'a', None, 'a', 'b']),
            [1, 2, 3, 'a', None, 'b'],
        )
        self.assertEqual(
            uniqify([{'a': 1}, {'a': 2}, {'a': 1}]), [{'a': 1}, {'a': 2}]
        )
        self.assertEqual(
            uniqify(
                [{'a': 1, 'b': 3}, {'a': 2, 'b': 2}, {'a': 1, 'b': 1}],
                key=lambda i: i['a'],
            ),
            [{'a': 1, 'b': 3}, {'a': 2, 'b': 2}],
        )


if __name__ == '__main__':
    unittest.main()
