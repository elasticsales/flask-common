from flask_common.enum import Enum


class TestEnum(Enum):
    A = 'a'
    B = 'b'


def test_enum():
    # Fetch twice to ensure cache is correct
    assert TestEnum.values() == ['a', 'b']
    assert TestEnum.values() == ['a', 'b']
    assert TestEnum.choices() == [('a', 'A'), ('b', 'B')]
    assert TestEnum.choices() == [('a', 'A'), ('b', 'B')]
