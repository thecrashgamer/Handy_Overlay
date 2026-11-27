// UI-Test mit Fake-Daten: node tests/ui.test.js  (braucht fastapi + uvicorn und playwright)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8123;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-ui-'));  // frische, leere Konten
const URL = `http://localhost:${PORT}`;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const server = spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_FRIST_S: '3', PHONEBOX_DATEN: DATEN },
    stdio: 'inherit',
  });
  await wait(2000);
  const browser = await chromium.launch();
  const kontext = await browser.newContext({ viewport: { width: 667, height: 375 }, deviceScaleFactor: 1 });
  const page = await kontext.newPage();
  const text = (sel) => page.textContent(sel);
  const ok = (name) => console.log('ok  -', name);
  const seitenFehler = [];  // JavaScript-Fehler der Seite: duerfen im normalen Ablauf nie auftreten
  page.on('pageerror', (e) => seitenFehler.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') seitenFehler.push(m.text()); });
  const log = async () => (await page.request.get(`${URL}/log`)).text();
  try {
    // Ohne Anmeldung kommt man nicht auf die Seite; das erste Konto legt man am PC (localhost) an
    const reg = await page.request.post(`${URL}/api/registrieren`, {
      headers: { 'X-Phonebox': '1' }, data: { name: 'tester', passwort: 'Test-Passwort-77' } });
    assert.ok(reg.ok(), 'Registrierung: ' + await reg.text());
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

    // Herunterfahren: erst nach Rueckfrage, und der Server prueft selbst
    const aus = page.locator('.kachel', { hasText: 'Herunterfahren' }).first();
    await page.waitForSelector('#hinweis', { state: 'hidden' });  // Meldung der Kachel davor abwarten
    const ausgeloest = async () => /ausgelöst|fährt|Fehler/.test(await page.evaluate(() =>
      document.getElementById('hinweis').style.display === 'none' ? '' : document.getElementById('hinweis').textContent));
    await aus.click();
    await page.waitForSelector('#rueckfrage', { state: 'visible' });
    assert.strictEqual(await text('#rf-frage'), 'PC wirklich herunterfahren?');
    assert.ok(!(await ausgeloest()), 'darf noch nicht ausgeloest sein');
    await page.click('#rf-nein');
    await wait(500);
    assert.ok(!(await page.isVisible('#rueckfrage')) && !(await ausgeloest()));
    ok('Herunterfahren: Abbrechen loest nichts aus');
    await page.evaluate(() => ws.send('bestaetigt:6'));  // Bestaetigung ohne Rueckfrage
    await wait(700);
    assert.ok(!(await ausgeloest()), 'Server hat unaufgeforderte Bestaetigung angenommen');
    ok('Herunterfahren: Bestaetigung ohne Rueckfrage wird vom Server abgelehnt');
    await aus.click();
    await page.waitForSelector('#rueckfrage', { state: 'visible' });
    await wait(3800);  // Frist (im Test 3 s) laeuft ab
    assert.ok(!(await page.isVisible('#rueckfrage')), 'Rueckfrage laeuft nicht ab');
    await page.evaluate(() => ws.send('bestaetigt:6'));
    await wait(700);
    assert.ok(!(await ausgeloest()), 'abgelaufene Bestaetigung angenommen');
    ok('Herunterfahren: Rueckfrage laeuft ab, danach ist Bestaetigen wirkungslos');
    await aus.click();
    await page.waitForSelector('#rueckfrage', { state: 'visible' });
    await page.screenshot({ path: (process.env.SHOT || 'phonebox.png').replace('.png', '-frage.png') });
    await page.click('#rf-ja');
    await page.waitForFunction(() => document.getElementById('hinweis').textContent.includes('herunter'));
    ok('Herunterfahren: nach "Ja" wird es ausgeloest und gemeldet');
    const prot = await log();
    assert.ok(prot.includes('Rueckfrage gesendet: Herunterfahren an'), 'Protokoll: Rueckfrage nicht gesendet');
    assert.ok(prot.includes('Rueckfrage angezeigt auf einer Seite: gezeigt:6'), 'Protokoll: Anzeige nicht gemeldet');
    assert.ok(!prot.includes('WARNUNG: Seite'), 'aktuelle Seite faelschlich als alt gemeldet');
    ok('Protokoll belegt: Rueckfrage gesendet und auf der Seite angezeigt');
    assert.deepStrictEqual(seitenFehler, [], 'JavaScript-Fehler: ' + seitenFehler.join(' | '));
    ok('keine JavaScript-Fehler im normalen Ablauf');

    // Eine alte Seite ohne Rueckfrage-Fenster (alte index.html oder aus dem Zwischenspeicher)
    // muss der Server im Protokoll melden, sonst passiert beim Herunterfahren scheinbar nichts.
    await page.evaluate((p) => { window.alteSeite = new WebSocket('ws://localhost:' + p + '/ws'); }, PORT);
    await page.waitForFunction(() => window.alteSeite.readyState === 1);
    await wait(300);
    assert.ok((await log()).includes('WARNUNG: Seite ohne Versionskennung'), 'alte Seite nicht gemeldet');
    await page.evaluate(() => ws.send('shortcut:6'));
    await page.waitForSelector('#rueckfrage', { state: 'visible' });
    await page.click('#rf-nein');
    assert.ok((await log()).includes('davon zu alt: alt'), 'Rueckfrage an alte Seite nicht gemeldet');
    await page.evaluate(() => window.alteSeite.close());
    ok('alte Seite ohne Versionskennung wird im Protokoll gemeldet');

    // Nachrichten in der Form, wie sie am echten Windows-PC kommen (Spotify zu, Lautstaerke fehlt ...)
    const ECHT = {
      'Spotify nicht offen': (d) => { delete d.dauer; delete d.position; d.titel = 'Spotify ist nicht offen'; d.kuenstler = ''; d.cover = ''; d.laut = null; },
      'leere Werte': (d) => { d.titel = null; d.kuenstler = null; d.laut = null; d.cover = ''; d.dauer = 0; d.position = 0; },
      'Claude mit Verlauf': (d) => { d.claude = { status: 'arbeitet', text: '', aktion: 'Bearbeitet a.py', projekt: 'X', seit: Date.now() - 5000, dauer: 0, verlauf: [{ zeit: Date.now(), text: 'Bearbeitet a.py' }], jetzt: Date.now() }; },
      // ein Teil der Nachricht, an dem die Anzeige scheitert: Rueckfrage muss trotzdem erscheinen
      'kaputte Teile': (d) => { d.shortcuts = {}; d.claude = { status: 'fertig', verlauf: [null] }; },
    };
    for (const viewport of [{ width: 667, height: 375 }, { width: 375, height: 667 }]) {
      for (const [name, form] of Object.entries(ECHT)) {
        const p2 = await kontext.newPage();  // gleiche Anmeldung wie die Hauptseite
        await p2.setViewportSize(viewport);
        const fehler2 = [];
        p2.on('pageerror', (e) => fehler2.push(e.message));
        await p2.routeWebSocket(/\/ws(\?.*)?$/, (wsr) => {
          const srv = wsr.connectToServer();
          srv.onMessage((m) => { const d = JSON.parse(m); if (d.version) form(d); wsr.send(JSON.stringify(d)); });
          wsr.onMessage((m) => srv.send(m));
        });
        await p2.goto(URL);
        await p2.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
        await p2.evaluate(() => ws.send('shortcut:6'));
        await p2.waitForSelector('#rueckfrage', { state: 'visible', timeout: 3000 })
          .catch(() => { throw new Error(`Rueckfrage fehlt bei "${name}" ${viewport.width}x${viewport.height}`); });
        assert.strictEqual(await p2.textContent('#rf-frage'), 'PC wirklich herunterfahren?');
        if (name === 'kaputte Teile') {
          await p2.waitForSelector('#jsfehler', { state: 'visible' });
          assert.match(await p2.textContent('#jsfehler'), /Extras: .+/, 'Fehler in Extras nicht angezeigt');
          assert.match(await p2.textContent('#jsfehler'), /Claude: .+/, 'Fehler in Claude nicht angezeigt');
        } else {
          assert.deepStrictEqual(fehler2, [], 'JavaScript-Fehler: ' + fehler2.join(' | '));
          assert.ok(!(await p2.isVisible('#jsfehler')), 'Fehlerleiste ohne Fehler sichtbar');
        }
        await p2.click('#rf-nein');
        await p2.close();
      }
    }
    ok('Rueckfrage erscheint auch mit echten Datenformen und trotz kaputter Teile (beide Ausrichtungen)');

    await page.evaluate(() => setTimeout(() => { throw new Error('Probefehler'); }, 0));
    await page.waitForFunction(() => document.getElementById('jsfehler').textContent.includes('Probefehler'));
    await page.click('#jsfehler');
    assert.ok(!(await page.isVisible('#jsfehler')));
    ok('JavaScript-Fehler erscheinen als rote Leiste und lassen sich wegtippen');

    // Serverfehler erscheinen auf der Seite und der Server laeuft weiter
    await page.evaluate(() => ws.send('fehlertest'));
    await page.waitForFunction(() => document.getElementById('hinweis').textContent.includes('Testfehler'));
    ok('Serverfehler erscheint als rote Meldung');
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
      env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_FRIST_S: '3', PHONEBOX_DATEN: DATEN },
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
