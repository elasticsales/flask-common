import datetime
import unittest

from dateutil.tz import tzutc
from werkzeug.datastructures import MultiDict
from wtforms import Form

from flask_common.formfields import BetterDateTimeField


class FormFieldTestCase(unittest.TestCase):
    # TODO pytest-ify

    def test_datetime_field(self):
        class TestForm(Form):
            date = BetterDateTimeField()

        form = TestForm(MultiDict({'date': ''}))
        self.assertTrue(form.validate())
        self.assertEqual(form.data['date'], None)

        form = TestForm(MultiDict({'date': 'invalid'}))
        self.assertFalse(form.validate())

        form = TestForm(MultiDict({'date': '2012-09-06T01:29:14.107000+00:00'}))
        self.assertTrue(form.validate())
        self.assertEqual(
            form.data['date'],
            datetime.datetime(2012, 9, 6, 1, 29, 14, 107000, tzinfo=tzutc()),
        )

        form = TestForm(MultiDict({'date': '2012-09-06 01:29:14'}))
        self.assertTrue(form.validate())
        self.assertEqual(
            form.data['date'], datetime.datetime(2012, 9, 6, 1, 29, 14)
        )
