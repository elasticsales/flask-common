import sys

if sys.version_info[0] > 2:
    collect_ignore = [
        'test_legacy.py',
        'test_declenum.py',
        'test_formfields.py',
        'mongo/test_documents.py',
        'mongo/test_utils.py',
        'mongo/fields/test_basic.py',
        'mongo/fields/test_phone.py',
        'mongo/fields/test_tz.py',
    ]
