def response_success(response, code=None, exception_class=None):
    if exception_class is None:
        exception_class = AssertionError

    if (
        code is None
        and (response.status_code >= 300 or response.status_code < 200)
    ) or (code and code != response.status_code):
        raise exception_class(
            'Received %d response: %s' % (response.status_code, response.data)
        )


def validation_error(response, content_type='application/json'):
    assert content_type in response.content_type, (
        'Invalid content-type: %s' % response.content_type
    )
    response_error(response, code=400)


def response_error(response, code=None):
    if code is None:
        assert 400 <= response.status_code < 500, 'Received %d response: %s' % (
            response.status_code,
            response.data,
        )
    else:
        assert code == response.status_code, 'Received %d response: %s' % (
            response.status_code,
            response.data,
        )


def compare_req_resp(req_obj, resp_obj):
    for k, v in req_obj.iteritems():
        assert k in resp_obj.keys(), 'Key %r not in response (keys are %r)' % (
            k,
            resp_obj.keys(),
        )
        assert resp_obj[k] == v, 'Value for key %r should be %r but is %r' % (
            k,
            v,
            resp_obj[k],
        )
