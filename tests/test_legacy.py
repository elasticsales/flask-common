# -*- coding: utf-8 -*-

import unittest

from flask import Flask
from mongoengine.fields import (ReferenceField, SafeReferenceListField,
                                IntField)

from flask_mongoengine import MongoEngine
from flask_common.declenum import DeclEnum
from flask_common.mongo import iter_no_cache
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


class Book(db.Document):
    pass


class Author(db.Document):
    books = SafeReferenceListField(ReferenceField(Book))


class SafeReferenceListFieldTestCase(unittest.TestCase):
    def test_safe_reference_list_field(self):
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
        self.assertEqual(
            apply_recursively(None, lambda n: n + 1),
            None
        )

    def test_list(self):
        self.assertEqual(
            apply_recursively([1, 2, 3], lambda n: n + 1),
            [2, 3, 4]
        )

    def test_nested_tuple(self):
        self.assertEqual(
            apply_recursively([(1, 2), (3, 4)], lambda n: n + 1),
            [[2, 3], [4, 5]]
        )

    def test_nested_dict(self):
        self.assertEqual(
            apply_recursively([{'a': 1, 'b': [2, 3], 'c': {'d': 4, 'e': None}}, 5], lambda n: n + 1),
            [{'a': 2, 'b': [3, 4], 'c': {'d': 5, 'e': None}}, 6]
        )


class SlugifyTestCase(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify('  Foo  ???BAR\t\n\r'), 'foo_bar')
        self.assertEqual(slugify(u'äąé öóü', '-'), 'aae-oou')


class UtilsTestCase(unittest.TestCase):

    def test_uniqify(self):
        self.assertEqual(
            uniqify([1, 2, 3, 1, 'a', None, 'a', 'b']),
            [1, 2, 3, 'a', None, 'b']
        )
        self.assertEqual(
            uniqify([{'a': 1}, {'a': 2}, {'a': 1}]),
            [{'a': 1}, {'a': 2}]
        )
        self.assertEqual(
            uniqify([{'a': 1, 'b': 3}, {'a': 2, 'b': 2}, {'a': 1, 'b': 1}], key=lambda i: i['a']),
            [{'a': 1, 'b': 3}, {'a': 2, 'b': 2}]
        )


class DeclEnumTestCase(unittest.TestCase):
    def test_enum(self):
        class TestEnum(DeclEnum):
            alpha = 'alpha_value', 'Alpha Description'
            beta = 'beta_value', 'Beta Description'
        assert TestEnum.alpha != TestEnum.beta
        assert TestEnum.alpha.value == 'alpha_value'
        assert TestEnum.alpha.description == 'Alpha Description'
        assert TestEnum.from_string('alpha_value') == TestEnum.alpha

        db_type = TestEnum.db_type()
        self.assertEqual(set(db_type.enum.values()), set(['alpha_value', 'beta_value']))


class IterNoCacheTestCase(unittest.TestCase):
    def test_no_cache(self):
        import weakref

        def is_cached(qs):
            iterator = iter(qs)
            d = next(iterator)
            self.assertEqual(d.i, 0)
            w = weakref.ref(d)
            d = next(iterator)
            self.assertEqual(d.i, 1)
            # - If the weak reference is still valid at this point, then
            #   iterator or queryset is holding onto the first object
            # - Hold reference to qs until very end just in case
            #   Python gets smart enough to destroy it
            return w() is not None and qs is not None

        class D(db.Document):
            i = IntField()
            pass

        D.drop_collection()

        for i in range(10):
            D(i=i).save()

        self.assertTrue(is_cached(D.objects.all()))
        self.assertFalse(is_cached(iter_no_cache(D.objects.all())))

        # check for correct exit behavior
        self.assertEqual({d.i for d in iter_no_cache(D.objects.all())}, set(range(10)))
        self.assertEqual({d.i for d in iter_no_cache(D.objects.all().batch_size(5))}, set(range(10)))
        self.assertEqual({d.i for d in iter_no_cache(D.objects.order_by('i').limit(1))}, set(range(1)))


if __name__ == '__main__':
    unittest.main()
