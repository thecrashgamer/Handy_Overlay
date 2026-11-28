// Claude-Status: Einrichtung der Hooks, Ereignisse, Diagnose, Ton: node tests/claude.test.js
const { chromium, request } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const REPO = path.join(__dirname, '..');
const PORT = 8136;
const URL = `http://localhost:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-claude-'));
const KONFIG = path.join(TMP, 'claude-config');  // so wird NIE die echte settings.json beruehrt
const SETTINGS = path.join(KONFIG, 'settings.json');
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);
const json = () => JSON.parse(fs.readFileSync(SETTINGS, 'utf-8'));

fs.mkdirSync(KONFIG, { recursive: true });
fs.writeFileSync(SETTINGS, JSON.stringify({ model: 'opus', hooks: { SessionStart: [{ hooks: [{ type: 'command', command: 'echo hallo' }] }] } }));

(async () => {
  const server = spawn('python3', ['server.py'], { cwd: REPO,
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: path.join(TMP, 'daten'), CLAUDE_CONFIG_DIR: KONFIG }, stdio: 'ignore' });
  await wait(2500);
  const browser = await chromium.launch();
  try {
    const adminCtx = await browser.newContext({ viewport: { width: 900, height: 900 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    const lokal = await request.newContext();  // so meldet sich Claude Code: vom PC selbst, ohne Anmeldung
    const ereignis = (daten, extra = {}) => lokal.post(URL + '/claude-hook', { data: daten, ...extra });

    // ---- Zugriff
    assert.strictEqual((await lokal.get(URL + '/api/claude/diagnose')).status(), 401);
    assert.strictEqual((await gastCtx.request.get(URL + '/api/claude/diagnose')).status(), 403);
    for (const pfad of ['/api/claude/einrichten', '/api/claude/entfernen']) {
      assert.strictEqual((await gastCtx.request.post(URL + pfad, { headers: H, data: { passwort: PW } })).status(), 403, pfad);
      assert.strictEqual((await adminCtx.request.post(URL + pfad, { data: { passwort: PW } })).status(), 403, pfad + ' ohne Kopfzeile');
    }
    assert.strictEqual((await gastCtx.request.post(URL + '/api/claude/test', { headers: H, data: { status: 'fertig' } })).status(), 403);
    const fremd = await lokal.post(URL + '/claude-hook', { headers: { 'X-Forwarded-For': '203.0.113.7' }, data: { hook_event_name: 'Stop' } });
    assert.strictEqual(fremd.status(), 403, 'ueber einen Tunnel darf niemand Claude-Ereignisse einspeisen');
    ok('Einrichtung, Diagnose und Test nur fuer Administratoren; Ereignisse nur vom PC selbst');

    // ---- Admin-Seite: Ausgangslage, Einrichten
    const admin = await adminCtx.newPage();
    const jsFehler = [];
    admin.on('pageerror', (e) => jsFehler.push(e.message));
    await admin.goto(URL + '/admin');
    await admin.waitForFunction(() => /Noch nicht eingerichtet/.test(document.getElementById('cl-lage').textContent));
    assert.match(await admin.textContent('#cl-meldungen'), /noch nichts angekommen/);
    ok('Die Admin-Seite sagt klar: noch nicht eingerichtet, noch nichts angekommen');

    await admin.click('button:has-text("Hooks einrichten")');
    assert.match(await admin.textContent('#cl-fehler'), /Passwort/);
    await admin.fill('#cl-pw', 'falsch-falsch-1');
    await admin.click('button:has-text("Hooks einrichten")');
    await admin.waitForFunction(() => /Passwort stimmt nicht/.test(document.getElementById('cl-fehler').textContent));
    assert.ok(!json().hooks.PreToolUse, 'mit falschem Passwort darf nichts geschrieben werden');
    await admin.fill('#cl-pw', PW);
    await admin.click('button:has-text("Hooks einrichten")');
    await admin.waitForFunction(() => /Eingetragen in/.test(document.getElementById('cl-fehler').textContent));
    await admin.waitForFunction(() => /Hooks sind eingetragen \(http, ohne Python\)/.test(document.getElementById('cl-lage').textContent));
    const d = json();
    assert.strictEqual(d.model, 'opus');
    assert.deepStrictEqual(d.hooks.SessionStart, [{ hooks: [{ type: 'command', command: 'echo hallo' }] }], 'fremde Hooks muessen bleiben');
    for (const e of ['UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'Notification', 'Stop']) {
      assert.deepStrictEqual(d.hooks[e].at(-1).hooks[0], { type: 'http', url: `http://127.0.0.1:${PORT}/claude-hook`, timeout: e === "Stop" ? 600 : 3 }, e);
    }
    assert.match(d.hooks.Notification.at(-1).matcher, /permission_prompt/);
    assert.ok(fs.readdirSync(KONFIG).some((f) => f.includes('phonebox-sicherung')), 'Sicherung der alten Datei fehlt');
    ok('Hooks einrichten: richtiges Passwort noetig, dokumentierte Struktur, fremde Einstellungen und Hooks bleiben, Sicherung liegt da');

    // ---- Claude Code schickt Ereignisse
    const handy = await adminCtx.newPage();
    await handy.goto(URL + '/');
    await handy.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await handy.click('#wechsel'); await handy.click('#wechsel');  // Claude-Ansicht
    const proj = 'C:\\Users\\timo\\Handy_Overlay';
    const antwort = await ereignis({ hook_event_name: 'UserPromptSubmit', prompt: 'Baue die Zeitleiste ein', cwd: proj, session_id: 'abc' });
    assert.strictEqual(antwort.status(), 200);
    assert.deepStrictEqual(await antwort.json(), {}, 'Antwort {}: Claude Code macht normal weiter');
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude arbeitet');
    assert.strictEqual(await handy.textContent('#cl-projekt'), 'Projekt: Handy_Overlay');
    await ereignis({ hook_event_name: 'PreToolUse', tool_name: 'Edit', tool_input: { file_path: 'C:\\Users\\timo\\Handy_Overlay\\server.py', old_string: 'GEHEIM', new_string: 'x' }, cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-aktion').textContent === 'Bearbeitet server.py');
    await ereignis({ hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: "curl -H 'Authorization: Bearer GEHEIM' https://x" }, cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-aktion').textContent === 'Führt einen Befehl aus (curl)');
    ok('Ereignisse von Claude Code (mit Windows-Pfaden) ergeben Projekt und Aktion auf dem Handy');

    await ereignis({ hook_event_name: 'PermissionRequest', tool_name: 'Edit', tool_input: { file_path: 'C:\\a\\medien.py' }, cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude braucht dich');
    assert.strictEqual(await handy.textContent('#cl-aktion'), 'Erlaubnis nötig: Bearbeitet medien.py');
    await ereignis({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: { file_path: 'x.py' }, cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude arbeitet');
    await ereignis({ hook_event_name: 'Notification', notification_type: 'permission_prompt', message: 'Claude braucht deine Erlaubnis für Bash', cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude braucht dich');
    await ereignis({ hook_event_name: 'Stop', cwd: proj, last_assistant_message: 'Fertig' });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude ist fertig');
    ok('Erlaubnis-Abfrage, Benachrichtigung und Stop ergeben "braucht dich", "arbeitet" und "fertig"');

    // ---- Ignoriertes, Kaputtes, Grosses
    await ereignis({ hook_event_name: 'PostToolUse', tool_name: 'Edit', tool_response: { x: 'y'.repeat(50000) } });
    await ereignis({ hook_event_name: 'Notification', notification_type: 'idle_prompt', message: 'wartet' });
    await ereignis({ hook_event_name: 'SessionStart', source: 'startup' });
    assert.strictEqual(await handy.textContent('#cl-titel'), 'Claude ist fertig', 'ignorierte Ereignisse aendern die Anzeige nicht');
    assert.strictEqual((await lokal.post(URL + '/claude-hook', { data: Buffer.from('{kaputt'), headers: { 'Content-Type': 'application/json' } })).status(), 400);
    assert.strictEqual((await ereignis([1, 2, 3])).status(), 200);
    const gross = await lokal.post(URL + '/claude-hook', { data: Buffer.alloc(6_000_000, 97), headers: { 'Content-Type': 'application/json' } });
    assert.strictEqual(gross.status(), 413);
    assert.ok((await handy.textContent('#cl-titel')).length > 0);
    ok('Unwichtige Ereignisse werden gezaehlt, aber ignoriert; kaputte und riesige Anfragen werden abgewiesen');

    // ---- Diagnose zaehlt mit
    await admin.waitForFunction(() => /Letzte Meldung vor \d+ s/.test(document.getElementById('cl-meldungen').textContent), null, { timeout: 8000 });
    const zaehler = await admin.textContent('#cl-meldungen');
    for (const e of ['UserPromptSubmit 1', 'PreToolUse 3', 'PermissionRequest 1', 'Notification 2', 'Stop 1', 'PostToolUse 1', 'SessionStart 1']) assert.ok(zaehler.includes(e), e + ' in: ' + zaehler);
    ok('Die Diagnose zeigt, wann zuletzt etwas ankam und wie viele Ereignisse je Art');

    // ---- Python-Variante (Ersatz): Skript leitet stdin weiter
    const kopie = path.join(TMP, 'pb', 'hooks');
    fs.mkdirSync(kopie, { recursive: true });
    fs.copyFileSync(path.join(REPO, 'hooks', 'claude_status.py'), path.join(kopie, 'claude_status.py'));
    const skript = path.join(kopie, 'claude_status.py');
    const env = { ...process.env, PHONEBOX_URL: `http://127.0.0.1:${PORT}/claude` };
    const r1 = spawnSync('python3', [skript], { input: JSON.stringify({ hook_event_name: 'UserPromptSubmit', prompt: 'Per Skript', cwd: '/home/x/Skriptprojekt' }), env, encoding: 'utf-8' });
    assert.strictEqual(r1.status, 0, r1.stderr);
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude arbeitet');
    assert.strictEqual(await handy.textContent('#cl-projekt'), 'Projekt: Skriptprojekt');
    const t = spawnSync('python3', [skript, '--test'], { env, encoding: 'utf-8' });
    assert.strictEqual(t.status, 0);
    assert.match(t.stdout, /HTTP 200/);
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude braucht dich');
    const logDatei = path.join(TMP, 'pb', 'daten', 'claude-hook.log');
    assert.match(fs.readFileSync(logDatei, 'utf-8'), /UserPromptSubmit: HTTP 200/);
    // Server aus: das Skript darf Claude Code nie stoeren
    const tot = spawnSync('python3', [skript], { input: JSON.stringify({ hook_event_name: 'Stop' }), env: { ...process.env, PHONEBOX_URL: 'http://127.0.0.1:9/claude' }, encoding: 'utf-8' });
    assert.strictEqual(tot.status, 0, 'ohne Phonebox muss das Skript still mit 0 enden');
    assert.match(fs.readFileSync(logDatei, 'utf-8'), /FEHLER/);
    assert.strictEqual(spawnSync('python3', [skript], { input: '', env, encoding: 'utf-8' }).status, 0);
    assert.strictEqual(spawnSync('python3', [skript], { input: 'kein json', env, encoding: 'utf-8' }).status, 0);
    ok('Das Python-Skript leitet Ereignisse weiter, schreibt ein Protokoll und stoert Claude Code nie (auch bei ausgeschalteter Phonebox)');

    // ---- Python-Variante einrichten und entfernen
    await admin.fill('#cl-pw', PW);
    await admin.click('summary:has-text("Weitere Möglichkeiten")');
    await admin.click('button:has-text("Python-Variante einrichten")');
    await admin.waitForFunction(() => /python/.test(document.getElementById('cl-lage').textContent));
    const hp = json().hooks.Stop.at(-1).hooks[0];
    assert.strictEqual(hp.type, 'command');
    assert.ok(hp.args[0].endsWith(path.join('hooks', 'claude_status.py')) && fs.existsSync(hp.args[0]), 'Skript-Pfad muss stimmen');
    assert.ok(!/pythonw/i.test(hp.command), 'nie pythonw');
    assert.strictEqual(json().hooks.PreToolUse.at(-1).hooks[0].async, true);
    assert.strictEqual(json().hooks.Stop.length, 1, 'die http-Eintraege muessen ersetzt worden sein, nicht doppelt stehen');
    await admin.fill('#cl-pw', PW);
    admin.once('dialog', (x) => x.accept());
    await admin.click('button:has-text("Hooks entfernen")');
    await admin.waitForFunction(() => /Noch nicht eingerichtet/.test(document.getElementById('cl-lage').textContent));
    const nach = json();
    assert.deepStrictEqual(nach.hooks, { SessionStart: [{ hooks: [{ type: 'command', command: 'echo hallo' }] }] });
    assert.strictEqual(nach.model, 'opus');
    ok('Python-Variante ersetzt die http-Eintraege sauber, Entfernen loescht nur die Phonebox-Eintraege');

    // ---- Kaputte settings.json wird nicht angefasst
    fs.writeFileSync(SETTINGS, '{ "hooks": { , } }');
    await admin.waitForFunction(() => /fehlerhaft/.test(document.getElementById('cl-lage').textContent), null, { timeout: 8000 });
    await admin.fill('#cl-pw', PW);
    await admin.click('button:has-text("Hooks einrichten")');
    await admin.waitForFunction(() => /kein gültiges JSON|kein gueltiges JSON/.test(document.getElementById('cl-fehler').textContent));
    assert.strictEqual(fs.readFileSync(SETTINGS, 'utf-8'), '{ "hooks": { , } }');
    ok('Eine fehlerhafte settings.json wird erkannt, gemeldet und nicht veraendert');

    // ---- Testmeldungen aus dem Admin-Bereich
    await admin.click('button:has-text("Braucht dich")');
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude braucht dich');
    assert.match(await handy.textContent('#cl-aktion'), /Testmeldung/);
    ok('Die Testknoepfe zeigen eine Meldung auf dem Handy');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));

    // ---- Ton, Blitz und Vibration
    const ton = await browser.newContext({ viewport: { width: 667, height: 375 } });
    await ton.request.post(URL + '/api/anmelden', { headers: H, data: { name: 'Timo', passwort: PW } });
    await ton.addInitScript(() => {
      window.__t = { osc: [], vib: [] };
      window.AudioContext = class { constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; }
        resume() {} createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} }; }
        createOscillator() { const o = { frequency: { value: 0 }, connect() {}, start() {}, stop() {} }; window.__t.osc.push(o); return o; } };
      navigator.vibrate = (m) => { window.__t.vib.push(m); return true; };
    });
    const p = await ton.newPage();
    await ereignis({ hook_event_name: 'Stop' });  // schon "fertig", bevor die Seite geladen wird
    await p.goto(URL + '/');
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await wait(800);
    assert.strictEqual(await p.evaluate(() => window.__t.osc.length), 0, 'beim Laden der Seite darf nichts piepen');
    await p.mouse.click(300, 200);  // erster Tipp schaltet den Ton frei (wie bei iOS)
    const toene = () => p.evaluate(() => window.__t.osc.map((o) => o.frequency.value));
    await ereignis({ hook_event_name: 'UserPromptSubmit', prompt: 'x' });
    await wait(500);
    assert.deepStrictEqual(await toene(), [], 'arbeitet ist still');
    await ereignis({ hook_event_name: 'Stop' });
    await p.waitForFunction(() => window.__t.osc.length === 2);
    assert.deepStrictEqual(await toene(), [660, 880]);
    assert.strictEqual(await p.evaluate(() => getComputedStyle(document.getElementById('blitz')).backgroundColor), 'rgb(29, 185, 84)');
    assert.ok(await p.evaluate(() => document.getElementById('blitz').classList.contains('an')));
    assert.strictEqual(await p.evaluate(() => window.__t.vib.length), 1);
    await ereignis({ hook_event_name: 'PermissionRequest', tool_name: 'Bash', tool_input: {} });
    await p.waitForFunction(() => window.__t.osc.length === 5);
    assert.deepStrictEqual((await toene()).slice(2), [880, 880, 880]);
    assert.strictEqual(await p.evaluate(() => getComputedStyle(document.getElementById('blitz')).backgroundColor), 'rgb(59, 130, 246)');
    await ereignis({ hook_event_name: 'Notification', notification_type: 'permission_prompt', message: 'nochmal' });
    await wait(600);
    assert.strictEqual((await toene()).length, 5, 'schon "braucht dich": kein zweiter Alarm');
    ok('Ton und Blitz bei "fertig" (zwei Toene, gruen) und "braucht dich" (drei Toene, blau), nicht beim Laden, nicht doppelt');

    await p.evaluate(() => localStorage.setItem('phonebox-claude-signal', 'blitz'));
    await ereignis({ hook_event_name: 'UserPromptSubmit', prompt: 'y' });
    await ereignis({ hook_event_name: 'Stop' });
    await wait(700);
    assert.strictEqual((await toene()).length, 5, 'im Blitz-Modus bleibt es still');
    assert.strictEqual(await p.evaluate(() => window.__t.vib.length), 3);
    await p.evaluate(() => localStorage.setItem('phonebox-claude-signal', 'aus'));
    const vibVorher = await p.evaluate(() => window.__t.vib.length);
    await ereignis({ hook_event_name: 'UserPromptSubmit', prompt: 'z' });
    await ereignis({ hook_event_name: 'Stop' });
    await wait(700);
    assert.strictEqual((await toene()).length, 5);
    assert.strictEqual(await p.evaluate(() => window.__t.vib.length), vibVorher, 'bei "Nichts" auch keine Vibration');
    ok('Die Einstellung "Nur Blitz" und "Nichts" wird beachtet');

    console.log('Alle Claude-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
