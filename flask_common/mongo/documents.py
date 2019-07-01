import os
import datetime
from flask import current_app
from zbase62 import zbase62
from mongoengine import *
from mongoengine.queryset import OperationError
from mongoengine.errors import ValidationError

from flask_common.utils.lists import grouper


class StringIdField(StringField):
    def to_mongo(self, value):
        if not isinstance(value, basestring):
            raise ValidationError(errors={self.name: ['StringIdField only accepts string values.']})
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
                self.id = u'%s_%s' % (self.get_pk_prefix(), zbase62.b2a(os.urandom(32)))

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
            if unicode(err).startswith(u'Tried to save duplicate unique keys (E11000 duplicate key error index: %s.%s.$_id_ ' % (self._get_db().name, self._get_collection_name())):
                return self.save(*args, **kwargs)
            else:
                raise

    meta = {
        'abstract': True,
    }


class DocumentBase(Document):
    date_created = DateTimeField(required=True)
    date_updated = DateTimeField(required=True)

    meta = {
        'abstract': True,
    }

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
    def __call__(self, q_obj=None, class_check=True, slave_okay=False, read_preference=None, **query):
        # we don't use __ne=True here, because $ne isn't a selective query and doesn't utilize an index in the most efficient manner (http://docs.mongodb.org/manual/faq/indexes/#using-ne-and-nin-in-a-query-is-slow-why)
        extra_q_obj = Q(is_deleted=False)
        q_obj = q_obj & extra_q_obj if q_obj else extra_q_obj
        return super(NotDeletedQuerySet, self).__call__(q_obj, class_check, slave_okay, read_preference, **query)

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
            doc_cls._all_objs_queryset = QuerySet(doc_cls, doc_cls._get_collection())
        return doc_cls._all_objs_queryset

    meta = {
        'abstract': True,
        'queryset_class': NotDeletedQuerySet,
    }


class ForbiddenQueryException(Exception):
    """Exception raised by ForbiddenQueriesQuerySet"""


class ForbiddenQueriesQuerySet(QuerySet):
    """
    A queryset you can use to block some potentially dangerous queries
    just before they're sent to MongoDB. Override this queryset with a list
    of forbidden queries and then use the overridden class in a Document's
    meta['queryset_class'].

    `forbidden_queries` should be a list of dicts in the form of:
    {
        # shape of a query, e.g. `{"_cls": {"$in": 1}}`
        'query_shape': {...},

        # optional, forbids *all* orderings by default
        'orderings': [{key: direction, ...}, None, etc.]

        # optional, defaults to 0. Even if the query matches the shape and
        # the ordering, we allow queries with limit < `max_allowed_limit`.
        'max_allowed_limit': int or None
    }

    You can mark *any* queryset as safe with `mark_as_safe`.
    """
    forbidden_queries = None  # override this in a subclass

    _marked_as_safe = False

    def _check_for_forbidden_queries(self, idx_key=None):
        # idx_key can be a slice or an int from Doc.objects[idx_key]
        is_testing = False
        try:
            is_testing = current_app.testing
        except RuntimeError:
            pass

        if self._marked_as_safe or self._none or is_testing:
            return

        query_shape = self._get_query_shape(self._query)
        for forbidden in self.forbidden_queries:
            if (
                query_shape == forbidden['query_shape'] and
                (not forbidden.get('orderings') or self._ordering in forbidden['orderings'])
            ):

                # determine the real limit based on objects.limit or objects[idx_key]
                limit = self._limit
                if limit is None and idx_key is not None:
                    if isinstance(idx_key, slice):
                        limit = idx_key.stop
                    else:
                        limit = idx_key

                if limit is None or limit > forbidden.get('max_allowed_limit', 0):
                    raise ForbiddenQueryException(
                        'Forbidden query used! Query: %s, Ordering: %s, Limit: %s' % (
                            self._query, self._ordering, limit
                        )
                    )

    def next(self):
        self._check_for_forbidden_queries()
        return super(ForbiddenQueriesQuerySet, self).next()

    def __getitem__(self, key):
        self._check_for_forbidden_queries(key)
        return super(ForbiddenQueriesQuerySet, self).__getitem__(key)

    def mark_as_safe(self):
        """
        If you call Doc.objects.filter(...).mark_as_safe(), you can query by
        whatever you want (including the forbidden queries).
        """
        self._marked_as_safe = True
        return self

    def _get_query_shape(self, query):
        """
        Convert a query into a query shape, e.g.:
        * `{"_cls": "whatever"}` into `{"_cls": 1}`
        * `{"date": {"$gte": '2015-01-01', "$lte": "2015-01-31"}` into
          `{"date": {"$gte": 1, "$lte": 1}}`
        * `{"_cls": {"$in": ["a", "b", "c"]}}` into `{"_cls": {"$in": []}}`
        """
        if not query:
            return query

        query_shape = {}
        for key, val in query.items():
            if isinstance(val, dict):
                query_shape[key] = self._get_query_shape(val)
            elif isinstance(val, (list, tuple)):
                query_shape[key] = []
            else:
                query_shape[key] = 1
        return query_shape
