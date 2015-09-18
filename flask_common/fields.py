import re
import pytz
import phonenumbers
from bson import Binary
from sortedcontainers import SortedSet
from mongoengine.fields import StringField, BinaryField, ListField, EmailField

from flask.ext.common.utils import isortedset
from flask.ext.common.crypto import aes_encrypt, aes_decrypt, AuthenticationError, KEY_LENGTH


class TrimmedStringField(StringField):
    def __init__(self, *args, **kwargs):
        kwargs['required'] = kwargs.get('required', False) or kwargs.get('min_length', 0) > 0
        return super(TrimmedStringField, self).__init__(*args, **kwargs)

    def validate(self, value):
        super(TrimmedStringField, self).validate(value)
        if self.required and not value:
            self.error('Value cannot be blank.')

    def from_python(self, value):
        return value and value.strip()

    def to_mongo(self, value):
        return self.from_python(value)


class LowerStringField(StringField):
    def from_python(self, value):
        return value and value.lower()

    def to_python(self, value):
        return value and value.lower()

    def prepare_query_value(self, op, value):
        return super(LowerStringField, self).prepare_query_value(op, value and value.lower())


class LowerEmailField(StringField):
    def from_python(self, value):
        return value and value.lower().strip()

    def to_python(self, value):
        return self.from_python(value)

    def prepare_query_value(self, op, value):
        return super(LowerEmailField, self).prepare_query_value(op, value and value.lower().strip())

    def validate(self, value):
        if not EmailField.EMAIL_REGEX.match(value):
            self.error('Invalid email address: %s' % value)
        super(LowerEmailField, self).validate(value)


class TimezoneField(StringField):
    def __init__(self, *args, **kwargs):
        defaults = {
            'default': 'UTC',
            'choices': tuple(zip(pytz.all_timezones, pytz.all_timezones)),
        }
        defaults.update(kwargs)
        return super(TimezoneField, self).__init__(*args, **defaults)

    def to_python(self, value):
        return pytz.timezone(value)

    def to_mongo(self, value):
        return unicode(value)


class SortedSetField(ListField):
    """Like a ListField but sorts and de-duplicates items in the list before
    writing to the database in order to ensure that a sorted list is always retrieved.

    key = key to sort by

    .. warning::
        There is a potential race condition when handling lists.  If you set /
        save the whole list then other processes trying to save the whole list
        as well could overwrite changes.  The safest way to append to a list is
        to perform a push operation.
    """

    _key = None
    set_class = SortedSet

    def __init__(self, field, **kwargs):
        if 'key' in kwargs.keys():
            self._key = kwargs.pop('key')
        super(SortedSetField, self).__init__(field, **kwargs)

    def to_mongo(self, value):
        value = super(SortedSetField, self).to_mongo(value) or []
        if self._key is not None:
            return list(self.set_class(value, key=self._key)) or None
        else:
            return list(self.set_class(value)) or None


class ISortedSetField(SortedSetField):
    set_class = isortedset

    def __init__(self, field, **kwargs):
        kwargs['key'] = lambda s: s.lower()
        super(ISortedSetField, self).__init__(field, **kwargs)


class PhoneField(StringField):
    """
    Field that performs phone number validation.
    Values are stored in the format "+14151231234x123" in MongoDB and displayed
    in the format "+1 415-123-1234 ext. 123" in Python.
    """

    def __init__(self, *args, **kwargs):
        self._strict_validation = kwargs.pop('strict', False)
        super(PhoneField, self).__init__(*args, **kwargs)

    @classmethod
    def _parse(cls, value, region=None):
        # valid numbers don't start with the same digit(s) as their country code so we strip them
        country_code = phonenumbers.country_code_for_region(region)
        if country_code and value.startswith(str(country_code)):
            value = value[len(str(country_code)):]

        parsed = phonenumbers.parse(value, region)

        # strip empty extension
        if parsed.country_code == 1 and len(str(parsed.national_number)) > 10:
            regex = re.compile('.+\s*e?xt?\.?\s*$')
            if regex.match(value):
                value = re.sub('\s*e?xt?\.?\s*$', '', value)
                new_parsed = phonenumbers.parse(value, region)
                if len(str(new_parsed)) >= 10:
                    parsed = new_parsed

        return parsed

    def validate(self, value):
        if not self.required and not value:
            return None

        error_msg = 'Phone number is not valid. Please use the international format like +16505551234'
        try:
            number = PhoneField._parse(value)

            if self._strict_validation and not phonenumbers.is_valid_number(number):
                raise phonenumbers.NumberParseException(phonenumbers.NumberParseException.NOT_A_NUMBER, error_msg)

        except phonenumbers.NumberParseException:
            self.error(error_msg)

    def from_python(self, value):
        return PhoneField.to_raw_phone(value)

    def _get_formatted_phone(self, value, form):
        if isinstance(value, basestring) and value != '':
            try:
                phone = PhoneField._parse(value)
                value = phonenumbers.format_number(phone, form)
            except phonenumbers.NumberParseException:
                pass
        return value

    def to_formatted_phone(self, value):
        return self._get_formatted_phone(value, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

    def to_local_formatted_phone(self, value):
        return self._get_formatted_phone(value, phonenumbers.PhoneNumberFormat.NATIONAL)

    @classmethod
    def to_raw_phone(self, value, region=None):
        if isinstance(value, basestring) and value != '':
            try:
                number = value
                phone = PhoneField._parse(number, region)
                number = phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)
                if phone.extension:
                    number += 'x%s' % phone.extension
                return number
            except phonenumbers.NumberParseException:
                pass
        return value

    def prepare_query_value(self, op, value):
        return super(PhoneField, self).prepare_query_value(op, PhoneField.to_raw_phone(value))


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
        return value and self._decrypt(value) or None

    def to_mongo(self, value):
        return value and self._encrypt(value) or None
