import uuid

from zbase62 import zbase62


def uuid_to_id(uuid_obj, prefix):
    return '{}_{}'.format(prefix, zbase62.b2a(uuid_obj.bytes))


def id_to_uuid(id_str):
    uuid_bytes = zbase62.a2b(str(id_str[id_str.find('_') + 1:]))
    return uuid.UUID(bytes=uuid_bytes)
