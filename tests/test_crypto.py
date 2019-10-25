import pytest

from flask_common.crypto import (
    AuthenticationError,
    aes_decrypt,
    aes_encrypt,
    aes_generate_key,
)


def test_with_versioned_v0_data():
    data = b'test'

    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher the old
    # encrypted data.
    key = b"\xe6\xb53\x90\xb8\x8f'-=e\x86z\xc3\x90\xff\xb8*\xf5\xd9\xaf\xb8\xad\x81\xcadl\xed\xf4\t\xe8\x9c*\r\x16\xd2\x00/\xd8\x86@)\xc1\x9b\x8d\xabo\xf7E\xbc\xf8\xae@\x98O\xf0\xd8[\xd0\xe1\x9a\xf5w\x03r"
    encrypted_data = b'\x00o\x15\n\xef\x9a\xd62\x86\x81\x9cBS%\xfa\xf7\xdb\x1a\x9a9\xd2\xf8;\xe5\xc1\xd8l\x16\xdeH?\xcd\xd7D\x9d\xcd\xc2\x1ej\xabb\x86\xa4u@\x9f\x1b\xe2}FtQ\xd9\x1f\xd7\xa4\xc1\xe8\x94N\n\xe9\xb2\xa0\xccD2\xe9)'

    assert aes_decrypt(key, encrypted_data) == data


def test_with_versioned_v0_corrupted_data():
    data = b'test'

    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher the old
    # encrypted data.
    key = b"\xe6\xb53\x90\xb8\x8f'-=e\x86z\xc3\x90\xff\xb8*\xf5\xd9\xaf\xb8\xad\x81\xcadl\xed\xf4\t\xe8\x9c*\r\x16\xd2\x00/\xd8\x86@)\xc1\x9b\x8d\xabo\xf7E\xbc\xf8\xae@\x98O\xf0\xd8[\xd0\xe1\x9a\xf5w\x03r"
    encrypted_data = b'\x00a\x15\n\xef\x9a\xd62\x86\x81\x9cBS%\xfa\xf7\xdb\x1a\x9a9\xd2\xf8;\xe5\xc1\xd8l\x16\xdeH?\xcd\xd7D\x9d\xcd\xc2\x1ej\xabb\x86\xa4u@\x9f\x1b\xe2}FtQ\xd9\x1f\xd7\xa4\xc1\xe8\x94N\n\xe9\xb2\xa0\xccD2\xe9)'

    with pytest.raises(AuthenticationError):
        assert aes_decrypt(key, encrypted_data) == data


def test_with_versioned_v1_data():
    data = b'test'
    key = aes_generate_key()
    assert aes_decrypt(key, aes_encrypt(key, data)) == data


def test_with_versioned_v1_corrupted_data():
    data = b'test'
    key = aes_generate_key()
    encrypted_data = aes_encrypt(key, data)[3:]  # Missing first 3 bytes
    with pytest.raises(AuthenticationError):
        assert aes_decrypt(key, encrypted_data) == data
