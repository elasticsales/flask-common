# Basic fields that don't have any non-MongoEngine dependencies
from .basic import LowerEmailField, LowerStringField, TrimmedStringField

# Crypto fields
try:
    from .crypto import EncryptedStringField
except ImportError:
    pass

# Phone numbers fields
try:
    from .phone import PhoneField
except ImportError:
    pass

# Timezone fields
try:
    from .tz import TimezoneField
except ImportError:
    pass

# UUID fields
try:
    from .id import IDField
except ImportError:
    pass

__all__ = [
    'LowerEmailField',
    'LowerStringField',
    'TrimmedStringField',
    'EncryptedStringField',
    'PhoneField',
    'TimezoneField',
    'IDField',
]
