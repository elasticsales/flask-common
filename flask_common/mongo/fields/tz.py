import pytz
from builtins import str

from mongoengine.fields import StringField


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
        return str(value)
