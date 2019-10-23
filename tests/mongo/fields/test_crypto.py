import random
import string
import unittest

from mongoengine import Document, connection

from flask_common.crypto import aes_generate_key
from flask_common.mongo.fields import EncryptedStringField


class EncryptedStringFieldTestCase(unittest.TestCase):
    # TODO pytest-ify and test the field instance directly without persistence.

    def test_encrypted_field(self):
        class Secret(Document):
            password = EncryptedStringField(aes_generate_key())

        Secret.drop_collection()

        col = connection._get_db().secret

        # Test creating password
        s = Secret.objects.create(password=u'hello')
        self.assertEqual(s.password, u'hello')
        s.reload()
        self.assertEqual(s.password, u'hello')

        cipher = col.find({'_id': s.id})[0]['password']
        self.assertTrue('hello' not in cipher)
        self.assertTrue(len(cipher) > 16)

        # Test changing password
        s.password = u'other'
        s.save()
        s.reload()
        self.assertEqual(s.password, u'other')

        other_cipher = col.find({'_id': s.id})[0]['password']
        self.assertTrue('other' not in other_cipher)
        self.assertTrue(len(other_cipher) > 16)
        self.assertNotEqual(other_cipher, cipher)

        # Make sure password is encrypted differently if we resave.
        s.password = u'hello'
        s.save()
        s.reload()
        self.assertEqual(s.password, u'hello')

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
            pw = ''.join(
                random.choice(string.ascii_letters + string.digits)
                for x in range(pw_len)
            )
            s = Secret(password=pw)
            s.save()
            s.reload()
            self.assertEqual(s.password, pw)
