def test_importing_mongo():
    """Verify that we can at least *import* the `mongo` package.

    This is a given on Python 2, but we want to make sure that at least the
    syntax is parseable by Python 3.
    """
    from flask_common import mongo


