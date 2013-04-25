import unittest

import datetime
from dateutil.tz import tzutc
import pytz

from flask import Flask
from flask.ext.mongoengine import MongoEngine, ValidationError
from flask_common.utils import apply_recursively, isortedset
from flask_common.fields import PhoneField, TimezoneField, TrimmedStringField, EncryptedStringField, SafeReferenceListField, rng
from flask_common.formfields import BetterDateTimeField

from mongoengine import ReferenceField

from werkzeug.datastructures import MultiDict
from wtforms import Form

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

class Location(db.Document):
    timezone = TimezoneField()

class TestTrimmedFields(db.Document):
    name = TrimmedStringField(required=True)
    comment = TrimmedStringField()

class Secret(db.Document):
    password = EncryptedStringField(rng(32))

class Book(db.Document):
    pass

class Author(db.Document):
    books = SafeReferenceListField(ReferenceField(Book))

class FieldTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        Phone.drop_collection()
        Location.drop_collection()
        TestTrimmedFields.drop_collection()

    def test_format_number(self):
        phone = Phone(phone='4151231234')
        assert phone.phone == '+14151231234'
        phone.validate()

        phone.phone = 'notaphone'
        assert phone.phone == 'notaphone'
        self.assertRaises(ValidationError, phone.validate)
        self.assertRaises(ValidationError, phone.save)

        phone.phone = '+1 (650) 618 - 1234 x 768'
        assert phone.phone == '+16506181234x768'
        phone.validate()

        phone.save()

        assert phone.id == Phone.objects.get(phone='6506181234x768').id
        assert phone.id == Phone.objects.get(phone='+1 650-618-1234 ext 768').id

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
        try:
            test = TestTrimmedFields(name='') 
            test.save()
            self.fail("should have failed")
        except ValidationError, e:
            pass

        try:
            location = TestTrimmedFields(name='  ') 
            test.save()
            self.fail("should have failed")
        except ValidationError, e:
            pass

        test = TestTrimmedFields(name=' 1', comment='') 
        test.save()
        self.assertEqual(test.name, '1')
        self.assertEqual(test.comment, '')

        test = TestTrimmedFields(name=' big name', comment=' this is a comment') 
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
        from mongoengine import connection
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

class TestSafeReferenceListField(unittest.TestCase):
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


class TestISortedSet(unittest.TestCase):
    def test_isortedset(self):
        s = isortedset(['Z', 'b', 'A'])
        self.assertEqual(list(s), ['A', 'b', 'Z'])
        self.assertTrue('a' in s)
        self.assertTrue('A' in s)
        self.assertTrue('b' in s)
        self.assertTrue('B' in s)
        self.assertTrue('z' in s)
        self.assertTrue('Z' in s)
        self.assertTrue('c' not in s)
        self.assertTrue('C' not in s)

        s = isortedset(['A', 'a'])
        self.assertEqual(list(s), ['A'])
        self.assertTrue('a' in s)
        self.assertTrue('A' in s)


if __name__ == '__main__':
    unittest.main()
