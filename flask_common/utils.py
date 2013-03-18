import re
import csv
import base64
import codecs
import datetime
import cStringIO
import unidecode
from logging.handlers import SMTPHandler


class DetailedSMTPHandler(SMTPHandler):
    def __init__(self, app_name, *args, **kwargs):
        self.app_name = app_name
        return super(DetailedSMTPHandler, self).__init__(*args, **kwargs)

    def getSubject(self, record):
        from flask import request
        from socket import gethostname
        error = 'Error'
        ei = record.exc_info
        if ei:
            error = '(%s) %s' % (ei[0].__name__, ei[1])
        return "[%s] %s %s on %s" % (self.app_name, request.path, error, gethostname())

    def emit(self, record):
        """
        Emit a record.

        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib
            from email.utils import formatdate
            from flask import request
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\nTo: %s\nSubject: %s\nDate: %s\n\n%s\n\nRequest.url: %s\n\nRequest.headers: %s\n\nRequest.args: %s\n\nRequest.form: %s\n\nRequest.data: %s\n" % (
                            self.fromaddr,
                            ",".join(self.toaddrs),
                            self.getSubject(record),
                            formatdate(), msg, request.url, request.headers, request.args, request.form, request.data)
            if self.username:
                if self.secure is not None:
                    smtp.ehlo()
                    smtp.starttls(*self.secure)
                    smtp.ehlo()
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

def unicode_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data),
                            dialect=dialect, **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, 'utf-8') for cell in row]

def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        yield line.encode('utf-8')

"""
Wrapper around csv reader that ignores non utf-8 chars and strips the record
"""
class CsvReader(object):
    def __init__(self, file_name, delimiter=','):
        self.reader = csv.reader(open(file_name, 'rbU'), delimiter=delimiter)

    def __iter__(self):
        return self

    def next(self):
        row = self.reader.next()
        row = [el.decode('utf8', errors='ignore').replace('\"', '').strip() for el in row]
        return row

class CsvWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    From http://docs.python.org/2/library/csv.html
    """
    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

def smart_unicode(s, encoding='utf-8', errors='strict'):
    if isinstance(s, unicode):
        return s
    if not isinstance(s, basestring,):
        if hasattr(s, '__unicode__'):
            s = unicode(s)
        else:
            s = unicode(str(s), encoding, errors)
    elif not isinstance(s, unicode):
        s = s.decode(encoding, errors)
    return s


class Enum(object):
    @classmethod
    def choices(cls):
        return [(getattr(cls,v), v) for v in dir(cls) if not callable(getattr(cls,v)) and not (v.startswith('__') and v.endswith('__'))]

def grouper(n, iterable):
    # e.g. 2, [1, 2, 3, 4, 5] -> [[1, 2], [3, 4], [5]]
    return [iterable[i:i+n] for i in range(0, len(iterable), n)]


def utctoday():
    now = datetime.datetime.utcnow()
    today = datetime.date(*now.timetuple()[:3])
    return today


def localtoday(tz):
    import pytz
    local_now = tz.normalize(pytz.utc.localize(datetime.datetime.utcnow()).astimezone(tz))
    local_today = datetime.date(*local_now.timetuple()[:3])
    return local_today


def mail_exception(extra_subject=None, context=None, vars=True, subject=None, recipients=None):
    from socket import gethostname
    import traceback, sys
    from flask import current_app, request

    exc_info = sys.exc_info()

    if not subject:
        subject = "[%s] %s%s %s on %s" % (request.host, extra_subject and '%s: ' % extra_subject or '', request.path, exc_info[1].__class__.__name__, gethostname())

    message = ''

    if context:
        message += 'Context:\n\n'
        try:
            message += '\n'.join(['%s: %s' % (k, context[k]) for k in sorted(context.keys())])
        except:
            message += 'Error reporting context.'
        message += '\n\n\n\n'


    if vars:
        tb = exc_info[2]
        stack = []

        while tb:
            stack.append(tb.tb_frame)
            tb = tb.tb_next

        message += "Locals by frame, innermost last:\n"

        for frame in stack:
            message += "\nFrame %s in %s at line %s\n" % (frame.f_code.co_name,
                                                 frame.f_code.co_filename,
                                                 frame.f_lineno)
            for key, value in frame.f_locals.items():
                message += "\t%16s = " % key
                # We have to be careful not to cause a new error in our error
                # printer! Calling repr() on an unknown object could cause an
                # error we don't want.
                try:
                    message += '%s\n' % repr(value)
                except:
                    message += "<ERROR WHILE PRINTING VALUE>\n"


    message += '\n\n\n%s\n' % (
            '\n'.join(traceback.format_exception(*exc_info)),
        )

    recipients = recipients if recipients else current_app.config['ADMINS']

    if not current_app.testing:
        if current_app.debug:
            print subject
            print
            print message
        else:
            from flask.ext.mail import Mail, Message
            msg = Message(subject, sender=current_app.config['SERVER_EMAIL'], recipients=recipients)
            msg.body = message
            current_app.mail.send(msg)


def force_unicode(s):
    # Return a unicode object, no matter what the string is.

    if isinstance(s, unicode):
        return s
    try:
        return s.decode('utf8')
    except UnicodeDecodeError:
        # most common encoding, conersion shouldn't fail
        return s.decode('latin1')

# Applies a function to objects by traversing lists/tuples/dicts recursively.
def apply_recursively(obj, f):
    if isinstance(obj, (list, tuple)):
        return [apply_recursively(item, f) for item in obj]
    elif isinstance(obj, dict):
        return {k: apply_recursively(v, f) for k, v in obj.iteritems()}
    elif obj == None:
        return None
    else:
        return f(obj)

import time

class Timer(object):
    def __enter__(self):
        self.start = time.clock()
        return self

    def __exit__(self, *args):
        self.end = time.clock()
        self.interval = self.end - self.start
