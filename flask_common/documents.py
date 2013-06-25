import os
import datetime
from zbase62 import zbase62
from mongoengine import *
from mongoengine.base import ValidationError
from mongoengine.queryset import OperationError


class RandomPKDocument(Document):
    id = StringField(unique=True, primary_key=True)

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
    date_created = DateTimeField()
    date_updated = DateTimeField()

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

    meta = {
        'abstract': True,
    }


from bson.dbref import DBRef

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
    """

    if not objs:
        return

    if not cache_map:
        # list of objects that we fetched, over all iterations / from previous calls, by document class
        cache_map = {}

    # ids of objects that will be fetched in this iteration, by document class
    id_set_map = {}

    # Helper mapping: field_name -> field, db_field, document_class
    field_cache = {}

    instance = objs[0]
    for field_name, sub_field_dict in field_dict.iteritems():
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
        field, db_field, document_class = field_cache[field_name]

        if isinstance(field, SafeReferenceField):
            refs = [obj._db_data.get(db_field, None).id for obj in objs if field_name not in obj._internal_data and obj._db_data.get(db_field, None)]
        elif isinstance(field, ReferenceField):
            refs = [getattr(obj, field_name).pk for obj in objs if getattr(getattr(obj, field_name), '_lazy', False)]
        elif isinstance(field, SafeReferenceListField):
            refs = [obj._db_data.get(db_field, []) for obj in objs if field_name not in obj._internal_data]
            refs = [item.id for sublist in refs for item in sublist] # flatten

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
            rel_obj_map.update(
                document_class.objects.in_bulk(list(id_set))
            )

    # Assign objects
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class = field_cache[field_name]

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
                            setattr(obj, field_name, rel_obj_map.get(val.id))

                elif isinstance(field, ReferenceField):
                    val = getattr(obj, field_name)
                    if val and getattr(val, '_lazy', False):
                        rel_obj = rel_obj_map.get(val.id)
                        if rel_obj:
                            setattr(obj, field_name, rel_obj)

                elif isinstance(field, SafeReferenceListField):
                    if field_name not in obj._internal_data:
                        setattr(obj, field_name, filter(None, [rel_obj_map.get(val.id) for val in obj._db_data.get(db_field, [])]))
