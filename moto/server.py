from __future__ import unicode_literals
import re
import sys
import argparse

from threading import Lock

from flask import Flask
from werkzeug.routing import BaseConverter
from werkzeug.serving import run_simple

from moto.backends import BACKENDS
from moto.core.utils import convert_flask_to_httpretty_response

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "HEAD"]


class DomainDispatcherApplication(object):
    """
    Dispatch requests to different applications based on the "Host:" header
    value. We'll match the host header value with the url_bases of each backend.
    """

    def __init__(self, create_app, service=None, cors=False):
        self.create_app = create_app
        self.lock = Lock()
        self.cors = cors
        self.app_instances = {}
        self.service = service

    def get_backend_for_host(self, host):
        if self.service:
            return self.service

        for backend_name, backend in BACKENDS.items():
            for url_base in backend.url_bases:
                if re.match(url_base, 'http://%s' % host):
                    return backend_name

        raise RuntimeError('Invalid host: "%s"' % host)

    def get_application(self, host):
        host = host.split(':')[0]
        with self.lock:
            backend = self.get_backend_for_host(host)
            app = self.app_instances.get(backend, None)
            if app is None:
                app = self.create_app(backend,self.cors)
                self.app_instances[backend] = app


            return app

    def __call__(self, environ, start_response):
        backend_app = self.get_application(environ['HTTP_HOST'])
        return backend_app(environ, start_response)


class RegexConverter(BaseConverter):
    # http://werkzeug.pocoo.org/docs/routing/#custom-converters
    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]


def create_backend_app(service, cors=False):
    from werkzeug.routing import Map

    # Create the backend_app
    backend_app = Flask(__name__)

    # If we set the CORS flag, wrap the app to accept all
    if cors:
        @backend_app.after_request
        def allow_cors(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "X-CSRF-Token"
            response.headers["Access-Control-Max-Age"] = "3"
            response.headers["Access-Control-Allow-Methods"] = "OPTIONS, HEAD, GET, POST, PUT, DELETE"
            response.headers["X-CSRF-Token"] = "5A44B387B75E54417F6C64FF3D485141"
            print(response.headers)
            return response

    backend_app.debug = True

    # Reset view functions to reset the app
    backend_app.view_functions = {}
    backend_app.url_map = Map()
    backend_app.url_map.converters['regex'] = RegexConverter

    backend = BACKENDS[service]
    for url_path, handler in backend.flask_paths.items():
        if handler.__name__ == 'dispatch':
            endpoint = '{0}.dispatch'.format(handler.__self__.__name__)
        else:
            endpoint = None

        backend_app.route(
            url_path,
            endpoint=endpoint,
            methods=HTTP_METHODS)(convert_flask_to_httpretty_response(handler))

    return backend_app


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()

    # Keep this for backwards compat
    parser.add_argument(
        "service",
        type=str,
        nargs='?',  # http://stackoverflow.com/a/4480202/731592
        default=None)
    parser.add_argument(
        '-H', '--host', type=str,
        help='Which host to bind',
        default='0.0.0.0')
    parser.add_argument(
        '-p', '--port', type=int,
        help='Port number to use for connection',
        default=5000)
    parser.add_argument(
        '-c', '--cors',
        help="Add to set all endpoint's CORS header to accept '*'",
        action='store_true',
        default=False,
        )


    args = parser.parse_args(argv)

    # Wrap the main application
    main_app = DomainDispatcherApplication(
            create_backend_app,
            service=args.service,
            cors=args.cors)
    main_app.debug = True



    run_simple(args.host, args.port, main_app, threaded=True)

if __name__ == '__main__':
    main()
