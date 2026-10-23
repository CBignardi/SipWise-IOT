import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from hydration_classifier import (
    CLASS_NAMES,
    build_features,
    load_model,
    parse_timestamp,
)

# 1. Carica il dataset di test e il modello
df = pd.read_csv("sipwise_test_dataset.csv")
model = load_model()

# 2. Ricostruisce le feature partendo solo dai campi grezzi (come farebbe da ThingSpeak)
X_test = []
for _, row in df.iterrows():
    when = parse_timestamp(row["timestamp"], row["created_at"])
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    X_test.append(
        build_features(
            row["waterGoal"], row["temperature"], row["waterDrunk"],
            hour, row["sex"], row["age"], row["weight"]
        )
    )

# 3. Predizione e valutazione
y_true = df["label"].values
y_pred = model.predict(X_test)

print("=== REPORT DI CLASSIFICAZIONE SUL DATASET DI TEST ===")
print(classification_report(
    y_true, y_pred,
    target_names=[CLASS_NAMES[i] for i in range(3)]
))

print("=== MATRICE DI CONFUSIONE ===")
print(confusion_matrix(y_true, y_pred))

# 4. Verifica dei primi 15 casi limite curati
df["pred"] = y_pred
print("\n=== VERIFICA DEI PRIMI 15 CASI LIMITE ===")
for _, r in df.head(15).iterrows():
    esito = "OK" if r["label"] == r["pred"] else "ERR"
    print(f"[{esito}] {r['timestamp']} | {r['waterDrunk']:4d}/{r['waterGoal']} ml "
          f"({r['temperature']:4.1f}°C) -> Atteso: {r['label']} | Predetto: {r['pred']} | {r['scenario']}")