from functools import wraps


def with_context_manager(ctx_manager):
    """Decorator syntax for context managers."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            with ctx_manager:
                return f(*args, **kwargs)

        return decorated_function

    return decorator
