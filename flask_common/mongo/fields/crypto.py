from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

from bson import Binary
from mongoengine.fields import BinaryField

from flask_common.crypto import (
    KEY_LENGTH,
    AuthenticationError,
    aes_decrypt,
    aes_encrypt,
)


class EncryptedBinaryField(BinaryField):
    """
    Encrypted binary data field. Encryption is completely transparent
    to the caller as the field automatically decrypts when the field
    is accessed and encrypts when the document is saved. The
    underlying algorithm currently is AES-256.
    """

    def __init__(self, key_or_list, *args, **kwargs):
        """
        key_or_list: A 512-bit binary string containing a 256-bit AES
        key followed by a 256-bit HMAC-SHA256 key.
        Alternatively, a list of keys for decryption may be provided.
        The first key will always be used for encryption, the other
        ones will be sequentially tried for decryption. This is e.g.
        useful for key migration.
        """
        if isinstance(key_or_list, (list, tuple)):
            self.key_list = key_or_list
        else:
            self.key_list = [key_or_list]
        assert len(self.key_list) > 0, "No key provided"
        for key in self.key_list:
            assert len(key) == KEY_LENGTH, 'invalid key size'
        super(EncryptedBinaryField, self).__init__(*args, **kwargs)

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
        return self._decrypt(value) if value else None

    def to_mongo(self, value):
        return self._encrypt(value) if value else None


class EncryptedStringField(EncryptedBinaryField):
    """
    Encrypted Unicode string field. Encryption is completely transparent
    to the caller as the field automatically decrypts when the field
    is accessed and encrypts when the document is saved. The
    underlying algorithm currently is AES-256.
    """

    def to_python(self, value):
        decrypted_value = super(EncryptedStringField, self).to_python(value)
        return decrypted_value.decode('utf-8') if decrypted_value else None

    def to_mongo(self, value):
        encoded_value = value.encode('utf-8') if value else None
        return super(EncryptedStringField, self).to_mongo(encoded_value)
