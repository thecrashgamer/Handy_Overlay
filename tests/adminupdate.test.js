// Update per Knopf im Admin-Bereich, mit echtem Neustart: node tests/adminupdate.test.js
const { chromium, request } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const REPO = path.join(__dirname, '..');
const PORT = 8132;
const URL = `http://localhost:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-adminupdate-'));
const PB = path.join(TMP, 'pb');
const ZIP = path.join(TMP, 'neu.zip');
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);
const py = (code) => spawnSync('python3', ['-c', code], { encoding: 'utf-8' });

// Kopie der Phonebox, damit das Update nicht an den echten Dateien arbeitet
fs.mkdirSync(path.join(PB, 'daten'), { recursive: true });
for (const f of fs.readdirSync(REPO)) if (/\.(py|html|json)$|^requirements\.txt$/.test(f)) fs.copyFileSync(path.join(REPO, f), path.join(PB, f));
fs.writeFileSync(path.join(PB, 'daten', 'marker.txt'), 'bleibt');
const versionIn = (ordner) => /^VERSION = "([^"]+)"/m.exec(fs.readFileSync(path.join(ordner, 'server.py'), 'utf-8'))[1];
const ALT = versionIn(PB);

// Das "neue" Archiv: gleiche Dateien, aber Version v99 und eine zusaetzliche Datei
function zipBauen(zielZip, version) {
  const r = py(`
import zipfile, os, re
src, ziel, version = ${JSON.stringify(PB)}, ${JSON.stringify(zielZip)}, ${JSON.stringify(version)}
with zipfile.ZipFile(ziel, "w") as z:
    for f in sorted(os.listdir(src)):
        p = os.path.join(src, f)
        if not os.path.isfile(p): continue
        inhalt = open(p, encoding="utf-8").read()
        if f == "server.py" and version: inhalt = re.sub(r'^VERSION = ".*"$', 'VERSION = "%s"' % version, inhalt, count=1, flags=re.M)
        if f == "index.html" and version: inhalt = re.sub(r'SEITE = "v\\d+"', 'SEITE = "%s"' % version.split(" ")[0], inhalt, count=1)
        z.writestr("Handy_Overlay-main/" + f, inhalt)
    if version: z.writestr("Handy_Overlay-main/neu.txt", "neu")
`);
  assert.strictEqual(r.status, 0, r.stderr);
}

function pidAmPort(port) {
  const r = py(`
import psutil
print(next((c.pid for c in psutil.net_connections(kind="inet") if c.status == "LISTEN" and c.laddr.port == ${port}), 0))`);
  return Number(r.stdout.trim()) || 0;
}
function alleBeenden() {
  py(`
import psutil
for c in psutil.net_connections(kind="inet"):
    if c.status == "LISTEN" and c.laddr.port == ${PORT}:
        try: psutil.Process(c.pid).kill()
        except Exception: pass`);
}

function serverStarten(quelle) {
  return spawn('python3', ['server.py'], {
    cwd: PB,
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_HTTPS: '0', PHONEBOX_PORT: String(PORT), PHONEBOX_HTTPS_PORT: String(PORT + 1),
           PHONEBOX_DATEN: path.join(PB, 'daten'), PHONEBOX_UPDATE_QUELLE: quelle, PHONEBOX_UPDATE_OHNE_PIP: '1' },
    stdio: 'ignore',
  });
}
async function bereit(timeout = 30000) {
  const ende = Date.now() + timeout;
  while (Date.now() < ende) {
    try { const r = await fetch(URL + '/anmelden'); if (r.ok) return true; } catch (e) {}
    await wait(300);
  }
  return false;
}

(async () => {
  zipBauen(ZIP, 'v99 (Testupdate)');
  let server = serverStarten(ZIP);
  assert.ok(await bereit(), 'Server startet nicht');
  const browser = await chromium.launch();
  try {
    const adminCtx = await browser.newContext({ viewport: { width: 900, height: 900 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    const anonym = await request.newContext();

    // ---- Wer darf das?
    for (const r of [['GET', '/api/update/pruefen'], ['GET', '/api/update/status'], ['POST', '/api/update/starten']]) {
      const opt = { headers: H, data: { passwort: PW } };
      const a = r[0] === 'GET' ? await anonym.get(URL + r[1]) : await anonym.post(URL + r[1], opt);
      const g = r[0] === 'GET' ? await gastCtx.request.get(URL + r[1]) : await gastCtx.request.post(URL + r[1], opt);
      assert.strictEqual(a.status(), 401, r[1] + ' ohne Anmeldung');
      assert.strictEqual(g.status(), 403, r[1] + ' als Gast');
    }
    assert.strictEqual((await adminCtx.request.post(URL + '/api/update/starten', { data: { passwort: PW } })).status(), 403, 'ohne X-Phonebox-Kopfzeile');
    assert.strictEqual(versionIn(PB), ALT);
    ok('Das Update darf nur ein angemeldeter Administrator starten (und nur mit der eigenen Kopfzeile)');

    // ---- Suchen
    const p = await adminCtx.newPage();
    const jsFehler = [];
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.goto(URL + '/admin');
    await p.waitForFunction((v) => document.getElementById('upd-installiert').textContent === v, ALT);
    // Grüner Balken ganz oben, ohne dass man etwas anklickt
    await p.waitForFunction(() => { const b = document.getElementById('upd-banner'); return !b.hidden && /Neue Version verfügbar: v99/.test(b.textContent); });
    assert.ok((await p.$eval('#upd-banner', (b) => getComputedStyle(b).backgroundColor)).includes('29, 185, 84'), 'der Balken muss gruen sein');
    assert.ok((await p.$eval('#upd-banner', (b) => b.getBoundingClientRect().top)) < 20, 'der Balken muss ganz oben stehen');
    await p.click('#upd-pruefen');
    await p.waitForFunction(() => document.getElementById('upd-ergebnis').textContent.includes('Neue Version verfügbar: v99 (Testupdate)'));
    assert.ok(await p.isVisible('#upd-aktion'));
    ok('Der gruene Balken oben zeigt die neue Version von selbst; "Nach Updates suchen" findet sie ebenfalls');

    // ---- Falsches Passwort aendert nichts
    p.once('dialog', (d) => d.accept());
    await p.fill('#upd-pw', 'falsch-falsch-1');
    await p.click('#upd-start');
    await p.waitForFunction(() => /Passwort stimmt nicht/.test(document.getElementById('upd-meldung').textContent));
    assert.strictEqual(versionIn(PB), ALT);
    ok('Mit falschem Passwort passiert nichts');

    // ---- Das echte Update
    const pidVorher = pidAmPort(PORT);
    assert.ok(pidVorher > 0);
    p.once('dialog', (d) => d.accept());
    await p.fill('#upd-pw', PW);
    await p.click('#upd-start');
    await p.waitForFunction(() => !document.getElementById('upd-fortschritt').hidden);
    await p.waitForFunction(() => /Fertig: .* → v99/.test(document.getElementById('upd-meldung').textContent), null, { timeout: 90000 });
    await p.waitForFunction(() => document.getElementById('upd-installiert').textContent === 'v99 (Testupdate)', null, { timeout: 15000 });
    assert.strictEqual(versionIn(PB), 'v99 (Testupdate)');
    assert.strictEqual(fs.readFileSync(path.join(PB, 'neu.txt'), 'utf-8'), 'neu');
    assert.strictEqual(fs.readFileSync(path.join(PB, 'daten', 'marker.txt'), 'utf-8'), 'bleibt');
    assert.ok(fs.readdirSync(path.join(PB, 'daten', 'update-sicherung')).length >= 1, 'Sicherung fehlt');
    const pidNachher = pidAmPort(PORT);
    assert.ok(pidNachher > 0 && pidNachher !== pidVorher, 'der Server muss neu gestartet sein');
    assert.strictEqual((await adminCtx.request.get(URL + '/api/ich')).status(), 200, 'die Anmeldung muss das Update ueberleben');
    ok('Update per Knopf: alter Server beendet, Dateien getauscht, neuer Server laeuft, Anmeldung und Daten bleiben');

    // ---- Protokoll
    const akt = await (await adminCtx.request.get(URL + '/api/aktivitaet?limit=100')).json();
    assert.ok(akt.eintraege.some((e) => e.art === 'admin' && /Update gestartet/.test(e.text) && e.benutzer === 'Timo'));
    assert.ok(akt.eintraege.some((e) => e.art === 'system' && new RegExp(`Update: .* -> v99`).test(e.text)), 'Ergebnis nach dem Neustart fehlt im Protokoll');
    assert.ok(!JSON.stringify(akt).includes(PW));
    ok('Start und Ergebnis stehen im Aktivitaetsprotokoll (auch nach dem Neustart), ohne Passwort');

    // ---- Schon aktuell: kein Neustart
    await p.waitForFunction(() => document.getElementById('upd-installiert').textContent === 'v99 (Testupdate)');
    await p.click('#upd-pruefen');
    await p.waitForFunction(() => /neueste Version \(v99/.test(document.getElementById('upd-ergebnis').textContent));
    assert.ok(await p.$eval('#upd-banner', (b) => b.hidden), 'ohne neue Version darf kein Balken stehen');
    const pidA = pidAmPort(PORT);
    p.once('dialog', (d) => d.accept());
    await p.fill('#upd-pw', PW);
    await p.click('#upd-start');
    await p.waitForFunction(() => /Schon auf dem neuesten Stand/.test(document.getElementById('upd-meldung').textContent), null, { timeout: 30000 });
    assert.strictEqual(pidAmPort(PORT), pidA, 'ohne Aenderung darf nicht neu gestartet werden');
    ok('Ist schon alles aktuell, meldet das Update das und startet nichts neu');

    // ---- Zwei Updates gleichzeitig: nur eines laeuft; danach zurueck zur Sicherung
    const [a, b] = await Promise.all([
      adminCtx.request.post(URL + '/api/update/starten', { headers: H, data: { passwort: PW, zurueck: true } }),
      adminCtx.request.post(URL + '/api/update/starten', { headers: H, data: { passwort: PW, zurueck: true } }),
    ]);
    assert.deepStrictEqual([a.status(), b.status()].sort(), [200, 409], 'ein zweites gleichzeitiges Update muss abgelehnt werden');
    const ende = Date.now() + 90000;
    let st;
    do { await wait(1000); try { st = await (await adminCtx.request.get(URL + '/api/update/status')).json(); } catch (e) { st = null; } } while ((!st || st.zustand === 'laeuft') && Date.now() < ende);
    assert.strictEqual(st.zustand, 'fertig', JSON.stringify(st));
    assert.strictEqual(versionIn(PB), ALT, 'die Wiederherstellung muss die alte Version zurueckbringen');
    assert.strictEqual(fs.readFileSync(path.join(PB, 'daten', 'marker.txt'), 'utf-8'), 'bleibt');
    assert.ok(await bereit(), 'der Server muss nach der Wiederherstellung laufen');
    ok('Ein zweites gleichzeitiges Update wird abgelehnt, die Wiederherstellung bringt die alte Version zurueck');

    // ---- Fehlerfall: die Quelle gibt es nicht. Der Server muss weiterlaufen.
    alleBeenden();
    await wait(1500);
    server = serverStarten(path.join(TMP, 'gibtsnicht.zip'));
    assert.ok(await bereit());
    const p2 = await adminCtx.newPage();
    await p2.goto(URL + '/admin');
    await p2.waitForFunction((v) => document.getElementById('upd-installiert').textContent === v, ALT);
    const pidB = pidAmPort(PORT);
    p2.once('dialog', (d) => d.accept());
    await p2.click('summary:has-text("letzten Sicherung")', { trial: true }).catch(() => {});
    await p2.evaluate(() => { document.getElementById('upd-aktion').hidden = false; });
    await p2.fill('#upd-pw', PW);
    await p2.click('#upd-start');
    await p2.waitForFunction(() => /Fehlgeschlagen/.test(document.getElementById('upd-meldung').textContent), null, { timeout: 30000 });
    assert.strictEqual(pidAmPort(PORT), pidB, 'bei einem Fehler darf der Server nicht beendet werden');
    assert.strictEqual(versionIn(PB), ALT);
    assert.ok(await bereit());
    ok('Schlaegt das Update fehl (Quelle fehlt), laeuft der Server unveraendert weiter und der Fehler wird angezeigt');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));
    console.log('Alle Admin-Update-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    alleBeenden();
    await browser.close();
  }
})();
