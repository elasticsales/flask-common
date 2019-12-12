"""This file supports versioned encrypted information.

* Version 0: marked with first byte `\x00`

Implemented with `pycrypto`.

In this version, data is returned from `aes_encrypt` in the format:

[VERSION 0 byte][IV 32 bytes][Encrypted data][HMAC 32 bytes]

This format comes from a erroneous implementation that used an IV of
32 bytes when AES expects IVs of 16 bytes, and the library used at the
time (`pycrypto`) silently truncated the IV for us.

* Version 1: marked with first byte `\x01`

Implemented with `cryptography`.

In this version, data is returned from `aes_encrypt` in the format:

[VERSION 1 byte][IV 16 bytes][Encrypted data][HMAC 32 bytes]

This version came into existence to fix the wrong-sized IVs from
version 0.

Current code decrypts both versions, encrypts to version 1.

In CTR mode, IV is also often called a Nonce (in `cryptography`'s
public interface, for example).
"""
import hashlib
import hmac
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

backend = default_backend()

AES_KEY_SIZE = 32  # 256 bits
HMAC_KEY_SIZE = 32  # 256 bits
KEY_LENGTH = AES_KEY_SIZE + HMAC_KEY_SIZE

V0_IV_SIZE = 32  # 256 bits, wrong size used in version 0
IV_SIZE = 16  # 128 bits

HMAC_DIGEST = hashlib.sha256
HMAC_DIGEST_SIZE = hashlib.sha256().digest_size

V0_MARKER = b'\x00'
V1_MARKER = b'\x01'


class EncryptionError(Exception):
    pass


class AuthenticationError(Exception):
    pass


"""
Helper AES encryption/decryption methods. Uses AES-CTR + HMAC for authenticated
encryption. The same key/iv combination must never be reused to encrypt
different messages.
"""


# Returns a new randomly generated AES key.
def aes_generate_key():
    return os.urandom(KEY_LENGTH)


# Encrypt + sign using a random IV.
def aes_encrypt(key, data):
    assert len(key) == KEY_LENGTH, 'invalid key size'
    iv = os.urandom(IV_SIZE)
    return V1_MARKER + iv + aes_encrypt_iv(key, data, iv)


# Verify + decrypt data encrypted with IV.
def aes_decrypt(key, data):
    assert len(key) == KEY_LENGTH, 'invalid key size'

    # In Python 3, if you extract a single byte from a bytestring,
    # you'll get an int. That's why we extract it using a slice.
    extracted_version = data[0:1]
    data = data[1:]

    # In version 0, we used IVs with wrong sizes. We need to take this
    # into account when separating encrypted data from their IVs.
    if extracted_version == V0_MARKER:
        iv = data[:V0_IV_SIZE]
        data = data[V0_IV_SIZE:]
    elif extracted_version == V1_MARKER:
        iv = data[:IV_SIZE]
        data = data[IV_SIZE:]
    else:
        raise EncryptionError(
            'Found invalid version marker: {!r}'.format(extracted_version)
        )

    return aes_decrypt_iv(key, data, iv, extracted_version)


# Encrypt + sign using provided IV.
# Note: You should normally use aes_encrypt().
def aes_encrypt_iv(key, data, iv):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    encryptor = Cipher(
        algorithms.AES(aes_key), modes.CTR(iv), backend=backend
    ).encryptor()
    cipher = encryptor.update(data) + encryptor.finalize()
    sig = hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest()
    return cipher + sig


# Verify + decrypt using provided IV.
# Note: You should normally use aes_decrypt().
def aes_decrypt_iv(key, data, iv, extracted_version):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    cipher = data[:-HMAC_DIGEST_SIZE]
    sig = data[-HMAC_DIGEST_SIZE:]
    if hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest() != sig:
        raise AuthenticationError('message authentication failed')

    # In version 0, we used IVs with wrong sizes. `pycrypto` was
    # silently truncating those IVs for us before using them for
    # encryption. We need to do the same thing here, since
    # `cryptography` just expects the correctly-sized IV. Use the
    # **last** `IV_SIZE` bytes of the IV.
    if extracted_version == V0_MARKER:
        iv = iv[IV_SIZE:]

    decryptor = Cipher(
        algorithms.AES(aes_key), modes.CTR(iv), backend=backend
    ).decryptor()
    return decryptor.update(cipher) + decryptor.finalize()
