#!/usr/bin/env python3
"""
Classificatore delle abitudini idriche (SipWise / Borraccia Smart)
-------------------------------------------------------------------
1. Legge gli ultimi dati della borraccia da ThingSpeak (canale DATI)
2. Legge i dati personali dell'utente da ThingSpeak (canale UTENTE)
3. Classifica il comportamento con un modello di machine learning
4. Invia la classe con una POST al canale TREND (field1) solo per nuovi dati

Classi (le stesse usate dall'app MIT in selectTrendText):
    0 = "You're doing well!"
    1 = "It could be better."
    2 = "You need to improve!"

Uso:
    python hydration_classifier.py              # inferenza + POST
    python hydration_classifier.py --dry-run    # inferenza senza POST
    python hydration_classifier.py --loop 60    # ripete ogni 60 s (solo nuovi dati)
    python hydration_classifier.py --train      # riaddestra il modello
"""

import argparse
import math
import os
import re
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
#  CONFIGURAZIONE (con supporto variabili d'ambiente)
# ============================================================
DATA_URL = "https://api.thingspeak.com/channels/3201982/feeds.json"
DATA_READ_KEY = os.getenv("TS_DATA_READ_KEY", "PJBB45HC2Q7ZHLC0")

HUMAN_URL = "https://api.thingspeak.com/channels/3287534/feeds.json"
HUMAN_READ_KEY = os.getenv("TS_HUMAN_READ_KEY", "F4DPXNVX3OTXOVFJ")

UPDATE_URL = "https://api.thingspeak.com/update"
UPDATE_WRITE_KEY = os.getenv("TS_UPDATE_WRITE_KEY", "I4VYATTE7GLX1YW3")

DATA_FIELDS = {
    "waterGoal": "field1",
    "timestamp": "field2",
    "temperature": "field3",
    "waterDrunk": "field4",
}
HUMAN_FIELDS = {
    "sex": "field1",     # nell'app: 1 = Male, 0 = Female
    "weight": "field2",  # kg
    "age": "field3",     # anni
}

RESULTS = 10                         # scarica più righe per tollerare invii parziali
LOCAL_TZ = ZoneInfo("Europe/Rome")   # fuso locale per i timestamp
MODEL_PATH = "hydration_model.joblib"
WAKE_START, WAKE_END = 7.0, 22.0     # fascia oraria attiva (07:00 - 22:00)
NIGHT_RESET_HOUR = 4.0               # prima delle 04:00 conta come fine giornata precedente

CLASS_NAMES = {
    0: "You're doing well!",
    1: "It could be better.",
    2: "You need to improve!",
}

FEATURES = [
    "waterGoal", "temperature", "waterDrunk", "hour", "sex",
    "age", "weight", "recGoal", "progress", "expected", "pace"
]


# ============================================================
#  FEATURE ENGINEERING
# ============================================================
def normalize_hour(hour: float) -> float:
    """
    Gestisce gli orari dopo la mezzanotte (es. 00:30 -> 24.5)
    così non vengono confusi con il mattino presto prima della sveglia.
    """
    return hour + 24.0 if hour < NIGHT_RESET_HOUR else hour


def expected_progress(hour: float) -> float:
    """Frazione dell'obiettivo che dovrebbe essere già stata bevuta a quest'ora."""
    adj_hour = normalize_hour(hour)
    return float(np.clip((adj_hour - WAKE_START) / (WAKE_END - WAKE_START), 0.0, 1.0))


def recommended_goal(weight: float, age: float, sex: int, temp: float) -> float:
    """
    Stima il fabbisogno idrico giornaliero consigliato (ml) in base a
    peso, età, sesso e temperatura ambientale.
    """
    base_per_kg = 35.0 if age < 55 else (32.0 if age < 70 else 28.0)
    sex_offset = 200.0 if sex == 1 else 0.0
    heat_bonus = max(float(temp) - 25.0, 0.0) * 25.0
    return float(np.clip(weight * base_per_kg + sex_offset + heat_bonus, 1200.0, 4500.0))


def build_features(goal, temp, drunk, hour, sex, age, weight):
    """Costruisce il vettore di feature nell'ordine di FEATURES."""
    goal = max(float(goal), 500.0)
    rec_goal = recommended_goal(weight, age, sex, temp)
    # Obiettivo effettivo: tiene conto sia del goal utente sia del fabbisogno biologico
    effective_goal = 0.7 * goal + 0.3 * rec_goal
    expected = expected_progress(hour)
    progress = float(drunk) / effective_goal
    pace = progress / max(expected, 0.12)   # >1 = in anticipo, <1 = in ritardo
    return [
        goal, float(temp), float(drunk), float(hour), int(sex),
        float(age), float(weight), rec_goal, progress, expected, pace
    ]


# ============================================================
#  MODELLO
# ============================================================
def rule_label(goal, temp, drunk, hour, sex, age, weight):
    """
    Etichetta euristica per generare il dataset di addestramento.
    Evita salti bruschi al mattino usando anche il deficit assoluto in ml.
    """
    adj_hour = normalize_hour(hour)
    if adj_hour < WAKE_START + 0.75:
        return 0

    f = build_features(goal, temp, drunk, hour, sex, age, weight)
    rec_goal = f[7]
    expected = f[9]
    pace = f[10]

    effective_goal = 0.7 * max(float(goal), 500.0) + 0.3 * rec_goal
    deficit_ml = (effective_goal * expected) - float(drunk)

    # Se mancano meno di 200 ml (circa un bicchiere), l'utente è in regola
    if deficit_ml <= 200.0:
        return 0

    heat_strictness = 0.08 if temp > 28.0 else 0.0
    if pace >= 0.88 + heat_strictness:
        return 0
    if pace >= 0.58 + heat_strictness or deficit_ml <= 450.0:
        return 1
    return 2


def make_training_data(n=10000, seed=42):
    """Genera dati sintetici realistici su tutte le 24 ore."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for _ in range(n):
        sex = int(rng.integers(0, 2))
        age = int(rng.integers(12, 85))
        weight = float(np.clip(rng.normal(78 if sex else 63, 13), 38, 130))
        temp = float(np.clip(rng.normal(21, 7.5), -2, 42))
        hour = float(rng.uniform(0.0, 24.0))

        rec = recommended_goal(weight, age, sex, temp)
        # L'utente imposta un goal vicino a quello consigliato, ma con possibili scostamenti
        goal = float(np.clip(rec + rng.normal(0, 250), 1000, 4500))

        habit = rng.choice([1.05, 0.75, 0.40], p=[0.40, 0.35, 0.25])
        exp = expected_progress(hour)
        share = np.clip(exp * habit * rng.normal(1.0, 0.12) + rng.normal(0.0, 0.03), 0.0, 1.35)
        drunk = round(goal * share)

        label = rule_label(goal, temp, drunk, hour, sex, age, weight)
        if rng.random() < 0.03:  # leggero rumore
            label = int(np.clip(label + rng.choice([-1, 1]), 0, 2))

        X.append(build_features(goal, temp, drunk, hour, sex, age, weight))
        y.append(label)
    return np.array(X), np.array(y)


def train_model(path=MODEL_PATH):
    X, y = make_training_data()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=200, min_samples_leaf=3, random_state=42, n_jobs=-1
    )
    model.fit(X_tr, y_tr)
    print(classification_report(
        y_te, model.predict(X_te),
        target_names=[CLASS_NAMES[i] for i in range(3)]
    ))
    joblib.dump(model, path)
    print(f"Modello salvato in {path}")
    return model


def load_model(path=MODEL_PATH):
    if os.path.exists(path):
        model = joblib.load(path)
        # Se il vecchio modello salvato aveva un numero diverso di feature, riaddestra
        if getattr(model, "n_features_in_", None) == len(FEATURES):
            return model
        print("Schema feature aggiornato: riaddestro il modello...")
    else:
        print("Modello non trovato: lo addestro...")
    return train_model(path)


# ============================================================
#  THINGSPEAK
# ============================================================
def to_float(value, min_val=None, max_val=None):
    """Converte un valore ThingSpeak in float valido e finito, altrimenti None."""
    if value is None:
        return None
    try:
        val = float(str(value).strip().replace(",", "."))
        if not math.isfinite(val):
            return None
        if min_val is not None and val < min_val:
            return None
        if max_val is not None and val > max_val:
            return None
        return val
    except (TypeError, ValueError):
        return None


def parse_sex(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("1", "1.0", "m", "male", "maschio"):
        return 1
    if text in ("0", "0.0", "f", "female", "femmina"):
        return 0
    return None


def parse_timestamp(raw, created_at):
    """
    Ricava data/ora locale (sempre timezone-aware).
    Pulisce spazi Unicode speciali (es. \u202f) generati da Android/MIT App Inventor.
    """
    if raw:
        text = re.sub(r"[\s\u202f\xa0]+", " ", str(raw).strip())
        text = re.sub(r"(?i)\ba\.?m\.?\b", "AM", text)
        text = re.sub(r"(?i)\bp\.?m\.?\b", "PM", text)
        for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=LOCAL_TZ)
            except ValueError:
                pass
    if created_at:
        try:
            dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
            return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(LOCAL_TZ)
        except ValueError:
            pass
    return None


def fetch_feeds(session, url, key, results=RESULTS):
    r = session.get(url, params={"api_key": key, "results": results}, timeout=15)
    r.raise_for_status()
    return r.json().get("feeds", [])


def latest_data(session):
    """Ultima riga valida del canale DATI (filtra anche errori tipici dei sensori)."""
    for feed in reversed(fetch_feeds(session, DATA_URL, DATA_READ_KEY)):
        goal = to_float(feed.get(DATA_FIELDS["waterGoal"]), min_val=100, max_val=10000)
        temp = to_float(feed.get(DATA_FIELDS["temperature"]), min_val=-20, max_val=60)
        drunk = to_float(feed.get(DATA_FIELDS["waterDrunk"]), min_val=0, max_val=15000)
        when = parse_timestamp(feed.get(DATA_FIELDS["timestamp"]), feed.get("created_at"))

        # Ignora il codice di errore 85.0 °C tipico del sensore DS18B20 appena acceso
        if temp == 85.0:
            continue

        if None not in (goal, temp, drunk, when):
            hour = when.hour + when.minute / 60.0 + when.second / 3600.0
            return {
                "entry_id": feed.get("entry_id"),
                "goal": goal,
                "temp": temp,
                "drunk": drunk,
                "hour": hour,
                "when": when,
            }
    raise RuntimeError("Nessuna riga valida nel canale DATI")


def latest_person(session):
    """Ultima riga valida del canale UTENTE."""
    for feed in reversed(fetch_feeds(session, HUMAN_URL, HUMAN_READ_KEY)):
        sex = parse_sex(feed.get(HUMAN_FIELDS["sex"]))
        weight = to_float(feed.get(HUMAN_FIELDS["weight"]), min_val=20, max_val=250)
        age = to_float(feed.get(HUMAN_FIELDS["age"]), min_val=5, max_val=120)
        if sex is not None and weight is not None and age is not None:
            return {"sex": sex, "weight": weight, "age": age}
    raise RuntimeError("Nessuna riga valida nel canale UTENTE")


def post_result(session, label):
    """POST del risultato su field1. ThingSpeak risponde con l'id della riga (0 = errore)."""
    r = session.post(
        UPDATE_URL,
        data={"api_key": UPDATE_WRITE_KEY, "field1": int(label)},
        timeout=15,
    )
    r.raise_for_status()
    entry_id = r.text.strip()
    if entry_id == "0":
        raise RuntimeError(
            "ThingSpeak ha rifiutato l'update (limite di 15 s tra due scritture)"
        )
    return entry_id


# ============================================================
#  MAIN
# ============================================================
def run_once(session, model, dry_run=False, last_entry_id=None, force=False):
    data = latest_data(session)

    if not force and last_entry_id is not None and data["entry_id"] == last_entry_id:
        print(f"[entry_id={data['entry_id']}] Nessun nuovo dato dalla borraccia, salto POST.")
        return None, last_entry_id

    person = latest_person(session)
    x = build_features(
        data["goal"], data["temp"], data["drunk"], data["hour"],
        person["sex"], person["age"], person["weight"]
    )
    label = int(model.predict([x])[0])
    proba = model.predict_proba([x])[0]
    confidence = proba[list(model.classes_).index(label)]

    print(
         "\n"
        f"[{data['when']:%d/%m/%Y %H:%M}] drunk {data['drunk']:.0f}/"
        f"{data['goal']:.0f} ml (suggested: {x[7]:.0f} ml), {data['temp']:.1f} °C | "
        f"{'M' if person['sex'] else 'F'}, {person['age']:.0f} years old, "
        f"{person['weight']:.0f} kg"
    )
    print(f"→ class {label}: {CLASS_NAMES[label]} (confidence {confidence:.0%})")

    if dry_run:
        print("(dry-run: no data sent)")
    else:
        post_id = post_result(session, label)
        print(f"POST send successfully, trend entry_id = {post_id}")
        
    print("\n")

    return label, data["entry_id"]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--train", action="store_true", help="riaddestra e salva il modello")
    ap.add_argument("--dry-run", action="store_true", help="non invia la POST")
    ap.add_argument("--force", action="store_true", help="invia POST anche se il dato non è cambiato")
    ap.add_argument("--loop", type=int, metavar="SEC", help="ripete ogni SEC secondi (minimo 15)")
    args = ap.parse_args()

    model = train_model() if args.train else load_model()

    with requests.Session() as session:
        if not args.loop:
            run_once(session, model, dry_run=args.dry_run, force=True)
            return

        last_entry_id = None
        sleep_sec = max(args.loop, 15)
        print(f"Avvio monitoraggio continuo ogni {sleep_sec}s (Ctrl+C per terminare)...")
        try:
            while True:
                try:
                    _, last_entry_id = run_once(
                        session, model,
                        dry_run=args.dry_run,
                        last_entry_id=last_entry_id,
                        force=args.force
                    )
                except Exception as e:
                    print(f"Errore: {e}")
                time.sleep(sleep_sec)
        except KeyboardInterrupt:
            print("\nMonitoraggio interrotto dall'utente.")


if __name__ == "__main__":
    main()