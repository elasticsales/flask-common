"""This file supports versioned encrypted information.

* Version 0: marked with first byte `\x00`

Implemented with `pycrypto`.

In this version, data is returned from `aes_encrypt` in the format:

[VERSION 1 byte][IV 32 bytes][Encrypted data][HMAC 32 bytes]

This format comes from a erroneous implementation that used an IV of
32 bytes when AES expects IVs of 16 bytes, and the library used at the
time (`pycrypto`) silently truncated the IV for us.

* Version 1: marked with first byte `\x01`

Implemented with `cryptography`.

In this version, data is returned from `aes_encrypt` in the format:

[VERSION 1 byte][IV 16 bytes][Encrypted data][HMAC 32 bytes]

This version came into existence to fix the wrong-sized IVs from
version 0.

Current code decrypts both versions, encrypts in version 0.

In CTR mode, IV is also often called a Nonce (in `cryptography`'s
public interface, for example).
"""
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Util import Counter
import hashlib
import hmac

AES_KEY_SIZE = 32  # 256 bits
HMAC_KEY_SIZE = 32  # 256 bits
KEY_LENGTH = AES_KEY_SIZE + HMAC_KEY_SIZE

V0_IV_SIZE = 32  # 256 bits, wrong size used in version 0
IV_SIZE = 16  # 128 bits

HMAC_DIGEST = hashlib.sha256
HMAC_DIGEST_SIZE = hashlib.sha256().digest_size

V0_MARKER = b'\x00'
V1_MARKER = b'\x01'

rng = Random.new().read


class AuthenticationError(Exception):
    pass


"""
Helper AES encryption/decryption methods. Uses AES-CTR + HMAC for authenticated
encryption. The same key/iv combination must never be reused to encrypt
different messages.
"""

# TODO: Make these functions work on Python 3
# Remove crypto-related tests from tests/conftest.py blacklist when
# working on this.


# Returns a new randomly generated AES key
def aes_generate_key():
    return rng(KEY_LENGTH)


# Encrypt + sign using a random IV
def aes_encrypt(key, data):
    assert len(key) == KEY_LENGTH, 'invalid key size'
    iv = rng(V0_IV_SIZE)
    return V0_MARKER + iv + aes_encrypt_iv(key, data, iv)


# Verify + decrypt data encrypted with IV
def aes_decrypt(key, data):
    assert len(key) == KEY_LENGTH, 'invalid key size'

    extracted_version = data[0]
    data = data[1:]

    if extracted_version == V0_MARKER:
        iv = data[:V0_IV_SIZE]
        data = data[V0_IV_SIZE:]
    else:
        iv = data[:IV_SIZE]
        data = data[IV_SIZE:]

    return aes_decrypt_iv(key, data, iv, extracted_version)


# Encrypt + sign using provided IV.
# Note: You should normally use aes_encrypt()
def aes_encrypt_iv(key, data, iv):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    initial_value = long(iv.encode("hex"), 16)
    ctr = Counter.new(128, initial_value=initial_value)
    cipher = AES.new(aes_key, AES.MODE_CTR, counter=ctr).encrypt(data)
    sig = hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest()
    return cipher + sig


# Verify + decrypt using provided IV.
# Note: You should normally use aes_decrypt()
def aes_decrypt_iv(key, data, iv, extracted_version):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    cipher = data[:-HMAC_DIGEST_SIZE]
    sig = data[-HMAC_DIGEST_SIZE:]
    if hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest() != sig:
        raise AuthenticationError('message authentication failed')
    initial_value = long(iv.encode("hex"), 16)
    ctr = Counter.new(128, initial_value=initial_value)
    plain = AES.new(aes_key, AES.MODE_CTR, counter=ctr).decrypt(cipher)
    return plain
