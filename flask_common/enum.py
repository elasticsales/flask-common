class Enum(object):
    """
    A list of constants that can be defined in a declarative way.

    Example usage:

    class MyEnum(Enum):
        Choice1 = 'value1'
        Choice2 = 'value2'

    In this case, we can refer to the choices as MyEnum.Choice1 or
    MyEnum.Choice2, and don't have to reference the actual string value, which
    is prone to typos.
    """

    # Cached values and choices to avoid introspection on every call.
    __values = []
    __choices = []

    @classmethod
    def values(cls):
        """
        Returns a list of all the values, e.g.: ('choice1', 'choice2')
        """
        if not cls.__values:
            cls.__values = [
                getattr(cls, v)
                for v in dir(cls)
                if not callable(getattr(cls, v)) and not v.startswith('_')
            ]

        return cls.__values

    @classmethod
    def choices(cls):
        """
        Returns a list of choice tuples, e.g.:
        [('value1', 'Choice1'), ('value2', 'Choice2')]
        """
        if not cls.__choices:
            cls.__choices = [
                (getattr(cls, v), v)
                for v in dir(cls)
                if not callable(getattr(cls, v)) and not v.startswith('_')
            ]

        return cls.__choices
