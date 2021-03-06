# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Module tests."""

from __future__ import absolute_import, print_function

import json

from flask import Blueprint, Flask, request

from invenio_rest.csrf import CSRF_COOKIE_NAME, REASON_BAD_REFERER, \
    REASON_BAD_TOKEN, REASON_INSECURE_REFERER, REASON_MALFORMED_REFERER, \
    REASON_NO_CSRF_COOKIE, REASON_NO_REFERER, CSRFMiddleware
from invenio_rest.ext import InvenioREST


def test_csrf_init():
    """Test extension initialization."""
    app = Flask('testapp')
    ext = CSRFMiddleware(app)
    assert 'invenio-csrf' in app.extensions

    app = Flask('testapp')
    ext = CSRFMiddleware()
    assert 'invenio-csrf' not in app.extensions
    ext.init_app(app)
    assert 'invenio-csrf' in app.extensions


def test_csrf_disabled(csrf_app):
    """Test CSRF disabled."""
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert CSRF_COOKIE_NAME not in res.headers.get('Set-Cookie', '')


def test_csrf_enabled(csrf_app, csrf):
    """Test CSRF enabled."""
    with csrf_app.test_client() as client:
        # call a dummy request to obtain the csrf token in the first time
        client.get('/ping')

        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )

        assert CSRF_COOKIE_NAME in request.headers.get('Cookie', '')
        assert res.json['message'] == REASON_BAD_TOKEN
        assert res.status_code == 400

        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
            headers={
                'X-CSRF-Token': request.cookies[CSRF_COOKIE_NAME]
            }

        )
        assert res.status_code == 200


def test_csrf_before_csrf_protect(csrf_app, csrf):
    """Test before csrf protect decorator."""
    assert csrf._before_protect_funcs == []

    @csrf.before_csrf_protect
    def before_protect():
        pass

    assert csrf._before_protect_funcs == [before_protect]

    csrf.before_csrf_protect(before_protect)

    assert csrf._before_protect_funcs == [before_protect, before_protect]


def test_csrf_exempt(csrf_app, csrf):
    """Test before csrf protect decorator."""

    # Test `exempt` as a function passing the name of the view as string
    csrf.exempt('conftest.csrf_test')
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.status_code == 200

    # Test `exempt` as a decorator on a view
    @csrf_app.route('/another-csrf-protect', methods=['POST'])
    @csrf.exempt
    def another_csrf_test():
        return 'another test'

    with csrf_app.test_client() as client:
        res = client.post(
            '/another-csrf-protect',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.status_code == 200

    # Test `exempt` as a decorator on a blueprint
    blueprint = Blueprint("test_csrf_bp", __name__, url_prefix="")

    @blueprint.route('/csrf-protect-bp', methods=['POST'])
    def csrf_bp():
        return 'csrf bp test'

    @blueprint.route('/csrf-protect-bp-2', methods=['POST'])
    def csrf_bp_2():
        return 'csrf bp test 2'

    csrf_app.register_blueprint(blueprint)

    csrf.exempt(blueprint)

    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protect-bp',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.status_code == 200

        res = client.post(
            '/csrf-protect-bp-2',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.status_code == 200


def test_skip_csrf_check(csrf_app, csrf):
    """Test skipping csrf check."""
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.json['message'] == REASON_NO_CSRF_COOKIE
        assert res.status_code == 400

        @csrf.before_csrf_protect
        def csrf_skip():
            request.skip_csrf_check = True

        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json'
        )
        assert res.status_code == 200


def test_csrf_not_signed_correctly(csrf_app, csrf):
    """Test CSRF malicious attempt with passing malicious cookie and header."""
    from invenio_rest.errors import RESTCSRFError
    from itsdangerous import URLSafeSerializer

    with csrf_app.test_client() as client:
        # try to pass our own signed cookie and header in an attempt to bypass
        # the csrf check
        csrf_serializer = URLSafeSerializer('my_secret')
        malicious_cookie = csrf_serializer.dumps(
            {'user': 'malicious'}, 'my_secret')
        client.set_cookie('localhost', CSRF_COOKIE_NAME, malicious_cookie)

        res = client.post(
            '/csrf-protected',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
            headers={
                'X-CSRF-Token': malicious_cookie
            },
        )

        assert res.json['message'] == RESTCSRFError.description
        assert res.status_code == 400


def test_csrf_no_referrer(csrf_app, csrf):
    """Test CSRF no referrer in a secure request."""
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            base_url='https://localhost',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
        )
        assert res.json['message'] == REASON_NO_REFERER
        assert res.status_code == 400


def test_csrf_malformed_referrer(csrf_app, csrf):
    """Test CSRF malformed referrer in a secure request."""
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            base_url='https://localhost',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
            headers={
                'Referer': 'bad-referrer'
            }
        )
        assert res.json['message'] == REASON_MALFORMED_REFERER
        assert res.status_code == 400


def test_csrf_insecure_referrer(csrf_app, csrf):
    """Test CSRF insecure referrer in a secure request."""
    with csrf_app.test_client() as client:
        res = client.post(
            '/csrf-protected',
            base_url='https://localhost',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
            headers={
                'Referer': 'http://insecure-referrer'
            }
        )
        assert res.json['message'] == REASON_INSECURE_REFERER
        assert res.status_code == 400


def test_csrf_bad_referrer(csrf_app, csrf):
    """Test CSRF bad referrer in a secure request."""
    with csrf_app.test_client() as client:
        csrf_app.config['APP_ALLOWED_HOSTS'] = [
            'allowed-referrer'
        ]
        not_allowed_referrer = 'https://not-allowed-referrer'
        res = client.post(
            '/csrf-protected',
            base_url='https://localhost',
            data=json.dumps(dict(foo='bar')),
            content_type='application/json',
            headers={
                'Referer': not_allowed_referrer
            }
        )
        assert res.json['message'] == REASON_BAD_REFERER % not_allowed_referrer
        assert res.status_code == 400
