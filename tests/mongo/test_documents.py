import datetime
import time
import unittest

from mongoengine import Document, ReferenceField, StringField, ValidationError

from flask_common.mongo import DocumentBase, RandomPKDocument


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
            set__date_updated=new_date_updated
        )
        doc.reload()

        self.assertEqual(doc.date_created.replace(tzinfo=None), new_date_created)
        self.assertEqual(doc.date_updated.replace(tzinfo=None), new_date_updated)

        time.sleep(0.001)  # make sure some time passes between the updates
        doc.update(set__text='newest', update_date=False)
        doc.reload()

        self.assertEqual(doc.text, 'newest')
        self.assertEqual(doc.date_created.replace(tzinfo=None), new_date_created)
        self.assertEqual(doc.date_updated.replace(tzinfo=None), new_date_updated)
