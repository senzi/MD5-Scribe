"""
Minimal Flask mock for integration testing without installing Flask.
Uses only stdlib + jinja2 (which is available).
"""

import io
import json
import os
import sys
import types
from urllib.parse import urlencode, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import jinja2

# Global context mocks
class _RequestCtx:
    def __init__(self):
        self.form = {}
        self.method = "GET"
        self.args = {}

class _SessionCtx(dict):
    pass

request = _RequestCtx()
session = _SessionCtx()

_flashes = []

def flash(message, category="message"):
    _flashes.append((category, message))

def get_flashed_messages(with_categories=False):
    msgs = list(_flashes)
    _flashes.clear()
    if with_categories:
        return msgs
    return [m for _, m in msgs]

def redirect(location, code=302):
    return Response("", status=code, headers={"Location": location})

def url_for(endpoint, **values):
    if endpoint == "index":
        return "/"
    if endpoint == "init_state":
        return "/init"
    if endpoint == "step_control":
        return f"/step/{values.get('step_id', 0)}"
    if endpoint == "step_print":
        return f"/step/{values.get('step_id', 0)}/print"
    if endpoint == "step_verify":
        return f"/step/{values.get('step_id', 0)}/verify"
    if endpoint == "final_report":
        return "/report"
    parts = [""]
    for k, v in values.items():
        parts.append(f"{k}={v}")
    if len(parts) > 1:
        return "/" + endpoint.replace(".", "/") + "?" + "&".join(parts[1:])
    return "/" + endpoint.replace(".", "/")

def jsonify(*args, **kwargs):
    if args and kwargs:
        data = (dict(args[0], **kwargs))
    elif args:
        data = args[0]
    else:
        data = kwargs
    return Response(json.dumps(data), status=200, content_type="application/json")

class Response:
    def __init__(self, data=b"", status=200, headers=None, content_type="text/html"):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.data = data
        self.status_code = status
        self.headers = headers or {}
        self.content_type = content_type

    def get_json(self, force=False):
        return json.loads(self.data)

class _FakeJinjaEnv:
    globals = {}

class Flask:
    def __init__(self, name):
        self.name = name
        self.routes = []
        self.secret_key = b"mock"
        self.template_folder = "templates"
        self.static_folder = "static"
        self._jinja = None
        self.jinja_env = _FakeJinjaEnv()

    def _get_jinja(self):
        if self._jinja is None:
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            loader = jinja2.FileSystemLoader(os.path.join(here, self.template_folder))
            self._jinja = jinja2.Environment(loader=loader)
        return self._jinja

    def route(self, rule, methods=None, **kwargs):
        methods = methods or ["GET"]
        def decorator(f):
            self.routes.append((rule, methods, f))
            return f
        return decorator

    def run(self, **kwargs):
        pass

    def test_client(self):
        return TestClient(self)

def render_template(template_name, **context):
    import app as app_mod
    env = app_mod.app._get_jinja()
    tmpl = env.get_template(template_name)
    ctx = dict(context)
    ctx.setdefault("get_flashed_messages", get_flashed_messages)
    ctx.setdefault("url_for", url_for)
    ctx.setdefault("zip", zip)
    ctx.setdefault("range", range)
    ctx.setdefault("len", len)
    return tmpl.render(ctx)

class TestClient:
    def __init__(self, app):
        self.app = app
        self.testing = True

    def get(self, path):
        return self._request("GET", path, data=None)

    def post(self, path, data=None, follow_redirects=False):
        resp = self._request("POST", path, data=data)
        if follow_redirects and resp.status_code in (301, 302, 307, 308):
            loc = resp.headers.get("Location", "/")
            return self.get(loc)
        return resp

    def _request(self, method, path, data):
        request.method = method
        request.form = data or {}
        request.args = {}

        if "?" in path:
            path, qs = path.split("?", 1)
            for k, v in parse_qs(qs).items():
                request.args[k] = v[0]

        handler = None
        url_values = {}
        for rule, methods, func in self.app.routes:
            if method not in methods:
                continue
            matched, values = self._match(rule, path)
            if matched:
                handler = func
                url_values = values
                break

        if handler is None:
            return Response(f"Not Found: {path}", status=404)

        try:
            kwargs = dict(url_values)
            result = handler(**kwargs)
            if isinstance(result, str):
                return Response(result)
            return result
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            return Response(f"500 Error: {e}\n{tb}", status=500)

    def _match(self, rule, path):
        import re
        pattern = rule
        pattern = pattern.replace("/", "\/")
        pattern = re.sub(r"<int:(\w+)>", r"{{INT:\1}}", pattern)
        pattern = re.sub(r"<(\w+)>", lambda m: f"(?P<{m.group(1)}>[^/]+)", pattern)
        pattern = re.sub(r"\{\{INT:(\w+)\}\}", lambda m: f"(?P<{m.group(1)}>\\d+)", pattern)
        pattern = "^" + pattern + "$"
        m = re.match(pattern, path)
        if m:
            vals = {}
            for k, v in m.groupdict().items():
                if k.endswith("_id") or k == "id":
                    try:
                        v = int(v)
                    except ValueError:
                        pass
                vals[k] = v
            return True, vals
        return False, {}

sys.modules["flask"] = sys.modules[__name__]
sys.modules["werkzeug"] = types.ModuleType("werkzeug")

Flask.app_context = lambda self: _NullCtx()
Flask.request_context = lambda self, environ: _NullCtx()

class _NullCtx:
    def __enter__(self): pass
    def __exit__(self, *args): pass
