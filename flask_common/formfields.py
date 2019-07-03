import dateutil.parser
from wtforms.fields import DateTimeField


class BetterDateTimeField(DateTimeField):
    """ Like DateTimeField, but uses dateutil.parser to parse the date """

    def process_formdata(self, valuelist):
        if valuelist:
            date_str = u' '.join(valuelist)
            # dateutil returns the current day if passing an empty string.
            if date_str.strip():
                try:
                    self.data = dateutil.parser.parse(date_str)
                except ValueError:
                    self.data = None
                    raise
            else:
                self.data = None
