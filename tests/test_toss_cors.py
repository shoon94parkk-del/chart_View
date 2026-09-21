"""Exercise production CORS configuration without starting market-data workers."""
import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def client():
    app = FastAPI()
    source = ast.parse(Path('main.py').read_text(encoding='utf-8'))
    statement = next(node for node in source.body if isinstance(node, ast.Expr)
                     and isinstance(node.value, ast.Call)
                     and isinstance(node.value.func, ast.Attribute)
                     and node.value.func.attr == 'add_middleware')
    exec(compile(ast.Module(body=[statement], type_ignores=[]), 'cors-config', 'exec'),
         {'app': app, 'CORSMiddleware': CORSMiddleware})

    @app.get('/api/search')
    def search():
        return {'results': []}

    return TestClient(app)


@pytest.mark.parametrize('origin', [
    'https://chartview.web.tossmini.com',
    'https://chartview.private-web.tossmini.com',
    'https://chartview.apps.tossmini.com',
    'https://chart-view-toss.onrender.com',
])
def test_toss_get_and_preflight(origin):
    with client() as http:
        preflight = http.options('/api/search', headers={'Origin': origin,
            'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'cache-control'})
        assert preflight.status_code == 200
        assert preflight.headers['access-control-allow-origin'] == origin
        response = http.get('/api/search', headers={'Origin': origin})
        assert response.headers['access-control-allow-origin'] == origin


def test_unrelated_origin_is_not_allowed():
    with client() as http:
        response = http.options('/api/search', headers={'Origin': 'https://attacker.example',
            'Access-Control-Request-Method': 'GET'})
        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers
