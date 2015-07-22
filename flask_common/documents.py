import os
import datetime
from zbase62 import zbase62
from mongoengine import *
from mongoengine.queryset import OperationError
from mongoengine.errors import ValidationError

class StringIdField(StringField):
    def to_mongo(self, value):
        if not isinstance(value, basestring):
            raise ValidationError(errors={self.name: ['StringIdField only accepts string values.']})
        return super(StringIdField, self).to_mongo(value)

class RandomPKDocument(Document):
    id = StringIdField(primary_key=True)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.id)

    def get_pk_prefix(self):
        return self._get_collection_name()[:4]

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
                kwargs['cascade_kwargs'] = { 'force_insert': False }

            return super(RandomPKDocument, self).save(*args, **kwargs)
        except OperationError, err:
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

    @classmethod
    def ensure_indexes(cls, *args, **kwargs):
        """
        Overridden version of ensure_indexes - makes sure we don't create
        foreground indexes unless we explicitly call this method with a
        `force=True` kwargs. Same effect could be achieved by adding
        `'auto_create_index': False` to all the documents' meta dicts, but
        it's just cumbersome and easy to forget.
        """
        if kwargs.pop('force', False):
            return super(DocumentBase, cls).ensure_indexes(*args, **kwargs)
        return

    meta = {
        'abstract': True,
    }


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

    def update(self, **kwargs):
        if 'set__is_deleted' in kwargs and kwargs['set__is_deleted'] is None:
            raise ValidationError('is_deleted cannot be set to None')
        super(SoftDeleteDocument, self).update(**kwargs)

    def delete(self, **kwargs):
        # delete only if already saved
        if self.pk:
            self.is_deleted = True
            self.update(set__is_deleted=self.is_deleted)

    @queryset_manager
    def all_objects(doc_cls, queryset):
        if not hasattr(doc_cls, '_all_objs_queryset'):
            doc_cls._all_objs_queryset = QuerySet(doc_cls, doc_cls._get_collection())
        return doc_cls._all_objs_queryset

    meta = {
        'abstract': True,
        'queryset_class': NotDeletedQuerySet,
    }


def fetch_related(objs, field_dict, cache_map=None):
    """
    Recursively fetches related objects for the given document instances.
    Sample usage:

    fetch_related(objs, {
        'user': True,
        'lead': {
            'created_by': True,
            'updated_by': True,
        }
    })

    In this sample, users and leads for all objs will be fetched and attached.
    Then, created_by and updated_by users are fetched in one query and attached.

    Note that the function doesn't merge queries for the same document class
    across multiple (recursive) function calls, but it never fetches the same
    related object twice.

    If you need to call fetch_related multiple times, it's worth passing a
    cache_map (initially it can be an empty dictionary). It will be extended
    during each call to include all the objects fetched up until the current
    call. This way we ensure that the same objects aren't fetched more than
    once across multiple fetch_related calls. Cache map has a form of:
    { DocumentClass: [list, of, objects, fetched, for, a, given, class] }.
    """

    if not objs:
        return

    if cache_map == None:
        # list of objects that we fetched, over all iterations / from previous calls, by document class
        cache_map = {}

    # ids of objects that will be fetched in this iteration, by document class
    id_set_map = {}

    # Helper mapping: field_name -> field, db_field, document_class
    field_cache = {}

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

    instances = get_instance_for_each_type(objs)
    for field_name, sub_field_dict in field_dict.iteritems():

        instance = [instance for instance in instances if field_name in instance.__class__._fields]
        if not instance:
            continue  # None of the objects contains this field

        instance = instance[0]
        field = instance.__class__._fields[field_name]
        db_field = instance._db_field_map.get(field_name, field_name)
        if isinstance(field, ReferenceField): # includes SafeReferenceListField
            document_class = field.document_type
        elif isinstance(field, SafeReferenceListField):
            document_class = field.field.document_type
        else:
            raise NotImplementedError('%s class not supported for fetch_related' % field.__class__.__name__)
        field_cache[field_name] = (field, db_field, document_class)

    # Determine what IDs we want to fetch
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class = field_cache.get(field_name) or (None, None, None)
        if not field:
            continue

        if isinstance(field, SafeReferenceField):
            refs = [id_from_value(field, obj._db_data.get(db_field, None)) for obj in objs if field_name not in obj._internal_data and obj._db_data.get(db_field, None)]
        elif isinstance(field, ReferenceField):
            refs = [getattr(obj, field_name).pk for obj in objs if getattr(obj, field_name, None) and getattr(getattr(obj, field_name), '_lazy', False)]
        elif isinstance(field, SafeReferenceListField):
            refs = [obj._db_data.get(db_field, []) for obj in objs if field_name not in obj._internal_data]
            refs = [id_from_value(field.field, item) for sublist in refs for item in sublist] # flatten

        if refs:
            if not document_class in cache_map:
                rel_obj_map = cache_map[document_class] = {}
            else:
                rel_obj_map = cache_map[document_class]

            if not document_class in id_set_map:
                id_set = id_set_map[document_class] = set()
            else:
                id_set = id_set_map[document_class]

            # Never fetch already fetched objects
            id_set.update(set(refs) - set(rel_obj_map.keys()))

    # Fetch objects
    for document_class, id_set in id_set_map.iteritems():
        rel_obj_map = cache_map[document_class]

        if id_set:
            id_set = list(id_set)
            if len(id_set) == 1:
                rel_obj_map.update({ id_set[0]: document_class.objects.filter(pk=id_set[0]).first() })
            else:
                rel_obj_map.update(
                    document_class.objects.in_bulk(id_set)
                )

    # Assign objects
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class = field_cache.get(field_name) or (None, None, None)

        if not field:
            continue

        rel_obj_map = cache_map.get(document_class)
        if rel_obj_map:
            # Go recursive
            if isinstance(sub_field_dict, dict):
                fetch_related(rel_obj_map.values(), sub_field_dict)

            for obj in objs:
                if isinstance(field, SafeReferenceField):
                    if field_name not in obj._internal_data:
                        val = obj._db_data.get(db_field, None)
                        if val:
                            setattr_unchanged(obj, field_name,
                                    rel_obj_map.get(id_from_value(field, val)))

                elif isinstance(field, ReferenceField):
                    val = getattr(obj, field_name, None)
                    if val and getattr(val, '_lazy', False):
                        rel_obj = rel_obj_map.get(val.pk)
                        if rel_obj:
                            setattr_unchanged(obj, field_name, rel_obj)

                elif isinstance(field, SafeReferenceListField):
                    if field_name not in obj._internal_data:
                        value = filter(None, [rel_obj_map.get(id_from_value(field.field, val))
                                for val in obj._db_data.get(db_field, [])])
                        setattr_unchanged(obj, field_name, value)
