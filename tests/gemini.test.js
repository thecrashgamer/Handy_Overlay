// Gemini CLI statt Claude Code: Auswahl im Admin-Bereich, Hooks einrichten, Ereignisse, Anweisungen vom Handy: node tests/gemini.test.js
const { chromium, request } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const REPO = path.join(__dirname, '..');
const PORT = 8137;
const URL = `http://localhost:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-gemini-'));
const HOME = path.join(TMP, 'home');  // so wird NIE die echte ~/.gemini/settings.json beruehrt
const SETTINGS = path.join(HOME, '.gemini', 'settings.json');
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);
const json = () => JSON.parse(fs.readFileSync(SETTINGS, 'utf-8'));

fs.mkdirSync(path.dirname(SETTINGS), { recursive: true });
fs.writeFileSync(SETTINGS, JSON.stringify({ theme: 'dunkel', hooks: { SessionStart: [{ hooks: [{ type: 'command', command: 'echo hallo' }] }] } }));

(async () => {
  const server = spawn('python3', ['server.py'], { cwd: REPO, stdio: 'ignore',
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: path.join(TMP, 'daten'),
           HOME, USERPROFILE: HOME, CLAUDE_CONFIG_DIR: path.join(TMP, 'claude'), PHONEBOX_GEMINI_HALTEN_S: '2' } });
  await wait(2500);
  const browser = await chromium.launch();
  try {
    const adminCtx = await browser.newContext({ viewport: { width: 900, height: 900 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    const lokal = await request.newContext();  // so meldet sich der Hook: vom PC selbst, ohne Anmeldung
    const gemini = (daten) => lokal.post(URL + '/gemini-hook', { data: daten });
    const claude = (daten) => lokal.post(URL + '/claude-hook', { data: daten });

    // ---- Auswahl nur fuer Administratoren, nur mit Passwort
    assert.strictEqual((await gastCtx.request.post(URL + '/api/claude/anbieter', { headers: H, data: { passwort: PW, anbieter: 'gemini' } })).status(), 403);
    assert.strictEqual((await adminCtx.request.post(URL + '/api/claude/anbieter', { data: { passwort: PW, anbieter: 'gemini' } })).status(), 403, 'ohne Kopfzeile');
    assert.notStrictEqual((await adminCtx.request.post(URL + '/api/claude/anbieter', { headers: H, data: { passwort: 'falsch-falsch-1', anbieter: 'gemini' } })).status(), 200);
    assert.strictEqual((await adminCtx.request.post(URL + '/api/claude/anbieter', { headers: H, data: { passwort: PW, anbieter: 'unbekannt' } })).status(), 422);
    assert.strictEqual((await (await adminCtx.request.get(URL + '/api/claude/diagnose')).json()).anbieter, 'claude', 'Standard ist Claude');
    ok('Die Auswahl der KI geht nur als Administrator mit Passwort; Standard ist Claude');

    // ---- Im Admin-Bereich auf Gemini umstellen und einrichten
    const admin = await adminCtx.newPage();
    const jsFehler = [];
    admin.on('pageerror', (e) => jsFehler.push(e.message));
    await admin.goto(URL + '/admin');
    await admin.waitForFunction(() => /Noch nicht eingerichtet/.test(document.getElementById('cl-lage').textContent));
    await admin.selectOption('#cl-anbieter', 'gemini');
    await admin.fill('#cl-pw', PW);
    await admin.click('button:has-text("Übernehmen")');
    await admin.waitForFunction(() => document.getElementById('cl-ki-name').textContent === 'Gemini');
    assert.ok(await admin.isVisible('#cl-so-gemini') && !(await admin.isVisible('#cl-so-claude')));
    assert.ok(!(await admin.isVisible('#cl-python-knopf')), 'Gemini kennt nur eine Art von Hooks');
    await admin.fill('#cl-pw', PW);
    await admin.click('button:has-text("Hooks einrichten")');
    await admin.waitForFunction(() => /Eingetragen in/.test(document.getElementById('cl-fehler').textContent));
    await admin.waitForFunction(() => /Hooks sind eingetragen/.test(document.getElementById('cl-lage').textContent));
    const d = json();
    assert.strictEqual(d.theme, 'dunkel');
    assert.deepStrictEqual(d.hooks.SessionStart, [{ hooks: [{ type: 'command', command: 'echo hallo' }] }], 'fremde Hooks muessen bleiben');
    for (const e of ['BeforeAgent', 'BeforeTool', 'Notification', 'AfterAgent']) {
      const h = d.hooks[e].at(-1).hooks[0];
      assert.strictEqual(h.type, 'command', e);
      assert.ok(h.command.includes('gemini_status.py') && !/pythonw/i.test(h.command), e);
      assert.strictEqual(h.timeout, e === 'AfterAgent' ? 600000 : 5000, e + ': Gemini rechnet in Millisekunden');
    }
    assert.ok(!fs.existsSync(path.join(TMP, 'claude', 'settings.json')), 'die Claude-Datei darf nicht angefasst werden');
    ok('Auf Gemini umstellen, Hooks in ~/.gemini/settings.json eintragen: fremde Hooks bleiben, Zeiten in Millisekunden');

    // ---- Gemini CLI schickt Ereignisse
    const handy = await adminCtx.newPage();
    await handy.goto(URL + '/');
    await handy.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await handy.click('#wechsel'); await handy.click('#wechsel');  // Claude-Ansicht (zeigt jetzt Gemini)
    const proj = 'C:\\Users\\timo\\Handy_Overlay';
    const antwort = await gemini({ hook_event_name: 'BeforeAgent', prompt: 'Baue die Zeitleiste ein', cwd: proj, session_id: 'g1' });
    assert.deepStrictEqual(await antwort.json(), {}, 'Antwort {}: Gemini macht normal weiter');
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Gemini arbeitet');
    assert.strictEqual(await handy.textContent('#cl-projekt'), 'Projekt: Handy_Overlay');
    await gemini({ hook_event_name: 'BeforeTool', tool_name: 'replace', tool_input: { file_path: 'C:\\x\\server.py', old_string: 'GEHEIM' }, cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-aktion').textContent === 'Bearbeitet server.py');
    await gemini({ hook_event_name: 'Notification', notification_type: 'ToolPermission', message: 'Shell-Befehl erlauben?', cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Gemini braucht dich');
    assert.strictEqual(await handy.textContent('#cl-aktion'), 'Shell-Befehl erlauben?');
    await gemini({ hook_event_name: 'AfterAgent', prompt_response: 'Fertig', cwd: proj });
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Gemini ist fertig');
    await gemini({ hook_event_name: 'SessionStart', source: 'startup' });
    await gemini({ hook_event_name: 'AfterTool', tool_name: 'replace' });
    ok('Gemini-Ereignisse ergeben Projekt, Aktion, "braucht dich" und "fertig" mit dem Namen Gemini; Unwichtiges wird ignoriert');

    // ---- Ereignisse der anderen KI werden gezaehlt, aber nicht angezeigt
    await claude({ hook_event_name: 'UserPromptSubmit', prompt: 'Aufgabe fuer Claude', cwd: proj });
    await wait(300);
    assert.strictEqual(await handy.textContent('#cl-titel'), 'Gemini ist fertig');
    ok('Ereignisse von Claude Code aendern die Anzeige nicht, solange Gemini gewaehlt ist');

    // ---- Anweisungen vom Handy
    await admin.fill('#cl-pw', PW);
    admin.once('dialog', (x) => x.accept());
    await admin.click('#cl-eingabe-knopf');
    await admin.waitForFunction(() => /Eingeschaltet/.test(document.getElementById('cl-fehler').textContent));
    await handy.waitForSelector('#cl-text', { state: 'visible' });
    assert.strictEqual(await handy.getAttribute('#cl-text', 'placeholder'), 'Anweisung an Gemini ...');
    assert.strictEqual((await handy.textContent('#cl-senden')).trim(), 'An Gemini senden');
    // Gemini ist gerade fertig: die Anweisung geht bei AfterAgent als "deny" mit Grund (= neue Eingabe an Gemini) mit
    const senden = (text) => adminCtx.request.post(URL + '/api/claude/nachricht', { headers: H, data: { text } });
    assert.strictEqual((await senden('Raeume die Tests auf')).status(), 200);
    let a = await (await gemini({ hook_event_name: 'AfterAgent', prompt_response: 'Fertig', cwd: proj })).json();
    assert.strictEqual(a.decision, 'deny');
    assert.match(a.reason, /Raeume die Tests auf/);
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Gemini arbeitet');
    // Zu Beginn einer neuen Aufgabe geht sie als Zusatztext mit (BeforeAgent)
    assert.strictEqual((await senden('Und dann committen')).status(), 200);
    a = await (await gemini({ hook_event_name: 'BeforeAgent', prompt: 'weiter', cwd: proj })).json();
    assert.strictEqual(a.hookSpecificOutput.hookEventName, 'BeforeAgent');
    assert.match(a.hookSpecificOutput.additionalContext, /Und dann committen/);
    // Mitten in der Arbeit (BeforeTool) nimmt Gemini nichts an: sie bleibt wartend
    assert.strictEqual((await senden('Bleibt liegen')).status(), 200);
    a = await (await gemini({ hook_event_name: 'BeforeTool', tool_name: 'read_file', tool_input: { file_path: 'x' } })).json();
    assert.deepStrictEqual(a, {});
    // Bei AfterAgent wartet die Antwort kurz (hier 2 s) und gibt die liegende Anweisung dann mit
    a = await (await gemini({ hook_event_name: 'AfterAgent', prompt_response: 'Fertig' })).json();
    assert.match(a.reason, /Bleibt liegen/);
    // Ohne Anweisung kehrt AfterAgent nach der Wartezeit mit {} zurueck
    const t0 = Date.now();
    assert.deepStrictEqual(await (await gemini({ hook_event_name: 'AfterAgent', prompt_response: 'Fertig' })).json(), {});
    assert.ok(Date.now() - t0 >= 1800, 'die Antwort muss die eingestellte Wartezeit abwarten');
    ok('Anweisungen vom Handy: bei AfterAgent als deny mit Grund, bei BeforeAgent als Zusatztext, mitten in der Arbeit nie, danach wird gewartet');

    // ---- Das Python-Skript fuer Gemini CLI
    const skript = path.join(REPO, 'hooks', 'gemini_status.py');
    const pro = path.join(TMP, 'pb');
    fs.mkdirSync(path.join(pro, 'hooks'), { recursive: true });
    fs.copyFileSync(skript, path.join(pro, 'hooks', 'gemini_status.py'));
    fs.mkdirSync(path.join(pro, 'daten'), { recursive: true });
    fs.writeFileSync(path.join(pro, 'daten', 'server.json'), JSON.stringify({ port: PORT }));
    const lauf = (eingabe, port = PORT) => {
      fs.writeFileSync(path.join(pro, 'daten', 'server.json'), JSON.stringify({ port }));
      return spawnSync('python3', [path.join(pro, 'hooks', 'gemini_status.py')], { input: eingabe, encoding: 'utf-8' });
    };
    let r = lauf(JSON.stringify({ hook_event_name: 'BeforeAgent', prompt: 'Aus dem Skript', cwd: proj }));
    assert.strictEqual(r.status, 0);
    assert.deepStrictEqual(JSON.parse(r.stdout), {}, 'auf stdout steht nur JSON');
    await handy.waitForFunction(() => /Aus dem Skript/.test(document.getElementById('cl-verlauf').textContent));
    assert.strictEqual((await senden('Per Skript')).status(), 200);
    r = lauf(JSON.stringify({ hook_event_name: 'AfterAgent', prompt_response: 'x', cwd: proj }));
    assert.match(JSON.parse(r.stdout).reason, /Per Skript/, 'das Skript gibt die Antwort der Phonebox an Gemini CLI weiter');
    r = lauf(JSON.stringify({ hook_event_name: 'BeforeAgent' }), 1);  // Phonebox nicht erreichbar
    assert.strictEqual(r.status, 0);
    assert.strictEqual(r.stdout, '{}', 'Gemini CLI wird nie gebremst');
    r = lauf('');
    assert.strictEqual(r.stdout, '{}');
    assert.ok(/BeforeAgent: HTTP 200/.test(fs.readFileSync(path.join(pro, 'daten', 'gemini-hook.log'), 'utf-8')));
    ok('hooks/gemini_status.py: gibt nur JSON aus, reicht die Antwort durch, stoert Gemini CLI nie und schreibt ein Protokoll');

    // ---- Entfernen und zurueck zu Claude
    await admin.fill('#cl-pw', PW);
    admin.once('dialog', (x) => x.accept());
    await admin.click('summary:has-text("Weitere Möglichkeiten")');
    await admin.click('button:has-text("Hooks entfernen")');
    await admin.waitForFunction(() => /Noch nicht eingerichtet/.test(document.getElementById('cl-lage').textContent));
    assert.deepStrictEqual(json().hooks, { SessionStart: [{ hooks: [{ type: 'command', command: 'echo hallo' }] }] });
    await admin.selectOption('#cl-anbieter', 'claude');
    await admin.fill('#cl-pw', PW);
    await admin.click('button:has-text("Übernehmen")');
    await admin.waitForFunction(() => document.getElementById('cl-ki-name').textContent === 'Claude');
    await handy.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude ruht');
    ok('Entfernen loescht nur die Phonebox-Eintraege; zurueck auf Claude leert die Anzeige');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));
    console.log('Alle Gemini-Tests bestanden');
  } catch (f) {
    console.log('FEHLER:', f.message);
    process.exitCode = 1;
  } finally {
    await browser.close();
    server.kill();
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})();
