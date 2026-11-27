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
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Testlied Eins');
    ok('verbindet und zeigt Titel');

    await page.click('#weiter');
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Zweites Lied');
    assert.strictEqual(await text('#kuenstler'), 'Die Pruefer');
    ok('Weiter wechselt den Titel');

    await page.click('#zurueck');
    await page.waitForFunction(() => document.getElementById('titel').textContent === 'Testlied Eins');
    ok('Zurueck wechselt den Titel');

    // Zeitleiste: laeuft von selbst weiter und springt auf Wunsch
    await page.waitForFunction(() => document.getElementById('dauer').textContent === '3:20');
    const pos1 = Number(await page.inputValue('#zeit'));
    await wait(2200);
    const pos2 = Number(await page.inputValue('#zeit'));
    assert.ok(pos2 > pos1, `Zeitleiste laeuft nicht (${pos1} -> ${pos2})`);
    ok('Zeitleiste zeigt Laufzeit und laeuft weiter');
    await page.fill('#zeit', '120');
    await page.dispatchEvent('#zeit', 'change');
    await wait(1800);
    await page.reload();
    await page.waitForFunction(() => Number(document.getElementById('zeit').value) >= 120);
    const gesprungen = Number(await page.inputValue('#zeit'));
    assert.ok(gesprungen >= 120 && gesprungen < 130, 'Sprung nicht uebernommen: ' + gesprungen);
    ok('Sprung in der Zeitleiste klappt (auf ' + gesprungen + ' s)');

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

    const protokoll = await (await page.request.get(`${URL}/log`)).text();
    assert.ok(protokoll.includes('laeuft auf Port'), 'Protokoll leer');
    ok('/log zeigt das Server-Protokoll');

    await page.request.post(`${URL}/claude`, { data: { status: 'arbeitet' } });
    await page.waitForFunction(() => document.getElementById('claude').textContent.includes('arbeitet'));
    ok('Claude-Status "arbeitet" erscheint');
    await page.request.post(`${URL}/claude`, { data: { status: 'wartet', text: 'Frage offen' } });
    await page.waitForFunction(() => document.getElementById('claude').textContent === 'Frage offen');
    ok('Claude-Status mit eigenem Text');

    // Claude-Ansicht: Aktion, Verlauf, Stoppuhr
    const post = (d) => page.request.post(`${URL}/claude`, { data: d });
    await post({ status: 'arbeitet', neu: true, projekt: 'Handy_Overlay', aktion: 'Neue Aufgabe: Cover bauen' });
    await post({ status: 'arbeitet', aktion: 'Bearbeitet server.py' });
    await post({ status: 'arbeitet', aktion: 'Liest medien.py' });
    await page.waitForFunction(() => document.getElementById('claude').textContent === 'Claude: Liest medien.py');
    ok('Banner zeigt die aktuelle Aktion');
    await page.click('#wechsel');
    await page.click('#wechsel');
    assert.ok(await page.isVisible('#claudeview'), 'Claude-Ansicht nicht sichtbar');
    assert.ok(!(await page.isVisible('#claude')), 'Banner sollte dort ausgeblendet sein');
    await page.waitForFunction(() => document.getElementById('cl-aktion').textContent === 'Liest medien.py');
    assert.strictEqual(await text('#cl-titel'), 'Claude arbeitet');
    assert.strictEqual(await text('#cl-projekt'), 'Projekt: Handy_Overlay');
    assert.match(await text('#cl-zeit'), /^seit \d+:\d\d$/);
    const verlauf = await page.locator('#cl-verlauf li').allTextContents();
    assert.strictEqual(verlauf.length, 3, 'Verlauf: ' + JSON.stringify(verlauf));
    assert.ok(verlauf[0].endsWith('Liest medien.py') && verlauf[2].endsWith('Neue Aufgabe: Cover bauen'));
    ok('Claude-Ansicht: Projekt, Aktion, Stoppuhr und Verlauf (neueste zuerst)');
    await post({ status: 'arbeitet', aktion: 'Liest medien.py' });  // gleiche Aktion nicht doppelt
    await wait(300);
    assert.strictEqual(await page.locator('#cl-verlauf li').count(), 3);
    await post({ status: 'fertig' });
    await page.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude ist fertig');
    assert.match(await text('#cl-zeit'), /^fertig nach \d+:\d\d$/);
    ok('Claude-Ansicht: fertig mit Dauer');
    await page.screenshot({ path: (process.env.SHOT || 'phonebox.png').replace('.png', '-claude.png') });
    await page.click('#wechsel');  // zurueck zu Musik
    assert.ok(await page.isVisible('#titel'));
    await post({ status: 'arbeitet', aktion: 'x' });
    await post({ status: '' });
    await page.waitForFunction(() => document.getElementById('claude').textContent === '');
    ok('leerer Status blendet das Banner aus');

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
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'), null, { timeout: 15000 });
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
