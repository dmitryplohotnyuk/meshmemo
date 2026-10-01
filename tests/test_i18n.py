"""Keep every shipped locale complete, including text interpolation and accessible labels."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src/meshtastic_sf/web'


def test_locale_catalogs_cover_ui_and_preserve_placeholders():
    catalogs = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'static/locales').glob('*.json')}
    source = catalogs['ru']
    markup = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    static_keys = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', markup))
    assert static_keys <= source.keys(), static_keys - source.keys()
    for lang, catalog in catalogs.items():
        assert catalog.keys() == source.keys(), lang
        for key, value in catalog.items():
            if isinstance(value, dict):
                assert set(value) == {'one', 'few', 'many', 'other'}
                assert all('{count}' in form for form in value.values())
            else:
                assert value.strip(), (lang, key)
                assert set(re.findall(r'\{\w+\}', value)) == set(re.findall(r'\{\w+\}', source[key])), (lang, key)


def test_language_assets_are_served_without_opening_usb(tmp_path):
    from fastapi.testclient import TestClient
    from functools import partial
    from meshtastic_sf.web.application import create_app
    create_app = partial(create_app, admin_password="test-only-password")
    TestClient = partial(TestClient, headers={"Authorization": "Basic YWRtaW46dGVzdC1vbmx5LXBhc3N3b3Jk"})
    with TestClient(create_app(str(tmp_path / 'archive.db')), base_url='http://127.0.0.1') as client:
        for lang in ('ru', 'uk', 'en'):
            response = client.get(f'/static/locales/{lang}.json')
            assert response.status_code == 200
            assert 'message_count' in response.json()
        assert client.get('/static/i18n.js').status_code == 200
        assert client.get('/api/status').json()['runtime']['device'] is None
