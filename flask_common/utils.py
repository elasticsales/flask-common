import re
import csv
import codecs
import datetime
import cStringIO
import unidecode
from blist import sortedset
from logging.handlers import SMTPHandler

class isortedset(sortedset):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('key'):
            kwargs['key'] = lambda s: s.lower()
        super(isortedset, self).__init__(*args, **kwargs)

    def __contains__(self, key):
        if not self:
            return False
        try:
            return self[self.bisect_left(key)].lower() == key.lower()
        except IndexError:
            return False

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

def slugify(str, separator='_'):
    str = unidecode.unidecode(str).lower().strip()
    return re.sub(r'\W+', separator, str).strip(separator)

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
import signal

class Timeout(Exception):
    pass

class Timer(object):
    # Timer class with an optional signal timer.
    # Raises a Timeout exception when the timeout occurs.
    # When using timeouts, you must not nest this function nor call it in
    # any thread other than the main thread.

    def __init__(self, timeout=None, timeout_message=''):
        self.timeout = timeout
        self.timeout_message = timeout_message

        if timeout:
            signal.signal(signal.SIGALRM, self._alarm_handler)

    def _alarm_handler(self, signum, frame):
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        raise Timeout(self.timeout_message)

    def __enter__(self):
        if self.timeout:
            signal.alarm(self.timeout)
        self.start = datetime.datetime.utcnow()
        return self

    def __exit__(self, *args):
        self.end = datetime.datetime.utcnow()
        delta = (self.end - self.start)
        self.interval = delta.days * 86400 + delta.seconds + delta.microseconds / 1000000.
        if self.timeout:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, signal.SIG_IGN)


import threading

# Semaphore implementation from Python 3 which supports timeouts.
class Semaphore(threading._Verbose):

    # After Tim Peters' semaphore class, but not quite the same (no maximum)

    def __init__(self, value=1, verbose=None):
        if value < 0:
            raise ValueError("semaphore initial value must be >= 0")
        threading._Verbose.__init__(self, verbose)
        self._cond = threading.Condition(threading.Lock())
        self._value = value

    def acquire(self, blocking=True, timeout=None):
        if not blocking and timeout is not None:
            raise ValueError("can't specify timeout for non-blocking acquire")
        rc = False
        endtime = None
        self._cond.acquire()
        while self._value == 0:
            if not blocking:
                break
            if __debug__:
                self._note("%s.acquire(%s): blocked waiting, value=%s",
                           self, blocking, self._value)
            if timeout is not None:
                if endtime is None:
                    endtime = threading._time() + timeout
                else:
                    timeout = endtime - threading._time()
                    if timeout <= 0:
                        break
            self._cond.wait(timeout)
        else:
            self._value = self._value - 1
            if __debug__:
                self._note("%s.acquire: success, value=%s",
                           self, self._value)
            rc = True
        self._cond.release()
        return rc

    __enter__ = acquire

    def release(self):
        self._cond.acquire()
        self._value = self._value + 1
        if __debug__:
            self._note("%s.release: success, value=%s",
                       self, self._value)
        self._cond.notify()
        self._cond.release()

    def __exit__(self, t, v, tb):
        self.release()


class ThreadedTimer(object):
    # Timer class with an optional threaded timer.
    # By default, interrupts the main thread with a KeyboardInterrupt.

    def __init__(self, timeout=None, on_timeout=None):
        self.timeout = timeout
        self.on_timeout = on_timeout or self._timeout_handler

    def _timeout_handler(self):
        import thread
        thread.interrupt_main()

    def __enter__(self):
        if self.timeout:
            self._timer = threading.Timer(self.timeout, self.on_timeout)
            self._timer.start()
        self.start = datetime.datetime.utcnow()
        return self

    def __exit__(self, *args):
        if self.timeout:
            self._timer.cancel()
        self.end = datetime.datetime.utcnow()
        delta = (self.end - self.start)
        self.interval = delta.days * 86400 + delta.seconds + delta.microseconds / 1000000.
