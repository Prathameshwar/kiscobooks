"""Prepare actual rendered fixtures for the headless browser without deploying."""
import base64
import gzip
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[3]
artifacts = root / '.test_artifacts/product-detail-design'
pages = {file.stem: file.read_text(encoding='utf-8') for file in artifacts.glob('*.html')}
css = re.search(r'<style>(.*?)</style>', next(iter(pages.values())), re.S)[1]
bundle = {
    'css': css,
    'pages': {name: re.sub(r'<style>.*?</style>', '<style>__CSS__</style>', html, flags=re.S)
              for name, html in pages.items()},
}
payload = base64.b64encode(gzip.compress(json.dumps(bundle).encode())).decode()
(artifacts / 'browser-input.b64').write_text(payload, encoding='ascii')
browser = (pathlib.Path(__file__).parent / 'browser.cjs').read_text(encoding='utf-8')
browser = browser.replace("require('node:fs').readFileSync(0,'utf8').trim()", repr(payload))
(artifacts / 'vm-browser-script.b64').write_text(
    base64.b64encode(browser.encode()).decode(), encoding='ascii')
print(f'Prepared {len(pages)} rendered pages.')
