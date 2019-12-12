import datetime
import time
import unittest

from mongoengine import Document, ReferenceField, StringField, ValidationError

from flask_common.mongo.documents import (
    DocumentBase,
    RandomPKDocument,
    SoftDeleteDocument,
)


class DocumentBaseTestCase(unittest.TestCase):
    def test_cls_inheritance(self):
        """
        Make sure _cls is not appended to queries and indexes and that
        allow_inheritance is disabled by default for docs inheriting from
        RandomPKDocument and DocumentBase.
        """

        class Doc(DocumentBase, RandomPKDocument):
            text = StringField()

        self.assertEqual(Doc.objects.filter(text='')._query, {'text': ''})
        self.assertFalse(Doc._meta['allow_inheritance'])

    def test_pk_validation(self):
        """
        Make sure that you cannot save crap in a ReferenceField that
        references a RandomPKDocument.
        """

        class A(RandomPKDocument):
            text = StringField()

        class B(Document):
            ref = ReferenceField(A)

        self.assertRaises(ValidationError, B.objects.create, ref={'dict': True})

    def test_document_base_date_updated(self):
        """
        Make sure a class inheriting from DocumentBase correctly handles
        updates to date_updated.
        """

        class Doc(DocumentBase, RandomPKDocument):
            text = StringField()

        doc = Doc.objects.create(text='aaa')
        doc.reload()
        last_date_created = doc.date_created
        last_date_updated = doc.date_updated

        doc.text = 'new'
        doc.save()
        doc.reload()

        self.assertEqual(doc.date_created, last_date_created)
        self.assertTrue(doc.date_updated > last_date_updated)
        last_date_updated = doc.date_updated

        time.sleep(0.001)  # make sure some time passes between the updates
        doc.update(set__text='newer')
        doc.reload()

        self.assertEqual(doc.date_created, last_date_created)
        self.assertTrue(doc.date_updated > last_date_updated)
        last_date_updated = doc.date_updated

        time.sleep(0.001)  # make sure some time passes between the updates
        doc.update(set__date_created=datetime.datetime.utcnow())
        doc.reload()

        self.assertTrue(doc.date_created > last_date_created)
        self.assertTrue(doc.date_updated > last_date_updated)
        last_date_created = doc.date_created
        last_date_updated = doc.date_updated

        new_date_created = datetime.datetime(2014, 6, 12)
        new_date_updated = datetime.datetime(2014, 10, 12)
        time.sleep(0.001)  # make sure some time passes between the updates
        doc.update(
            set__date_created=new_date_created,
            set__date_updated=new_date_updated,
        )
        doc.reload()

        self.assertEqual(
            doc.date_created.replace(tzinfo=None), new_date_created
        )
        self.assertEqual(
            doc.date_updated.replace(tzinfo=None), new_date_updated
        )

        time.sleep(0.001)  # make sure some time passes between the updates
        doc.update(set__text='newest', update_date=False)
        doc.reload()

        self.assertEqual(doc.text, 'newest')
        self.assertEqual(
            doc.date_created.replace(tzinfo=None), new_date_created
        )
        self.assertEqual(
            doc.date_updated.replace(tzinfo=None), new_date_updated
        )


class SoftDeleteDocumentTestCase(unittest.TestCase):
    class Person(DocumentBase, RandomPKDocument, SoftDeleteDocument):
        name = StringField()

        meta = {'allow_inheritance': True}

    class Programmer(Person):
        language = StringField()

    def setUp(self):
        self.Person.drop_collection()
        self.Programmer.drop_collection()

    def test_default_is_deleted(self):
        """Make sure is_deleted is never null."""
        s = self.Person.objects.create(name='Steve')
        self.assertEqual(s.reload()._db_data['is_deleted'], False)

        def _bad_update():
            s.update(set__is_deleted=None)

        self.assertRaises(ValidationError, _bad_update)

    def test_queryset_manager(self):
        a = self.Person.objects.create(name='Anthony')

        # test all the ways to filter/aggregate counts
        self.assertEqual(len(self.Person.objects.all()), 1)
        self.assertEqual(self.Person.objects.all().count(), 1)
        self.assertEqual(self.Person.objects.filter(name='Anthony').count(), 1)
        self.assertEqual(self.Person.objects.count(), 1)

        a.delete()
        self.assertEqual(len(self.Person.objects.all()), 0)
        self.assertEqual(self.Person.objects.all().count(), 0)
        self.assertEqual(self.Person.objects.filter(name='Anthony').count(), 0)
        self.assertEqual(self.Person.objects.count(), 0)

        self.assertEqual(len(self.Person.objects.filter(name='Anthony')), 0)
        a.is_deleted = False
        a.save()
        self.assertEqual(len(self.Person.objects.filter(name='Anthony')), 1)

        b = self.Programmer.objects.create(name='Thomas', language='python.net')
        self.assertEqual(len(self.Programmer.objects.all()), 1)
        b.delete()
        self.assertEqual(len(self.Programmer.objects.all()), 0)

        self.assertEqual(len(self.Programmer.objects.filter(name='Thomas')), 0)
        b.is_deleted = False
        b.save()
        self.assertEqual(len(self.Programmer.objects.filter(name='Thomas')), 1)

    def test_date_updated(self):
        a = self.Person.objects.create(name='Anthony')
        a.reload()
        last_date_updated = a.date_updated

        time.sleep(0.001)  # make sure some time passes between the updates
        a.update(set__name='Tony')
        a.reload()

        self.assertTrue(a.date_updated > last_date_updated)
        last_date_updated = a.date_updated

        time.sleep(0.001)  # make sure some time passes between the updates
        a.delete()
        a.reload()

        self.assertTrue(a.date_updated > last_date_updated)
        self.assertEqual(a.is_deleted, True)
