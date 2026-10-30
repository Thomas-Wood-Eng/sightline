"""Record the browser extension on its look-alike checkout page for the demo video:
python demo/record_extension_clip.py  ->  demo/assets/extension_clip.webm

The real extension, loaded unpacked in Chromium, on extension/test/fixtures/paypal_review.html (a local page that says it is
not PayPal). Silent: Chromium is muted and the copy's speech calls are stubbed, as in the extension tests.
"""
import functools
import http.server
import json
import shutil
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT, FIXTURES = ROOT / 'extension', ROOT / 'extension/test/fixtures'
OUT = ROOT / 'demo/assets/extension_clip.webm'
DIALOG = 'iframe[title="Sightline payment check"]'
SIZE = {'width': 1920, 'height': 940}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    tmp = Path(tempfile.mkdtemp())
    ext = tmp / 'sightline'
    shutil.copytree(EXT, ext, ignore=shutil.ignore_patterns('test', 'screenshots'))
    manifest = json.loads((ext / 'manifest.json').read_text(encoding='utf-8'))
    manifest['content_scripts'][0]['matches'].append('http://127.0.0.1/*')   # the local look-alike page
    (ext / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    for js in ext.glob('*.js'):   # never make a sound on this computer
        js.write_text('if (self.speechSynthesis) speechSynthesis.speak = () => {};\n' + js.read_text(encoding='utf-8'),
                      encoding='utf-8')
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(FIXTURES)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp / 'profile'), channel='chromium', headless=True, viewport=SIZE, record_video_dir=str(tmp / 'video'),
            record_video_size=SIZE, args=[f'--disable-extensions-except={ext}', f'--load-extension={ext}', '--mute-audio'])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
        setup = ctx.new_page()   # set the PIN in the extension's own settings page (its own video, discarded)
        try:
            setup.goto(f"chrome-extension://{sw.url.split('/')[2]}/popup.html")
        except Error:   # the extension opens its settings page on install, racing this navigation to the same page
            setup.wait_for_load_state()
        setup.fill('#new', '1234')
        setup.fill('#repeat', '1234')
        setup.click('text=Save PIN')
        setup.close()
        for extra in ctx.pages:   # e.g. the settings tab opened on install
            extra.close()
        page = ctx.new_page()
        page.goto(f'{base}/paypal_review.html')
        page.wait_for_timeout(1200)
        page.click('#pay')
        dlg = page.frame_locator(DIALOG)
        dlg.locator('#confirm').wait_for()
        page.wait_for_timeout(2600)   # the Readback, read on screen
        dlg.locator('#confirm').click()
        dlg.locator('#pin').wait_for()
        page.wait_for_timeout(900)
        dlg.locator('#pin').press_sequentially('1234', delay=180)
        page.wait_for_timeout(2300)   # the PIN step stays on screen long enough to read
        dlg.locator('#pin').press('Enter')
        dlg.locator('#count').wait_for()
        page.wait_for_timeout(2500)   # the undo countdown
        dlg.locator('#undo').press('Enter')   # the shopper changes their mind
        page.wait_for_timeout(2200)   # the page's own result: not paid
        video = page.video.path()
        ctx.close()
    httpd.shutdown()
    shutil.copy(video, OUT)
    print(OUT)


if __name__ == '__main__':
    main()
