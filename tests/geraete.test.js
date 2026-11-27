// GPU und Geraete-Akkus in der Extras-Ansicht: node tests/geraete.test.js
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);
const starten = (port, extra = {}) => {
  const daten = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-geraete-'));
  return spawn('python3', ['server.py'], { cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(port), PHONEBOX_DATEN: daten, ...extra }, stdio: 'ignore' });
};

async function seite(browser, port, viewport, vorher) {
  const ctx = await browser.newContext({ viewport });
  await ctx.request.post(`http://localhost:${port}/api/registrieren`, { headers: { 'X-Phonebox': '1' }, data: { name: 'Timo', passwort: 'Sommer-Regen-42' } });
  const p = await ctx.newPage();
  const fehler = [];
  p.on('pageerror', (e) => fehler.push(e.message));
  if (vorher) await p.addInitScript(vorher);
  await p.goto(`http://localhost:${port}/`);
  await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
  await p.click('#wechsel');
  return { p, fehler };
}

(async () => {
  const mit = starten(8134);
  const ohne = starten(8135, { PHONEBOX_TEST_OHNE_GERAETE: '1' });
  await wait(2500);
  const browser = await chromium.launch();
  try {
    const { p, fehler } = await seite(browser, 8134, { width: 667, height: 375 });

    // ---- GPU
    await p.waitForFunction(() => document.querySelectorAll('#gpus .messung').length === 1);
    assert.strictEqual(await p.textContent('#gpus .messung span'), 'GPU 37 %');
    assert.strictEqual(await p.textContent('#gpus .unter'), 'Test-GPU · 2,0 von 8,0 GB · 54 °C');
    assert.strictEqual(await p.evaluate(() => document.querySelector('#gpus .fuell').style.width), '37%');
    ok('GPU: Auslastung, Name, Grafikspeicher und Temperatur stehen unter CPU und RAM');

    // ---- Akkus
    await p.waitForFunction(() => document.querySelectorAll('#akkuliste .akku').length === 4);
    const zeilen = await p.$$eval('#akkuliste .akku', (els) => els.map((e) => ({
      name: e.querySelector('.name').textContent, wert: e.querySelector('.wert').textContent,
      schwach: e.classList.contains('schwach'), farbe: (e.querySelector('.fuell') || {}).className || '' })));
    const byName = Object.fromEntries(zeilen.map((z) => [z.name.replace(/^\S+\s/, ''), z]));
    assert.strictEqual(byName['Test-Headset'].wert, '82 %');
    assert.strictEqual(byName['Test-Maus'].wert, '12 %');
    assert.ok(byName['Test-Maus'].schwach && /schwach/.test(byName['Test-Maus'].farbe), 'schwacher Akku muss rot markiert sein');
    assert.ok(!byName['Test-Headset'].schwach);
    assert.strictEqual(byName['Xbox-Controller 1'].wert, '60 %');
    assert.strictEqual(byName['PC (Akku)'].wert, '55 % ⚡');
    assert.ok(!byName['PC (Akku)'].schwach);
    assert.ok(zeilen[0].name.startsWith('🎧') && zeilen[1].name.startsWith('🖱') && zeilen[2].name.startsWith('🎮') && zeilen[3].name.startsWith('💻'), 'Symbole je Geraeteart');
    assert.strictEqual(await p.isVisible('#akkus'), true);
    ok('Akkus: Headset, Maus, Controller und PC mit Prozent, Symbol, Laden-Zeichen und roter Warnung ab 20 %');

    // ---- Passt auf den Bildschirm
    for (const vp of [{ width: 667, height: 375 }, { width: 375, height: 667 }]) {
      await p.setViewportSize(vp);
      await wait(300);
      const mass = await p.evaluate(() => ({ seite: document.documentElement.scrollHeight, fenster: innerHeight,
        system: (() => { const s = document.getElementById('system').getBoundingClientRect(); return { oben: s.top, unten: s.bottom }; })() }));
      assert.ok(mass.seite <= mass.fenster, `die Seite darf nicht scrollen (${vp.width}x${vp.height}): ${JSON.stringify(mass)}`);
      assert.ok(mass.system.oben >= 0 && mass.system.unten <= mass.fenster, 'die Anzeige muss im Fenster liegen: ' + JSON.stringify(mass));
    }
    // Im Querformat darf nichts unter den Knoepfen (Konto, Standby) verschwinden und nichts Scrollen noetig sein
    await p.setViewportSize({ width: 667, height: 375 });
    await wait(300);
    const quer = await p.evaluate(() => {
      const s = document.getElementById('system');
      const letzte = Array.from(document.querySelectorAll('#akkuliste .akku')).pop().getBoundingClientRect();
      return { scrollt: s.scrollHeight > s.clientHeight + 1, letzteUnten: letzte.bottom, knopfOben: document.getElementById('konto').getBoundingClientRect().top,
               uhrOben: document.getElementById('uhr').getBoundingClientRect().top };
    });
    assert.ok(!quer.scrollt, 'vier Geraete muessen im Querformat ohne Scrollen passen: ' + JSON.stringify(quer));
    assert.ok(quer.letzteUnten <= quer.knopfOben, 'das letzte Geraet darf nicht unter den Knoepfen liegen: ' + JSON.stringify(quer));
    assert.ok(quer.uhrOben >= 0, 'die Uhr darf nicht abgeschnitten sein');
    await p.screenshot({ path: (process.env.SHOT || 'phonebox.png').replace('.png', '-geraete.png') });
    ok('Die Anzeige passt in Quer- und Hochformat auf den Bildschirm (bei Bedarf scrollt nur die Spalte)');

    // ---- Standby zeigt nur schwache Akkus
    await p.evaluate(() => { try { localStorage.setItem('phonebox-standby-sek', '2'); } catch (e) {} });
    await p.click('#schlaf');
    await p.waitForSelector('#standby', { state: 'visible' });
    await p.waitForFunction(() => document.getElementById('sb-akku').style.display === 'block');
    const warn = await p.textContent('#sb-akku');
    assert.ok(warn.includes('Test-Maus 12 %') && !warn.includes('Headset') && !warn.includes('Controller') && !warn.includes('PC (Akku)'), 'nur schwache Akkus: ' + warn);
    ok('Im Standby erscheint nur der schwache Akku (Maus 12 %), geladene Geraete nicht');
    assert.deepStrictEqual(fehler, [], 'JavaScript-Fehler: ' + fehler.join(' | '));

    // ---- Ohne Geraete: nichts Leeres anzeigen
    const leer = await seite(browser, 8135, { width: 667, height: 375 });
    await wait(2500);
    assert.strictEqual(await leer.p.locator('#gpus .messung').count(), 0);
    assert.strictEqual(await leer.p.isVisible('#akkus'), false);
    assert.match(await leer.p.textContent('#cputext'), /^CPU \d+ %$/);
    assert.deepStrictEqual(leer.fehler, []);
    ok('Ohne GPU-Daten und ohne Geraete bleibt die Anzeige sauber: keine leeren Kaesten');

    console.log('Alle Geraete-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    mit.kill(); ohne.kill();
    await browser.close();
  }
})();
