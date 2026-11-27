// Test des Admin-Bereichs (Shortcuts bearbeiten): node tests/admin.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8125;
const URL = `http://localhost:${PORT}`;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-admin-'));
const PW = 'Sommer-Regen-42';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const H = { 'X-Phonebox': '1' };
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
    // Zugang: Administrator (am PC angelegt) und ein normaler Benutzer
    const adminCtx = await browser.newContext({ viewport: { width: 900, height: 900 } });
    const reg = await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    assert.ok(reg.ok());
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } }); // ohne Anmeldung: abgelehnt
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast1', passwort: 'Wolken-Kaffee-19' } });

    // ---- Nur Administratoren
    const anonym = await request.newContext();
    assert.strictEqual((await anonym.get(URL + '/admin', { maxRedirects: 0 })).status(), 303);
    assert.strictEqual((await anonym.get(URL + '/api/shortcuts')).status(), 401);
    assert.strictEqual((await gastCtx.request.get(URL + '/admin')).status(), 403);
    assert.strictEqual((await gastCtx.request.get(URL + '/api/shortcuts')).status(), 403);
    const gastSpeichern = await gastCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: [{ name: 'X', programm: 'cmd.exe' }], passwort: 'Wolken-Kaffee-19' } });
    assert.strictEqual(gastSpeichern.status(), 403);
    assert.ok(!fs.existsSync(path.join(DATEN, 'shortcuts.json')), 'Gast darf nichts gespeichert haben');
    ok('Admin-Bereich nur fuer Administratoren (Seite, Liste und Speichern)');

    // ---- Seite laedt die Standardliste
    const p = await adminCtx.newPage();
    const jsFehler = [];
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.goto(URL + '/admin');
    await p.waitForFunction(() => document.querySelectorAll('#liste .karte').length > 0);
    const anzahlStart = await p.locator('#liste .karte').count();
    assert.ok(anzahlStart >= 6);
    assert.strictEqual(await p.locator('#vorschau .kachel').count(), anzahlStart);
    assert.match(await p.textContent('#quelle'), /Standardliste/);
    assert.ok(await p.isDisabled('#speichern'), 'ohne Aenderung nichts zu speichern');
    ok('Admin-Seite zeigt Standardliste und Vorschau, Speichern erst bei Aenderungen');

    // ---- Neuen Shortcut anlegen (Programm)
    await p.click('text=+ Neuer Shortcut');
    const neu = p.locator('#liste .karte').last();
    await neu.locator('input[type=text]').first().fill('Notizen');
    await neu.locator('.iconknopf').click();
    await p.locator('#emoji button', { hasText: '📝' }).first().click();
    await neu.locator('input[placeholder^="z. B. calc"]').fill('notepad.exe');
    assert.ok(await p.isEnabled('#speichern'));
    assert.strictEqual(await p.locator('#vorschau .kachel').count(), anzahlStart + 1);
    assert.match(await p.locator('#vorschau .kachel').last().textContent(), /📝.*Notizen/);
    ok('Neuer Shortcut mit Symbol erscheint sofort in der Vorschau');

    // ---- Tastenkuerzel aufnehmen
    await p.click('text=+ Neuer Shortcut');
    const tk = p.locator('#liste .karte').last();
    await tk.locator('input[type=text]').first().fill('Mitschnitt');
    await tk.locator('select').first().selectOption('tasten');
    await tk.locator('button:has-text("Aufnehmen")').click();
    await p.keyboard.press('Control+Shift+KeyM');
    assert.strictEqual(await tk.locator('input[placeholder^="z. B. ctrl"]').inputValue(), 'ctrl+shift+m');
    ok('Tastenkuerzel lassen sich aufnehmen (Strg+Umschalt+M -> ctrl+shift+m)');

    // ---- Speichern braucht das richtige Passwort
    await p.click('#speichern');
    assert.match(await p.textContent('#meldung'), /Passwort/);
    await p.fill('#pw', 'falsch-falsch-1');
    await p.click('#speichern');
    await p.waitForFunction(() => /Passwort stimmt nicht/.test(document.getElementById('meldung').textContent));
    assert.ok(!fs.existsSync(path.join(DATEN, 'shortcuts.json')), 'mit falschem Passwort darf nichts gespeichert werden');
    ok('Speichern verlangt das Passwort, falsches wird abgelehnt');

    // ---- Server prueft streng: doppelter Name, ungueltiges Kuerzel
    await tk.locator('input[placeholder^="z. B. ctrl"]').fill('ctrl+quatsch');
    await p.fill('#pw', PW);
    await p.click('#speichern');
    await p.waitForFunction(() => /Tastenkuerzel ungueltig/.test(document.getElementById('meldung').textContent));
    assert.ok(!fs.existsSync(path.join(DATEN, 'shortcuts.json')));
    await tk.locator('input[placeholder^="z. B. ctrl"]').fill('ctrl+shift+m');
    await tk.locator('input[type=text]').first().fill('notizen');  // gleicher Name wie "Notizen"
    await p.fill('#pw', PW);
    await p.click('#speichern');
    await p.waitForFunction(() => /doppelt/.test(document.getElementById('meldung').textContent));
    ok('Ungueltiges Kuerzel und doppelter Name werden vom Server abgelehnt');

    // ---- Reihenfolge, loeschen, speichern
    await tk.locator('input[type=text]').first().fill('Mitschnitt');
    await p.locator('#liste .karte').last().locator('button[title="Nach oben"]').click();  // Mitschnitt vor Notizen
    p.once('dialog', (d) => d.accept());
    await p.locator('#liste .karte').first().locator('button[title="Löschen"]').click();      // ersten (Rechner) loeschen
    const erwartet = (await p.locator('#liste .karte input[type=text]').evaluateAll((els) => els.filter((e) => e.placeholder === 'Name').map((e) => e.value)));
    assert.deepStrictEqual(erwartet.slice(-2), ['Mitschnitt', 'Notizen']);
    assert.ok(!erwartet.includes('Rechner'));
    await p.fill('#pw', PW);
    await p.click('#speichern');
    await p.waitForFunction(() => /Gespeichert/.test(document.getElementById('meldung').textContent));
    assert.ok(await p.isDisabled('#speichern'), 'nach dem Speichern ist nichts mehr offen');
    const datei = JSON.parse(fs.readFileSync(path.join(DATEN, 'shortcuts.json'), 'utf-8'));
    assert.deepStrictEqual(datei.slice(-2).map((e) => e.name), ['Mitschnitt', 'Notizen']);
    assert.strictEqual(datei.find((e) => e.name === 'Mitschnitt').tasten, 'ctrl+shift+m');
    assert.deepStrictEqual(datei.find((e) => e.name === 'Notizen'), { name: 'Notizen', icon: '📝', programm: 'notepad.exe' });
    assert.ok(!datei.some((e) => e.name === 'Rechner'));
    assert.strictEqual(jsFehler.length, 0, 'JavaScript-Fehler: ' + jsFehler.join(' | '));
    ok('Reihenfolge aendern, loeschen und speichern: Datei in daten/ ist korrekt');

    // ---- Am Handy erscheint die neue Liste (ohne Neustart)
    const handy = await adminCtx.newPage();
    await handy.goto(URL + '/');
    await handy.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await handy.click('#wechsel');
    await handy.waitForFunction(() => document.querySelectorAll('.kachel').length > 0);
    const namenHandy = await handy.locator('.kachel span:nth-child(2)').allTextContents();
    assert.deepStrictEqual(namenHandy.slice(-2), ['Mitschnitt', 'Notizen']);
    assert.ok(!namenHandy.includes('Rechner'));
    // und aendert sich live, wenn im Admin-Bereich wieder gespeichert wird
    await p.locator('#liste .karte').last().locator('input[type=text]').first().fill('Notizblock');
    await p.fill('#pw', PW);
    await p.click('#speichern');
    await handy.waitForFunction(() => Array.from(document.querySelectorAll('.kachel span:nth-child(2)')).some((s) => s.textContent === 'Notizblock'), null, { timeout: 5000 });
    ok('Das Handy zeigt die neue Liste sofort (live, ohne Neuladen)');

    // ---- Ausloesen am Handy funktioniert mit der neuen Liste (Testmodus fuehrt nichts aus)
    await handy.locator('.kachel', { hasText: 'Notizblock' }).click();
    await handy.waitForFunction(() => document.getElementById('hinweis').textContent.includes('Notizblock ausgel'));
    ok('Ein neu angelegter Shortcut laesst sich am Handy ausloesen');

    // ---- Herunterfahren bleibt mit Rueckfrage, auch wenn man den Haken im Formular nicht setzt
    await p.reload();
    await p.waitForSelector('#liste .karte');
    const roh = await adminCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: [{ name: 'Aus', aktion: 'herunterfahren' }, { name: 'Weg', programm: 'x.exe', argumente: ['a b'] }], passwort: PW } });
    assert.ok(roh.ok());
    await handy.waitForFunction(() => document.querySelectorAll('.kachel').length === 2);
    await handy.locator('.kachel', { hasText: 'Aus' }).click();
    await handy.waitForSelector('#rueckfrage', { state: 'visible' });
    await handy.click('#rf-nein');
    ok('Herunterfahren fragt immer nach, auch ohne gesetzten Haken');

    // ---- Datei ist von Hand reparierbar und die alte Fassung bleibt als Sicherung
    assert.ok(fs.existsSync(path.join(DATEN, 'shortcuts.json.bak')), 'Sicherung fehlt');
    ok('Die vorherige Fassung bleibt als shortcuts.json.bak erhalten');

    console.log('Alle Admin-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
