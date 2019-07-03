from flask import Flask

class Application(Flask):
    def __init__(self, name, *args, **kwargs):
        config = kwargs.pop('config', None)
        super(Application, self).__init__(name, *args, **kwargs)
        self.config.from_object('%s.config' % name)
        if config is not None:
            self.config.update(**config)
