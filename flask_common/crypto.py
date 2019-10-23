import hashlib
import hmac
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

backend = default_backend()

AES_KEY_SIZE = 32  # 256 bits
HMAC_KEY_SIZE = 32  # 256 bits
IV_SIZE = 16  # 128 bits
HMAC_DIGEST = hashlib.sha256
HMAC_DIGEST_SIZE = hashlib.sha256().digest_size
KEY_LENGTH = AES_KEY_SIZE + HMAC_KEY_SIZE

rng = os.urandom

V0_MARKER = b'\x00'
V1_MARKER = b'\x01'


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
    iv = rng(IV_SIZE)
    return V1_MARKER + iv + aes_encrypt_iv(key, data, iv)


# Verify + decrypt data encrypted with IV
def aes_decrypt(key, data):
    assert len(key) == KEY_LENGTH, 'invalid key size'
    extracted_version = data[0]
    data = data[1:]
    if extracted_version == V0_MARKER:
        iv = data[:AES_KEY_SIZE]
        data = data[AES_KEY_SIZE:]
    else:
        iv = data[:IV_SIZE]
        data = data[IV_SIZE:]
    return aes_decrypt_iv(key, data, iv, extracted_version)


# Encrypt + sign using no IV or provided IV. Pass empty string for no IV.
# Note: You should normally use aes_encrypt()
def aes_encrypt_iv(key, data, iv):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    encryptor = Cipher(
        algorithms.AES(aes_key), modes.CTR(iv), backend=backend
    ).encryptor()
    cipher = encryptor.update(data) + encryptor.finalize()
    sig = hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest()
    return cipher + sig


# Verify + decrypt using no IV or provided IV. Pass empty string for no IV.
# Note: You should normally use aes_decrypt()
def aes_decrypt_iv(key, data, iv, extracted_version):
    aes_key = key[:AES_KEY_SIZE]
    hmac_key = key[AES_KEY_SIZE:]
    sig_size = HMAC_DIGEST_SIZE
    cipher = data[:-sig_size]
    sig = data[-sig_size:]
    if hmac.new(hmac_key, iv + cipher, HMAC_DIGEST).digest() != sig:
        raise AuthenticationError('message authentication failed')
    if extracted_version == V0_MARKER:
        iv = iv[IV_SIZE:]
    decryptor = Cipher(
        algorithms.AES(aes_key), modes.CTR(iv), backend=backend
    ).decryptor()
    return decryptor.update(cipher) + decryptor.finalize()
