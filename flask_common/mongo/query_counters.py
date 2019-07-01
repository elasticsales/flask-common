from mongoengine.context_managers import query_counter


class custom_query_counter(query_counter):
    """
    Subclass of MongoEngine's query_counter context manager that also lets
    you ignore some of the collections (just extend `get_ignored_collections`).

    Initialize with `custom_query_counter(verbose=True)` for debugging.
    """

    def __init__(self, verbose=False):
        super(custom_query_counter, self).__init__()
        self.verbose = verbose

    def get_ignored_collections(self):
        return [
            "{0}.system.indexes".format(self.db.name),
            "{0}.system.namespaces".format(self.db.name),
            "{0}.system.profile".format(self.db.name),
            "{0}.$cmd".format(self.db.name),
        ]

    def _get_queries(self):
        filter_query = { "$or": [
            { "ns": {"$nin": self.get_ignored_collections()}, "op": { "$ne": "killcursors" } },
            { "ns": "{0}.$cmd".format(self.db.name), "command.findAndModify": { "$exists": True } },
        ]}
        return self.db.system.profile.find(filter_query)

    def _get_count(self):
        """ Get the number of queries. """
        queries = self._get_queries()
        if self.verbose:
            print('-'*80)
            for query in queries:
                # findAndModify appear in $cmd -- we'll make them more readable
                if query['ns'].endswith('.$cmd'):
                    if 'findAndModify' in query['command']:
                        ns = '.'.join([query['ns'].split('.')[0], query['command']['findAndModify']])
                        op = 'findAndModify'
                        query = query['command'].get('query')
                    else:
                        ns = query['ns']
                        op = query['op']
                        query = query['command']
                else:
                    ns = query['ns']
                    op = query['op']
                    query = query.get('query')
                print('{} [{}] {}'.format(ns, op, query))
                print()
            print('-'*80)
        count = queries.count()
        return count


