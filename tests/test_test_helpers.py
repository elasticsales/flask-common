from flask_common.test_helpers import (
    Capture,
    DictCompare,
    RegexSetCompare,
    SetCompare,
)


# Note we're using "not" instead of "!=" for comparisons here since the latter
# uses __ne__, which is not implemented.


def test_set_compare():
    assert SetCompare([1, 2, 3]) == [2, 3, 1]
    assert not (SetCompare([1, 2, 3]) == [2, 2, 2])

    assert not (SetCompare([1, 2, 3]) != [2, 3, 1])
    assert SetCompare([1, 2, 3]) != [2, 2, 2]


def test_regex_set_compare():
    regex = '(.*) OR (.*) OR (.*)'
    assert RegexSetCompare(regex, ['1', '2', '3']) == '2 OR 3 OR 1'
    assert not (RegexSetCompare(regex, ['2', '2', '2']) == '2 OR 3 OR 1')

    assert not (RegexSetCompare(regex, ['1', '2', '3']) != '2 OR 3 OR 1')
    assert RegexSetCompare(regex, ['2', '2', '2']) != '2 OR 3 OR 1'


def test_capture():
    capture = Capture()
    assert capture == 'hello'
    assert capture() == 'hello'


def test_dict_compare():
    assert DictCompare({'a': 'b'}) == {'a': 'b'}
    assert not (DictCompare({'a': 'b'}) == {'a': 'c'})
    assert DictCompare({'a': 'b'}) == {'a': 'b', 'c': 'd'}
    assert not (DictCompare({'a': 'b'}) == {'a': 'c', 'c': 'd'})
    assert not (DictCompare({'c': 'd'}) == {'a': 'b'})

    assert not (DictCompare({'a': 'b'}) != {'a': 'b'})
    assert DictCompare({'a': 'b'}) != {'a': 'c'}
    assert not (DictCompare({'a': 'b'}) != {'a': 'b', 'c': 'd'})
    assert DictCompare({'a': 'b'}) != {'a': 'c', 'c': 'd'}
    assert DictCompare({'c': 'd'}) != {'a': 'b'}
