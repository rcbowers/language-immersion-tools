#!/usr/bin/env python3
"""Create Spanish output training Anki cards via AnkiConnect.

Tenses covered: imperfect subjunctive, present perfect subjunctive,
pluperfect subjunctive, future, future perfect, conditional, conditional perfect.
"""

import json
import sys
import urllib.error
import urllib.request

ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "spanish output"
MODEL_NAME = "Basic"
TAGS = ["spanish", "output", "subjunctive", "preterite", "imperfect", "future", "conditional"]

# (front_html, back_html) — verbs bolded on both sides
CARDS = [
    # --- Imperfect subjunctive ---
    (
        "I <b>wanted</b> you to <b>come</b> earlier.",
        "<b>Quería</b> que <b>vinieras</b> más temprano.",
    ),
    (
        "It was important that they <b>knew</b> the truth.",
        "Era importante que <b>supieran</b> la verdad.",
    ),
    (
        "If I <b>had</b> more money, I <b>would travel</b> more.",
        "Si <b>tuviera</b> más dinero, <b>viajaría</b> más.",
    ),
    (
        "If she <b>were</b> here, she <b>would help</b> us.",
        "Si ella <b>estuviera</b> aquí, nos <b>ayudaría</b>.",
    ),
    (
        "I <b>doubted</b> that he <b>could</b> do it.",
        "<b>Dudaba</b> que él <b>pudiera</b> hacerlo.",
    ),
    (
        "They <b>asked</b> that we <b>leave</b> immediately.",
        "<b>Pidieron</b> que <b>saliéramos</b> inmediatamente.",
    ),
    (
        "I <b>was</b> happy that you <b>came</b>.",
        "Me <b>alegraba</b> que <b>vinieras</b>.",
    ),
    (
        "I <b>feared</b> that they might <b>get lost</b>.",
        "<b>Temía</b> que se <b>perdieran</b>.",
    ),
    (
        "We <b>recommended</b> that she <b>speak</b> with the manager.",
        "<b>Recomendamos</b> que <b>hablara</b> con el gerente.",
    ),
    (
        "It <b>bothered</b> me that he was always late.",
        "Me <b>molestaba</b> que él siempre <b>llegara</b> tarde.",
    ),
    (
        "I'm <b>looking for</b> someone who <b>knows</b> Japanese.",
        "<b>Busco</b> a alguien que <b>sepa</b> japonés.",
    ),
    (
        "There was no one who <b>could help</b> us.",
        "No había nadie que <b>pudiera ayudarnos</b>.",
    ),
    (
        "If I <b>were</b> you, I <b>wouldn't do</b> that.",
        "Si yo <b>fuera</b> tú, no <b>haría</b> eso.",
    ),
    (
        "Even if it <b>were</b> true, I <b>wouldn't believe</b> it.",
        "Aunque <b>fuera</b> verdad, no lo <b>creería</b>.",
    ),
    # --- Pluperfect subjunctive ---
    (
        "If we <b>had studied</b> more, we <b>would have passed</b>.",
        "Si <b>hubiéramos estudiado</b> más, <b>habríamos aprobado</b>.",
    ),
    (
        "If I <b>had known</b>, I <b>would have told</b> you.",
        "Si lo <b>hubiera sabido</b>, te lo <b>habría dicho</b>.",
    ),
    (
        "I <b>wish</b> you <b>had called</b> me.",
        "Ojalá me <b>hubieras llamado</b>.",
    ),
    (
        "It was strange that she <b>had said</b> that.",
        "Era extraño que ella <b>hubiera dicho</b> eso.",
    ),
    (
        "I didn't <b>think</b> they <b>had arrived</b> yet.",
        "No <b>creía</b> que <b>hubieran llegado</b> todavía.",
    ),
    (
        "I <b>doubted</b> that she <b>had understood</b> the instructions.",
        "<b>Dudaba</b> que ella <b>hubiera entendido</b> las instrucciones.",
    ),
    (
        "I <b>would have liked</b> for you to <b>come</b> with us.",
        "Me <b>habría gustado</b> que <b>vinieras</b> con nosotros.",
    ),
    (
        "If they <b>had seen</b> the problem earlier, they <b>could have fixed</b> it.",
        "Si <b>hubieran visto</b> el problema antes, <b>habrían podido arreglarlo</b>.",
    ),
    # --- Present perfect subjunctive ---
    (
        "I <b>hope</b> that you <b>have had</b> a good trip.",
        "<b>Espero</b> que <b>hayas tenido</b> un buen viaje.",
    ),
    (
        "I don't <b>think</b> he <b>has finished</b> yet.",
        "No <b>creo</b> que <b>haya terminado</b> todavía.",
    ),
    (
        "It's possible that they <b>have forgotten</b>.",
        "Es posible que <b>hayan olvidado</b>.",
    ),
    # --- Future ---
    (
        "Next year, we <b>will live</b> in Spain.",
        "El próximo año, <b>viviremos</b> en España.",
    ),
    (
        "Will you <b>come</b> with us tomorrow?",
        "¿<b>Vendrás</b> con nosotros mañana?",
    ),
    (
        "She will probably <b>know</b> the answer.",
        "Ella probablemente <b>sabrá</b> la respuesta.",
    ),
    (
        "If it <b>rains</b> tomorrow, we <b>won't go</b>.",
        "Si <b>llueve</b> mañana, no <b>iremos</b>.",
    ),
    (
        "When you <b>arrive</b>, <b>call</b> me.",
        "Cuando <b>llegues</b>, <b>llámame</b>.",
    ),
    (
        "After we <b>finish</b> eating, we <b>will leave</b>.",
        "Después de que <b>terminemos</b> de comer, <b>saldremos</b>.",
    ),
    (
        "As soon as he <b>sees</b> it, he <b>will understand</b>.",
        "En cuanto lo <b>vea</b>, lo <b>entenderá</b>.",
    ),
    (
        "When I <b>finish</b> my degree, I <b>will work</b> in aerospace engineering.",
        "Cuando <b>termine</b> mi carrera, <b>trabajaré</b> en ingeniería aeroespacial.",
    ),
    # --- Future perfect ---
    (
        "By tomorrow, I <b>will have finished</b> the project.",
        "Para mañana, <b>habré terminado</b> el proyecto.",
    ),
    (
        "By the time you <b>arrive</b>, they will already <b>have eaten</b>.",
        "Para cuando <b>llegues</b>, ya <b>habrán comido</b>.",
    ),
    # --- Conditional ---
    (
        "I <b>would buy</b> that car if I <b>had</b> enough money.",
        "<b>Compraría</b> ese coche si <b>tuviera</b> suficiente dinero.",
    ),
    (
        "Would you <b>help</b> me if I <b>asked</b> you?",
        "¿Me <b>ayudarías</b> si te lo <b>pidiera</b>?",
    ),
    (
        "She <b>said</b> she <b>would come</b> later.",
        "Ella <b>dijo</b> que <b>vendría</b> más tarde.",
    ),
    # --- Conditional perfect ---
    (
        "We <b>would have gone</b> if we <b>had had</b> time.",
        "<b>Habríamos ido</b> si <b>hubiéramos tenido</b> tiempo.",
    ),
    (
        "He would never <b>have done</b> that.",
        "Él nunca <b>habría hecho</b> eso.",
    ),
]


def invoke(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        ANKI_CONNECT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"Cannot reach AnkiConnect at {ANKI_CONNECT_URL}: {exc}")
        print("Make sure Anki is open and the AnkiConnect add-on is installed.")
        sys.exit(1)
    if result.get("error") is not None:
        raise RuntimeError(f"AnkiConnect error: {result['error']}")
    return result["result"]


def add_note(front: str, back: str) -> int | None:
    return invoke(
        "addNote",
        note={
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {"Front": front, "Back": back},
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            "tags": TAGS,
        },
    )


def main() -> None:
    print(f"Connecting to AnkiConnect at {ANKI_CONNECT_URL}...")
    invoke("createDeck", deck=DECK_NAME)
    print(f"Deck '{DECK_NAME}' ready. Adding {len(CARDS)} cards...\n")

    added = skipped = errors = 0
    for i, (front, back) in enumerate(CARDS, 1):
        preview = front.replace("<b>", "").replace("</b>", "")[:55]
        try:
            note_id = add_note(front, back)
            if note_id is None:
                print(f"  [{i:02d}] SKIP (duplicate): {preview}")
                skipped += 1
            else:
                print(f"  [{i:02d}] OK   (id={note_id}): {preview}")
                added += 1
        except RuntimeError as exc:
            print(f"  [{i:02d}] ERR: {exc}")
            errors += 1

    print(f"\nDone: {added} added, {skipped} skipped (duplicates), {errors} errors.")


if __name__ == "__main__":
    main()
