// Phonebox-Mod: fragt alle 2 Sekunden die Phonebox auf diesem PC (127.0.0.1) nach einer Anweisung vom Handy
// und schickt sie als normale Nachricht in diese Claude-Sitzung. Das klappt auch, wenn Claude gerade fertig ist.
const BASIS = 'http://127.0.0.1:8000'
const GRUND_GESTOPPT = 'nobody has sent input since'
const GRUND_ENTFERNT = 'removed from the queue'

// Text, der nach einem Abbruch (Esc/Stop) nicht gesendet werden konnte: wird nach dem naechsten Zug erneut versucht
let offen = null
let laeuft = false

async function versuchen($, text, alsNutzer) {
  try {
    const r = await $.prompt.submit(alsNutzer ? { text, asUser: true } : { text })
    return { grund: (r && r.drop) || '', fehler: '' }
  } catch (f) {
    return { grund: '', fehler: String((f && f.message) || f) }
  }
}

async function senden($, text) {
  // Erst als eigene Nachricht des Nutzers; klappt das nicht, mit dem Hinweis "von der Phonebox"
  let e = await versuchen($, text, true)
  if ((e.grund || e.fehler) && !(e.grund + e.fehler).includes(GRUND_GESTOPPT) && !(e.grund + e.fehler).includes(GRUND_ENTFERNT)) {
    $.ui.log('Anweisung vom Handy: erster Versuch fehlgeschlagen (' + (e.grund || e.fehler).slice(0, 120) + '), zweiter Versuch ...')
    e = await versuchen($, 'Nachricht vom Handy des Nutzers (über die Phonebox): ' + text, false)
  }
  const grund = e.grund || e.fehler
  if (!grund) return
  if (grund.includes(GRUND_GESTOPPT) || grund.includes(GRUND_ENTFERNT)) {
    offen = text
    $.ui.log('Anweisung vom Handy wartet: Die Sitzung wurde gestoppt. Sie wird nach dem nächsten Zug zugestellt.')
  } else {
    $.ui.log('Anweisung vom Handy konnte nicht zugestellt werden: ' + grund.slice(0, 200))
  }
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    let sid = ''
    let cwd = ''
    try { sid = String(await $.session.id()) } catch (_) {}
    try { cwd = String(await $.session.cwd()) } catch (_) {}
    $.clock.every(2000, async () => {
      if (laeuft) return
      laeuft = true
      try {
        const r = await $.http.fetch(BASIS + '/api/claude/mod/abholen', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-phonebox': '1' },
          body: JSON.stringify({ session_id: sid, cwd }),
        })
        if (r.status === 200) {
          const d = JSON.parse(r.text || '{}')
          if (d.text) {
            $.ui.log('Vom Handy: ' + String(d.text).slice(0, 80))
            senden($, d.text) // nicht abwarten: wartet, bis Claude Zeit hat
          }
        }
      } catch (_) {
        // Phonebox aus oder nicht erreichbar: still weiter versuchen
      } finally {
        laeuft = false
      }
    })
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (offen !== null && !e.agentId) {
      const t = offen
      offen = null
      senden($, t)
    }
    return next(e)
  })
}
