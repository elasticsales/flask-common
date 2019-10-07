import re

import phonenumbers
from mongoengine.fields import StringField


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
            value = value[len(str(country_code)) :]

        parsed = phonenumbers.parse(value, region)

        # strip empty extension
        if parsed.country_code == 1 and len(str(parsed.national_number)) > 10:
            regex = re.compile(r'.+\s*e?xt?\.?\s*$')
            if regex.match(value):
                value = re.sub(r'\s*e?xt?\.?\s*$', '', value)
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

            if self._strict_validation and not phonenumbers.is_valid_number(
                number
            ):
                raise phonenumbers.NumberParseException(
                    phonenumbers.NumberParseException.NOT_A_NUMBER, error_msg
                )

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
        return self._get_formatted_phone(
            value, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )

    def to_local_formatted_phone(self, value):
        return self._get_formatted_phone(
            value, phonenumbers.PhoneNumberFormat.NATIONAL
        )

    @classmethod
    def to_raw_phone(cls, value, region=None):
        if isinstance(value, basestring) and value != '':
            try:
                number = value
                phone = PhoneField._parse(number, region)
                number = phonenumbers.format_number(
                    phone, phonenumbers.PhoneNumberFormat.E164
                )
                if phone.extension:
                    number += 'x%s' % phone.extension
                return number
            except phonenumbers.NumberParseException:
                pass
        return value

    def prepare_query_value(self, op, value):
        return super(PhoneField, self).prepare_query_value(
            op, PhoneField.to_raw_phone(value)
        )
