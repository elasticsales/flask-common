# UUID related helpers
try:
    from .id import id_to_uuid, uuid_to_id
except ImportError:
    pass

# List/iterator helpers
from .lists import grouper

# TODO: split these up
try:
    from .legacy import (
        CsvReader,
        CsvWriter,
        DetailedSMTPHandler,
        FileFormatException,
        NamedCsvReader,
        Reader,
        Normalization,
        NormalizationReader,
        ThreadedTimer,
        Timeout,
        Timer,
        apply_recursively,
        build_normalization_map,
        combine,
        finite_float,
        force_unicode,
        format_locals,
        json_list_generator,
        lazylist,
        localtoday,
        mail_admins,
        mail_exception,
        make_unaware,
        parse_date_tz,
        returns_xml,
        retry,
        slugify,
        smart_unicode,
        truncate,
        unicode_csv_reader,
        uniqify,
        utctime,
        utctoday,
        utf_8_encoder,
    )
except ImportError:
    pass
