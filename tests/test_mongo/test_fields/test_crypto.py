# coding: utf-8

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import pytest

from flask_common.crypto import AuthenticationError, aes_generate_key
from flask_common.mongo.fields import (
    EncryptedBinaryField,
    EncryptedStringField,
)


def test_encrypted_binary_field_can_encrypt_and_decrypt():
    token = EncryptedBinaryField(aes_generate_key())
    assert token.to_python(token.to_mongo(b'\x00\x01')) == b'\x00\x01'


def test_encrypted_binary_field_can_rotate():
    key_1 = aes_generate_key()
    token = EncryptedBinaryField(key_1)
    encrypted_data = token.to_mongo(b'\x00\x01')

    key_2 = aes_generate_key()
    token = EncryptedBinaryField([key_2, key_1])
    assert token.to_python(encrypted_data) == b'\x00\x01'


def test_encrypted_binary_field_will_fail_on_corrupted_data():
    key_1 = aes_generate_key()
    token = EncryptedBinaryField(key_1)
    corrupted_encrypted_data = token.to_mongo(b'\x00\x01')[:3]
    with pytest.raises(AuthenticationError) as excinfo:
        token.to_python(corrupted_encrypted_data)
    assert str(excinfo.value) == 'message authentication failed'


def test_encrypted_binary_field_with_none():
    token = EncryptedBinaryField(aes_generate_key())
    assert token.to_python(token.to_mongo(None)) is None


def test_encrypted_string_field_works_with_unicode_data():
    token = EncryptedStringField(aes_generate_key())
    assert token.to_python(token.to_mongo(u'ãé')) == u'ãé'
