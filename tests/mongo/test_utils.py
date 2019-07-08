import unittest
import weakref

from mongoengine import (
    Document,
    DoesNotExist,
    IntField,
    ReferenceField,
    SafeReferenceField,
    SafeReferenceListField,
    StringField,
)

from flask_common.mongo.query_counters import custom_query_counter
from flask_common.mongo.utils import fetch_related, iter_no_cache


class IterNoCacheTestCase(unittest.TestCase):
    def test_no_cache(self):
        def is_cached(qs):
            iterator = iter(qs)
            d = next(iterator)
            self.assertEqual(d.i, 0)
            w = weakref.ref(d)
            d = next(iterator)
            self.assertEqual(d.i, 1)
            # - If the weak reference is still valid at this point, then
            #   iterator or queryset is holding onto the first object
            # - Hold reference to qs until very end just in case
            #   Python gets smart enough to destroy it
            return w() is not None and qs is not None

        class D(Document):
            i = IntField()
            pass

        D.drop_collection()

        for i in range(10):
            D(i=i).save()

        self.assertTrue(is_cached(D.objects.all()))
        self.assertFalse(is_cached(iter_no_cache(D.objects.all())))

        # check for correct exit behavior
        self.assertEqual(
            {d.i for d in iter_no_cache(D.objects.all())}, set(range(10))
        )
        self.assertEqual(
            {d.i for d in iter_no_cache(D.objects.all().batch_size(5))},
            set(range(10)),
        )
        self.assertEqual(
            {d.i for d in iter_no_cache(D.objects.order_by('i').limit(1))},
            set(range(1)),
        )


class FetchRelatedTestCase(unittest.TestCase):
    def setUp(self):
        super(FetchRelatedTestCase, self).setUp()

        class Shard(Document):
            pass

        class A(Document):
            shard_a = ReferenceField(Shard)
            txt = StringField()

        class B(Document):
            shard_b = ReferenceField(Shard)
            ref = ReferenceField(A)

        class C(Document):
            shard_c = ReferenceField(Shard)
            ref_a = ReferenceField(A)

        class D(Document):
            shard_d = ReferenceField(Shard)
            ref_c = ReferenceField(C)
            ref_a = ReferenceField(A)

        class E(Document):
            shard_e = ReferenceField(Shard)
            refs_a = SafeReferenceListField(ReferenceField(A))
            ref_b = SafeReferenceField(B)

        class F(Document):
            shard_f = ReferenceField(Shard)
            ref_a = ReferenceField(A)

        A.drop_collection()
        B.drop_collection()
        C.drop_collection()
        D.drop_collection()
        E.drop_collection()
        F.drop_collection()

        self.Shard = Shard
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.E = E
        self.F = F

        self.shard = Shard.objects.create()
        self.a1 = A.objects.create(shard_a=self.shard, txt='a1')
        self.a2 = A.objects.create(shard_a=self.shard, txt='a2')
        self.a3 = A.objects.create(shard_a=self.shard, txt='a3')
        self.b1 = B.objects.create(shard_b=self.shard, ref=self.a1)
        self.b2 = B.objects.create(shard_b=self.shard, ref=self.a2)
        self.c1 = C.objects.create(shard_c=self.shard, ref_a=self.a3)
        self.d1 = D.objects.create(
            shard_d=self.shard, ref_c=self.c1, ref_a=self.a3
        )
        self.e1 = E.objects.create(
            shard_e=self.shard,
            refs_a=[self.a1, self.a2, self.a3],
            ref_b=self.b1,
        )
        self.f1 = F.objects.create(shard_f=self.shard, ref_a=None)  # empty ref

    def test_fetch_related(self):
        with custom_query_counter() as q:
            objs = list(self.B.objects.all())
            fetch_related(objs, {'ref': True})

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2'))

            # one query for B, one query for A
            self.assertEqual(q, 2)

    def test_fetch_related_multiple_objs(self):
        with custom_query_counter() as q:
            objs = list(self.B.objects.all()) + list(self.C.objects.all())
            fetch_related(objs, {'ref': True, 'ref_a': True})

            # make sure A objs are fetched
            for obj in objs:
                if isinstance(obj, self.B):
                    self.assertTrue(obj.ref.txt in ('a1', 'a2'))
                else:
                    self.assertEqual(obj.ref_a.txt, 'a3')

            # one query for B, one for C, one for A
            self.assertEqual(q, 3)

    def test_fetch_related_subdict(self):
        """
        Make sure fetching related references works with subfields and that
        it uses caching properly.
        """
        with custom_query_counter() as q:
            objs = list(self.D.objects.all())
            fetch_related(objs, {'ref_a': True, 'ref_c': {'ref_a': True}})

            # make sure A objs are fetched
            for obj in objs:
                self.assertEqual(obj.ref_a.txt, 'a3')
                self.assertEqual(obj.ref_c.ref_a.txt, 'a3')

            # one query for D, one query for C, one query for A
            self.assertEqual(q, 3)

    def test_fetch_related_subdict_broken_reference(self):
        """
        Make sure that fetching sub-references of a broken reference works.
        """

        # delete the object referenced by self.d1.ref_c
        self.c1.delete()

        objs = list(self.D.objects.all())
        fetch_related(objs, {'ref_c': {'ref_a': True}})
        self.assertTrue(
            objs[0].ref_c.pk
        )  # pk still exists even though the reference is broken
        self.assertRaises(DoesNotExist, lambda: objs[0].ref_c.ref_a)

    def test_partial_fetch_related(self):
        """
        Make sure we can only fetch particular fields of a reference.
        """
        objs = list(self.B.objects.all())
        fetch_related(objs, {'ref': ["id"]})
        self.assertEqual(objs[0].ref.pk, self.a1.pk)

        # "txt" field of the referenced object shouldn't be fetched
        self.assertEqual(objs[0].ref.txt, None)
        self.assertTrue(self.a1.txt)

    def test_partial_fetch_fields_conflict(self):
        """
        Fetching certain fields via fetch_related has a limitation that
        different fields cannot be fetched for the same document class.
        Make sure that contraint is respected.
        """
        objs = list(self.B.objects.all()) + list(self.C.objects.all())
        self.assertRaises(
            RuntimeError, fetch_related, objs, {'ref': ["id"], 'ref_a': True}
        )

    def test_partial_fetch_cache_map(self):
        """
        Make sure doing a partial fetch in fetch_related doesn't cache
        the results (it could be dangerous for any subsequent fetch_related
        call).
        """
        cache_map = {}
        objs = list(self.D.objects.all())
        fetch_related(
            objs, {'ref_a': True, 'ref_c': ["id"]}, cache_map=cache_map
        )
        self.assertEqual(objs[0].ref_c.pk, self.c1.pk)
        self.assertEqual(objs[0].ref_a.pk, self.a3.pk)

        # C reference shouldn't be cached because it was a partial fetch
        self.assertEqual(cache_map, {self.A: {self.a3.pk: self.a3}, self.C: {}})

    def test_safe_reference_fields(self):
        """
        Make sure SafeReferenceField and SafeReferenceListField don't fetch
        the entire objects if we use a partial fetch_related on them.
        """
        objs = list(self.E.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {'refs_a': ["id"], 'ref_b': ["id"]})

        # make sure the IDs match
        self.assertEqual(
            [a.pk for a in objs[0].refs_a], [self.a1.pk, self.a2.pk, self.a3.pk]
        )
        self.assertEqual(objs[0].ref_b.pk, self.b1.pk)

        # make sure other fields are empty
        self.assertEqual(set([a.txt for a in objs[0].refs_a]), set([None]))
        self.assertEqual(objs[0].ref_b.ref, None)

        # make sure the queries to MongoDB only fetched the IDs
        queries = list(
            q.db.system.profile.find({'op': 'query'}, {'ns': 1, 'execStats': 1})
        )
        self.assertEqual({q['ns'].split('.')[1] for q in queries}, {'a', 'b'})
        self.assertEqual(
            {q['execStats']['stage'] for q in queries}, {'PROJECTION'}
        )
        self.assertEqual(
            {tuple(q['execStats']['transformBy'].keys()) for q in queries},
            {('_id',)},
        )

    def test_fetch_field_without_refs(self):
        """
        Make sure calling fetch_related on a field that doesn't hold any
        references works.
        """
        # full fetch
        objs = list(self.F.objects.all())
        fetch_related(objs, {'ref_a': True})
        self.assertEqual(objs[0].ref_a, None)

        # partial fetch
        objs = list(self.F.objects.all())
        fetch_related(objs, {'ref_a': ["id"]})
        self.assertEqual(objs[0].ref_a, None)

    def test_fetch_same_doc_class_multiple_times_with_cache_map(self):
        """
        Make sure that the right documents are fetched when we reuse a cache
        map for the same document type and the second fetch_related is a
        partial fetch.
        """
        self.b1.reload()
        self.c1.reload()
        cache_map = {}
        objs = [self.b1, self.c1]
        with custom_query_counter() as q:
            fetch_related(objs, {'ref': True}, cache_map=cache_map)
            fetch_related(objs, {'ref_a': ['id']}, cache_map=cache_map)

            self.assertEqual(q, 2)
            self.assertEqual(
                [
                    op['query']['filter']['_id']['$in'][0]
                    for op in q.db.system.profile.find({'op': 'query'})
                ],
                [self.a1.pk, self.a3.pk],
            )

    def test_extra_filters(self):
        """
        Ensure we apply extra filters by collection.
        """
        objs = list(self.E.objects.all())

        with custom_query_counter() as q:
            fetch_related(
                objs,
                {'refs_a': True, 'ref_b': True},
                extra_filters={
                    self.A: {'shard_a': self.shard},
                    self.B: {'shard_b': self.shard},
                },
            )
        ops = list(q.db.system.profile.find({'op': 'query'}))
        assert len(ops) == 2
        filters = {op['query']['find']: op['query']['filter'] for op in ops}
        assert filters['a']['shard_a'] == self.shard.pk
        assert filters['b']['shard_b'] == self.shard.pk

    def test_batch_size_1(self):
        """
        Ensure we batch requests properly, if a batch size is given.
        """
        objs = list(self.B.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {'ref': True}, batch_size=2)

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2', 'a3'))

            # We need two queries to fetch 3 objects.
            self.assertEqual(q, 2)

    def test_batch_size_2(self):
        """
        Ensure we batch requests properly, if a batch size is given.
        """
        objs = list(self.B.objects.all())

        with custom_query_counter() as q:
            fetch_related(objs, {'ref': True}, batch_size=3)

            # make sure A objs are fetched
            for obj in objs:
                self.assertTrue(obj.ref.txt in ('a1', 'a2', 'a3'))

            # All 3 objects are fetched in one query.
            self.assertEqual(q, 1)
