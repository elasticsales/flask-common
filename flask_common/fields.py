import re
import pytz
from mongoengine.fields import ReferenceField, StringField, BinaryField, ListField
from phonenumbers.phonenumberutil import format_number, parse, PhoneNumberFormat, NumberParseException
from flask.ext.common.utils import isortedset
from bson import Binary
from bson.dbref import DBRef
from Crypto.Cipher import AES
from Crypto import Random
from blist import sortedset
import Padding


class TrimmedStringField(StringField):
    def __init__(self, *args, **kwargs):
        kwargs['required'] = kwargs.get('required', False) or kwargs.get('min_length', 0) > 0
        return super(TrimmedStringField, self).__init__(*args, **kwargs)

    def validate(self, value):
        super(TrimmedStringField, self).validate(value)
        if self.required and not value:
            self.error('Value cannot be blank.')

    def __set__(self, instance, value):
        value = self.to_python(value)
        return super(TrimmedStringField, self).__set__(instance, value)

    def to_python(self, value):
        if value:
            value = value.strip()
        return value

    def to_mongo(self, value):
        return self.to_python(value)


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
    set_class = sortedset

    def __init__(self, field, **kwargs):
        if 'key' in kwargs.keys():
            self._key = kwargs.pop('key')
        super(SortedSetField, self).__init__(field, **kwargs)

    def to_mongo(self, value):
        value = super(SortedSetField, self).to_mongo(value)
        if self._key is not None:
            return list(self.set_class(value, key=self._key))
        else:
            return list(self.set_class(value))


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

    def _parse(self, value):
        parsed = parse(value, 'US')

        # strip empty extension
        if parsed.country_code == 1 and len(str(parsed.national_number)) > 10:
            regex = re.compile('.+\s*e?xt?\.?\s*$')
            if regex.match(value):
                value = re.sub('\s*e?xt?\.?\s*$', '', value)
                new_parsed = parse(value, 'US')
                if len(str(new_parsed)) >= 10:
                    parsed = new_parsed

        return parsed

    def __set__(self, instance, value):
        value = self.to_python(value)
        return super(PhoneField, self).__set__(instance, value)

    def validate(self, value):
        if not self.required and not value:
            return None
        else:
            try:
                self._parse(value)
            except NumberParseException:
                self.error('Phone is not valid')

    def to_python(self, value):
        return self.to_raw_phone(value)

    def to_mongo(self, value):
        return self.to_raw_phone(value)

    def to_formatted_phone(self, value):
        if isinstance(value, basestring) and value != '':
            try:
                phone = self._parse(value)
                value = format_number(phone, PhoneNumberFormat.INTERNATIONAL)
            except NumberParseException:
                pass
        return value

    def to_raw_phone(self, value):
        if isinstance(value, basestring) and value != '':
            try:
                phone = self._parse(value)
                value = format_number(phone, PhoneNumberFormat.E164)
                if phone.extension:
                    value += 'x%s' % phone.extension
            except NumberParseException:
                pass
        return value

    def prepare_query_value(self, op, value):
        return self.to_raw_phone(value)


rng = Random.new().read

class EncryptedStringField(BinaryField):
    """
    Encrypted string field. Uses AES256 bit encryption with a different 128 bit
    IV every time the field is saved. Encryption is completely transparent to
    the user as the field automatically unencrypts when the field is accessed
    and encrypts when the document is saved.
    """

    IV_SIZE = 16

    def __init__(self, key, *args, **kwargs):
        """
        Key: 32 byte binary string containing the 256 bit AES key
        """
        self.key = key
        return super(EncryptedStringField, self).__init__(*args, **kwargs)

    def _encrypt(self, data):
        iv = rng(self.IV_SIZE)
        ret = Binary(iv + AES.new(self.key, AES.MODE_CBC, iv).encrypt(Padding.appendPadding(data)))
        return ret

    def _decrypt(self, data):
        iv, cipher = data[:self.IV_SIZE], data[self.IV_SIZE:]
        return Padding.removePadding(AES.new(self.key, AES.MODE_CBC, iv).decrypt(cipher))

    def to_python(self, value):
        return value and self._decrypt(value) or None

    def to_mongo(self, value):
        return value and self._encrypt(value) or None


class SafeReferenceListField(ListField):
    """
    Like a ListField, but doesn't return non-existing references when
    dereferencing, i.e. no DBRefs are returned. This means that the next time
    an object is saved, the non-existing references are removed and application
    code can rely on having only valid dereferenced objects.

    Must use ReferenceField as its field class.
    """
    def __get__(self, instance, owner):
        result = super(SafeReferenceListField, self).__get__(instance, owner)
        if instance is None:
            return result
        # modify the list in-place
        result[:] = [obj for obj in result if not isinstance(obj, DBRef)]
        return result


class SafeReferenceField(ReferenceField):
    """
    Like a ReferenceField, but doesn't return non-existing references when
    dereferencing, i.e. no DBRefs are returned. This means that the next time
    an object is saved, the non-existing references are removed and application
    code can rely on having only valid dereferenced objects.
    """
    def __get__(self, instance, owner):
        result = super(SafeReferenceField, self).__get__(instance, owner)
        if isinstance(result, DBRef):
            instance._data[self.name] = None
            instance._mark_as_changed(self.name)
            return None
        return result
