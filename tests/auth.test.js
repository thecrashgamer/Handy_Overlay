// Test des Konten-Systems mit echtem Server und Browser: node tests/auth.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8124;
const URL = `http://localhost:${PORT}`;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-auth-'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const H = { 'X-Phonebox': '1' };

function starten() {
  return spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: DATEN },
    stdio: 'ignore',
  });
}
const ok = (name) => console.log('ok  -', name);

(async () => {
  let server = starten();
  await wait(2000);
  const browser = await chromium.launch();
  try {
    // ---- Ohne Anmeldung kommt man nirgends hin
    const gast = await request.newContext();
    for (const pfad of ['/', '/konto']) {
      const r = await gast.get(URL + pfad, { maxRedirects: 0 });
      assert.strictEqual(r.status(), 303, pfad + ' sollte zur Anmeldung leiten');
      assert.ok(r.headers().location.endsWith('/anmelden'));
    }
    assert.strictEqual((await gast.get(URL + '/log', { maxRedirects: 0 })).status(), 303);
    assert.strictEqual((await gast.get(URL + '/cover')).status(), 401);
    assert.strictEqual((await gast.get(URL + '/api/ich')).status(), 401);
    assert.strictEqual((await gast.get(URL + '/api/benutzer')).status(), 401);
    assert.strictEqual((await gast.get(URL + '/anmelden')).status(), 200);
    ok('ohne Anmeldung sind Seite, Cover, Protokoll und Verwaltung gesperrt');

    const ohneKopf = await gast.post(URL + '/api/anmelden', { data: { name: 'a', passwort: 'b' } });
    assert.strictEqual(ohneKopf.status(), 403);
    ok('Aenderungen ohne eigenen Kopfzeilen-Eintrag werden abgelehnt (Schutz vor fremden Webseiten)');

    const seite0 = await browser.newPage();
    await seite0.goto(URL + '/anmelden');
    const wsOffen = await seite0.evaluate((p) => new Promise((res) => {
      const w = new WebSocket('ws://localhost:' + p + '/ws');
      w.onopen = () => res('offen');
      w.onclose = () => res('zu');
      setTimeout(() => res('zeit'), 3000);
    }), PORT);
    assert.strictEqual(wsOffen, 'zu', 'WebSocket ohne Anmeldung darf nicht aufgehen');
    ok('WebSocket ohne Anmeldung wird abgelehnt');
    await seite0.close();

    const claude = await gast.post(URL + '/claude', { data: { status: 'arbeitet' } });
    assert.strictEqual(claude.status(), 200, 'Claude-Hooks vom PC selbst muessen ohne Anmeldung gehen');
    ok('Claude-Status vom PC selbst geht ohne Anmeldung');

    // Kommt eine Anfrage ueber einen Tunnel/Proxy (Weiterleitungs-Kopfzeile), gilt sie nicht als "am PC selbst"
    const fremd = { 'X-Forwarded-For': '203.0.113.9' };
    const tunnelClaude = await gast.post(URL + '/claude', { headers: fremd, data: { status: 'arbeitet' } });
    assert.strictEqual(tunnelClaude.status(), 403);
    const tunnelErst = await gast.post(URL + '/api/registrieren', { headers: { ...H, ...fremd }, data: { name: 'Fremder', passwort: 'Sommer-Regen-42' } });
    assert.strictEqual(tunnelErst.status(), 403, 'das erste Konto darf nicht von aussen angelegt werden');
    ok('Anfragen ueber einen Tunnel gelten nicht als lokal (kein Erstkonto, kein Claude-Status von aussen)');

    // ---- Ersteinrichtung ueber die Seite
    const admin = await browser.newContext({ viewport: { width: 400, height: 800 } });
    const p = await admin.newPage();
    await p.goto(URL + '/');
    await p.waitForURL(/\/anmelden$/);
    await p.waitForFunction(() => document.getElementById('unter').textContent === 'Ersteinrichtung');
    assert.ok(await p.isVisible('#f-konto'), 'Konto-Formular sollte offen sein');
    ok('Start leitet zur Anmeldung, Ersteinrichtung wird erkannt');

    await p.fill('#k-name', 'Timo');
    await p.fill('#k-pw', 'Sommer-Regen-42');
    await p.fill('#k-pw2', 'Sommer-Regen-43');
    await p.click('#k-knopf');
    assert.match(await p.textContent('#meldung'), /nicht gleich/);
    await p.fill('#k-pw', '12345678');
    await p.fill('#k-pw2', '12345678');
    await p.click('#k-knopf');
    await p.waitForFunction(() => /zu einfach/.test(document.getElementById('meldung').textContent));
    await p.fill('#k-pw', 'Sommer-Regen-42');
    await p.fill('#k-pw2', 'Sommer-Regen-42');
    await p.click('#k-knopf');
    await p.waitForSelector('#codes-teil', { state: 'visible' });
    const codes = await p.locator('#codes div').allTextContents();
    assert.strictEqual(codes.length, 8);
    assert.ok(codes.every((c) => /^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(c)), 'Codeformat: ' + codes[0]);
    assert.ok(await p.isDisabled('#weiter'), 'Weiter darf erst nach der Bestaetigung gehen');
    await p.check('#gesichert');
    await p.click('#weiter');
    await p.waitForURL(URL + '/');
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    ok('Konto erstellen: Regeln, Wiederherstellungscodes, Bestaetigung, danach angemeldet in der Phonebox');

    // ---- Konto-Seite, Abmelden, Anmelden (mit und ohne "merken")
    await p.goto(URL + '/konto');
    await p.waitForFunction(() => document.getElementById('name').textContent === 'Timo');
    assert.strictEqual(await p.textContent('#rolle'), 'Administrator');
    await p.click('text=Abmelden');
    await p.waitForURL(/\/anmelden$/);
    assert.strictEqual((await p.context().cookies()).filter((c) => c.name === 'phonebox_session').length, 0);
    ok('Abmelden loescht die Sitzung');

    await p.fill('#a-name', 'timo');
    await p.fill('#a-pw', 'falsches-Passwort');
    await p.click('#a-knopf');
    await p.waitForFunction(() => /stimmt nicht/.test(document.getElementById('meldung').textContent));
    await p.fill('#a-pw', 'Sommer-Regen-42');
    await p.uncheck('#a-merken');
    await p.click('#a-knopf');
    await p.waitForURL(URL + '/');
    let cookie = (await p.context().cookies()).find((c) => c.name === 'phonebox_session');
    assert.ok(cookie && cookie.httpOnly && cookie.sameSite === 'Lax', 'Cookie sollte httpOnly und SameSite=Lax sein');
    assert.strictEqual(cookie.expires, -1, 'ohne "merken" ein Sitzungs-Cookie');
    ok('Anmelden (Name egal ob gross/klein), falsches Passwort wird abgelehnt, sicheres Cookie');

    await p.goto(URL + '/konto');
    await p.click('text=Abmelden');
    await p.waitForURL(/\/anmelden$/);
    await p.fill('#a-name', 'Timo');
    await p.fill('#a-pw', 'Sommer-Regen-42');
    await p.check('#a-merken');
    await p.click('#a-knopf');
    await p.waitForURL(URL + '/');
    cookie = (await p.context().cookies()).find((c) => c.name === 'phonebox_session');
    assert.ok(cookie.expires > Date.now() / 1000 + 80 * 86400, 'mit "merken" etwa 90 Tage');
    ok('"Angemeldet bleiben" setzt ein langlebiges Cookie (90 Tage)');

    // Server neu starten: Anmeldung bleibt erhalten
    server.kill();
    await wait(800);
    server = starten();
    await wait(2000);
    await p.goto(URL + '/');
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    ok('Anmeldung ueberlebt einen Neustart des Servers');

    // ---- Zweites Konto: Freigabe durch den Administrator
    const gastKontext = await browser.newContext();
    const g = await gastKontext.newPage();
    await g.goto(URL + '/anmelden');
    await g.waitForFunction(() => document.getElementById('k-info').textContent.includes('freigeben'));
    await g.click('#r-konto');
    await g.fill('#k-name', 'Gast1');
    await g.fill('#k-pw', 'Wolken-Kaffee-19');
    await g.fill('#k-pw2', 'Wolken-Kaffee-19');
    await g.click('#k-knopf');
    await g.waitForSelector('#codes-teil', { state: 'visible' });
    const gastCodes = await g.locator('#codes div').allTextContents();
    await g.check('#gesichert');
    await g.click('#weiter');
    await g.waitForFunction(() => /wartet auf die Freigabe/.test(document.getElementById('meldung').textContent));
    await g.fill('#a-name', 'Gast1');
    await g.fill('#a-pw', 'Wolken-Kaffee-19');
    await g.click('#a-knopf');
    await g.waitForFunction(() => /Freigabe/.test(document.getElementById('meldung').textContent) &&
      document.getElementById('meldung').className.includes('fehler'));
    assert.strictEqual((await g.goto(URL + '/', { waitUntil: 'load' })).url().endsWith('/anmelden'), true);
    ok('Neues Konto wartet auf Freigabe und kommt noch nicht hinein');

    await p.goto(URL + '/konto');
    await p.waitForFunction(() => document.getElementById('liste').textContent.includes('wartet auf Freigabe'));
    await p.click('button:has-text("Freigeben")');
    await p.waitForFunction(() => !document.getElementById('liste').textContent.includes('wartet auf Freigabe'));
    await g.goto(URL + '/anmelden');
    await g.fill('#a-name', 'Gast1');
    await g.fill('#a-pw', 'Wolken-Kaffee-19');
    await g.click('#a-knopf');
    await g.waitForURL(URL + '/');
    await g.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    ok('Administrator gibt frei, danach kann sich das Konto anmelden');

    // Gast darf nicht verwalten und kein Protokoll sehen
    assert.strictEqual((await gastKontext.request.get(URL + '/api/benutzer')).status(), 403);
    assert.strictEqual((await gastKontext.request.get(URL + '/log')).status(), 403);
    assert.strictEqual((await gastKontext.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } })).status(), 403);
    ok('Normale Benutzer duerfen weder verwalten noch das Protokoll lesen');

    // ---- Passwort zuruecksetzen mit Wiederherstellungscode
    const anonym = await browser.newContext();
    const z = await anonym.newPage();
    await z.goto(URL + '/anmelden');
    await z.click('#r-vergessen');
    await z.fill('#v-name', 'gast1');
    await z.fill('#v-code', 'AAAA-BBBB-CCCC');
    await z.fill('#v-pw', 'Neues-Passwort-5');
    await z.fill('#v-pw2', 'Neues-Passwort-5');
    await z.click('#v-knopf');
    await z.waitForFunction(() => /Name oder Code stimmt nicht/.test(document.getElementById('meldung').textContent));
    await z.fill('#v-code', gastCodes[0].toLowerCase());
    await z.click('#v-knopf');
    await z.waitForFunction(() => /neu gesetzt/.test(document.getElementById('meldung').textContent));
    await z.fill('#a-name', 'Gast1');
    await z.fill('#a-pw', 'Wolken-Kaffee-19');
    await z.click('#a-knopf');
    await z.waitForFunction(() => /stimmt nicht/.test(document.getElementById('meldung').textContent));
    await z.fill('#a-pw', 'Neues-Passwort-5');
    await z.click('#a-knopf');
    await z.waitForURL(URL + '/');
    ok('Passwort zuruecksetzen mit Code: falscher Code abgelehnt, richtiger geht, altes Passwort ungueltig');
    // alte Sitzung des Gastes wurde beim Zuruecksetzen beendet
    assert.strictEqual((await gastKontext.request.get(URL + '/api/ich')).status(), 401);
    ok('Beim Zuruecksetzen werden alle anderen Geraete abgemeldet');
    const nochmal = await anonym.request.post(URL + '/api/zuruecksetzen', { headers: H, data: { name: 'Gast1', code: gastCodes[0], neues: 'Noch-Ein-Pass-77' } });
    assert.strictEqual(nochmal.status(), 403, 'ein Code darf nur einmal gelten');
    ok('Ein Wiederherstellungscode gilt nur einmal');

    // ---- Gesperrtes Konto wird sofort rausgeworfen
    await z.goto(URL + '/');
    await z.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await p.goto(URL + '/konto');
    await p.waitForSelector('text=Gast1');
    await p.locator('.benutzer', { hasText: 'Gast1' }).locator('button:has-text("Sperren")').click();
    await z.waitForURL(/\/anmelden$/, { timeout: 25000 });
    ok('Gesperrtes Konto wird innerhalb kurzer Zeit abgemeldet und getrennt');

    // ---- Registrierung schliessen
    await p.selectOption('#registrierung', 'geschlossen');
    await wait(500);
    const zu = await anonym.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Spaeter', passwort: 'Sonne-Mond-Sterne-1' } });
    assert.strictEqual(zu.status(), 403);
    ok('Registrierung laesst sich schliessen');

    // ---- Schutz vor dem Aussperren und Raten
    const eigene = await admin.request.get(URL + '/api/benutzer');
    const timoId = (await eigene.json()).ich;
    const selbst = await admin.request.post(URL + '/api/benutzer/aktion', { headers: H, data: { id: timoId, aktion: 'loeschen' } });
    assert.strictEqual(selbst.status(), 400, 'der letzte Administrator darf sich nicht selbst loeschen');
    ok('Der letzte Administrator kann sich nicht selbst aussperren');

    const rater = await request.newContext();
    let letzter;
    for (let i = 0; i < 6; i++) {
      letzter = await rater.post(URL + '/api/anmelden', { headers: H, data: { name: 'Timo', passwort: 'falsch-' + i + '-xxxx' } });
    }
    assert.strictEqual(letzter.status(), 429);
    const richtigGesperrt = await rater.post(URL + '/api/anmelden', { headers: H, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
    assert.strictEqual(richtigGesperrt.status(), 429, 'auch das richtige Passwort geht waehrend der Sperre nicht');
    ok('Nach 5 Fehlversuchen wird gesperrt, auch fuer das richtige Passwort');

    console.log('Alle Konten-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
