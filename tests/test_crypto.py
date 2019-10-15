from flask_common.crypto import aes_encrypt, aes_decrypt, aes_generate_key


def test_new_decrypt_function_can_process_old_data():
    data = 'test'

    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher the old
    # encrypted data.
    key = b"\xe6\xb53\x90\xb8\x8f'-=e\x86z\xc3\x90\xff\xb8*\xf5\xd9\xaf\xb8\xad\x81\xcadl\xed\xf4\t\xe8\x9c*\r\x16\xd2\x00/\xd8\x86@)\xc1\x9b\x8d\xabo\xf7E\xbc\xf8\xae@\x98O\xf0\xd8[\xd0\xe1\x9a\xf5w\x03r"
    encrypted_data = b'o\x15\n\xef\x9a\xd62\x86\x81\x9cBS%\xfa\xf7\xdb\x1a\x9a9\xd2\xf8;\xe5\xc1\xd8l\x16\xdeH?\xcd\xd7D\x9d\xcd\xc2\x1ej\xabb\x86\xa4u@\x9f\x1b\xe2}FtQ\xd9\x1f\xd7\xa4\xc1\xe8\x94N\n\xe9\xb2\xa0\xccD2\xe9)'

    assert aes_decrypt(key, encrypted_data) == data


def test_new_decrypt_function_can_process_old_data_with_v2_marker():
    data = 'test'

    # These were generated using the old encrypt functions.
    # We make sure the new functions can still decypher the old
    # encrypted data.
    key = b'\xfe\xaf`\xa9UsC\xd5r\x00mm\x7f\x199\x96&]\xd6xI(*l\xb2\xe0\x9b\xb3&\\\x11\xe5\xcc\x9d\x92\xe8\x17)\x13\xf1\xcb\xf2=\xb6\x13Uv\xc6\x91\x1c@]\x8a\x91b\x07|\xb3\xa2\xb8\x8bJ\x88\xee'
    encrypted_data = b'v21uM\xf7\x17\xd7\xa4\x167\xa0W\xf8<?\xde_\xc0@\xf6\x0c\xd21 Q\xbc1\xb9\xa9\xb8\x87\xd1x\xff\x86\x1e\xb5\xa6\x80\xa60\xaf^v\xc6\xba]ir\xd9\x9b\xfe7\xe0\xd46\xc0?\xb0\xa6n\xfe]\xcf\xacq '

    assert aes_decrypt(key, encrypted_data) == data


def test_new_decrypt_function_can_process_new_data():
    data = 'test'
    key = aes_generate_key()
    assert aes_decrypt(key, aes_encrypt(key, data)) == data
