from mongoengine import ListField, ReferenceField, SafeReferenceField

from flask_common.utils import grouper


def iter_no_cache(query_set):
    """Iterate over a MongoEngine QuerySet without caching it.

    Useful for iterating over large result sets / bulk actions.

    If a batch size is not set, apply a sensible default of 1000
    that's better than what Mongo server is doing (101 first and
    then as many as it can fit in 4MB) to avoid cursor timeouts.
    """
    if query_set._batch_size is None:
        query_set = query_set.batch_size(1000)

    while True:
        yield query_set.next()


def fetch_related(
    objs, field_dict, cache_map=None, extra_filters={}, batch_size=100
):
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

        instance = [
            instance
            for instance in instances
            if instance and field_name in instance.__class__._fields
        ]
        if not instance:
            continue  # None of the objects contains this field

        instance = instance[0]
        field = instance.__class__._fields[field_name]
        db_field = instance._db_field_map.get(field_name, field_name)
        if isinstance(field, ReferenceField):  # includes SafeReferenceListField
            document_class = field.document_type
        elif isinstance(field, ListField) and isinstance(
            field.field, ReferenceField
        ):
            document_class = field.field.document_type
        else:
            raise NotImplementedError(
                '%s class not supported for fetch_related'
                % field.__class__.__name__
            )
        fields_to_fetch = (
            sub_field_dict
            if isinstance(sub_field_dict, (list, tuple))
            else None
        )
        field_info[field_name] = (
            field,
            db_field,
            document_class,
            fields_to_fetch,
        )

    # Determine what IDs we want to fetch
    for field_name, sub_field_dict in field_dict.iteritems():
        field, db_field, document_class, fields_to_fetch = field_info.get(
            field_name
        ) or (None, None, None, None)
        if not field:
            continue

        # we need to use _db_data for safe references because touching their
        # pks triggers a query
        if isinstance(field, SafeReferenceField):
            ids = {
                id_from_value(field, obj._db_data.get(db_field, None))
                for obj in objs
                if field_name not in obj._internal_data
                and obj._db_data.get(db_field, None)
            }
        elif isinstance(field, ListField):
            ids = [
                obj._db_data.get(db_field, [])
                for obj in objs
                if field_name not in obj._internal_data
            ]
            ids = {
                id_from_value(field.field, item)
                for sublist in ids
                for item in sublist
            }  # flatten the list of lists
        elif isinstance(field, ReferenceField):
            ids = {
                getattr(obj, field_name).pk
                for obj in objs
                if getattr(obj, field_name, None)
                and getattr(getattr(obj, field_name), '_lazy', False)
            }

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
                raise RuntimeError(
                    'Cannot specify different fields_to_fetch for the same document class %s'
                    % document_class
                )
        else:
            fetch_map[document_class] = {
                'ids': ids,
                'fields_to_fetch': fields_to_fetch,
            }

    # Fetch objects and cache them
    for document_class, fetch_opts in fetch_map.iteritems():
        cls_filters = extra_filters.get(document_class, {})

        # Fetch objects in batches. Also set the batch size so we don't do
        # multiple queries per batch.
        for id_group in grouper(batch_size, list(fetch_opts['ids'])):
            qs = document_class.objects.filter(
                pk__in=id_group, **cls_filters
            ).clear_cls_query()

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
        field, db_field, document_class, fields_to_fetch = field_info.get(
            field_name
        ) or (None, None, None, None)

        if not field:
            continue

        # merge the permanent and temporary caches for the ease of assignment
        pk_to_obj = cache_map.get(document_class, {}).copy()
        pk_to_obj.update(partial_cache_map.get(document_class, {}))

        # if a dict of subfields was passed, go recursive
        if pk_to_obj and isinstance(sub_field_dict, dict):
            fetch_related(
                pk_to_obj.values(), sub_field_dict, cache_map=cache_map
            )

        # attach all the values to all the objects
        for obj in objs:
            if isinstance(field, SafeReferenceField):
                if field_name not in obj._internal_data:
                    val = obj._db_data.get(db_field, None)
                    if val:
                        setattr_unchanged(
                            obj,
                            field_name,
                            pk_to_obj.get(id_from_value(field, val)),
                        )

            elif isinstance(field, ReferenceField):
                val = getattr(obj, field_name, None)
                if val and getattr(val, '_lazy', False):
                    rel_obj = pk_to_obj.get(val.pk)
                    if rel_obj:
                        setattr_unchanged(obj, field_name, rel_obj)

            elif isinstance(field, ListField):
                if field_name not in obj._internal_data:
                    value = filter(
                        None,
                        [
                            pk_to_obj.get(id_from_value(field.field, val))
                            for val in obj._db_data.get(db_field, [])
                        ],
                    )
                    setattr_unchanged(obj, field_name, value)
