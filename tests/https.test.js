// HTTPS-Test: node tests/https.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const https = require('https');
const crypto = require('crypto');
const net = require('net');
const path = require('path');
const fs = require('fs');
const os = require('os');

const HTTP = 8126, HTTPS = 8446;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-https-'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);
const lanIp = Object.values(os.networkInterfaces()).flat().find((i) => i.family === 'IPv4' && !i.internal)?.address;

function starten(daten, http, https, extra = {}) {
  return spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_HTTPS: '1', PHONEBOX_PORT: String(http), PHONEBOX_HTTPS_PORT: String(https),
           PHONEBOX_DATEN: daten, ...extra },
    stdio: 'ignore',
  });
}
function offen(host, port) {
  return new Promise((res) => {
    const s = net.connect({ host, port, timeout: 1500 });
    s.on('connect', () => { s.destroy(); res(true); });
    s.on('error', () => res(false));
    s.on('timeout', () => { s.destroy(); res(false); });
  });
}
function holen(url, ca) {
  return new Promise((res, rej) => https.get(url, { ca }, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res({ status: r.statusCode, body: d, headers: r.headers })); }).on('error', rej));
}

(async () => {
  let server = starten(DATEN, HTTP, HTTPS, { PHONEBOX_ZUSATZ_NAMEN: 'pc.beispiel.ts.net' });
  let zweit;
  await wait(3500);
  const browser = await chromium.launch();
  try {
    const caPfad = path.join(DATEN, 'https', 'ca.pem');
    const ca = fs.readFileSync(caPfad);

    // ---- Wer erreicht was?
    assert.ok(await offen('127.0.0.1', HTTP), 'am PC muss http gehen');
    assert.ok(await offen('127.0.0.1', HTTPS));
    if (lanIp) {
      assert.ok(await offen(lanIp, HTTPS), 'im Netz muss https gehen');
      assert.ok(!(await offen(lanIp, HTTP)), 'im Netz darf es KEIN unverschluesseltes http mehr geben');
      ok(`WLAN-Adresse ${lanIp}: nur https offen, http nur am PC`);
    } else console.log('(keine Netzwerkadresse gefunden, WLAN-Pruefung uebersprungen)');

    // ---- Das Zertifikat ist fuer Namen und Adressen gueltig, wenn man der CA vertraut
    for (const host of ['localhost', '127.0.0.1', ...(lanIp ? [lanIp] : [])]) {
      const r = await holen(`https://${host}:${HTTPS}/anmelden`, ca);
      assert.strictEqual(r.status, 200, host);
    }
    await assert.rejects(holen(`https://localhost:${HTTPS}/anmelden`, undefined), /self-signed|unable to verify|certificate/i);
    ok('Mit der Phonebox-CA ist die Verbindung gueltig (localhost, 127.0.0.1, WLAN-IP), ohne sie nicht');

    // ---- Zertifikatsseite: oeffentlich, richtiger Fingerabdruck, kein privater Schluessel
    const seite = await holen(`https://localhost:${HTTPS}/zertifikat`, ca);
    const f = new crypto.X509Certificate(ca).fingerprint256;
    assert.strictEqual(seite.status, 200);
    assert.ok(seite.body.includes(f), 'Fingerabdruck auf der Seite muss zur CA passen');
    const crt = await holen(`https://localhost:${HTTPS}/ca.crt`, ca);
    assert.strictEqual(crt.headers['content-type'], 'application/x-x509-ca-cert');
    assert.ok(crt.body.startsWith('-----BEGIN CERTIFICATE-----') && !/PRIVATE/.test(crt.body));
    for (const pfad of ['/ca-key.pem', '/daten/https/ca-key.pem', '/https/server-key.pem', '/../daten/https/ca-key.pem']) {
      const r = await holen(`https://localhost:${HTTPS}${pfad}`, ca);
      assert.ok(![200].includes(r.status) && !/PRIVATE/.test(r.body), pfad + ' darf nie ausgeliefert werden');
    }
    ok('Zertifikatsseite zeigt den richtigen Fingerabdruck, geheime Schluessel werden nie ausgeliefert');

    // ---- Browser: ohne Vertrauen Warnung, mit https funktioniert alles inkl. wss
    const strikt = await browser.newPage();
    await assert.rejects(strikt.goto(`https://localhost:${HTTPS}/`), /ERR_CERT/);
    await strikt.close();
    ok('Ein Browser ohne installiertes Zertifikat verweigert die Verbindung (kein stilles Vertrauen)');

    const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 667, height: 375 } });
    const reg = await ctx.request.post(`https://localhost:${HTTPS}/api/registrieren`, { headers: { 'X-Phonebox': '1' }, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
    assert.ok(reg.ok(), await reg.text());
    const p = await ctx.newPage();
    await p.goto(`https://localhost:${HTTPS}/`);
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    assert.ok(await p.evaluate(() => ws.url.startsWith('wss://')), 'die Seite muss wss benutzen');
    const cookie = (await ctx.cookies()).find((c) => c.name === 'phonebox_session');
    assert.ok(cookie.secure && cookie.httpOnly, 'Cookie muss Secure und HttpOnly sein');
    await p.click('#weiter');
    await p.waitForFunction(() => document.getElementById('titel').textContent === 'Zweites Lied');
    ok('Anmelden und Steuern ueber https/wss, Cookie ist Secure und HttpOnly');

    // ---- Am PC ueber http bleibt es ohne Secure-Cookie nutzbar
    const pcCtx = await browser.newContext();
    const pcLogin = await pcCtx.request.post(`http://localhost:${HTTP}/api/anmelden`, { headers: { 'X-Phonebox': '1' }, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
    assert.ok(pcLogin.ok());
    const pcCookie = (await pcCtx.cookies()).find((c) => c.name === 'phonebox_session');
    assert.ok(pcCookie && !pcCookie.secure, 'bei http am PC darf das Cookie nicht Secure sein, sonst ginge es nie');
    ok('Am PC (http://localhost) funktioniert die Anmeldung weiter');

    // ---- Neustart: dieselbe CA, das Handy muss nichts neu installieren
    server.kill();
    await wait(1000);
    server = starten(DATEN, HTTP, HTTPS, { PHONEBOX_ZUSATZ_NAMEN: 'pc.beispiel.ts.net' });
    await wait(3000);
    const seite2 = await holen(`https://localhost:${HTTPS}/zertifikat`, ca);
    assert.ok(seite2.body.includes(f), 'die CA darf sich bei einem Neustart nicht aendern');
    ok('Nach einem Neustart bleibt dieselbe CA (nichts neu zu installieren)');

    // ---- Fail-closed: geht HTTPS nicht, bleibt der Server auf den PC beschraenkt
    server.kill();
    const kaputt = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-kaputt-'));
    fs.writeFileSync(path.join(kaputt, 'https'), 'ich bin eine Datei, kein Ordner');  // Zertifikate lassen sich nicht anlegen
    zweit = starten(kaputt, HTTP + 10, HTTPS + 10);
    await wait(3000);
    assert.ok(await offen('127.0.0.1', HTTP + 10), 'am PC muss es trotzdem gehen');
    assert.ok(!(await offen('127.0.0.1', HTTPS + 10)));
    if (lanIp) assert.ok(!(await offen(lanIp, HTTP + 10)), 'ohne HTTPS darf nichts im WLAN offen sein');
    const log = await (await request.newContext()).get(`http://localhost:${HTTP + 10}/anmelden`);
    assert.strictEqual(log.status(), 200);
    ok('Klappt HTTPS nicht, laeuft die Phonebox nur am PC und nie unverschluesselt im WLAN');

    console.log('Alle HTTPS-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    if (zweit) zweit.kill();
    await browser.close();
  }
})();
