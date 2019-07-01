import unittest

from mongoengine import (Document, EmbeddedDocument, EmbeddedDocumentField,
                         ValidationError, NotUniqueError)

from flask_common.mongo import (LowerEmailField, LowerStringField,
                                TrimmedStringField)


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


class LowerStringFieldTestCase(unittest.TestCase):
    # TODO pytest-ify and test the field instance directly without persistence.

    def test_case_insensitive_query(self):

        class Test(Document):
            field = LowerStringField()

        Test.drop_collection()

        Test(field='whatever').save()

        obj1 = Test.objects.get(field='whatever')
        obj2 = Test.objects.get(field='WHATEVER')

        self.assertEqual(obj1, obj2)

        Test.drop_collection()

    def test_case_insensitive_uniqueness(self):

        class Test(Document):
            field = LowerStringField(unique=True)

        Test.drop_collection()
        Test.ensure_indexes()

        Test(field='whatever').save()
        self.assertRaises(NotUniqueError, Test(field='WHATEVER').save)


class LowerEmailFieldTestCase(unittest.TestCase):
    # TODO pytest-ify and test the field instance directly without persistence.

    def test_email_validation(self):

        class Test(Document):
            email = LowerEmailField()

        Test.drop_collection()

        Test(email='valid@email.com').save()
        self.assertRaises(ValidationError, Test(email='invalid email').save)

    def test_case_insensitive_querying(self):

        class Test(Document):
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

        class EmbeddedDoc(EmbeddedDocument):
            email = LowerEmailField()

        class Test(Document):
            embedded = EmbeddedDocumentField(EmbeddedDoc)

        Test.drop_collection()

        obj = Test(embedded=EmbeddedDoc(email='valid@email.com'))
        obj.save()

        self.assertTrue(
            obj in Test.objects.filter(
                embedded__email__in=['VALID@EMAIL.COM', 'whatever']
            )
        )
