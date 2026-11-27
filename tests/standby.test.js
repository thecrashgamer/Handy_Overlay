// Standby (dunkle Uhr) und Aufwecken: node tests/standby.test.js
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8128;
const URL = `http://localhost:${PORT}`;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-standby-'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);

(async () => {
  const server = spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: DATEN },
    stdio: 'ignore',
  });
  await wait(2000);
  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 667, height: 375 } });
    await ctx.request.post(URL + '/api/registrieren', { headers: { 'X-Phonebox': '1' }, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
    const p = await ctx.newPage();
    const jsFehler = [];
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.addInitScript(() => { try { if (localStorage.getItem('phonebox-standby-sek') === null && !window.name) localStorage.setItem('phonebox-standby-sek', '2'); } catch (e) {} });
    await p.goto(URL + '/');
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    const sichtbar = () => p.isVisible('#standby');

    // ---- Standard ohne Einstellung: 10 Minuten (in einem eigenen Browserprofil, damit nichts durcheinanderkommt)
    const frisch = await browser.newContext();
    await frisch.request.post(URL + '/api/anmelden', { headers: { 'X-Phonebox': '1' }, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
    const q0 = await frisch.newPage();
    await q0.goto(URL + '/');
    await q0.waitForFunction(() => typeof standbySekunden === 'function');
    assert.strictEqual(await q0.evaluate(() => standbySekunden()), 600, 'Standard sind 10 Minuten');
    await frisch.close();
    ok('Ohne Einstellung gilt Standby nach 10 Minuten');

    // ---- Schlaeft erst nach der Wartezeit ein
    assert.ok(!(await sichtbar()));
    await wait(1200);
    assert.ok(!(await sichtbar()), 'darf nach 1,2 s noch nicht schlafen (Grenze 2 s)');
    await p.waitForSelector('#standby', { state: 'visible', timeout: 5000 });
    assert.match(await p.textContent('#sb-uhr'), /^\d\d:\d\d$/);
    assert.ok((await p.textContent('#sb-datum')).length > 5);
    await p.waitForFunction(() => document.getElementById('sb-musik').style.display === 'flex');
    assert.strictEqual(await p.textContent('#sb-titel'), 'Testlied Eins');
    assert.strictEqual(await p.textContent('#sb-kuenstler'), 'Test-Band');
    await p.waitForFunction(() => { const c = document.getElementById('sb-cover'); return c.complete && c.naturalWidth > 0; });
    await p.screenshot({ path: (process.env.SHOT || 'phonebox.png').replace('.png', '-standby.png') });
    ok('Nach der Wartezeit erscheint die dunkle Uhr mit Datum, Titel, Kuenstler und Cover');

    // ---- Der erste Tipp weckt nur auf und loest nichts darunter aus
    const box = await p.locator('#weiter').boundingBox();
    await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await wait(500);
    assert.ok(!(await sichtbar()), 'ein Tipp muss aufwecken');
    assert.strictEqual(await p.textContent('#titel'), 'Testlied Eins', 'der Tipp darf nicht auf die Taste darunter durchschlagen');
    ok('Ein Tipp weckt auf, ohne die Taste darunter zu druecken');

    // ---- Nach dem Aufwecken beginnt die Wartezeit neu
    await wait(1200);
    assert.ok(!(await sichtbar()), 'direkt nach dem Aufwecken nicht gleich wieder einschlafen');
    await p.waitForSelector('#standby', { state: 'visible', timeout: 5000 });
    ok('Nach dem Aufwecken beginnt die Wartezeit neu');

    // ---- Tastatur weckt auch auf, und Benutzen verhindert das Einschlafen
    await p.keyboard.press('Space');
    await wait(300);
    assert.ok(!(await sichtbar()));
    for (let i = 0; i < 4; i++) { await p.mouse.move(100 + i * 10, 100); await p.mouse.down(); await p.mouse.up(); await wait(700); }
    assert.ok(!(await sichtbar()), 'solange man tippt, schlaeft die Seite nicht ein');
    ok('Tastendruck weckt auf, und solange jemand das Geraet benutzt, bleibt es wach');

    // ---- Ohne laufende Musik keine Musikzeile
    await p.click('#play');
    await p.waitForFunction(() => document.getElementById('play').textContent.includes('\u25B6'));  // pausiert: Play-Zeichen
    await p.waitForSelector('#standby', { state: 'visible', timeout: 6000 });
    assert.strictEqual(await p.evaluate(() => document.getElementById('sb-musik').style.display), 'none');
    await p.click('#standby');
    await p.click('#play');  // wieder spielen
    ok('Bei pausierter Musik zeigt der Standby nur die Uhr');

    // ---- Claude: "arbeitet" bleibt im Standby sichtbar, "braucht dich" weckt auf
    await p.waitForSelector('#standby', { state: 'visible', timeout: 6000 });
    await p.request.post(URL + '/claude', { data: { status: 'arbeitet', aktion: 'Bearbeitet server.py' } });
    await p.waitForFunction(() => document.getElementById('sb-claude').style.display === 'block');
    assert.match(await p.textContent('#sb-claude-text'), /Claude arbeitet: Bearbeitet server\.py/);
    assert.ok(await sichtbar(), 'arbeitet darf nicht aufwecken');
    await p.request.post(URL + '/claude', { data: { status: 'wartet', text: 'Frage' } });
    await p.waitForSelector('#standby', { state: 'hidden', timeout: 4000 });
    await p.request.post(URL + '/claude', { data: { status: '' } });
    ok('Claude-Status erscheint im Standby, und "Claude braucht dich" weckt auf');

    // ---- Rueckfrage weckt auf und verhindert das Einschlafen
    await p.waitForSelector('#standby', { state: 'visible', timeout: 6000 });
    await p.evaluate(() => ws.send('shortcut:6'));
    await p.waitForSelector('#rueckfrage', { state: 'visible', timeout: 4000 });
    assert.ok(!(await sichtbar()), 'die Rueckfrage muss ueber dem Standby sichtbar sein');
    await wait(3000);  // laenger als die Wartezeit
    assert.ok(await p.isVisible('#rueckfrage') && !(await sichtbar()), 'waehrend einer Rueckfrage nicht einschlafen');
    await p.click('#rf-nein');
    ok('Eine Rueckfrage weckt auf und haelt wach');

    // ---- Manuell einschlafen
    await p.click('#schlaf');
    assert.ok(await sichtbar());
    await p.click('#standby');
    assert.ok(!(await sichtbar()));
    ok('Der Mond-Knopf schickt die Phonebox sofort in den Standby');

    // ---- Verbindungsabbruch im Standby wird gezeigt
    await p.click('#schlaf');
    server.kill();
    await p.waitForFunction(() => /Warte auf PC/.test(document.getElementById('sb-status').textContent), null, { timeout: 8000 });
    ok('Bricht die Verbindung ab, steht das auch im Standby');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));

    // ---- Einstellung "Nie" und die Auswahl in der Konto-Seite
    const server2 = spawn('python3', ['server.py'], { cwd: path.join(__dirname, '..'),
      env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: DATEN }, stdio: 'ignore' });
    await wait(2500);
    try {
      const q = await ctx.newPage();
      await q.addInitScript(() => { try { localStorage.setItem('phonebox-standby-sek', '0'); } catch (e) {} });
      await q.goto(URL + '/');
      await q.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
      await wait(3500);
      assert.ok(!(await q.isVisible('#standby')), 'bei "Nie" schlaeft die Seite nie ein');
      await q.close();
      ok('Mit der Einstellung "Nie" schlaeft die Phonebox nie ein');

      const k = await ctx.newPage();
      await k.goto(URL + '/konto');
      await k.evaluate(() => { localStorage.removeItem('phonebox-standby-sek'); localStorage.removeItem('phonebox-standby'); });
      await k.reload();
      assert.strictEqual(await k.inputValue('#standby'), '10');
      await k.selectOption('#standby', '5');
      assert.strictEqual(await k.evaluate(() => localStorage.getItem('phonebox-standby')), '5');
      await k.reload();
      assert.strictEqual(await k.inputValue('#standby'), '5');
      ok('Die Standby-Zeit laesst sich in der Konto-Seite einstellen und bleibt gespeichert');
    } finally {
      server2.kill();
    }

    console.log('Alle Standby-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
