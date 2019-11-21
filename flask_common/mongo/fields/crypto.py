from bson import Binary
from mongoengine.fields import BinaryField
from mongoengine.python_support import bin_type, txt_type, PY3

from flask_common.crypto import (
    KEY_LENGTH,
    AuthenticationError,
    aes_encrypt,
    aes_decrypt,
)


class EncryptedStringField(BinaryField):
    """
    Encrypted string field. Uses AES256 bit encryption with a different 128 bit
    IV every time the field is saved. Encryption is completely transparent to
    the user as the field automatically unencrypts when the field is accessed
    and encrypts when the document is saved.
    """

    def __init__(self, key_or_list, *args, **kwargs):
        """
        key_or_list: 64 byte binary string containing a 256 bit AES key and a
        256 bit HMAC-SHA256 key.
        Alternatively, a list of keys for decryption may be provided. The
        first key will always be used for encryption. This is e.g. useful for
        key migration.
        """
        if isinstance(key_or_list, (list, tuple)):
            self.key_list = key_or_list
        else:
            self.key_list = [key_or_list]
        assert len(self.key_list) > 0, "No key provided"
        for key in self.key_list:
            assert len(key) == KEY_LENGTH, 'invalid key size'
        return super(EncryptedStringField, self).__init__(*args, **kwargs)

    def __set__(self, instance, value):
        # Handle unicode strings by encoding them
        if isinstance(value, txt_type):
            value = value.encode('utf-8')
        return super(BinaryField, self).__set__(instance, value)

    def _encrypt(self, data):
        return Binary(aes_encrypt(self.key_list[0], data))

    def _decrypt(self, data):
        for key in self.key_list:
            try:
                return aes_decrypt(key, data)
            except AuthenticationError:
                pass

        raise AuthenticationError('message authentication failed')

    def to_python(self, value):
        return value and self._decrypt(value).decode('utf-8') or None

    def to_mongo(self, value):
        return value and self._encrypt(value.encode('utf-8')) or None
