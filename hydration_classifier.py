#!/usr/bin/env python3
"""
Classificatore delle abitudini idriche (SipWise / Borraccia Smart)
-------------------------------------------------------------------
1. Legge gli ultimi dati della borraccia da ThingSpeak (canale DATI)
2. Legge i dati personali dell'utente da ThingSpeak (canale UTENTE)
3. Classifica il comportamento con un modello di machine learning
4. Invia la classe con una POST al canale TREND (field1)

Classi (le stesse usate dall'app MIT in selectTrendText):
    0 = "You're doing well!"
    1 = "It could be better."
    2 = "You need to improve!"

Uso:
    python hydration_classifier.py              # inferenza + POST
    python hydration_classifier.py --dry-run    # inferenza senza POST
    python hydration_classifier.py --loop 60    # ripete ogni 60 s
    python hydration_classifier.py --train      # riaddestra il modello

Dipendenze:
    pip install requests scikit-learn numpy joblib
"""

import argparse
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

# ============================================================
#  CONFIGURAZIONE
# ============================================================
# Canale DATI (borraccia)
DATA_URL = "https://api.thingspeak.com/channels/3201982/feeds.json"
DATA_READ_KEY = "PJBB45HC2Q7ZHLC0"
# Canale UTENTE (sesso, peso, età)
HUMAN_URL = "https://api.thingspeak.com/channels/3287534/feeds.json"
HUMAN_READ_KEY = "F4DPXNVX3OTXOVFJ"
# Canale TREND (dove si scrive il risultato)
UPDATE_URL = "https://api.thingspeak.com/update"
UPDATE_WRITE_KEY = "I4VYATTE7GLX1YW3"

# Associazione nome feature -> campo ThingSpeak (da correggere se serve)
DATA_FIELDS = {
    "waterGoal": "field2",
    "timestamp": "field3",
    "temperature": "field4",
    "waterDrunk": "field5",
}
HUMAN_FIELDS = {
    "sex": "field2",     # nell'app: 1 = Male, 0 = Female
    "weight": "field3",  # kg
    "age": "field4",     # anni
}

RESULTS = 2                          # quante righe scaricare
LOCAL_TZ = ZoneInfo("Europe/Rome")   # fuso per created_at (che è in UTC)
MODEL_PATH = "hydration_model.joblib"
WAKE_START, WAKE_END = 7.0, 22.0     # ore della giornata in cui si beve

CLASS_NAMES = {
    0: "You're doing well!",
    1: "It could be better.",
    2: "You need to improve!",
}

FEATURES = ["waterGoal", "temperature", "waterDrunk", "hour", "sex",
            "age", "weight", "progress", "expected", "pace"]


# ============================================================
#  FEATURE ENGINEERING
# ============================================================
def expected_progress(hour: float) -> float:
    """Frazione dell'obiettivo che dovrebbe essere già stata bevuta a quest'ora."""
    return float(np.clip((hour - WAKE_START) / (WAKE_END - WAKE_START), 0.0, 1.0))


def build_features(goal, temp, drunk, hour, sex, age, weight):
    """Costruisce il vettore di feature nell'ordine di FEATURES."""
    goal = max(float(goal), 1.0)
    expected = expected_progress(hour)
    progress = float(drunk) / goal
    pace = progress / max(expected, 0.15)   # >1 = in anticipo, <1 = in ritardo
    return [goal, temp, drunk, hour, sex, age, weight, progress, expected, pace]


# ============================================================
#  MODELLO
# ============================================================
def rule_label(goal, temp, drunk, hour):
    """
    Etichetta euristica usata per generare i dati di addestramento.
    Al mattino presto non si giudica (classe 0); col caldo si è più severi.
    """
    if hour < WAKE_START + 1:
        return 0
    f = build_features(goal, temp, drunk, hour, 0, 0, 0)
    pace = f[-1]
    bonus = 0.1 if temp > 28 else 0.0
    if pace >= 0.9 + bonus:
        return 0
    if pace >= 0.6 + bonus:
        return 1
    return 2


def make_training_data(n=8000, seed=42):
    """
    Dati SINTETICI: non esiste ancora un dataset etichettato reale.
    Quando avrai dati veri (con una classe assegnata a mano), sostituisci
    questa funzione con il caricamento del tuo dataset.
    """
    rng = np.random.default_rng(seed)
    X, y = [], []
    for _ in range(n):
        sex = int(rng.integers(0, 2))
        age = int(rng.integers(10, 85))
        weight = float(np.clip(rng.normal(80 if sex else 65, 13), 35, 130))
        temp = float(np.clip(rng.normal(20, 8), -5, 42))
        hour = float(rng.uniform(6, 24))
        goal = float(np.clip(weight * 35 + max(temp - 25, 0) * 20
                             + rng.normal(0, 150), 1200, 4500))
        habit = rng.choice([1.05, 0.75, 0.40], p=[0.40, 0.35, 0.25])
        share = np.clip(expected_progress(hour) * habit * rng.normal(1, 0.12)
                        + rng.normal(0, 0.03), 0, 1.3)
        drunk = round(goal * share)

        label = rule_label(goal, temp, drunk, hour)
        if rng.random() < 0.04:                       # un po' di rumore
            label = int(np.clip(label + rng.choice([-1, 1]), 0, 2))

        X.append(build_features(goal, temp, drunk, hour, sex, age, weight))
        y.append(label)
    return np.array(X), np.array(y)


def train_model(path=MODEL_PATH):
    X, y = make_training_data()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=200, min_samples_leaf=3,
                                   random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)
    print(classification_report(y_te, model.predict(X_te),
                                target_names=[CLASS_NAMES[i] for i in range(3)]))
    joblib.dump(model, path)
    print(f"Modello salvato in {path}")
    return model


def load_model(path=MODEL_PATH):
    if os.path.exists(path):
        return joblib.load(path)
    print("Modello non trovato: lo addestro...")
    return train_model(path)


# ============================================================
#  THINGSPEAK
# ============================================================
def to_float(value):
    """Converte un valore ThingSpeak (stringa o None) in float, oppure None."""
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_sex(value):
    text = str(value).strip().lower()
    if text in ("1", "m", "male", "maschio"):
        return 1
    if text in ("0", "f", "female", "femmina"):
        return 0
    return None


def parse_timestamp(raw, created_at):
    """
    Ricava la data/ora locale. Il campo 'timestamp' scritto dall'app ha
    il formato 'dd/MM/yyyy hh:mm:ss a' (12 ore + AM/PM). Se non è leggibile
    si usa created_at di ThingSpeak (UTC), convertito nel fuso locale.
    """
    if raw:
        text = str(raw).strip().replace("a.m.", "AM").replace("p.m.", "PM")
        for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S",
                    "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
    if created_at:
        dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(LOCAL_TZ)
    return None


def fetch_feeds(url, key, results=RESULTS):
    r = requests.get(url, params={"api_key": key, "results": results}, timeout=15)
    r.raise_for_status()
    return r.json().get("feeds", [])


def latest_data():
    """Ultima riga valida del canale DATI."""
    for feed in reversed(fetch_feeds(DATA_URL, DATA_READ_KEY)):
        goal = to_float(feed.get(DATA_FIELDS["waterGoal"]))
        temp = to_float(feed.get(DATA_FIELDS["temperature"]))
        drunk = to_float(feed.get(DATA_FIELDS["waterDrunk"]))
        when = parse_timestamp(feed.get(DATA_FIELDS["timestamp"]),
                               feed.get("created_at"))
        if None not in (goal, temp, drunk, when):
            return {"goal": goal, "temp": temp, "drunk": drunk,
                    "hour": when.hour + when.minute / 60, "when": when}
    raise RuntimeError("Nessuna riga valida nel canale DATI")


def latest_person():
    """Ultima riga valida del canale UTENTE."""
    for feed in reversed(fetch_feeds(HUMAN_URL, HUMAN_READ_KEY)):
        sex = parse_sex(feed.get(HUMAN_FIELDS["sex"]))
        weight = to_float(feed.get(HUMAN_FIELDS["weight"]))
        age = to_float(feed.get(HUMAN_FIELDS["age"]))
        if sex is not None and weight and age:
            return {"sex": sex, "weight": weight, "age": age}
    raise RuntimeError("Nessuna riga valida nel canale UTENTE")


def post_result(label):
    """POST del risultato su field1. ThingSpeak risponde con l'id della riga (0 = errore)."""
    r = requests.post(UPDATE_URL,
                      data={"api_key": UPDATE_WRITE_KEY, "field1": int(label)},
                      timeout=15)
    r.raise_for_status()
    if r.text.strip() == "0":
        raise RuntimeError("ThingSpeak ha rifiutato l'update "
                           "(limite di 15 s tra due scritture?)")
    return r.text.strip()


# ============================================================
#  MAIN
# ============================================================
def run_once(model, dry_run=False):
    data = latest_data()
    person = latest_person()
    x = build_features(data["goal"], data["temp"], data["drunk"], data["hour"],
                       person["sex"], person["age"], person["weight"])
    label = int(model.predict([x])[0])
    proba = model.predict_proba([x])[0]
    confidence = proba[list(model.classes_).index(label)]

    print(f"[{data['when']:%d/%m/%Y %H:%M}] bevuti {data['drunk']:.0f}/"
          f"{data['goal']:.0f} ml, {data['temp']:.1f} °C | "
          f"{'M' if person['sex'] else 'F'}, {person['age']:.0f} anni, "
          f"{person['weight']:.0f} kg")
    print(f"→ classe {label}: {CLASS_NAMES[label]} (confidenza {confidence:.0%})")

    if dry_run:
        print("(dry-run: nessun invio)")
    else:
        print(f"POST inviata, entry id = {post_result(label)}")
    return label


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true", help="riaddestra e salva il modello")
    ap.add_argument("--dry-run", action="store_true", help="non invia la POST")
    ap.add_argument("--loop", type=int, metavar="SEC",
                    help="ripete ogni SEC secondi (minimo 15)")
    args = ap.parse_args()

    model = train_model() if args.train else load_model()

    if not args.loop:
        run_once(model, args.dry_run)
        return
    while True:
        try:
            run_once(model, args.dry_run)
        except Exception as e:                       # la rete può cadere: si riprova
            print(f"Errore: {e}")
        time.sleep(max(args.loop, 15))


if __name__ == "__main__":
    main()
