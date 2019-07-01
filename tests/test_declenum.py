import unittest

from flask_common.declenum import DeclEnum


class DeclEnumTestCase(unittest.TestCase):
    # TODO pytest-ify

    def test_enum(self):
        class TestEnum(DeclEnum):
            alpha = 'alpha_value', 'Alpha Description'
            beta = 'beta_value', 'Beta Description'
        assert TestEnum.alpha != TestEnum.beta
        assert TestEnum.alpha.value == 'alpha_value'
        assert TestEnum.alpha.description == 'Alpha Description'
        assert TestEnum.from_string('alpha_value') == TestEnum.alpha

        db_type = TestEnum.db_type()
        self.assertEqual(set(db_type.enum.values()), set(['alpha_value', 'beta_value']))
