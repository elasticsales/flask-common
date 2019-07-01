import unittest

from mongoengine import Document, ValidationError

from flask_common.mongo import TrimmedStringField


class TrimmedStringFieldTestCase(unittest.TestCase):
    # TODO pytest-ify and test the field instance directly without persistence.

    def test_trimmedstring_field(self):
        class Person(Document):
            name = TrimmedStringField(required=True)
            comment = TrimmedStringField()
        Person.drop_collection()

        person = Person(name='')
        self.assertRaises(ValidationError, person.save)

        person = Person(name='  ')
        self.assertRaises(ValidationError, person.save)

        person = Person(name=' 1', comment='')
        person.save()
        self.assertEqual(person.name, '1')
        self.assertEqual(person.comment, '')

        person = Person(name=' big name', comment=' this is a comment')
        person.save()
        self.assertEqual(person.name, 'big name')
        self.assertEqual(person.comment, 'this is a comment')
