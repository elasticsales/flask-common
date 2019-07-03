from sqlalchemy.types import SchemaType, TypeDecorator, Enum
import re


class DeclEnumType(SchemaType, TypeDecorator):
    """
    DeclEnumType supports object instantiation in two different ways:

    Passing in an enum:
    This is to be used in the application code. It will pull enum values straight from
    the DeclEnum object. A helper for this is available in DeclEnum.db_type()

    Passing in a tuple with enum values:
    In migrations the enum value list needs to be fix. It should not be pulled in from
    the application code, otherwise later modifications of enum values could result in
    those values being added in an earlier migration when re-running migrations from the
    beginning. Therefore DeclEnum(enum_values=('one', 'two'), enum_name='MyEnum') should
    be used.

    """

    def __init__(self, enum=None, enum_values=None, enum_name=None):
        self.enum = enum
        self.enum_values = enum_values
        self.enum_name = enum_name

        if enum:
            self.enum_values = enum.values()
            self.enum_name = enum.__name__

        self.impl = Enum(
            *self.enum_values,
            name="ck%s"
            % re.sub(
                '([A-Z])', lambda m: "_" + m.group(1).lower(), self.enum_name
            )
        )

    def create(self, bind=None, checkfirst=False):
        """Issue CREATE ddl for this type, if applicable."""
        super(DeclEnumType, self).create(bind, checkfirst)
        t = self.dialect_impl(bind.dialect)
        if t.impl.__class__ is not self.__class__ and isinstance(t, SchemaType):
            t.impl.create(bind=bind, checkfirst=checkfirst)

    def _set_table(self, table, column):
        self.impl._set_table(table, column)

    def copy(self):
        if self.enum:
            return DeclEnumType(self.enum)
        else:
            return DeclEnumType(
                enum_name=self.enum_name, enum_values=self.enum_values
            )

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return value.value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.enum.from_string(value.strip())


class EnumSymbol(object):
    """Define a fixed symbol tied to a parent class."""

    def __init__(self, cls_, name, value, description):
        self.cls_ = cls_
        self.name = name
        self.value = value
        self.description = description

    def __reduce__(self):
        """Allow unpickling to return the symbol
        linked to the DeclEnum class."""
        return getattr, (self.cls_, self.name)

    def __iter__(self):
        return iter([self.value, self.description])

    def __repr__(self):
        return "<%s>" % self.name


class EnumMeta(type):
    """Generate new DeclEnum classes."""

    def __init__(cls, classname, bases, dict_):
        cls._reg = reg = cls._reg.copy()
        for k, v in dict_.items():
            if isinstance(v, tuple):
                sym = reg[v[0]] = EnumSymbol(cls, k, *v)
                setattr(cls, k, sym)
        return type.__init__(cls, classname, bases, dict_)

    def __iter__(cls):
        return iter(cls._reg.values())


class DeclEnum(object):
    """
    Declarative enumeration.
    ---
    For information on internals, see: http://techspot.zzzeek.org/2011/01/14/the-enum-recipe/

    Usage:

        from flask_common.declenum import DeclEnum

        class Colors(DeclEnum):
            blue = 'blue', 'Blue color'
            red = 'red', 'Red color'


        color = Colors.red
        color == Colors.red
        color.value == 'red'
        color == Colors.from_string('red')
        Colors.red.description == 'Red Color'
        Colors.red.value = 'red'

    Usage in SQLAlchemy:
        color = sql.Column(Colors.db_type(), default=Colors.red)


    """

    __metaclass__ = EnumMeta
    _reg = {}

    @classmethod
    def from_string(cls, value):
        try:
            return cls._reg[value]
        except KeyError:
            raise ValueError("Invalid value for %r: %r" % (cls.__name__, value))

    @classmethod
    def values(cls):
        return cls._reg.keys()

    @classmethod
    def db_type(cls):
        return DeclEnumType(cls)
