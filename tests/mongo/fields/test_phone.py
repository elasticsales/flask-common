import unittest

from mongoengine import Document, ValidationError

from flask_common.mongo import PhoneField


class PhoneFieldTestCase(unittest.TestCase):

    def test_format_number(self):
        class Person(Document):
            phone = PhoneField()
        Person.drop_collection()

        person = Person(phone='14151231234')
        assert person.phone == '14151231234'

        person.phone = 'notaphone'
        assert person.phone == 'notaphone'
        self.assertRaises(ValidationError, person.validate)
        self.assertRaises(ValidationError, person.save)

        person.phone = '+1 (650) 618 - 1234 x 768'
        assert person.phone == '+16506181234x768'
        person.validate()
        person.save()

        assert person.id == Person.objects.get(phone='+16506181234x768').id
        assert person.id == Person.objects.get(phone='+1 650-618-1234 ext 768').id

    def test_strict_format_number(self):
        class Person(Document):
            phone = PhoneField(strict=True)
        Person.drop_collection()

        person = Person(phone='12223334444')
        self.assertRaises(ValidationError, person.validate)
        self.assertRaises(ValidationError, person.save)

        person = Person(phone='+6594772797')
        assert person.phone == '+6594772797'

        person.save()
