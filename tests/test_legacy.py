# -*- coding: utf-8 -*-

import datetime
import random
import string
import time
import unittest

from dateutil.tz import tzutc
from flask import Flask
from mongoengine import connection, Document
from mongoengine.errors import DoesNotExist
from mongoengine.fields import (ReferenceField, SafeReferenceField,
                                SafeReferenceListField, StringField,
                                IntField)
import pytz
from werkzeug.datastructures import MultiDict
from wtforms import Form

from flask_mongoengine import MongoEngine, ValidationError
from flask_common.crypto import aes_generate_key
from flask_common.declenum import DeclEnum
from flask_common.fields import (PhoneField, TimezoneField, TrimmedStringField,
                                EncryptedStringField, LowerStringField,
                                LowerEmailField)
from flask_common.formfields import BetterDateTimeField
from flask_common.mongo import (DocumentBase, RandomPKDocument,
                                SoftDeleteDocument, custom_query_counter,
                                fetch_related, iter_no_cache)
from flask_common.utils import apply_recursively, slugify, uniqify



app = Flask(__name__)

app.config.update(
    DEBUG = True,
    TESTING = True,
    MONGODB_HOST = 'localhost',
    MONGODB_PORT = '27017',
    MONGODB_DB = 'common_example_app',
)

db = MongoEngine(app)


class Phone(db.Document):
    phone = PhoneField()
    strict_phone = PhoneField(strict=True)


class Location(db.Document):
    timezone = TimezoneField()


class TrimmedFields(db.Document):
    name = TrimmedStringField(required=True)
    comment = TrimmedStringField()


class Secret(db.Document):
    password = EncryptedStringField(aes_generate_key())


class Book(db.Document):
    pass


class Author(db.Document):
    books = SafeReferenceListField(ReferenceField(Book))


class FieldTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        Phone.drop_collection()
        Location.drop_collection()
        TrimmedFields.drop_collection()

    def test_format_number(self):
        phone = Phone(phone='14151231234')
        assert phone.phone == '14151231234'

        phone.phone = 'notaphone'
        assert phone.phone == 'notaphone'
        self.assertRaises(ValidationError, phone.validate)
        self.assertRaises(ValidationError, phone.save)

        phone.phone = '+1 (650) 618 - 1234 x 768'
        assert phone.phone == '+16506181234x768'
        phone.validate()

        phone.save()

        assert phone.id == Phone.objects.get(phone='+16506181234x768').id
        assert phone.id == Phone.objects.get(phone='+1 650-618-1234 ext 768').id

    def test_strict_format_number(self):
        phone = Phone(strict_phone='12223334444')
        self.assertRaises(ValidationError, phone.validate)
        self.assertRaises(ValidationError, phone.save)

        phone = Phone(phone='+6594772797')
        assert phone.phone == '+6594772797'

        phone.save()

    def test_timezone_field(self):
        location = Location()
        location.save()
        location = Location.objects.get(id=location.id)
        assert location.timezone == pytz.UTC
        location.timezone = 'America/Los_Angeles'
        location.save()
        location = Location.objects.get(id=location.id)
        assert location.timezone == pytz.timezone('America/Los_Angeles')

    def test_trimmedstring_field(self):
        test = TrimmedFields(name='')
        self.assertRaises(ValidationError, test.save)

        test = TrimmedFields(name='  ')
        self.assertRaises(ValidationError, test.save)

        test = TrimmedFields(name=' 1', comment='')
        test.save()
        self.assertEqual(test.name, '1')
        self.assertEqual(test.comment, '')

        test = TrimmedFields(name=' big name', comment=' this is a comment')
        test.save()
        self.assertEqual(test.name, 'big name')
        self.assertEqual(test.comment, 'this is a comment')

    def tearDown(self):
        pass


class FormFieldTestCase(unittest.TestCase):
    def setUp(self):
        pass
    def test_datetime_field(self):
        class TestForm(Form):
            date = BetterDateTimeField()

        form = TestForm(MultiDict({'date': ''}))
        self.assertTrue(form.validate())
        self.assertEqual(form.data['date'], None)

        form = TestForm(MultiDict({'date': 'invalid'}))
        self.assertFalse(form.validate())

        form = TestForm(MultiDict({'date': '2012-09-06T01:29:14.107000+00:00'}))
        self.assertTrue(form.validate())
        self.assertEqual(form.data['date'], datetime.datetime(2012, 9, 6, 1, 29, 14, 107000, tzinfo=tzutc()))

        form = TestForm(MultiDict({'date': '2012-09-06 01:29:14'}))
        self.assertTrue(form.validate())
        self.assertEqual(form.data['date'], datetime.datetime(2012, 9, 6, 1, 29, 14))


class SecretTestCase(unittest.TestCase):
    def test_encrypted_field(self):
        col = connection._get_db().secret

        # Test creating password
        s = Secret.objects.create(password='hello')
        self.assertEqual(s.password, 'hello')
        s.reload()
        self.assertEqual(s.password, 'hello')

        cipher = col.find({'_id': s.id})[0]['password']
        self.assertTrue('hello' not in cipher)
        self.assertTrue(len(cipher) > 16)

        # Test changing password
        s.password = 'other'
        s.save()
        s.reload()
        self.assertEqual(s.password, 'other')

        other_cipher = col.find({'_id': s.id})[0]['password']
        self.assertTrue('other' not in other_cipher)
        self.assertTrue(len(other_cipher) > 16)
        self.assertNotEqual(other_cipher, cipher)

        # Make sure password is encrypted differently if we resave.
        s.password = 'hello'
        s.save()
        s.reload()
        self.assertEqual(s.password, 'hello')

        new_cipher = col.find({'_id': s.id})[0]['password']
        self.assertTrue('hello' not in new_cipher)
        self.assertTrue(len(new_cipher) > 16)
        self.assertNotEqual(new_cipher, cipher)
        self.assertNotEqual(other_cipher, cipher)

        # Test empty password
        s.password = None
        s.save()
        s.reload()
        self.assertEqual(s.password, None)

        raw = col.find({'_id': s.id})[0]
        self.assertTrue('password' not in raw)

        # Test passwords of various lengths
        for pw_len in range(1, 50):
            pw = ''.join(random.choice(string.ascii_letters + string.digits) for x in range(pw_len))
            s = Secret(password=pw)
            s.save()
            s.reload()
            self.assertEqual(s.password, pw)


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
            apply_recursively(None, lambda n: n+1),
            None
        )

    def test_list(self):
        self.assertEqual(
            apply_recursively([1,2,3], lambda n: n+1),
            [2,3,4]
        )

    def test_nested_tuple(self):
        self.assertEqual(
            apply_recursively([(1,2),(3,4)], lambda n: n+1),
            [[2,3],[4,5]]
        )

    def test_nested_dict(self):
        self.assertEqual(
            apply_recursively([{'a': 1, 'b': [2,3], 'c': { 'd': 4, 'e': None }}, 5], lambda n: n+1),
            [{'a': 2, 'b': [3,4], 'c': { 'd': 5, 'e': None }}, 6]
        )


class LowerFieldTestCase(unittest.TestCase):

    def test_case_insensitive_query(self):

        class Test(db.Document):
            field = LowerStringField()

        Test.drop_collection()

        Test(field='whatever').save()

        obj1 = Test.objects.get(field='whatever')
        obj2 = Test.objects.get(field='WHATEVER')

        self.assertEqual(obj1, obj2)

        Test.drop_collection()

    def test_case_insensitive_uniqueness(self):

        class Test(db.Document):
            field = LowerStringField(unique=True)

        Test.drop_collection()
        Test.ensure_indexes()

        Test(field='whatever').save()
        self.assertRaises(db.NotUniqueError, Test(field='WHATEVER').save)

    def test_email_validation(self):

        class Test(db.Document):
            email = LowerEmailField()

        Test.drop_collection()

        Test(email='valid@email.com').save()
        self.assertRaises(db.ValidationError, Test(email='invalid email').save)

    def test_case_insensitive_querying(self):

        class Test(db.Document):
            email = LowerEmailField()

        Test.drop_collection()

        obj = Test(email='valid@email.com')
        obj.save()

        self.assertEqual(Test.objects.get(email='valid@email.com'), obj)
        self.assertEqual(Test.objects.get(email='VALID@EMAIL.COM'), obj)
        self.assertEqual(Test.objects.get(email__in=['VALID@EMAIL.COM']), obj)
        self.assertEqual(Test.objects.get(email__nin=['different@email.com']), obj)
        self.assertEqual(Test.objects.filter(email__ne='VALID@EMAIL.COM').count(), 0)

    def test_lower_field_in_embedded_doc(self):

        class EmbeddedDoc(db.EmbeddedDocument):
            email = LowerEmailField()

        class Test(db.Document):
            embedded = db.EmbeddedDocumentField(EmbeddedDoc)

        Test.drop_collection()

        obj = Test(embedded=EmbeddedDoc(email='valid@email.com'))
        obj.save()

        self.assertTrue(obj in Test.objects.filter(embedded__email__in=['VALID@EMAIL.COM', 'whatever']))


class SlugifyTestCase(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify('  Foo  ???BAR\t\n\r'), 'foo_bar')
        self.assertEqual(slugify(u'äąé öóü', '-'), 'aae-oou')


class FetchRelatedTestCase(unittest.TestCase):

    def setUp(self):
        super(FetchRelatedTestCase, self).setUp()

        class Shard(db.Document):
            pass

        class A(db.Document):
            shard_a = ReferenceField(Shard)
            txt = StringField()

        class B(db.Document):
            shard_b = ReferenceField(Shard)
            ref = ReferenceField(A)

        class C(db.Document):
            shard_c = ReferenceField(Shard)
            ref_a = ReferenceField(A)

        class D(db.Document):
            shard_d = ReferenceField(Shard)
            ref_c = ReferenceField(C)
            ref_a = ReferenceField(A)

        class E(db.Document):
            shard_e = ReferenceField(Shard)
            refs_a = SafeReferenceListField(ReferenceField(A))
            ref_b = SafeReferenceField(B)

        class F(db.Document):
            shard_f = ReferenceField(Shard)
            ref_a = ReferenceField(A)

        A.drop_collection()
        B.drop_collection()
        C.drop_collection()
        D.drop_collection()
        E.drop_collection()
        F.drop_collection()

        self.Shard = Shard
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.E = E
        self.F = F

        self.shard = Shard.objects.create()
        self.a1 = A.objects.create(shard_a=self.shard, txt='a1')
        self.a2 = A.objects.create(shard_a=self.shard, txt='a2')
        self.a3 = A.objects.create(shard_a=self.shard, txt='a3')
        self.b1 = B.objects.create(shard_b=self.shard, ref=self.a1)
        self.b2 = B.objects.create(shard_b=self.shard, ref=self.a2)
        self.c1 = C.objects.create(shard_c=self.shard, ref_a=self.a3)
        self.d1 = D.objects.create(
            shard_d=self.shard,
            ref_c=self.c1,
            ref_a=self.a3
        )
        self.e1 = E.objects.create(
            shard_e=self.shard,
            refs_a=[self.a1, self.a2, self.a3],
            ref_b=self.b1
        )
        self.f1 = F.objects.create(shard_f=self.shard, ref_a=None)  # empty ref

    def test_fetch_related(self):
        with custom_query_counter() as q:
            objs = list(self.B.objects.all())
            fetch_related(objs, {
                'ref': True
            })

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2'))

            # one query for B, one query for A
            self.assertEqual(q, 2)

    def test_fetch_related_multiple_objs(self):
        with custom_query_counter() as q:
            objs = list(self.B.objects.all()) + list(self.C.objects.all())
            fetch_related(objs, {
                'ref': True,
                'ref_a': True
            })

            # make sure A objs are fetched
            for obj in objs:
                if isinstance(obj, self.B):
                    self.assertTrue(obj.ref.txt in ('a1', 'a2'))
                else:
                    self.assertEqual(obj.ref_a.txt, 'a3')

            # one query for B, one for C, one for A
            self.assertEqual(q, 3)

    def test_fetch_related_subdict(self):
        """
        Make sure fetching related references works with subfields and that
        it uses caching properly.
        """
        with custom_query_counter() as q:
            objs = list(self.D.objects.all())
            fetch_related(objs, {
                'ref_a': True,
                'ref_c': {
                    'ref_a': True
                }
            })

            # make sure A objs are fetched
            for obj in objs:
                self.assertEqual(obj.ref_a.txt, 'a3')
                self.assertEqual(obj.ref_c.ref_a.txt, 'a3')

            # one query for D, one query for C, one query for A
            self.assertEqual(q, 3)

    def test_fetch_related_subdict_broken_reference(self):
        """
        Make sure that fetching sub-references of a broken reference works.
        """

        # delete the object referenced by self.d1.ref_c
        self.c1.delete()

        objs = list(self.D.objects.all())
        fetch_related(objs, {
            'ref_c': {
                'ref_a': True
            }
        })
        self.assertTrue(objs[0].ref_c.pk)  # pk still exists even though the reference is broken
        self.assertRaises(DoesNotExist, lambda: objs[0].ref_c.ref_a)

    def test_partial_fetch_related(self):
        """
        Make sure we can only fetch particular fields of a reference.
        """
        objs = list(self.B.objects.all())
        fetch_related(objs, {
            'ref': ["id"]
        })
        self.assertEqual(objs[0].ref.pk, self.a1.pk)

        # "txt" field of the referenced object shouldn't be fetched
        self.assertEqual(objs[0].ref.txt, None)
        self.assertTrue(self.a1.txt)

    def test_partial_fetch_fields_conflict(self):
        """
        Fetching certain fields via fetch_related has a limitation that
        different fields cannot be fetched for the same document class.
        Make sure that contraint is respected.
        """
        objs = list(self.B.objects.all()) + list(self.C.objects.all())
        self.assertRaises(RuntimeError, fetch_related, objs, {
            'ref': ["id"],
            'ref_a': True
        })

    def test_partial_fetch_cache_map(self):
        """
        Make sure doing a partial fetch in fetch_related doesn't cache
        the results (it could be dangerous for any subsequent fetch_related
        call).
        """
        cache_map = {}
        objs = list(self.D.objects.all())
        fetch_related(objs, {
            'ref_a': True,
            'ref_c': ["id"]
        }, cache_map=cache_map)
        self.assertEqual(objs[0].ref_c.pk, self.c1.pk)
        self.assertEqual(objs[0].ref_a.pk, self.a3.pk)

        # C reference shouldn't be cached because it was a partial fetch
        self.assertEqual(cache_map, {
            self.A: { self.a3.pk: self.a3 },
            self.C: {}
        })

    def test_safe_reference_fields(self):
        """
        Make sure SafeReferenceField and SafeReferenceListField don't fetch
        the entire objects if we use a partial fetch_related on them.
        """
        objs = list(self.E.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {
                'refs_a': ["id"],
                'ref_b': ["id"]
            })

        # make sure the IDs match
        self.assertEqual(
            [a.pk for a in objs[0].refs_a],
            [self.a1.pk, self.a2.pk, self.a3.pk]
        )
        self.assertEqual(objs[0].ref_b.pk, self.b1.pk)

        # make sure other fields are empty
        self.assertEqual(set([a.txt for a in objs[0].refs_a]), set([None]))
        self.assertEqual(objs[0].ref_b.ref, None)

        # make sure the queries to MongoDB only fetched the IDs
        queries = list(q.db.system.profile.find({ 'op': 'query' }, { 'ns': 1, 'execStats': 1 }))
        self.assertEqual(
            set([ q['ns'].split('.')[1] for q in queries ]),
            set([ 'a', 'b' ])
        )
        self.assertEqual(
            set([ q['execStats']['stage'] for q in queries ]),
            set([ 'PROJECTION' ]),
        )
        self.assertEqual(
            set([ tuple(q['execStats']['transformBy'].keys()) for q in queries ]),
            set([ ('_id',) ]),
        )

    def test_fetch_field_without_refs(self):
        """
        Make sure calling fetch_related on a field that doesn't hold any
        references works.
        """
        # full fetch
        objs = list(self.F.objects.all())
        fetch_related(objs, {
            'ref_a': True
        })
        self.assertEqual(objs[0].ref_a, None)

        # partial fetch
        objs = list(self.F.objects.all())
        fetch_related(objs, {
            'ref_a': ["id"],
        })
        self.assertEqual(objs[0].ref_a, None)

    def test_fetch_same_doc_class_multiple_times_with_cache_map(self):
        """
        Make sure that the right documents are fetched when we reuse a cache
        map for the same document type and the second fetch_related is a
        partial fetch.
        """
        self.b1.reload()
        self.c1.reload()
        cache_map = {}
        objs = [self.b1, self.c1]
        with custom_query_counter() as q:
            fetch_related(objs, {
                'ref': True
            }, cache_map=cache_map)
            fetch_related(objs, {
                'ref_a': ['id']
            }, cache_map=cache_map)

            self.assertEqual(q, 2)
            self.assertEqual(
                [op['query']['filter']['_id']['$in'][0]
                    for op in q.db.system.profile.find({'op': 'query'})],
                [self.a1.pk, self.a3.pk]
            )

    def test_extra_filters(self):
        """
        Ensure we apply extra filters by collection.
        """
        objs = list(self.E.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {
                'refs_a': True,
                'ref_b': True,
            }, extra_filters={
                self.A: {'shard_a': self.shard},
                self.B: {'shard_b': self.shard},
            })
        ops = list(q.db.system.profile.find({'op': 'query'}))
        assert len(ops) == 2
        filters = {op['query']['find']: op['query']['filter'] for op in ops}
        assert filters['a']['shard_a'] == self.shard.pk
        assert filters['b']['shard_b'] == self.shard.pk

    def test_batch_size_1(self):
        """
        Ensure we batch requests properly, if a batch size is given.
        """
        objs = list(self.B.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {
                'ref': True,
            }, batch_size=2)

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2', 'a3'))

            # We need two queries to fetch 3 objects.
            self.assertEqual(q, 2)

    def test_batch_size_2(self):
        """
        Ensure we batch requests properly, if a batch size is given.
        """
        objs = list(self.B.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {
                'ref': True,
            }, batch_size=3)

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2', 'a3'))

            # All 3 objects are fetched in one query.
            self.assertEqual(q, 1)


class UtilsTestCase(unittest.TestCase):

    def test_uniqify(self):
        self.assertEqual(
            uniqify([1, 2, 3, 1, 'a', None, 'a', 'b']),
            [1, 2, 3, 'a', None, 'b']
        )
        self.assertEqual(
            uniqify([ { 'a': 1 }, { 'a': 2 }, { 'a': 1 } ]),
            [ { 'a': 1 }, { 'a': 2 } ]
        )
        self.assertEqual(
            uniqify([ { 'a': 1, 'b': 3 }, { 'a': 2, 'b': 2 }, { 'a': 1, 'b': 1 } ], key=lambda i: i['a']),
            [ { 'a': 1, 'b': 3 }, { 'a': 2, 'b': 2 } ]
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
