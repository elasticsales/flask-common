from mongoengine.fields import StringField, EmailField


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

