// Phonebox-Mod: fragt alle 2 Sekunden die Phonebox auf diesem PC (127.0.0.1) nach einer Anweisung vom Handy
// und schickt sie als normale Nachricht in diese Claude-Sitzung. Das klappt auch, wenn Claude gerade fertig ist.
const BASIS = 'http://127.0.0.1:8000'
const GRUND_GESTOPPT = 'nobody has sent input since'
const GRUND_ENTFERNT = 'removed from the queue'

// Text, der nach einem Abbruch (Esc/Stop) nicht gesendet werden konnte: wird nach dem naechsten Zug erneut versucht
let offen = null
let laeuft = false

async function senden($, text) {
  let grund = ''
  try {
    const r = await $.prompt.submit({ text, asUser: true })
    grund = (r && r.drop) || ''
  } catch (f) {
    grund = String((f && f.message) || f)
  }
  if (grund.includes(GRUND_GESTOPPT) || grund.includes(GRUND_ENTFERNT)) offen = text
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
