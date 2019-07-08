"""
This module allows to run Flask-Script lazily (i.e. the app doesn't need to be
created until the command is run). This allows to:

- Speed up commands that don't need the app object
- Allow custom app configuration in commands that need customization
"""

from flask import Flask
import flask_script
from werkzeug.local import LocalProxy


__all__ = ['ContextlessCommand', 'Manager', 'Test']


# Hack to satisfy isinstance() check in flask_scripts.Manager.__call__ for
# custom managers.
class FlaskProxy(LocalProxy, Flask):
    pass


class Manager(flask_script.Manager):
    """
    A Flask-Script manager that supports contextless commands, i.e. commands
    that don't require app context. When initialized lazily, contextless
    commands can be executed faster since the app doesn't need to be
    initialized. To initialize lazily, pass either a callable that returns
    the app object, or a dotted string to the module and function that returns
    the app, e.g. 'myapp.main.setup_app'.
    """

    def __init__(self, app=None, *args, **kwargs):
        """
        Like flask_script.Manager, but allows you to pass a function that
        creates the app (in addition to passing a regular Flask app.
        """
        if not isinstance(app, Flask):
            if isinstance(app, str):
                pkg, func_name = app.rsplit('.', 1)

                def create_app(*args, **kwargs):
                    import importlib

                    module = importlib.import_module(pkg)
                    return getattr(module, func_name)(*args, **kwargs)

                app = create_app

            if callable(app):
                self._create_app = app
                self._cached_app = None
                app = FlaskProxy(self.get_or_create_app)

        super(Manager, self).__init__(app=app, *args, **kwargs)

    def get_or_create_app(self, *args, **kwargs):
        if self._cached_app is None:
            # Create app
            self._cached_app = self._create_app(*args, **kwargs)
        return self._cached_app

    def __call__(self, app=None, **kwargs):
        if app is not None:
            self.app = app
        return self.app

    def contextless_command(self, func):
        """
        Function decorator for a command that doesn't require app context.
        """
        command = ContextlessCommand(func)
        self.add_command(func.__name__, command)
        return func


class ContextlessCommand(flask_script.Command):
    """
    A Flask-Script command that doesn't require app context.
    """

    def __call__(self, app=None, *args, **kwargs):
        return self.run(*args, **kwargs)


class Test(flask_script.Command):
    """
    Management command that runs tests via pytest. Any command line arguments
    are passed directly to pytest.

    When using a Manager with a lazily created app (i.e. a callable), any
    args/kwargs passed to the constructor will be passed to the callable.

    Example:

        def setup_app(config=None):
            app = Flask('app')
            if config:
                app.config.from_object(config)
            return app

        manager = Manager(setup_app)
        manager.add_command('test', Test(config='config.app_testing'))

    """

    capture_all_args = True
    help = 'Run tests'

    def __init__(self, *args, **kwargs):
        super(Test, self).__init__()
        self.app_args = args
        self.app_kwargs = kwargs

    def __call__(self, app=None, *args, **kwargs):
        # By default, use the manager's app object, but if a callable was
        # passed we can forward all args.
        if self.app_args or self.app_kwargs:
            if isinstance(app, FlaskProxy):
                app = self.parent.get_or_create_app(
                    *self.app_args, **self.app_kwargs
                )
            else:
                raise Exception(
                    'Must use flask_common.commands.Manager when '
                    'passing args to the Test() command.'
                )

        return super(Test, self).__call__(app, *args, **kwargs)

    def create_parser(self, *args, **kwargs):
        # Override the default parser so we can pass all arguments to pytest.
        import argparse

        func_stack = kwargs.pop('func_stack', ())
        parent = kwargs.pop('parent', None)
        parser = argparse.ArgumentParser(*args, add_help=False, **kwargs)
        parser.set_defaults(func_stack=func_stack + (self,))
        self.parser = parser
        self.parent = parent
        return parser

    def run(self, args):
        # Keep imports inlined so they're not unnecessarily imported.
        import pytest
        import sys

        sys.exit(pytest.main(args))
