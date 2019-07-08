from flask import current_app
from mongoengine import Q, QuerySet


class NotDeletedQuerySet(QuerySet):
    """QuerySet that doesn't return soft-deleted documents by default."""

    def __call__(
        self,
        q_obj=None,
        class_check=True,
        slave_okay=False,
        read_preference=None,
        **query
    ):
        # We don't use __ne=True here, because $ne isn't a selective query and
        # doesn't utilize an index in the most efficient manner. See
        # http://docs.mongodb.org/manual/faq/indexes/#using-ne-and-nin-in-a-query-is-slow-why.
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
            if query_shape == forbidden['query_shape'] and (
                not forbidden.get('orderings')
                or self._ordering in forbidden['orderings']
            ):

                # determine the real limit based on objects.limit or objects[idx_key]
                limit = self._limit
                if limit is None and idx_key is not None:
                    if isinstance(idx_key, slice):
                        limit = idx_key.stop
                    else:
                        limit = idx_key

                if limit is None or limit > forbidden.get(
                    'max_allowed_limit', 0
                ):
                    raise ForbiddenQueryException(
                        'Forbidden query used! Query: %s, Ordering: %s, Limit: %s'
                        % (self._query, self._ordering, limit)
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
