// Anweisungen vom Handy an Claude: node tests/eingabe.test.js
const { chromium, request } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8138;
const URL = `http://localhost:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'phonebox-eingabe-'));
const PW = 'Sommer-Regen-42';
const H = { 'X-Phonebox': '1' };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ok = (n) => console.log('ok  -', n);

(async () => {
  const server = spawn('python3', ['server.py'], { cwd: path.join(__dirname, '..'),
    env: { ...process.env, PHONEBOX_TEST: '1', PHONEBOX_PORT: String(PORT), PHONEBOX_DATEN: TMP, PHONEBOX_EINGABE_VERFALL_S: '4', PHONEBOX_EINGABE_HALTEN_S: '3',
           CLAUDE_CONFIG_DIR: path.join(TMP, 'k') }, stdio: 'ignore' });
  await wait(2500);
  const browser = await chromium.launch();
  try {
    const adminCtx = await browser.newContext({ viewport: { width: 667, height: 375 } });
    await adminCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Timo', passwort: PW } });
    await adminCtx.request.post(URL + '/api/einstellungen', { headers: H, data: { registrierung: 'offen' } });
    const gastCtx = await browser.newContext();
    await gastCtx.request.post(URL + '/api/registrieren', { headers: H, data: { name: 'Gast', passwort: PW } });
    const pc = await request.newContext();  // so meldet sich Claude Code: vom PC selbst
    const hook = async (daten) => (await pc.post(URL + '/claude-hook', { data: daten })).json();
    const senden = (ctx, text) => ctx.request.post(URL + '/api/claude/nachricht', { headers: H, data: { text } });

    // ---- Standard: aus
    let r = await senden(adminCtx, 'Hallo');
    assert.strictEqual(r.status(), 403);
    assert.match((await r.json()).fehler, /ausgeschaltet/);
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {});
    const p = await adminCtx.newPage();
    const jsFehler = [];
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.goto(URL + '/');
    await p.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await p.click('#wechsel'); await p.click('#wechsel');
    await wait(500);
    assert.ok(!(await p.isVisible('#cl-eingabe')), 'ausgeschaltet: kein Eingabefeld');
    ok('Standard: ausgeschaltet, kein Eingabefeld, nichts wird uebergeben');

    // ---- Einschalten: nur Administrator, nur mit Passwort
    assert.strictEqual((await gastCtx.request.post(URL + '/api/claude/eingabe', { headers: H, data: { passwort: PW, an: true } })).status(), 403);
    assert.strictEqual((await adminCtx.request.post(URL + '/api/claude/eingabe', { headers: H, data: { passwort: 'falsch-falsch-1', an: true } })).status(), 403);
    assert.strictEqual((await adminCtx.request.post(URL + '/api/claude/eingabe', { data: { passwort: PW, an: true } })).status(), 403, 'ohne Kopfzeile');
    assert.ok((await adminCtx.request.post(URL + '/api/claude/eingabe', { headers: H, data: { passwort: PW, an: true } })).ok());
    await p.waitForSelector('#cl-eingabe', { state: 'visible', timeout: 5000 });
    const g = await gastCtx.newPage();
    await g.goto(URL + '/'); await g.waitForFunction(() => document.getElementById('status').textContent.startsWith('Verbunden'));
    await g.click('#wechsel'); await g.click('#wechsel'); await wait(500);
    assert.ok(!(await g.isVisible('#cl-eingabe')), 'ein normaler Benutzer sieht kein Eingabefeld');
    assert.strictEqual((await senden(gastCtx, 'Ich auch')).status(), 403);
    ok('Einschalten nur als Administrator mit Passwort; normale Benutzer sehen kein Eingabefeld und koennen nichts senden');

    // ---- Senden ueber die Oberflaeche
    await p.fill('#cl-text', 'Mach den Knopf gruen');
    await p.click('#cl-senden');
    await p.waitForFunction(() => document.querySelector('#cl-eliste .zustand.wartet'));
    assert.strictEqual(await p.inputValue('#cl-text'), '');
    assert.match(await p.textContent('#cl-eliste'), /Mach den Knopf gruen/);
    await p.click('#cl-senden');
    assert.match(await p.textContent('#cl-efehler'), /Schreib erst etwas/);
    ok('Senden: Text erscheint als "wartet auf Claude", leeres Feld wird abgelehnt');

    // ---- Claude-Mod: holt Anweisungen selbst ab, nur vom PC, und die Hook-Wege treten dann zurueck
    const abholen = (kopf = {}) => pc.post(URL + '/api/claude/mod/abholen', { headers: { 'X-Phonebox': '1', ...kopf }, data: { session_id: 's1', cwd: '/x' } });
    assert.strictEqual((await abholen({ 'X-Forwarded-For': '203.0.113.7' })).status(), 403, 'von aussen nicht');
    const m1 = await (await abholen()).json();
    assert.strictEqual(m1.text, 'Mach den Knopf gruen');
    assert.deepStrictEqual(await (await abholen()).json(), {}, 'nur einmal');
    await senden(adminCtx, 'nur fuer den Mod');
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {}, 'mit Mod keine Uebergabe ueber Hooks');
    const tm = Date.now();
    assert.deepStrictEqual(await hook({ hook_event_name: 'Stop', cwd: '/x' }), {});
    assert.ok(Date.now() - tm < 1500, 'mit Mod haelt Stop nicht offen');
    assert.strictEqual((await (await abholen()).json()).text, 'nur fuer den Mod');
    // Mehrere Sitzungen: nur die zuletzt aktive bekommt die Anweisung
    const als = (sid) => pc.post(URL + '/api/claude/mod/abholen', { headers: { 'X-Phonebox': '1' }, data: { session_id: sid, cwd: '/x' } });
    await als('B');
    await hook({ hook_event_name: 'UserPromptSubmit', prompt: 'x', cwd: '/x', session_id: 'A' });
    await als('A');
    await senden(adminCtx, 'nur fuer A');
    assert.deepStrictEqual(await (await als('B')).json(), {}, 'die andere Sitzung bekommt nichts');
    assert.strictEqual((await (await als('A')).json()).text, 'nur fuer A');
    await hook({ hook_event_name: 'UserPromptSubmit', prompt: 'y', cwd: '/x', session_id: 'B' });
    await senden(adminCtx, 'nur fuer B');
    assert.deepStrictEqual(await (await als('A')).json(), {});
    assert.strictEqual((await (await als('B')).json()).text, 'nur fuer B');
    await wait(10600);  // Herzschlag des Mods laeuft ab: die Hook-Wege gelten wieder
    await senden(adminCtx, 'Mach den Knopf gruen');
    ok('Mod: holt Anweisungen nur vom PC ab, genau einmal; solange er verbunden ist, uebergeben die Hooks nichts und Stop wartet nicht');

    // ---- Uebergabe waehrend der Arbeit (PreToolUse -> additionalContext)
    const a1 = await hook({ hook_event_name: 'PreToolUse', tool_name: 'Edit', tool_input: { file_path: 'a.py' }, cwd: '/x/proj' });
    assert.strictEqual(a1.hookSpecificOutput.hookEventName, 'PreToolUse');
    assert.ok(a1.hookSpecificOutput.additionalContext.includes('Mach den Knopf gruen'));
    assert.match(a1.hookSpecificOutput.additionalContext, /Phonebox/);
    assert.ok(!('decision' in a1), 'waehrend der Arbeit wird nichts blockiert');
    await p.waitForFunction(() => /übergeben/.test(document.querySelector('#cl-eliste .zustand').textContent));
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {}, 'nur einmal uebergeben');
    ok('Waehrend Claude arbeitet, geht die Anweisung als Zusatztext (additionalContext) mit, genau einmal');

    // ---- Uebergabe am Ende (Stop -> decision block)
    await hook({ hook_event_name: 'UserPromptSubmit', prompt: 'x', cwd: '/x/proj' });
    await senden(adminCtx, 'Schreib noch einen Test');
    const s1 = await hook({ hook_event_name: 'Stop', cwd: '/x/proj', stop_hook_active: false });
    assert.strictEqual(s1.decision, 'block');
    assert.ok(s1.reason.includes('Schreib noch einen Test'));
    await wait(400);
    assert.strictEqual(await p.textContent('#cl-titel'), 'Claude arbeitet', 'Claude macht weiter: nicht "fertig"');
    const s2 = await hook({ hook_event_name: 'Stop', cwd: '/x/proj', stop_hook_active: true });
    assert.deepStrictEqual(s2, {}, 'ohne neue Anweisung darf Claude jetzt aufhoeren (keine Endlosschleife)');
    await p.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude ist fertig');
    ok('Am Ende des Zuges laesst eine wartende Anweisung Claude weiterarbeiten (nicht "fertig"), ohne neue Anweisung endet er');

    // ---- Claude ist schon fertig: Stop bleibt offen und wartet auf eine Anweisung vom Handy
    const t0 = Date.now();
    const warten = hook({ hook_event_name: 'Stop', cwd: '/x/proj', stop_hook_active: false });
    await p.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude ist fertig');
    await wait(700);
    await senden(adminCtx, 'Nachträglich vom Handy');
    const geweckt = await warten;
    assert.strictEqual(geweckt.decision, 'block');
    assert.ok(geweckt.reason.includes('Nachträglich vom Handy'));
    assert.ok(Date.now() - t0 < 2800, 'sofort nach dem Senden, nicht erst nach Ablauf');
    await p.waitForFunction(() => document.getElementById('cl-titel').textContent === 'Claude arbeitet');
    const t1 = Date.now();
    assert.deepStrictEqual(await hook({ hook_event_name: 'Stop', cwd: '/x/proj', stop_hook_active: true }), {});
    assert.ok(Date.now() - t1 >= 2500, 'ohne Anweisung wartet Stop bis zum Ende des Zeitfensters');
    ok('Ist Claude schon fertig, bleibt Stop offen: eine Anweisung vom Handy weckt ihn sofort, sonst endet das Fenster');

    // ---- Mehrere zusammen, in Reihenfolge; UserPromptSubmit
    await senden(adminCtx, 'erstens'); await senden(adminCtx, 'zweitens');
    const u = await hook({ hook_event_name: 'UserPromptSubmit', prompt: 'was am PC getippt wurde', cwd: '/x' });
    const text = u.hookSpecificOutput.additionalContext;
    assert.ok(text.indexOf('erstens') >= 0 && text.indexOf('erstens') < text.indexOf('zweitens'));
    ok('Mehrere Anweisungen gehen zusammen und in der richtigen Reihenfolge mit');

    // ---- Nur an den PC, nie an einen angemeldeten Browser
    await senden(adminCtx, 'geheime Anweisung');
    const mitTunnel = await pc.post(URL + '/claude-hook', { headers: { 'X-Forwarded-For': '203.0.113.7' }, data: { hook_event_name: 'PreToolUse' } });
    assert.strictEqual(mitTunnel.status(), 403, 'Anfragen von aussen (Weiterleitung) bekommen nichts');
    assert.ok(!(await mitTunnel.text()).includes('geheime'));
    const echt = await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} });
    assert.ok(echt.hookSpecificOutput.additionalContext.includes('geheime Anweisung'), 'noch da und fuer den PC abholbar');
    ok('Wartende Anweisungen bekommt nur Claude Code auf dem PC selbst, nie Anfragen von aussen');

    // ---- Zurueckziehen, Grenzen, Verfall
    await wait(61000);  // die Bremse (10 pro Minute) hat bis hierher schon einiges gezaehlt
    const w = await (await senden(adminCtx, 'doch nicht')).json();
    await p.waitForSelector('#cl-eliste button');
    await p.click('#cl-eliste button');
    await p.waitForFunction(() => /zurückgezogen/.test(document.getElementById('cl-eliste').textContent));
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {}, 'Zurueckgezogenes wird nicht uebergeben');
    assert.strictEqual((await adminCtx.request.post(URL + '/api/claude/nachricht/zurueckziehen', { headers: H, data: { id: w.id } })).status(), 409);
    assert.strictEqual((await senden(adminCtx, 'x'.repeat(2001))).status(), 400);
    assert.strictEqual((await senden(adminCtx, '   ')).status(), 400);
    const antworten = [];
    for (let i = 0; i < 6; i++) antworten.push((await senden(adminCtx, 'b' + i)).status());
    assert.ok(antworten.includes(400) || antworten.includes(429), 'Begrenzung (5 wartende bzw. Bremse): ' + antworten);
    ok('Zurueckziehen, Laengengrenze, leere Texte und die Grenze von 5 wartenden Anweisungen');

    await wait(4500);  // Verfall im Test: 4 Sekunden (sonst 15 Minuten)
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {}, 'Verfallenes wird nie uebergeben');
    await p.waitForFunction(() => /verfallen/.test(document.getElementById('cl-eliste').textContent));
    ok('Eine Anweisung, die zu lange wartet, verfaellt und geht nie spaeter ploetzlich los');

    // ---- Rate-Limit und Ausschalten
    let limit = 0;
    for (let i = 0; i < 12; i++) if ((await senden(adminCtx, 'z' + i)).status() === 429) limit++;
    assert.ok(limit >= 1, 'zu viele Anweisungen pro Minute muessen gebremst werden');
    await senden(adminCtx, 'bleibt nicht').catch(() => {});
    assert.ok((await adminCtx.request.post(URL + '/api/claude/eingabe', { headers: H, data: { passwort: PW, an: false } })).ok());
    assert.deepStrictEqual(await hook({ hook_event_name: 'PreToolUse', tool_name: 'Read', tool_input: {} }), {}, 'nach dem Ausschalten geht nichts mehr raus');
    await p.waitForSelector('#cl-eingabe', { state: 'hidden', timeout: 5000 });
    assert.strictEqual((await senden(adminCtx, 'nochmal')).status(), 403);
    ok('Zu schnelles Senden wird gebremst, Ausschalten leert die Warteschlange und blendet das Feld aus');

    // ---- Protokoll ohne Passwoerter
    const akt = await (await adminCtx.request.get(URL + '/api/aktivitaet?art=claude,admin&limit=200')).json();
    assert.ok(akt.eintraege.some((e) => e.art === 'claude' && /Anweisung an Claude \(/.test(e.text)));
    assert.ok(akt.eintraege.some((e) => e.art === 'claude' && /übergeben/.test(e.text)));
    assert.ok(akt.eintraege.some((e) => e.art === 'admin' && /eingeschaltet/.test(e.text)));
    assert.ok(akt.eintraege.some((e) => e.art === 'admin' && /ausgeschaltet/.test(e.text)));
    assert.ok(!JSON.stringify(akt).includes(PW));
    ok('Senden, Uebergabe, Ein- und Ausschalten stehen im Aktivitaetsprotokoll');

    assert.deepStrictEqual(jsFehler, [], 'JavaScript-Fehler: ' + jsFehler.join(' | '));
    console.log('Alle Eingabe-Tests bestanden');
  } catch (e) {
    console.error('FEHLER:', e.message);
    process.exitCode = 1;
  } finally {
    server.kill();
    await browser.close();
  }
})();
