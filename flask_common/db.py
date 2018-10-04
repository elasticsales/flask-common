from bson import ObjectId
import uuid
import sqlalchemy as db
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship, synonym

__all__ = ['MongoReference', 'MongoEmbedded', 'MongoEmbeddedList', 'Base', 'UserBase']

def MongoReference(field, ref_cls, queryset=None):
    """
    Reference to a MongoDB document.

    The value is cached until an assignment is made.

    To use a custom queryset (instead of the default `ref_cls.objects`),
    pass it as the `queryset` kwarg.
    """
    if queryset is None:
        queryset = ref_cls.objects

    def _get(obj):
        if not hasattr(obj, '_%s__cache' % field):
            ref_id = getattr(obj, field)
            if ref_id is None:
                ref = None
            else:
                ref = queryset.get(pk=ref_id)
            setattr(obj, '_%s__cache' % field, ref)
        return getattr(obj, '_%s__cache' % field)

    def _set(obj, val):
        if hasattr(obj, '_%s__cache' % field):
            delattr(obj, '_%s__cache' % field)
        if isinstance(val, ref_cls):
            val = val.pk
        if isinstance(val, ObjectId):
            val = str(val)
        setattr(obj, field, val)

    return synonym(field, descriptor=property(_get, _set))

def MongoEmbedded(field, emb_cls):
    """
    Converts the JSON value to/from an EmbeddedDocument. Note that a new
    instance is returned every time we access and we must reassign any changes
    back to the model.
    """
    def _get(obj):
        return emb_cls._from_son(getattr(obj, field))
    def _set(obj, val):
        setattr(obj, field, val.to_mongo())
    return synonym(field, descriptor=property(_get, _set))

def MongoEmbeddedList(field, emb_cls):
    def _get(obj):
        return [emb_cls._from_son(item) for item in getattr(obj, field)]
    def _set(obj, val):
        setattr(obj, field, [item.to_mongo() for item in val])
    return synonym(field, descriptor=property(_get, _set))

# From https://code.launchpad.net/~stefanor/ibid/sqlalchemy-0.6-trunk/+merge/66033
class PGSQLModeListener(object):
    def connect(self, dbapi_con, con_record):
        c = dbapi_con.cursor()
        c.execute("SET TIME ZONE UTC")
        c.close()

class Base(object):
    id = db.Column(UUID, default=lambda: str(uuid.uuid4()), primary_key=True)
    created_at = db.Column(db.DateTime(), default=db.func.now())
    updated_at = db.Column(db.DateTime(), default=db.func.now(), onupdate=db.func.now())

    @property
    def pk(self):
        return self.id

    __mapper_args__ = {
        'order_by': db.desc('updated_at')
    }

class UserBase(Base):
    created_by_id = declared_attr(lambda cls: db.Column(UUID, db.ForeignKey('user.id'), default=cls._get_current_user))
    created_by = declared_attr(lambda cls: relationship('User', primaryjoin='%s.created_by_id == User.id' % cls.__name__))
    updated_by_id = declared_attr(lambda cls: db.Column(UUID, db.ForeignKey('user.id'), default=cls._get_current_user, onupdate=cls._get_current_user))
    updated_by = declared_attr(lambda cls: relationship('User', primaryjoin='%s.updated_by_id == User.id' % cls.__name__))

    @classmethod
    def _get_current_user(cls):
        return None
