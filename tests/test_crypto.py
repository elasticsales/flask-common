import pytest
from flask_common.crypto import (
    AuthenticationError,
    EncryptionError,
    aes_decrypt,
    aes_encrypt,
    aes_generate_key,
)


def test_with_v0_data():
    data = b'test'

    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher data
    # encrypted the old way.
    key = b"\xe6\xb53\x90\xb8\x8f'-=e\x86z\xc3\x90\xff\xb8*\xf5\xd9\xaf\xb8\xad\x81\xcadl\xed\xf4\t\xe8\x9c*\r\x16\xd2\x00/\xd8\x86@)\xc1\x9b\x8d\xabo\xf7E\xbc\xf8\xae@\x98O\xf0\xd8[\xd0\xe1\x9a\xf5w\x03r"
    encrypted_data = b'\x00o\x15\n\xef\x9a\xd62\x86\x81\x9cBS%\xfa\xf7\xdb\x1a\x9a9\xd2\xf8;\xe5\xc1\xd8l\x16\xdeH?\xcd\xd7D\x9d\xcd\xc2\x1ej\xabb\x86\xa4u@\x9f\x1b\xe2}FtQ\xd9\x1f\xd7\xa4\xc1\xe8\x94N\n\xe9\xb2\xa0\xccD2\xe9)'

    assert aes_decrypt(key, encrypted_data) == data


def test_with_v0_corrupted_data():
    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher the old
    # encrypted data.
    key = b"\xe6\xb53\x90\xb8\x8f'-=e\x86z\xc3\x90\xff\xb8*\xf5\xd9\xaf\xb8\xad\x81\xcadl\xed\xf4\t\xe8\x9c*\r\x16\xd2\x00/\xd8\x86@)\xc1\x9b\x8d\xabo\xf7E\xbc\xf8\xae@\x98O\xf0\xd8[\xd0\xe1\x9a\xf5w\x03r"
    corrupted_encrypted_data = b'\x00a\x15\n\xef\x9a\xd62\x86\x81\x9cBS%\xfa\xf7\xdb\x1a\x9a9\xd2\xf8;\xe5\xc1\xd8l\x16\xdeH?\xcd\xd7D\x9d\xcd\xc2\x1ej\xabb\x86\xa4u@\x9f\x1b\xe2}FtQ\xd9\x1f\xd7\xa4\xc1\xe8\x94N\n\xe9\xb2\xa0\xccD2\xe9)'

    with pytest.raises(AuthenticationError) as excinfo:
        aes_decrypt(key, corrupted_encrypted_data)
    assert str(excinfo.value) == "message authentication failed"


def test_with_v1_data():
    data = b'test'
    key = aes_generate_key()
    encrypted_data = aes_encrypt(key, data)
    assert encrypted_data[0:1] == b'\x01'
    assert aes_decrypt(key, encrypted_data) == data


def test_with_v1_corrupted_data():
    data = b'test'
    key = aes_generate_key()
    encrypted_data = aes_encrypt(key, data)
    assert encrypted_data[0:1] == b'\x01'
    corrupted_encrypted_data = encrypted_data[:-3]
    with pytest.raises(AuthenticationError) as excinfo:
        aes_decrypt(key, corrupted_encrypted_data)
    assert str(excinfo.value) == "message authentication failed"


def test_with_data_exactly_as_long_as_aes_block():
    data = b'a' * 128
    key = aes_generate_key()
    assert aes_decrypt(key, aes_encrypt(key, data)) == data


def test_with_data_longer_than_aes_block():
    data = b'a' * 130
    key = aes_generate_key()
    assert aes_decrypt(key, aes_encrypt(key, data)) == data


def test_data_encrypted_twice_is_different():
    data = b'test'
    key = aes_generate_key()

    first_encryption = aes_encrypt(key, data)
    second_encryption = aes_encrypt(key, data)
    assert first_encryption != second_encryption


def test_with_invalid_version():
    key = b']\x1a\xa2\nW\x97\xab)\x951\xa8t\x8b\xd8\xac\x08\xebjlY\xd0S\x90d\xcc\rR\x1f\xbf\x13\xe0:\xb5\x7f\xbf\xa7\x83|\x10bQ\x03\xd3Z]\xea\x1f2\xf6tB\x13\xaeP\xcc\x8fb\xabY\xda#\xe9QE'
    encrypted_data = b'\xa1M\xcdjP\xfd\xcc\xa1\xd7\xda\x11(Q \xbd\xe4w\n\x03C\x14!\x99N\xe8\xf0H\xbc\xf8\xf41\xa5\x10E\x0e\xbc\x04\x01\x85\x0b\xd5F\x1bq>\x12\x04\x11Y\x10\x8f\x0f\x06'
    with pytest.raises(EncryptionError) as excinfo:
        aes_decrypt(key, encrypted_data)
    assert str(excinfo.value) == "Found invalid version marker: {!r}".format(
        b'\xa1'
    )
