import os
import datetime
from flask import current_app
from zbase62 import zbase62
from mongoengine import *
from mongoengine.queryset import OperationError
from mongoengine.errors import ValidationError

from .utils.lists import grouper


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


def fetch_related(objs, field_dict, cache_map=None, extra_filters={},
                  batch_size=100):
    """
    Recursively fetches related objects for the given document instances.
    Sample usage:

    fetch_related(objs, {
        'user': True,
        'lead': {
            'created_by': True,
            'updated_by': True,
        },
        'contact': ['id'],
    })

    In this sample, users and leads for all objs will be fetched and attached.
    Then, lead.created_by and lead.updated_by users are fetched in one query
    and attached. Finally, a contact will be pulled in, only fetching the ID
    from the database.

    Note that the function doesn't merge queries for the same document class
    across multiple (recursive) function calls, but it never fetches the same
    related object twice.

    Be *very* cautious when pulling in only specific fields for a related
    object. Accessing fields that haven't been pulled will falsely show None
    even if a value for that field exists in the database.

    Given how fragile partially pulled objects are, we don't cache them in the
    cache map and hence the same related object may be fetched more than once.

    If you need to call fetch_related multiple times, it's worth passing a
    cache_map (initially it can be an empty dictionary). It will be extended
    during each call to include all the objects fetched up until the current
    call. This way we ensure that the same objects aren't fetched more than
    once across multiple fetch_related calls. Cache map has a form of:
    { DocumentClass: { id_of_fetched_obj: obj, id_of_fetched_obj2: obj2 } }.

    The function takes an optional dict extra_filters in the form
    {document_class: filters} which will be passed as filters to the QuerySet.
    This can be useful to pass a shard key filter. For example, if the Contact
    model uses organization_id as a shard key, and all contacts are expected to
    be in the same organization, you can pass:
    {Contact: {'organization_id': organization.pk}}
    """
    if not objs:
        return

    # Cache map holds a map of pks to objs for objects we fetched, over all
    # iterations / from previous calls, by document class (doesn't include
    # partially fetched objects)
    if cache_map is None:
        cache_map = {}

    # Cache map for partial fetches (i.e. ones where only specific fields
    # were requested). is only temporary since we don't want to cache partial
    # data through subsequent calls of this function
    partial_cache_map = {}

    # Helper mapping: field_name -> (
    #   field instance,
    #   name of the field in the db,
    #   document class,
    #   fields to fetch (or None if the whole related obj should be fetched)
    # )
    field_info = {}

    # IDs to fetch and their fetch options, by document class
    fetch_map = {}

    def id_from_value(field, val):
        if field.dbref:
            return val.id
        else:
            return val

    def get_instance_for_each_type(objs):
        instances = []
        types = []
        for obj in objs:
            if type(obj) not in types:
                instances.append(obj)
                types.append(type(obj))
        return instances

    def setattr_unchanged(obj, key, val):
        """
        Sets an attribute on the given document object without changing the
        _changed_fields set. This is because we don't actually modify the
        related objects.
        """
        changed = key in obj._changed_fields
        setattr(obj, key, val)
        if not changed and key in obj._changed_fields:
            obj._changed_fields.remove(key)

    # Populate the field_info
    instances = get_instance_for_each_type(objs)
    for field_name, sub_field_dict in field_dict.iteritems():

        instance = [instance for instance in instances
                    if instance and field_name in instance.__class__._fields]
        if not instance:
            continue  # None of the objects contains this field

        instance = instance[0]
        field = instance.__class__._fields[field_name]
        db_field = instance._db_field_map.get(field_name, field_name)
        if isinstance(field, ReferenceField):  # includes SafeReferenceListField
            document_class = field.document_type
        elif isinstance(field, SafeReferenceListField):
            document_class = field.field.document_type
        else:
            raise NotImplementedError('%s class not supported for fetch_related' % field.__class__.__name__)
        fields_to_fetch = sub_field_dict if isinstance(sub_field_dict, (list, tuple)) else None
        field_info[field_name] = (field, db_field, document_class, fields_to_fetch)

    # Determine what IDs we want to fetch
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class, fields_to_fetch = field_info.get(field_name) or (None, None, None, None)
        if not field:
            continue

        # we need to use _db_data for safe references because touching their
        # pks triggers a query
        if isinstance(field, SafeReferenceField):
            ids = {id_from_value(field, obj._db_data.get(db_field, None))
                   for obj in objs if field_name not in obj._internal_data and
                   obj._db_data.get(db_field, None)}
        elif isinstance(field, SafeReferenceListField):
            ids = [obj._db_data.get(db_field, []) for obj in objs
                   if field_name not in obj._internal_data]
            ids = {id_from_value(field.field, item)
                   for sublist in ids for item in sublist}  # flatten the list of lists
        elif isinstance(field, ReferenceField):
            ids = {getattr(obj, field_name).pk for obj in objs
                   if getattr(obj, field_name, None) and
                   getattr(getattr(obj, field_name), '_lazy', False)}

        # remove ids of objects that are already in the cache map
        if document_class in cache_map:
            ids -= set(cache_map[document_class])

        # no point setting up the data structures for fields where there's nothing to fetch
        if not ids:
            continue

        # set up cache maps for the newly seen document class
        if document_class not in cache_map:
            cache_map[document_class] = {}
        if document_class not in partial_cache_map:
            partial_cache_map[document_class] = {}

        # set up a fetch map for this document class
        if document_class in fetch_map:
            fetch_map[document_class]['ids'] |= ids

            # make sure we don't allow partial fetching if the same document class
            # has conflicting fields_to_fetch (e.g. { user: ["id"], created_by: True })
            # TODO this could be improved to fetch a union of all requested fields
            if fields_to_fetch != fetch_map[document_class]['fields_to_fetch']:
                raise RuntimeError('Cannot specify different fields_to_fetch for the same document class %s' % document_class)
        else:
            fetch_map[document_class] = {
                'ids': ids,
                'fields_to_fetch': fields_to_fetch
            }

    # Fetch objects and cache them
    for document_class, fetch_opts in fetch_map.iteritems():
        cls_filters = extra_filters.get(document_class, {})

        # Fetch objects in batches. Also set the batch size so we don't do
        # multiple queries per batch.
        for id_group in grouper(batch_size, list(fetch_opts['ids'])):
            qs = (document_class.objects.filter(pk__in=id_group, **cls_filters)
                                        .clear_initial_query())

            # only fetch the requested fields
            if fetch_opts['fields_to_fetch']:
                qs = qs.only(*fetch_opts['fields_to_fetch'])

            # We have to apply this at the end, or only() won't work.
            qs = qs.batch_size(batch_size)

            # update the cache map - either the persistent one with full
            # objects, or the ephemeral partial cache
            update_dict = {obj.pk: obj for obj in qs}
            if fetch_opts['fields_to_fetch'] is None:
                cache_map[document_class].update(update_dict)
            else:
                partial_cache_map[document_class].update(update_dict)

    # Assign objects
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class, fields_to_fetch = field_info.get(field_name) or (None, None, None, None)

        if not field:
            continue

        # merge the permanent and temporary caches for the ease of assignment
        pk_to_obj = cache_map.get(document_class, {}).copy()
        pk_to_obj.update(partial_cache_map.get(document_class, {}))

        # if a dict of subfields was passed, go recursive
        if pk_to_obj and isinstance(sub_field_dict, dict):
            fetch_related(pk_to_obj.values(), sub_field_dict, cache_map=cache_map)

        # attach all the values to all the objects
        for obj in objs:
            if isinstance(field, SafeReferenceField):
                if field_name not in obj._internal_data:
                    val = obj._db_data.get(db_field, None)
                    if val:
                        setattr_unchanged(
                            obj,
                            field_name,
                            pk_to_obj.get(id_from_value(field, val))
                        )

            elif isinstance(field, ReferenceField):
                val = getattr(obj, field_name, None)
                if val and getattr(val, '_lazy', False):
                    rel_obj = pk_to_obj.get(val.pk)
                    if rel_obj:
                        setattr_unchanged(obj, field_name, rel_obj)

            elif isinstance(field, SafeReferenceListField):
                if field_name not in obj._internal_data:
                    value = filter(None, [pk_to_obj.get(id_from_value(field.field, val))
                                          for val in obj._db_data.get(db_field, [])])
                    setattr_unchanged(obj, field_name, value)


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


def iter_no_cache(query_set):
    """Iterate over queryset without caching it.

    Useful for iterating over large result sets / bulk actions.

    If a batch size is not set, apply a sensible default of 1000
    that's better than what Mongo server is doing (101 first and
    then as many as it can fit in 4MB) to avoid cursor timeouts.
    """
    if query_set._batch_size is None:
        query_set = query_set.batch_size(1000)

    while True:
        yield query_set.next()
