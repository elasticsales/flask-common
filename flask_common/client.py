import base64
import json

from flask import current_app
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers


class Client(FlaskClient):
    """
    Test client that supports JSON and uses the application's response class.
    """
    def __init__(self, app, response_wrapper=None, **kwargs):
        if not response_wrapper:
            response_wrapper = app.response_class
        return super(Client, self).__init__(app, response_wrapper, **kwargs)

    def open(self, *args, **kwargs):
        if 'json' in kwargs and 'data' not in kwargs:
            kwargs['data'] = json.dumps(kwargs.pop('json'))

        resp = super(Client, self).open(*args, **kwargs)

        try:
            resp.json = lambda: json.loads(resp.data)
        except ValueError:
            pass

        return resp

class ApiClient(Client):
    """
    API test client that supports JSON and uses the given API key.
    """
    def __init__(self, app, api_key=None):
        self.api_key = api_key
        return super(ApiClient, self).__init__(app, use_cookies=False)

    def get_headers(self, api_key):
        api_key = api_key or self.api_key
        return Headers([('Authorization','Basic %s' % (base64.b64encode('%s:' % api_key)))])

    def open(self, *args, **kwargs):
        # include api_key auth header in all api calls
        api_key = kwargs.pop('api_key', self.api_key)
        if 'headers' not in kwargs:
            kwargs['headers'] = self.get_headers(api_key)
        return super(ApiClient, self).open(*args, **kwargs)

def local_request(view, method='GET', data=None, view_args=None, user=None, api_key=None):
    """
    Performs a request to the current application's view without the network
    overhead and without request pre and postprocessing. Returns a tuple
    (response_status_code, response_json_data).

    Examples:

    # List leads for a given organization (as seen by user A)
    local_request(LeadView(), data={ 'organization_id': 'orga_abc' }, user=user_A)

    # Post a note as user B
    local_request(NoteView(), method='POST', data={ 'organization_id': 'orga_abc', 'note': 'hello' }, user=user_B)

    # Update an opportunity as a user associated with an API key "abc"
    local_request(OpportunityView(), method='PUT', data={ 'status': 'won' },
                  view_args={ 'pk': 'oppo_abcd' }, api_key='abc')
    """
    if api_key is not None and user is not None:
        raise TypeError("local_request can only take an api_key or a user, not both.")

    if not view_args:
        view_args = {}

    ctx = current_app.test_request_context()
    ctx.request.environ['REQUEST_METHOD'] = method  # we can't directly manipulate request.method (it's immutable)
    ctx.user = user
    if api_key is not None:
        ctx.g.api_key = api_key
    if data and method == 'GET':
        ctx.request.args = data
    elif data:
        ctx.request.data = json.dumps(data)
    ctx.push()

    try:
        resp = view.dispatch_request(**view_args)
        json_data = json.loads(resp.data)
    except Exception as e:
        ctx.pop()
        raise
    else:
        ctx.pop()

    return resp.status_code, json_data
