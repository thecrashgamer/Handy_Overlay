// Bilder als Shortcut-Symbole (Ziehen und Ablegen): node tests/icons.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const zlib = require('zlib');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8129;
const URL = `http://localhost:${PORT}`;
const DATEN = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-icons-'));
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);

function chunk(typ, inhalt) {
  const l = Buffer.alloc(4); l.writeUInt32BE(inhalt.length);
  const c = Buffer.alloc(4); c.writeUInt32BE(zlib.crc32(Buffer.concat([Buffer.from(typ), inhalt])));
  return Buffer.concat([l, Buffer.from(typ), inhalt, c]);
}
function png(w = 16, h = 16) {
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  const zeile = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 4, 200)]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(Array(h).fill(zeile)))), chunk('IEND', Buffer.alloc(0))]);
}

// Legt in der Seite eine Datei an und laesst sie auf ein Element fallen
async function ablegen(page, selektor, art, dateiname, typ) {
  return page.evaluate(async ({ selektor, art, dateiname, typ }) => {
    let blob;
    if (art === 'svg') {
      blob = new Blob(['<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><script>alert(1)</script><rect width="64" height="64" fill="#2a6"/></svg>'], { type: 'image/svg+xml' });
    } else if (art === 'text') {
      blob = new Blob(['das ist kein Bild'], { type: 'text/plain' });
    } else {
      const c = document.createElement('canvas'); c.width = 80; c.height = 40;
      const x = c.getContext('2d'); x.fillStyle = '#c33'; x.fillRect(0, 0, 80, 40);
      blob = await new Promise((r) => c.toBlob(r, typ));
    }
    const dt = new DataTransfer();
    dt.items.add(new File([blob], dateiname, { type: art === 'svg' ? 'image/svg+xml' : art === 'text' ? 'text/plain' : typ }));
    const ziel = document.querySelector(selektor);
    ziel.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
    const drop = new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true });
    ziel.dispatchEvent(drop);
    return drop.defaultPrevented;
  }, { selektor, art, dateiname, typ });
}

(async () => {
  const server = spawn('python3', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: DATEN }, stdio: 'ignore',
  });
  await wait(2000);
  const browser = await chromium.launch();
  try {
    const adminCtx = await browser.newContext({ viewport: { width: 1000, height: 900 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    const anonym = await request.newContext();
    const b64 = (buf) => buf.toString('base64');

    // ---- Schnittstelle: wer darf hochladen, was wird akzeptiert
    assert.strictEqual((await anonym.post(URL + '/api/icons', { headers: H, data: { daten: b64(png()) } })).status(), 401);
    assert.strictEqual((await gastCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: b64(png()) } })).status(), 403);
    const gut = await adminCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: b64(png()) } });
    assert.ok(gut.ok(), await gut.text());
    const name = (await gut.json()).name;
    assert.match(name, /^[0-9a-f]{16}\.png$/);
    ok('Nur Administratoren duerfen Bilder hochladen, ein gueltiges PNG wird angenommen');

    const boese = {
      'HTML statt Bild': Buffer.from('<html><script>alert(1)</script></html>' + ' '.repeat(80)),
      'abgeschnittenes PNG': png().subarray(0, 40),
      'zu grosses Bild (600 Pixel)': png(600, 10),
      'PNG mit angehaengtem Skript': Buffer.concat([png(), Buffer.from('<script>alert(1)</script>')]),
      'SVG': Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>' + ' '.repeat(80)),
    };
    for (const [bez, buf] of Object.entries(boese)) {
      const r = await adminCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: b64(buf) } });
      assert.strictEqual(r.status(), 400, bez + ' muss abgelehnt werden');
    }
    assert.strictEqual((await adminCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: 'kein base64 !!!' } })).status(), 400);
    assert.strictEqual((await adminCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: 'A'.repeat(300001) } })).status(), 422);
    assert.deepStrictEqual(fs.readdirSync(path.join(DATEN, 'icons')), [name], 'es darf nur das gueltige Bild gespeichert sein');
    ok('HTML, SVG, abgeschnittene oder zu grosse Dateien und Skripte hinter einem Bild werden abgelehnt');

    // ---- Ausliefern
    const holen = await gastCtx.request.get(`${URL}/icons/${name}`);
    assert.strictEqual(holen.status(), 200);
    const kopf = holen.headers();
    assert.strictEqual(kopf['content-type'], 'image/png');
    assert.strictEqual(kopf['x-content-type-options'], 'nosniff');
    assert.match(kopf['content-security-policy'], /sandbox/);
    assert.ok((await holen.body()).equals(png()));
    assert.strictEqual((await anonym.get(`${URL}/icons/${name}`)).status(), 401);
    for (const pfad of ['/icons/0123456789abcdef.png', '/icons/..%2f..%2fdaten%2fphonebox.db', '/icons/%2e%2e/phonebox.db', '/icons/' + name.toUpperCase(),
                        '/icons/' + name + '%00.html', '/icons/..%5c..%5cphonebox.db', '/icons/phonebox.db']) {
      const r = await adminCtx.request.get(URL + pfad);
      assert.ok([404, 400, 422].includes(r.status()), pfad + ' -> ' + r.status());
      assert.ok(!(await r.body()).includes(Buffer.from('SQLite')), pfad + ' darf keine Datenbank liefern');
    }
    ok('Bilder gibt es nur fuer Angemeldete, mit nosniff und Sandbox, Pfad-Tricks liefern nichts');

    // ---- Speichern prueft, ob das Bild existiert
    const liste = (await (await adminCtx.request.get(URL + '/api/shortcuts')).json()).shortcuts;
    const fehlt = await adminCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: [{ name: 'A', programm: 'a.exe', bild: '0123456789abcdef.png' }], passwort: PW } });
    assert.strictEqual(fehlt.status(), 400);
    assert.match((await fehlt.json()).fehler, /Bild fehlt/);
    const unsinn = await adminCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: [{ name: 'A', programm: 'a.exe', bild: '../../x.png' }], passwort: PW } });
    assert.strictEqual(unsinn.status(), 400);
    assert.ok(liste.length >= 6);
    ok('Ein Shortcut kann nur auf vorhandene, gueltig benannte Bilder zeigen');

    // ---- Oberflaeche: Ziehen und Ablegen
    const p = await adminCtx.newPage();
    const jsFehler = [];
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.goto(URL + '/admin');
    await p.waitForSelector('#liste .karte');
    let defaultVerhindert = await ablegen(p, '#liste .karte:nth-child(1)', 'bild', 'rot.png', 'image/png');
    assert.ok(defaultVerhindert, 'der Browser darf das Bild nicht selbst oeffnen');
    await p.waitForSelector('#liste .karte:nth-child(1) .iconknopf img');
    assert.ok(await p.evaluate(() => { const i = document.querySelector('#liste .karte:nth-child(1) .iconknopf img'); return i.complete && i.naturalWidth > 0; }));
    assert.ok(await p.isVisible('#vorschau .kachel:nth-child(1) img.bild'));
    assert.ok(await p.isEnabled('#speichern'));
    ok('Ein Bild auf eine Karte ziehen: erscheint im Symbol und in der Vorschau');

    // SVG mit Skript: wird im Browser zu einem harmlosen PNG
    await ablegen(p, '#liste .karte:nth-child(2)', 'svg', 'vektor.svg');
    await p.waitForSelector('#liste .karte:nth-child(2) .iconknopf img');
    // JPEG
    await ablegen(p, '#liste .karte:nth-child(3)', 'bild', 'foto.jpg', 'image/jpeg');
    await p.waitForSelector('#liste .karte:nth-child(3) .iconknopf img');
    for (const datei of fs.readdirSync(path.join(DATEN, 'icons'))) {
      const inhalt = fs.readFileSync(path.join(DATEN, 'icons', datei));
      assert.ok(inhalt.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47])), datei + ' muss ein PNG sein');
      assert.ok(!inhalt.toString('latin1').includes('<script'), datei + ' darf kein Skript enthalten');
    }
    ok('SVG und JPEG werden zu sauberen PNG-Dateien umgewandelt (das Skript im SVG verschwindet)');

    // Kein Bild
    await ablegen(p, '#liste .karte:nth-child(4)', 'text', 'notiz.txt');
    await p.waitForFunction(() => /Bilddatei/.test(document.getElementById('meldung').textContent));
    assert.strictEqual(await p.locator('#liste .karte:nth-child(4) .iconknopf img').count(), 0);
    ok('Eine Textdatei statt eines Bildes wird mit einem Hinweis abgelehnt');

    // Neuer Shortcut aus einem Bild
    const vorher = await p.locator('#liste .karte').count();
    await ablegen(p, '#neuzone', 'bild', 'mein-programm.png', 'image/png');
    await p.waitForFunction((n) => document.querySelectorAll('#liste .karte').length === n + 1, vorher);
    const neuKarte = p.locator('#liste .karte').last();
    assert.strictEqual(await neuKarte.locator('input[placeholder="Name"]').inputValue(), 'mein-programm');
    assert.ok(await neuKarte.locator('.iconknopf img').isVisible());
    await neuKarte.locator('input[placeholder^="z. B. calc"]').fill('notepad.exe');
    ok('Ein Bild in die Ablagefläche ziehen legt einen neuen Shortcut mit dem Dateinamen an');

    // Einfuegen (Strg+V)
    await p.locator('#liste .karte:nth-child(5) input[placeholder="Name"]').focus();
    await p.evaluate(async () => {
      const c = document.createElement('canvas'); c.width = c.height = 50; c.getContext('2d').fillRect(0, 0, 50, 50);
      const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
      const dt = new DataTransfer(); dt.items.add(new File([blob], 'screenshot.png', { type: 'image/png' }));
      document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    });
    await p.waitForSelector('#liste .karte:nth-child(5) .iconknopf img');
    ok('Ein eingefuegtes Bild (Strg+V) landet in der Karte, in der man gerade tippt');

    // Neben die Karten fallen lassen darf die Seite nicht verlassen
    const url0 = p.url();
    const verhindert = await ablegen(p, 'h1', 'bild', 'daneben.png', 'image/png');
    assert.ok(verhindert);
    await wait(300);
    assert.strictEqual(p.url(), url0);
    ok('Ein Bild neben die Karten fallen zu lassen oeffnet nichts und verlaesst die Seite nicht');

    // Bild wieder entfernen
    await p.locator('#liste .karte:nth-child(5)').locator('button:has-text("Bild entfernen")').click();
    assert.strictEqual(await p.locator('#liste .karte:nth-child(5) .iconknopf img').count(), 0);

    // ---- Speichern und am Handy sehen
    await p.fill('#pw', PW);
    await p.click('#speichern');
    await p.waitForFunction(() => /Gespeichert/.test(document.getElementById('meldung').textContent));
    const gespeichert = JSON.parse(fs.readFileSync(path.join(DATEN, 'shortcuts.json'), 'utf-8'));
    const mitBild = gespeichert.filter((e) => e.bild);
    assert.ok(mitBild.length >= 4 && mitBild.every((e) => /^[0-9a-f]{16}\.png$/.test(e.bild)));
    assert.ok(mitBild.every((e) => fs.existsSync(path.join(DATEN, 'icons', e.bild))));
    ok('Speichern legt die Bild-Namen in der Liste ab');

    const handy = await adminCtx.newPage();
    await handy.goto(URL + '/');
    await handy.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await handy.click('#wechsel');
    await handy.waitForFunction(() => document.querySelectorAll('.kachel img.bildsymbol').length >= 4);
    assert.ok(await handy.evaluate(() => Array.from(document.querySelectorAll('.kachel img.bildsymbol')).every((i) => i.complete && i.naturalWidth > 0)));
    ok('Am Handy erscheinen die Bilder als Symbol auf den Kacheln');

    // Gesperrte Kacheln zeigen das Schloss statt des Bildes
    const gast = await gastCtx.newPage();
    await gast.goto(URL + '/');
    await gast.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await gast.click('#wechsel');
    await gast.waitForFunction(() => document.querySelectorAll('.kachel').length >= 4);
    assert.strictEqual(await gast.locator('.kachel img.bildsymbol').count(), 0, 'gesperrte Kacheln zeigen kein Bild');
    assert.ok((await gast.locator('.kachel .symbol').first().textContent()).includes('🔒'));
    ok('Wer eine Kachel nicht benutzen darf, sieht ein Schloss statt des Bildes');

    // Bilder der Liste bleiben, ein ungenutztes frisches Bild wird nicht sofort geloescht
    const frisch = (await (await adminCtx.request.post(URL + '/api/icons', { headers: H, data: { daten: b64(png(20, 20)) } })).json()).name;
    const nurEins = gespeichert.slice(0, 1).map((e) => ({ ...e }));
    const r = await adminCtx.request.post(URL + '/api/shortcuts/speichern', { headers: H, data: { shortcuts: nurEins.map(({ bild, ...rest }) => rest), passwort: PW } });
    assert.ok(r.ok(), await r.text());
    assert.ok(fs.existsSync(path.join(DATEN, 'icons', frisch)), 'ein frisch hochgeladenes Bild darf nicht sofort verschwinden');
    ok('Frisch hochgeladene Bilder bleiben, auch wenn sie gerade noch niemand benutzt');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));
    console.log('Alle Bilder-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
