import os
import datetime

from zbase62 import zbase62
from mongoengine import (
    BooleanField,
    DateTimeField,
    Document,
    OperationError,
    Q,
    QuerySet,
    StringField,
    ValidationError,
    queryset_manager,
)


class StringIdField(StringField):
    def to_mongo(self, value):
        if not isinstance(value, basestring):
            raise ValidationError(
                errors={
                    self.name: ['StringIdField only accepts string values.']
                }
            )
        return super(StringIdField, self).to_mongo(value)


class RandomPKDocument(Document):
    id = StringIdField(primary_key=True)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.id)

    @classmethod
    def get_pk_prefix(cls):
        return cls._get_collection_name()[:4]

    def save(self, *args, **kwargs):
        old_id = self.id

        # Don't cascade saves by default.
        kwargs['cascade'] = kwargs.get('cascade', False)

        try:

            if not self.id:
                self.id = u'%s_%s' % (
                    self.get_pk_prefix(),
                    zbase62.b2a(os.urandom(32)),
                )

                # Throw an exception if another object with this id already exists.
                kwargs['force_insert'] = True

                # But don't do that when cascading.
                kwargs['cascade_kwargs'] = {'force_insert': False}

            return super(RandomPKDocument, self).save(*args, **kwargs)
        except OperationError as err:
            self.id = old_id

            # Use "startswith" instead of "in". Otherwise, if a free form
            # StringField had a unique constraint someone could inject that
            # string into the error message.
            if unicode(err).startswith(
                u'Tried to save duplicate unique keys (E11000 duplicate key error index: %s.%s.$_id_ '
                % (self._get_db().name, self._get_collection_name())
            ):
                return self.save(*args, **kwargs)
            else:
                raise

    meta = {'abstract': True}


class DocumentBase(Document):
    date_created = DateTimeField(required=True)
    date_updated = DateTimeField(required=True)

    meta = {'abstract': True}

    def _type(self):
        return unicode(self.__class__.__name__)

    def save(self, *args, **kwargs):
        update_date = kwargs.pop('update_date', True)
        kwargs['cascade'] = kwargs.get('cascade', False)
        if update_date:
            now = datetime.datetime.utcnow()
            if not self.date_created:
                self.date_created = now
            self.date_updated = now
        return super(DocumentBase, self).save(*args, **kwargs)

    def modify(self, *args, **kwargs):
        update_date = kwargs.pop('update_date', True)
        if update_date and 'set__date_updated' not in kwargs:
            kwargs['set__date_updated'] = datetime.datetime.utcnow()
        return super(DocumentBase, self).modify(*args, **kwargs)

    def update(self, *args, **kwargs):
        update_date = kwargs.pop('update_date', True)
        if update_date and 'set__date_updated' not in kwargs:
            kwargs['set__date_updated'] = datetime.datetime.utcnow()
        super(DocumentBase, self).update(*args, **kwargs)


class NotDeletedQuerySet(QuerySet):
    def __call__(
        self,
        q_obj=None,
        class_check=True,
        slave_okay=False,
        read_preference=None,
        **query
    ):
        # we don't use __ne=True here, because $ne isn't a selective query and doesn't utilize an index in the most efficient manner (http://docs.mongodb.org/manual/faq/indexes/#using-ne-and-nin-in-a-query-is-slow-why)
        extra_q_obj = Q(is_deleted=False)
        q_obj = q_obj & extra_q_obj if q_obj else extra_q_obj
        return super(NotDeletedQuerySet, self).__call__(
            q_obj, class_check, slave_okay, read_preference, **query
        )

    def count(self, *args, **kwargs):
        # we need this hack for doc.objects.count() to exclude deleted objects
        if not getattr(self, '_not_deleted_query_applied', False):
            self = self.all()
        return super(NotDeletedQuerySet, self).count(*args, **kwargs)


class SoftDeleteDocument(Document):
    is_deleted = BooleanField(default=False, required=True)

    def modify(self, **kwargs):
        if 'set__is_deleted' in kwargs and kwargs['set__is_deleted'] is None:
            raise ValidationError('is_deleted cannot be set to None')
        return super(SoftDeleteDocument, self).modify(**kwargs)

    def update(self, **kwargs):
        if 'set__is_deleted' in kwargs and kwargs['set__is_deleted'] is None:
            raise ValidationError('is_deleted cannot be set to None')
        super(SoftDeleteDocument, self).update(**kwargs)

    def delete(self, **kwargs):
        # delete only if already saved
        if self.pk:
            self.is_deleted = True
            self.modify(set__is_deleted=self.is_deleted)

    @queryset_manager
    def all_objects(doc_cls, queryset):
        if not hasattr(doc_cls, '_all_objs_queryset'):
            doc_cls._all_objs_queryset = QuerySet(
                doc_cls, doc_cls._get_collection()
            )
        return doc_cls._all_objs_queryset

    meta = {'abstract': True, 'queryset_class': NotDeletedQuerySet}
