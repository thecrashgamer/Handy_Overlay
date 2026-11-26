// UI-Test mit Fake-Daten: node tests/ui.test.js  (braucht fastapi + uvicorn und playwright)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');

const PORT = 8123;
const URL = `http://localhost:${PORT}`;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const server = spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT) },
    stdio: 'inherit',
  });
  await wait(2000);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 667, height: 375 }, deviceScaleFactor: 1 });
  const text = (sel) => page.textContent(sel);
  const ok = (name) => console.log('ok  -', name);
  try {
    await page.goto(URL);
    await page.waitForFunction(() => document.getElementById('status').textContent === 'Verbunden');
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Testlied Eins');
    ok('verbindet und zeigt Titel');

    await page.click('#weiter');
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Zweites Lied');
    assert.strictEqual(await text('#kuenstler'), 'Die Pruefer');
    ok('Weiter wechselt den Titel');

    await page.click('#zurueck');
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Testlied Eins');
    ok('Zurueck wechselt den Titel');

    const vorher = await page.innerHTML('#play');
    await page.click('#play');
    await page.waitForFunction((v) => document.getElementById('play').innerHTML !== v, vorher);
    ok('Play/Pause schaltet das Symbol um');

    await page.waitForFunction(() => {
      const c = document.getElementById('cover');
      return c.style.display === 'block' && c.complete && c.naturalWidth > 0;
    });
    ok('Cover wird geladen');

    await page.fill('#laut', '80');
    await page.dispatchEvent('#laut', 'change');
    await wait(500);
    await page.reload();
    await page.waitForFunction(() => document.getElementById('laut').value === '80');
    ok('Lautstaerke wird gesetzt und gemerkt');

    await page.request.post(`${URL}/claude`, { data: { status: 'arbeitet' } });
    await page.waitForFunction(() => document.getElementById('claude').textContent.includes('arbeitet'));
    ok('Claude-Status "arbeitet" erscheint');
    await page.request.post(`${URL}/claude`, { data: { status: 'wartet', text: 'Frage offen' } });
    await page.waitForFunction(() => document.getElementById('claude').textContent === 'Frage offen');
    ok('Claude-Status mit eigenem Text');

    await page.screenshot({ path: process.env.SHOT || 'phonebox.png' });

    // Extras-Ansicht
    await page.click('#wechsel');
    assert.ok(await page.isVisible('#extras'));
    assert.ok(!(await page.isVisible('#titel')));
    assert.match(await text('#uhr'), /^\d\d:\d\d$/);
    await page.waitForFunction(() => /^CPU \d+ %$/.test(document.getElementById('cputext').textContent));
    await page.waitForFunction(() => /^RAM \d+ %$/.test(document.getElementById('ramtext').textContent));
    ok('Extras: Uhr, CPU und RAM');
    const kacheln = await page.locator('.kachel').count();
    assert.ok(kacheln >= 1, 'keine Shortcut-Kacheln');
    const erster = (await page.locator('.kachel span').nth(1).textContent());
    await page.locator('.kachel').first().click();
    await page.waitForFunction((n) => document.getElementById('hinweis').textContent === n + ' ausgelöst', erster);
    ok('Shortcut "' + erster + '" wird ausgeloest und bestaetigt');
    await page.screenshot({ path: (process.env.SHOT || 'phonebox.png').replace('.png', '-extras.png') });
    await page.reload();
    assert.ok(await page.isVisible('#extras'), 'Ansicht wird nicht gemerkt');
    ok('Ansicht wird nach dem Neuladen gemerkt');
    await page.click('#wechsel');
    assert.ok(await page.isVisible('#titel'));

    server.kill();
    await page.waitForFunction(() => document.getElementById('status').textContent === 'Warte auf PC ...');
    ok('zeigt "Warte auf PC" bei ausgeschaltetem Server');

    const neu = spawn('python3', ['server.py'], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT) },
      stdio: 'inherit',
    });
    await page.waitForFunction(() => document.getElementById('status').textContent === 'Verbunden', null, { timeout: 15000 });
    ok('verbindet sich nach Neustart von selbst neu');
    neu.kill();
    console.log('Alle Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
