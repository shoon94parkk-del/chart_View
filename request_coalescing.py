"""Share concurrent provider work without changing its existing freshness rules."""
from concurrent.futures import Future
from functools import wraps
from threading import Lock


def singleflight(function):
    pending = {}
    lock = Lock()

    @wraps(function)
    def wrapped(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        with lock:
            future = pending.get(key)
            owner = future is None
            if owner:
                future = pending[key] = Future()
        if not owner:
            return future.result()
        try:
            result = function(*args, **kwargs)
            future.set_result(result)
            return result
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with lock:
                pending.pop(key, None)
    return wrapped
