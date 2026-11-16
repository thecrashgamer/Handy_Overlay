// Alle Projekte der Python-Werkstatt.
// Neues Projekt? Einfach einen weiteren Eintrag in PROJECTS ergänzen.
// Code steht in String.raw`...`, damit Backslashes (z. B. \n) erhalten bleiben.

const SANDBOX = {
  id: "sandbox",
  icon: "🧪",
  title: "Freie Sandkiste",
  level: "Frei",
  summary: "Hier gibt es keine Aufgaben. Probiere aus, was du willst.",
  concepts: [],
  steps: [{
    title: "Los geht's",
    text: "<p>Schreibe beliebigen Python-Code und drücke <b>Strg+Enter</b>.</p>",
    code: String.raw`# Hier gehört dir alles.
print("Hallo Welt!")
`,
    hint: "Fang klein an: Eine Zeile, ausführen, schauen was passiert.",
  }],
  ideas: ["Baue ein eigenes Spiel.", "Rechne etwas aus, das dich interessiert.", "Lass den Computer eine Geschichte erzählen."],
};

const PROJECTS = [
  {
    id: "hallo",
    icon: "👋",
    title: "Hallo, ich bin dein Computer",
    level: "Einsteiger",
    summary: "Dein erstes Programm: Text ausgeben, Namen merken, den Nutzer begrüßen.",
    concepts: ["print", "Variablen", "input", "f-Strings"],
    steps: [
      {
        title: "Text ausgeben",
        text: `<p>Mit <code>print()</code> schreibt Python etwas auf den Bildschirm. Text steht in Anführungszeichen.</p>
               <div class="task">Drücke <b>▶ Ausführen</b>. Ändere dann den Text und führe es nochmal aus.</div>`,
        code: String.raw`print("Hallo Welt!")
print("Ich lerne Python.")
`,
        hint: "Jede Zeile mit print() erzeugt eine eigene Zeile in der Ausgabe.",
      },
      {
        title: "Variablen: Dinge merken",
        text: `<p>Eine <b>Variable</b> ist eine Schublade mit Namen. Du legst etwas hinein und holst es später wieder heraus.</p>
               <p>Mit <code>f"..."</code> kannst du Variablen in Text einbauen: <code>{name}</code>.</p>
               <div class="task">Setze deinen eigenen Namen und dein Alter ein.</div>`,
        code: String.raw`name = "Alex"
alter = 12

print(f"Ich heiße {name}.")
print(f"Nächstes Jahr bin ich {alter + 1}.")
`,
        hint: "Zahlen stehen ohne Anführungszeichen, Text mit.",
      },
      {
        title: "Fragen stellen",
        text: `<p><code>input()</code> wartet, bis der Nutzer etwas eingibt. Das Ergebnis ist immer Text.</p>
               <div class="task">Frage zusätzlich nach der Lieblingsfarbe und sage etwas Passendes dazu.</div>`,
        code: String.raw`name = input("Wie heißt du? ")
print(f"Schön dich zu treffen, {name}!")

# Deine Erweiterung:
`,
        hint: "farbe = input(\"Lieblingsfarbe? \") und dann print(f\"{farbe} ist toll!\")",
      },
    ],
    ideas: ["Baue einen Steckbrief mit 5 Fragen.", "Lass den Computer dich mit einem Reim begrüßen.", "Frag nach dem Alter und rechne aus, in welchem Jahr du 18 wirst (Tipp: int(...))."],
  },

  {
    id: "zahlenraten",
    icon: "🎯",
    title: "Zahlenraten",
    level: "Einsteiger",
    summary: "Der Computer denkt sich eine Zahl aus. Du rätst, bis du sie hast.",
    concepts: ["random", "if / else", "while", "int()"],
    steps: [
      {
        title: "Eine Zahl auswürfeln",
        text: `<p>Das Modul <code>random</code> kann würfeln. <code>randint(1, 10)</code> gibt eine Zahl von 1 bis 10.</p>
               <div class="task">Führe den Code mehrmals aus. Ändere den Bereich auf 1 bis 100.</div>`,
        code: String.raw`import random

geheim = random.randint(1, 10)
print("Ich habe mir eine Zahl ausgedacht.")
print("(Schummeln:", geheim, ")")
`,
        hint: "Der Bereich steht in den Klammern: randint(untere, obere).",
      },
      {
        title: "Ein Rateversuch",
        text: `<p><code>input()</code> liefert Text. Mit <code>int(...)</code> machst du daraus eine Zahl. Dann vergleichst du mit <code>if</code> / <code>elif</code> / <code>else</code>.</p>`,
        code: String.raw`import random

geheim = random.randint(1, 10)
tipp = int(input("Dein Tipp (1-10): "))

if tipp == geheim:
    print("Treffer! 🎉")
elif tipp < geheim:
    print("Zu klein.")
else:
    print("Zu groß.")
`,
        hint: "Achtung: == vergleicht, = speichert in eine Variable. Die eingerückten Zeilen gehören zum if.",
      },
      {
        title: "Raten bis es klappt",
        text: `<p>Eine <code>while</code>-Schleife wiederholt Code, solange eine Bedingung stimmt. Wir zählen die Versuche mit.</p>
               <div class="task">Begrenze die Versuche auf 5. Danach verliert man und die Zahl wird verraten.</div>`,
        code: String.raw`import random

geheim = random.randint(1, 20)
versuche = 0
tipp = 0

while tipp != geheim:
    tipp = int(input("Dein Tipp (1-20): "))
    versuche += 1
    if tipp < geheim:
        print("Zu klein.")
    elif tipp > geheim:
        print("Zu groß.")

print(f"Geschafft in {versuche} Versuchen!")
`,
        hint: "Ändere die Bedingung zu: while tipp != geheim and versuche < 5 – und prüfe danach, ob tipp == geheim.",
      },
    ],
    ideas: ["Lass den Nutzer den Zahlenbereich wählen.", "Gib Schwierigkeitsgrade: leicht, mittel, schwer.", "Drehe es um: Du denkst dir eine Zahl und der Computer rät (Tipp: halbiere den Bereich)."],
  },

  {
    id: "madlibs",
    icon: "📖",
    title: "Verrückte Geschichten",
    level: "Einsteiger",
    summary: "Sammle Wörter vom Nutzer und baue eine lustige Geschichte daraus.",
    concepts: ["Strings", "f-Strings", "Methoden wie .upper()", "random.choice"],
    steps: [
      {
        title: "Wörter sammeln",
        text: `<p>Du fragst nach Wörtern und baust sie in eine Vorlage ein.</p>`,
        code: String.raw`tier = input("Ein Tier: ")
ort = input("Ein Ort: ")
essen = input("Ein Essen: ")

print()
print(f"Gestern ging ein {tier} nach {ort}.")
print(f"Dort aß es ganz allein {essen}.")
`,
        hint: "print() ohne Inhalt macht eine Leerzeile.",
      },
      {
        title: "Mit Text spielen",
        text: `<p>Texte haben eingebaute Werkzeuge: <code>.upper()</code>, <code>.lower()</code>, <code>.title()</code>, <code>.replace()</code>, <code>len()</code>.</p>
               <div class="task">Probiere jedes Werkzeug auf dem Tiernamen aus.</div>`,
        code: String.raw`tier = input("Ein Tier: ")

print(tier.upper())
print(tier.title())
print(tier * 3)
print("Dein Tier hat", len(tier), "Buchstaben")
print(tier.replace("e", "3"))
`,
        hint: "Mit * kannst du Text wiederholen.",
      },
      {
        title: "Zufällige Geschichte",
        text: `<p><code>random.choice(liste)</code> zieht ein zufälliges Element aus einer Liste. So wird jede Geschichte anders.</p>
               <div class="task">Füge weitere Einträge in die Listen ein oder erfinde eine neue Liste.</div>`,
        code: String.raw`import random

helden = ["ein Drache", "eine Katze", "ein Roboter"]
orte = ["im Supermarkt", "auf dem Mond", "in der Schule"]
taten = ["tanzte", "verlor seine Socken", "backte einen Kuchen"]

print(f"Es war einmal {random.choice(helden)} {random.choice(orte)}.")
print(f"Plötzlich {random.choice(taten)} es!")
`,
        hint: "Listen schreibst du mit eckigen Klammern, Einträge mit Komma getrennt.",
      },
    ],
    ideas: ["Erzeuge eine ganze Geschichte mit 5 Sätzen.", "Frage zuerst nach dem Namen und mach den Nutzer zum Helden.", "Baue einen Zufalls-Beleidigungs-Generator (Shakespeare-Style)."],
  },

  {
    id: "rechner",
    icon: "🧮",
    title: "Taschenrechner",
    level: "Einsteiger",
    summary: "Rechne mit Zahlen und baue dein erstes eigenes Werkzeug aus Funktionen.",
    concepts: ["Zahlen", "Funktionen", "def / return", "Rechenzeichen"],
    steps: [
      {
        title: "Rechnen",
        text: `<p>Python rechnet mit <code>+ - * /</code>. Dazu <code>**</code> (hoch), <code>//</code> (ganzzahlig teilen), <code>%</code> (Rest).</p>`,
        code: String.raw`print(7 + 3)
print(7 / 2)
print(7 // 2)
print(7 % 2)
print(2 ** 10)
`,
        hint: "Der Rest (%) zeigt zum Beispiel, ob eine Zahl gerade ist: zahl % 2 == 0.",
      },
      {
        title: "Eine eigene Funktion",
        text: `<p>Mit <code>def</code> baust du dir eigene Befehle. <code>return</code> gibt ein Ergebnis zurück.</p>
               <div class="task">Schreibe <code>mal(a, b)</code> und <code>minus(a, b)</code> dazu.</div>`,
        code: String.raw`def plus(a, b):
    return a + b

print(plus(3, 4))
print(plus(10, 25))
`,
        hint: "def mal(a, b):  ⏎  (4 Leerzeichen)return a * b",
      },
      {
        title: "Der ganze Rechner",
        text: `<p>Jetzt kombinieren wir alles: Der Nutzer wählt eine Rechenart.</p>
               <div class="task">Ergänze „hoch“ (<code>**</code>) und fange die Division durch 0 ab.</div>`,
        code: String.raw`def rechne(a, op, b):
    if op == "+":
        return a + b
    elif op == "-":
        return a - b
    elif op == "*":
        return a * b
    elif op == "/":
        return a / b
    else:
        return "Das kenne ich nicht."

a = float(input("Erste Zahl: "))
op = input("Rechenzeichen (+ - * /): ")
b = float(input("Zweite Zahl: "))

print("Ergebnis:", rechne(a, op, b))
`,
        hint: "Vor der Division prüfen: if b == 0: return \"Durch 0 geht nicht!\"",
      },
    ],
    ideas: ["Lass den Rechner in einer Schleife laufen, bis man „ende“ tippt.", "Baue einen Trinkgeld-Rechner.", "Rechne °C in °F um (F = C × 9/5 + 32)."],
  },

  {
    id: "sps",
    icon: "✂️",
    title: "Schere, Stein, Papier",
    level: "Einsteiger+",
    summary: "Spiele gegen den Computer und führe Punkte-Buch.",
    concepts: ["Listen", "Bedingungen", "Schleifen", "Punktestand"],
    steps: [
      {
        title: "Der Computer wählt",
        text: `<p>Der Computer zieht zufällig aus einer Liste.</p>`,
        code: String.raw`import random

wahl = ["Schere", "Stein", "Papier"]
computer = random.choice(wahl)
print("Computer:", computer)
`,
        hint: "random.choice(liste) gibt dir ein zufälliges Element.",
      },
      {
        title: "Wer gewinnt?",
        text: `<p>Wir prüfen alle Fälle. Schere schlägt Papier, Papier schlägt Stein, Stein schlägt Schere.</p>
               <div class="task">Baue noch „Echse“ und „Spock“ dazu und erweitere die Regeln.</div>`,
        code: String.raw`import random

wahl = ["Schere", "Stein", "Papier"]
schlaegt = {"Schere": "Papier", "Papier": "Stein", "Stein": "Schere"}

ich = input("Schere, Stein oder Papier? ").capitalize()
computer = random.choice(wahl)
print("Computer:", computer)

if ich == computer:
    print("Unentschieden.")
elif schlaegt.get(ich) == computer:
    print("Du gewinnst! 🎉")
else:
    print("Computer gewinnt.")
`,
        hint: "schlaegt ist ein Dictionary: Schlüssel schlägt Wert. So brauchst du keine 6 einzelnen Fälle.",
      },
      {
        title: "Best of Many",
        text: `<p>Spiele in einer Schleife und zähle die Siege beider Seiten.</p>`,
        code: String.raw`import random

wahl = ["Schere", "Stein", "Papier"]
schlaegt = {"Schere": "Papier", "Papier": "Stein", "Stein": "Schere"}
du, pc = 0, 0

while du < 3 and pc < 3:
    ich = input("Schere, Stein oder Papier? ").capitalize()
    if ich not in wahl:
        print("Das gibt es nicht.")
        continue
    computer = random.choice(wahl)
    print("Computer:", computer)
    if ich == computer:
        print("Unentschieden.")
    elif schlaegt[ich] == computer:
        du += 1
        print("Punkt für dich!")
    else:
        pc += 1
        print("Punkt für den Computer.")
    print(f"Stand: {du}:{pc}")

print("Du hast gewonnen! 🏆" if du == 3 else "Der Computer hat gewonnen.")
`,
        hint: "continue springt sofort zur nächsten Runde der Schleife.",
      },
    ],
    ideas: ["Lass den Computer klüger spielen: Er merkt sich, was du oft wählst.", "Speichere die Statistik aller Spiele.", "Baue ein Turnier mit „Best of 5“ und Namen."],
  },

  {
    id: "quiz",
    icon: "❓",
    title: "Dein eigenes Quiz",
    level: "Einsteiger+",
    summary: "Baue ein Quiz zu deinem Lieblingsthema, mit Punkten und Auswertung.",
    concepts: ["Listen", "Dictionaries", "for-Schleife", "Auswertung"],
    steps: [
      {
        title: "Eine Frage",
        text: `<p>Wir speichern Frage und Antwort und vergleichen die Eingabe.</p>`,
        code: String.raw`frage = "Wie heißt die Hauptstadt von Frankreich?"
antwort = "paris"

eingabe = input(frage + " ")
if eingabe.lower() == antwort:
    print("Richtig!")
else:
    print("Leider falsch.")
`,
        hint: ".lower() macht alles klein, so zählt auch „PARIS“ als richtig.",
      },
      {
        title: "Viele Fragen",
        text: `<p>Mit einer <b>Liste von Dictionaries</b> hältst du alle Fragen zusammen. Die <code>for</code>-Schleife geht sie durch.</p>
               <div class="task">Schreibe 5 Fragen zu deinem Lieblingsthema (Fußball, Minecraft, Tiere, …).</div>`,
        code: String.raw`fragen = [
    {"frage": "Wie viele Beine hat eine Spinne?", "antwort": "8"},
    {"frage": "Welcher Planet ist der Sonne am nächsten?", "antwort": "merkur"},
    {"frage": "Wie viel ist 6 mal 7?", "antwort": "42"},
]

punkte = 0
for f in fragen:
    eingabe = input(f["frage"] + " ")
    if eingabe.strip().lower() == f["antwort"]:
        print("Richtig! ✅")
        punkte += 1
    else:
        print("Falsch. ❌ Richtig wäre:", f["antwort"])

print(f"Du hast {punkte} von {len(fragen)} Punkten.")
`,
        hint: "Eine neue Frage ist ein neues {...}-Paar in der Liste. Vergiss das Komma nicht.",
      },
      {
        title: "Zufall und Auswertung",
        text: `<p>Mische die Fragen mit <code>random.shuffle</code> und gib eine Note aus.</p>`,
        code: String.raw`import random

fragen = [
    {"frage": "Wie viele Beine hat eine Spinne?", "antwort": "8"},
    {"frage": "Welcher Planet ist der Sonne am nächsten?", "antwort": "merkur"},
    {"frage": "Wie viel ist 6 mal 7?", "antwort": "42"},
]
random.shuffle(fragen)

punkte = 0
for f in fragen:
    if input(f["frage"] + " ").strip().lower() == f["antwort"]:
        punkte += 1

anteil = punkte / len(fragen)
if anteil == 1:
    print("Perfekt! 🏆")
elif anteil >= 0.5:
    print("Ganz gut!")
else:
    print("Übe noch ein bisschen.")
`,
        hint: "Ergänze zu jeder Frage eine Liste mit Alternativ-Antworten und prüfe mit „in“.",
      },
    ],
    ideas: ["Multiple Choice mit A/B/C/D.", "Mehrere Schwierigkeitsstufen.", "Bestenliste: Frage nach dem Namen und zeige die besten Ergebnisse."],
  },

  {
    id: "passwort",
    icon: "🔐",
    title: "Passwort-Generator",
    level: "Einsteiger+",
    summary: "Erzeuge sichere Passwörter und prüfe, wie stark ein Passwort ist.",
    concepts: ["string-Modul", "Schleifen", "Funktionen", "join"],
    steps: [
      {
        title: "Zufällige Zeichen",
        text: `<p>Das Modul <code>string</code> kennt Buchstaben und Ziffern. <code>random.choice</code> zieht eins, und <code>"".join(...)</code> klebt alles zusammen.</p>`,
        code: String.raw`import random
import string

zeichen = string.ascii_letters + string.digits
passwort = "".join(random.choice(zeichen) for _ in range(12))
print(passwort)
`,
        hint: "range(12) bestimmt die Länge. Mach daraus eine Variable.",
      },
      {
        title: "Als Funktion",
        text: `<p>Packe es in eine Funktion mit Parametern für Länge und Sonderzeichen.</p>
               <div class="task">Erlaube dem Nutzer, die Länge selbst zu wählen.</div>`,
        code: String.raw`import random
import string

def passwort(laenge=12, sonderzeichen=True):
    zeichen = string.ascii_letters + string.digits
    if sonderzeichen:
        zeichen += "!?#$%&*+-"
    return "".join(random.choice(zeichen) for _ in range(laenge))

for _ in range(5):
    print(passwort(16))
`,
        hint: "laenge = int(input(\"Wie lang? \"))",
      },
      {
        title: "Stärke prüfen",
        text: `<p>Wir geben Punkte für Länge und Zeichenarten.</p>
               <div class="task">Zeige zusätzlich an, was fehlt (z. B. „Es fehlt eine Zahl“).</div>`,
        code: String.raw`def staerke(pw):
    punkte = 0
    if len(pw) >= 8:
        punkte += 1
    if len(pw) >= 12:
        punkte += 1
    if any(c.isdigit() for c in pw):
        punkte += 1
    if any(c.isupper() for c in pw):
        punkte += 1
    if any(not c.isalnum() for c in pw):
        punkte += 1
    return ["sehr schwach", "schwach", "ok", "gut", "stark", "sehr stark"][punkte]

pw = input("Passwort zum Testen: ")
print("Stärke:", staerke(pw))
`,
        hint: "any(...) ist wahr, wenn mindestens ein Zeichen die Bedingung erfüllt.",
      },
    ],
    ideas: ["Generiere Passphrasen aus 4 zufälligen Wörtern.", "Zeige, wie viele Kombinationen es gibt (Länge hoch Zeichenzahl).", "Verbiete häufige Passwörter wie „123456“."],
  },

  {
    id: "muster",
    icon: "🎨",
    title: "Muster aus Zeichen",
    level: "Einsteiger+",
    summary: "Male Dreiecke, Pyramiden und Schachbretter mit Schleifen.",
    concepts: ["for", "range", "verschachtelte Schleifen", "String-Multiplikation"],
    steps: [
      {
        title: "Ein Dreieck",
        text: `<p>Text mal Zahl wiederholt den Text. Mit einer Schleife wächst das Dreieck.</p>`,
        code: String.raw`for zeile in range(1, 8):
    print("*" * zeile)
`,
        hint: "range(1, 8) zählt 1, 2, … 7.",
      },
      {
        title: "Pyramide",
        text: `<p>Eine Pyramide braucht erst Leerzeichen, dann Sterne.</p>
               <div class="task">Mach die Höhe einstellbar und probiere andere Zeichen als <code>*</code>.</div>`,
        code: String.raw`hoehe = 6
for i in range(hoehe):
    leer = " " * (hoehe - i - 1)
    sterne = "*" * (2 * i + 1)
    print(leer + sterne)
`,
        hint: "Tausche \"*\" gegen \"🌲\" – aber dann brauchst du doppelt so viele Leerzeichen.",
      },
      {
        title: "Schachbrett",
        text: `<p>Zwei Schleifen ineinander: außen die Zeilen, innen die Felder.</p>`,
        code: String.raw`for zeile in range(8):
    text = ""
    for spalte in range(8):
        if (zeile + spalte) % 2 == 0:
            text += "⬛"
        else:
            text += "⬜"
    print(text)
`,
        hint: "Das % 2 wechselt zwischen 0 und 1 und sorgt für das Muster.",
      },
    ],
    ideas: ["Zeichne eine Raute (Pyramide + umgekehrte Pyramide).", "Male eine Weihnachtsbaum mit Stamm.", "Das große Einmaleins als schöne Tabelle."],
  },

  {
    id: "wuerfel",
    icon: "🎲",
    title: "Würfel-Labor",
    level: "Fortgeschritten",
    summary: "Würfle tausende Male und schau dir die Verteilung als Balkendiagramm an.",
    concepts: ["Dictionaries", "Zählen", "Statistik", "Text-Diagramme"],
    steps: [
      {
        title: "Zwei Würfel",
        text: `<p>Wir würfeln zweimal und addieren.</p>`,
        code: String.raw`import random

a = random.randint(1, 6)
b = random.randint(1, 6)
print(f"{a} + {b} = {a + b}")
`,
        hint: "Mit a == b erkennst du einen Pasch.",
      },
      {
        title: "1000 Würfe zählen",
        text: `<p>Ein Dictionary zählt, wie oft jede Augensumme vorkommt.</p>
               <div class="task">Ändere die Anzahl auf 100000. Was fällt dir auf?</div>`,
        code: String.raw`import random

zaehler = {}
for _ in range(1000):
    summe = random.randint(1, 6) + random.randint(1, 6)
    zaehler[summe] = zaehler.get(summe, 0) + 1

for summe in sorted(zaehler):
    print(summe, zaehler[summe])
`,
        hint: "zaehler.get(summe, 0) gibt 0 zurück, wenn der Schlüssel noch fehlt.",
      },
      {
        title: "Balkendiagramm",
        text: `<p>Wir drucken Balken aus Zeichen. Jeder Block steht für 10 Würfe.</p>
               <div class="task">Warum ist die 7 am häufigsten? Zähle nach, auf wie viele Arten man sie würfeln kann.</div>`,
        code: String.raw`import random

N = 3000
zaehler = {}
for _ in range(N):
    summe = random.randint(1, 6) + random.randint(1, 6)
    zaehler[summe] = zaehler.get(summe, 0) + 1

for summe in range(2, 13):
    anzahl = zaehler.get(summe, 0)
    balken = "█" * (anzahl // 10)
    print(f"{summe:>2} | {balken} {anzahl}")
`,
        hint: "Die 7 geht über 1+6, 2+5, 3+4, 4+3, 5+2, 6+1: das sind 6 Möglichkeiten, bei der 2 nur eine.",
      },
    ],
    ideas: ["Simuliere 3 Würfel.", "Wie oft dauert es, bis eine 6 kommt? Mittelwert über 10000 Versuche.", "Münzwurf: Wie lang kann eine Serie werden?"],
  },
];
