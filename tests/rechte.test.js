// Rechte pro Benutzer und Aktivitaetsprotokoll: node tests/rechte.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8127;
const URL = `http://localhost:${PORT}`;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-rechte-'));
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);

function starten() {
  return spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: DATEN },
    stdio: 'ignore',
  });
}

(async () => {
  let server = starten();
  await wait(2000);
  const browser = await chromium.launch();
  try {
    // ---- Konten: Administrator und Gast
    const adminCtx = await browser.newContext({ viewport: { width: 700, height: 500 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext({ viewport: { width: 700, height: 500 } });
    const reg = await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    assert.ok(reg.ok(), await reg.text());
    const gastId = (await (await adminCtx.request.get(URL + '/api/benutzer')).json()).benutzer.find((b) => b.name === 'Gast').id;
    const aktion = (aktionsname) => adminCtx.request.post(URL + '/api/benutzer/aktion', { headers: H, data: { id: gastId, aktion: aktionsname } });

    const admin = await adminCtx.newPage();
    const gast = await gastCtx.newPage();
    for (const p of [admin, gast]) {
      await p.goto(URL + '/');
      await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    }
    const ichGast = await (await gastCtx.request.get(URL + '/api/ich')).json();
    assert.deepStrictEqual(ichGast.rechte, { musik: true, shortcuts: false, admin: false });
    ok('Neues Konto bekommt sichere Standardrechte (Musik ja, Shortcuts nein)');

    // ---- Gast: Musik geht, Kacheln sind gesperrt
    await gast.click('#weiter');
    await gast.waitForFunction(() => document.getElementById('titel').textContent === 'Zweites Lied');
    await gast.click('#wechsel');
    await gast.waitForFunction(() => document.querySelectorAll('.kachel').length >= 8);
    assert.strictEqual(await gast.locator('.kachel.gesperrt').count(), await gast.locator('.kachel').count());
    await gast.locator('.kachel').first().click();
    assert.match(await gast.textContent('#hinweis'), /keine Berechtigung/);
    ok('Gast darf Musik steuern, alle Kacheln sind gesperrt und zeigen ein Schloss');

    // ---- Angriff: der Gast schickt den Befehl direkt, ohne die Oberflaeche
    await gast.evaluate(() => ws.send('shortcut:0'));
    await gast.waitForFunction(() => /keine Berechtigung/.test(document.getElementById('hinweis').textContent));
    await gast.evaluate(() => ws.send('shortcut:6'));  // Herunterfahren
    await wait(600);
    assert.ok(!(await gast.isVisible('#rueckfrage')), 'Gast bekommt keine Rueckfrage fuers Herunterfahren');
    assert.ok(!(await admin.isVisible('#rueckfrage')), 'auch der Administrator wird nicht belaestigt');
    ok('Ein Gast, der Befehle direkt schickt, wird vom Server abgewiesen');

    // ---- Administrator gibt Shortcuts frei
    await aktion('shortcuts_an');
    await gast.waitForFunction(() => document.querySelectorAll('.kachel:not(.gesperrt)').length > 0, null, { timeout: 6000 });
    const frei = await gast.locator('.kachel:not(.gesperrt) span:nth-child(2)').allTextContents();
    assert.ok(frei.includes('Rechner') && frei.includes('Sperren'));
    assert.ok(!frei.includes('Herunterfahren') && !frei.includes('Herunterfahren stoppen'), 'Herunterfahren bleibt Administratoren vorbehalten: ' + frei);
    await gast.locator('.kachel', { hasText: 'Rechner' }).click();
    await gast.waitForFunction(() => document.getElementById('hinweis').textContent === 'Rechner ausgelöst');
    ok('Mit Shortcut-Recht darf der Gast normale Kacheln nutzen, Herunterfahren bleibt gesperrt');

    await gast.evaluate(() => ws.send('shortcut:6'));
    await wait(600);
    assert.ok(!(await gast.isVisible('#rueckfrage')));
    await gast.evaluate(() => ws.send('shortcut:7'));
    await gast.waitForFunction(() => /keine Berechtigung/.test(document.getElementById('hinweis').textContent));
    ok('Herunterfahren und Abbrechen sind trotz Shortcut-Recht nur fuer Administratoren');

    // ---- Rueckfragen gehoeren dem, der sie ausgeloest hat
    await admin.click('#wechsel');
    await admin.locator('.kachel', { hasText: 'Herunterfahren' }).first().click();
    await admin.waitForSelector('#rueckfrage', { state: 'visible' });
    await wait(1500);
    assert.ok(!(await gast.isVisible('#rueckfrage')), 'der Gast darf die Rueckfrage des Administrators nicht sehen');
    await gast.evaluate(() => ws.send('bestaetigt:6'));  // Angriff: fremde Rueckfrage bestaetigen
    await gast.evaluate(() => ws.send('abbruch'));        // und fremde Rueckfrage wegnehmen
    await wait(1500);
    assert.ok(await admin.isVisible('#rueckfrage'), 'die Rueckfrage des Administrators muss bestehen bleiben');
    assert.ok(!(await admin.isVisible('#hinweis') && /herunter/.test(await admin.textContent('#hinweis'))), 'darf nicht ausgeloest sein');
    await admin.click('#rf-nein');
    ok('Eine fremde Rueckfrage laesst sich weder sehen noch bestaetigen noch wegnehmen');

    // ---- Musik abschalten
    await aktion('musik_aus');
    await gast.click('#wechsel');  // zurueck zur Musik-Ansicht (Extras -> Claude -> Musik)
    await gast.click('#wechsel');
    await gast.waitForFunction(() => document.getElementById('weiter').disabled, null, { timeout: 6000 });
    assert.ok(await gast.isVisible('#ohnemusik'));
    const titelVorher = await gast.textContent('#titel');
    await gast.evaluate(() => ws.send('weiter'));
    await gast.waitForFunction(() => /Musiksteuerung ist für dein Konto abgeschaltet/.test(document.getElementById('hinweis').textContent));
    await wait(500);
    assert.strictEqual(await gast.textContent('#titel'), titelVorher, 'der Titel darf sich nicht geaendert haben');
    await aktion('musik_an');
    await gast.waitForFunction(() => !document.getElementById('weiter').disabled, null, { timeout: 6000 });
    ok('Musik laesst sich pro Benutzer abschalten und wieder einschalten (wirkt sofort)');

    // ---- Kachel nur fuer Administratoren
    const liste = (await (await adminCtx.request.get(URL + '/api/shortcuts')).json()).shortcuts;
    liste.find((e) => e.name === 'Rechner').nur_admin = true;
    const gespeichert = await adminCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: liste, passwort: PW } });
    assert.ok(gespeichert.ok(), await gespeichert.text());
    await gast.click('#wechsel');
    await gast.waitForFunction(() => { const k = Array.from(document.querySelectorAll('.kachel')).find((x) => x.textContent.includes('Rechner') || x.textContent.includes('🔒')); return document.querySelectorAll('.kachel.gesperrt').length >= 3; }, null, { timeout: 6000 });
    await gast.evaluate(() => ws.send('shortcut:0'));
    await gast.waitForFunction(() => /keine Berechtigung/.test(document.getElementById('hinweis').textContent));
    ok('Einzelne Kacheln lassen sich nur fuer Administratoren freigeben ("Nur fuer Administratoren")');

    // ---- Rechte in der Verwaltung sichtbar und per Oberflaeche aenderbar
    const k = await adminCtx.newPage();
    await k.goto(URL + '/konto');
    await k.waitForFunction(() => document.getElementById('liste').textContent.includes('Gast'));
    const zeile = k.locator('.benutzer', { hasText: 'Gast' });
    assert.ok(await zeile.locator('button:has-text("Shortcuts: an")').isVisible());
    await zeile.locator('button:has-text("Shortcuts: an")').click();
    await k.waitForFunction(() => document.getElementById('liste').textContent.includes('Shortcuts: aus'));
    assert.strictEqual((await (await gastCtx.request.get(URL + '/api/ich')).json()).rechte.shortcuts, false);
    ok('Rechte stehen in der Benutzerverwaltung und lassen sich dort umschalten');
    await aktion('shortcuts_an');

    // ---- Aktivitaetsprotokoll
    for (let i = 0; i < 3; i++) await request.newContext().then((c) => c.post(URL + '/api/anmelden', { headers: H, data: { name: 'Gast', passwort: 'falsch-falsch-' + i } }));
    const a = await (await adminCtx.request.get(URL + '/api/aktivitaet?limit=500')).json();
    const arten = new Set(a.eintraege.map((e) => e.art));
    for (const art of ['konto', 'shortcut', 'verweigert', 'admin', 'musik', 'anmeldung-fehler']) assert.ok(arten.has(art), 'Art fehlt im Protokoll: ' + art);
    const verweigert = a.eintraege.filter((e) => e.art === 'verweigert' && e.benutzer === 'Gast');
    assert.ok(verweigert.length >= 4 && verweigert.every((e) => e.ip), 'verweigerte Versuche mit Name und Adresse');
    assert.ok(a.eintraege.some((e) => e.art === 'shortcut' && e.benutzer === 'Gast' && e.text.startsWith('Rechner')));
    assert.ok(a.eintraege.some((e) => e.art === 'admin' && /shortcuts_an: Gast/.test(e.text) && e.benutzer === 'Timo'));
    assert.ok(a.eintraege.some((e) => e.art === 'musik' && e.benutzer === 'Gast'));
    const fehl = a.eintraege.filter((e) => e.art === 'anmeldung-fehler');
    assert.strictEqual(fehl.length, 3);
    assert.ok(!JSON.stringify(a).includes('falsch-falsch'), 'falsche Passwoerter duerfen nie im Protokoll stehen');
    assert.ok(!JSON.stringify(a).includes(PW), 'Passwoerter duerfen nie im Protokoll stehen');
    const gefiltert = await (await adminCtx.request.get(URL + '/api/aktivitaet?art=verweigert&benutzer=gast')).json();
    assert.ok(gefiltert.eintraege.length >= 4 && gefiltert.eintraege.every((e) => e.art === 'verweigert' && e.benutzer === 'Gast'));
    ok('Aktivitaetsprotokoll: Anmeldungen, Shortcuts, Musik, Verweigerungen und Verwaltung, ohne Passwoerter');

    // Sperre wegen Fehlversuchen: nur einmal ins Protokoll
    const roh = await request.newContext();
    for (let i = 0; i < 12; i++) await roh.post(URL + '/api/anmelden', { headers: H, data: { name: 'Gast', passwort: 'falsch-' + i + '-xxxxxx' } });
    const s = await (await adminCtx.request.get(URL + '/api/aktivitaet?art=sicherheit')).json();
    assert.strictEqual(s.eintraege.length, 1, 'die Sperre darf das Protokoll nicht fluten: ' + s.eintraege.length);
    ok('Eine Sperre wegen Fehlversuchen erscheint nur einmal im Protokoll (kein Fluten)');

    // Nur Administratoren
    assert.strictEqual((await gastCtx.request.get(URL + '/api/aktivitaet')).status(), 403);
    assert.strictEqual((await gastCtx.request.get(URL + '/aktivitaet')).status(), 403);
    assert.strictEqual((await (await request.newContext()).get(URL + '/api/aktivitaet')).status(), 401);
    ok('Das Aktivitaetsprotokoll sehen nur Administratoren');

    // Seite mit Filtern
    const ap = await adminCtx.newPage();
    const jsFehler = [];
    ap.on('pageerror', (e) => jsFehler.push(e.message));
    await ap.goto(URL + '/aktivitaet');
    await ap.waitForSelector('.eintrag');
    const alle = await ap.locator('.eintrag').count();
    await ap.selectOption('#art', 'verweigert');
    await ap.waitForFunction((n) => document.querySelectorAll('.eintrag').length < n, alle);
    assert.ok((await ap.locator('.eintrag .art').allTextContents()).every((t) => t === 'Verweigert'));
    await ap.selectOption('#art', '');
    await ap.fill('#wer', 'timo');
    await ap.waitForFunction(() => Array.from(document.querySelectorAll('.eintrag .wer')).every((w) => w.textContent.startsWith('Timo')));
    assert.deepStrictEqual(jsFehler, []);
    ok('Die Aktivitaetsseite zeigt die Eintraege und filtert nach Art und Benutzer');

    // ---- Alles bleibt nach einem Neustart erhalten
    server.kill();
    await wait(1000);
    server = starten();
    await wait(2500);
    const nach = await (await adminCtx.request.get(URL + '/api/aktivitaet?limit=2000')).json();
    assert.ok(nach.eintraege.length >= a.eintraege.length, 'Protokoll muss einen Neustart ueberleben');
    assert.strictEqual((await (await gastCtx.request.get(URL + '/api/ich')).json()).rechte.shortcuts, true);
    ok('Rechte und Protokoll bleiben nach einem Neustart erhalten');

    console.log('Alle Rechte-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
