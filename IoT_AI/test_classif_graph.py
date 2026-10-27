import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    balanced_accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    matthews_corrcoef,
    cohen_kappa_score,
    roc_curve,
    auc
)

from sklearn.preprocessing import label_binarize

from hydration_classifier import (
    CLASS_NAMES,
    build_features,
    load_model,
    parse_timestamp,
)


# ==========================================================
# 1. CARICAMENTO DATASET E MODELLO
# ==========================================================

df = pd.read_csv("sipwise_test_dataset.csv")
model = load_model()

# Conversione dei campi numerici
for col in ["waterGoal", "temperature", "waterDrunk", "age", "weight"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

X_test = []
timestamps = []

# Ricostruzione delle feature dai dati grezzi
for _, row in df.iterrows():

    when = parse_timestamp(row["timestamp"], row["created_at"])

    timestamps.append(when)

    hour = (
        when.hour
        + when.minute / 60.0
        + when.second / 3600.0
    )

    X_test.append(
        build_features(
            row["waterGoal"],
            row["temperature"],
            row["waterDrunk"],
            hour,
            row["sex"],
            row["age"],
            row["weight"]
        )
    )


# ==========================================================
# 2. PREDIZIONE
# ==========================================================

y_true = df["label"].values
y_pred = model.predict(X_test)

labels = [0, 1, 2]
class_names = [CLASS_NAMES[i] for i in labels]

df["pred"] = y_pred
df["timestamp_plot"] = pd.to_datetime(timestamps, errors="coerce")


# ==========================================================
# 3. REPORT DI CLASSIFICAZIONE
# ==========================================================

print("\n" + "=" * 60)
print("       REPORT DI CLASSIFICAZIONE SUL DATASET DI TEST")
print("=" * 60)

print(
    classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=class_names,
        zero_division=0
    )
)


# ==========================================================
# 4. METRICHE GENERALI DEL MODELLO
# ==========================================================

accuracy = accuracy_score(y_true, y_pred)

balanced_accuracy = balanced_accuracy_score(y_true, y_pred)

precision = precision_score(
    y_true, y_pred,
    average="weighted",
    zero_division=0
)

recall = recall_score(
    y_true, y_pred,
    average="weighted",
    zero_division=0
)

f1 = f1_score(
    y_true, y_pred,
    average="weighted",
    zero_division=0
)

mcc = matthews_corrcoef(y_true, y_pred)

kappa = cohen_kappa_score(y_true, y_pred)


print("\n" + "=" * 60)
print("             METRICHE GENERALI DEL MODELLO")
print("=" * 60)

print(f"Accuracy:           {accuracy:.4f}")
print(f"Balanced Accuracy:  {balanced_accuracy:.4f}")
print(f"Precision:          {precision:.4f}")
print(f"Recall:             {recall:.4f}")
print(f"F1-Score:           {f1:.4f}")
print(f"Matthews Corrcoef:  {mcc:.4f}")
print(f"Cohen Kappa:        {kappa:.4f}")


# ==========================================================
# 5. CONFUSION MATRIX
# ==========================================================

cm = confusion_matrix(
    y_true,
    y_pred,
    labels=labels
)

plt.figure(figsize=(8, 6))

sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=class_names,
    yticklabels=class_names
)

plt.title("Confusion Matrix")
plt.xlabel("Predicted Class")
plt.ylabel("Real Class")
plt.tight_layout()
plt.show()


# ==========================================================
# 6. CONFUSION MATRIX NORMALIZZATA
# ==========================================================

cm_normalized = confusion_matrix(
    y_true,
    y_pred,
    labels=labels,
    normalize="true"
)

plt.figure(figsize=(8, 6))

sns.heatmap(
    cm_normalized,
    annot=True,
    fmt=".2%",
    cmap="Greens",
    xticklabels=class_names,
    yticklabels=class_names,
    vmin=0,
    vmax=1
)

plt.title("Confusion Matrix Normalizzata (%)")
plt.xlabel("Classe Predetta")
plt.ylabel("Classe Reale")
plt.tight_layout()
plt.show()


# ==========================================================
# 7. PRECISION, RECALL E F1-SCORE PER CLASSE
# ==========================================================

report = classification_report(
    y_true,
    y_pred,
    labels=labels,
    target_names=class_names,
    output_dict=True,
    zero_division=0
)

metrics_df = pd.DataFrame({
    "Precision": [
        report[name]["precision"] for name in class_names
    ],
    "Recall": [
        report[name]["recall"] for name in class_names
    ],
    "F1-Score": [
        report[name]["f1-score"] for name in class_names
    ]
}, index=class_names)

print("\nMETRICHE PER CLASSE:")
print(metrics_df.round(4))

metrics_df.plot(
    kind="bar",
    figsize=(10, 6),
    ylim=(0, 1.05),
    width=0.8
)

plt.title("Precision, Recall e F1-Score per Classe")
plt.ylabel("Punteggio")
plt.xlabel("Classe")
plt.xticks(rotation=0)
plt.legend(loc="lower right")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()


# ==========================================================
# 8. DISTRIBUZIONE CLASSI REALI VS PREDIZIONI
# ==========================================================

real_counts = pd.Series(y_true).value_counts().reindex(
    labels, fill_value=0
)

pred_counts = pd.Series(y_pred).value_counts().reindex(
    labels, fill_value=0
)

distribution_df = pd.DataFrame({
    "Real": real_counts.values,
    "Predicted": pred_counts.values
}, index=class_names)

distribution_df.plot(
    kind="bar",
    figsize=(9, 6),
    width=0.8
)

plt.title("Class Distribution: Real vs Predicted")
plt.ylabel("Number of elements")
plt.xlabel("Class")
plt.xticks(rotation=0)
plt.legend()
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()


# ==========================================================
# 9. CURVE ROC MULTICLASSE
# ==========================================================

if hasattr(model, "predict_proba"):

    model_classes = list(model.classes_)

    if all(c in model_classes for c in labels):

        probabilities = model.predict_proba(X_test)

        # Riordina le probabilità secondo le classi 0, 1, 2
        probabilities = probabilities[
            :, [model_classes.index(c) for c in labels]
        ]

        y_binary = label_binarize(y_true, classes=labels)

        plt.figure(figsize=(9, 7))

        plotted = False

        for i, name in enumerate(class_names):

            # Una curva ROC richiede esempi positivi e negativi
            if len(np.unique(y_binary[:, i])) < 2:
                continue

            fpr, tpr, _ = roc_curve(
                y_binary[:, i],
                probabilities[:, i]
            )

            roc_auc = auc(fpr, tpr)

            plt.plot(
                fpr,
                tpr,
                label=f"{name} (AUC = {roc_auc:.3f})"
            )

            plotted = True

        if plotted:
            plt.plot(
                [0, 1],
                [0, 1],
                linestyle="--",
                label="Classificatore casuale"
            )

            plt.title("Curve ROC Multiclasse")
            plt.xlabel("False Positive Rate")
            plt.ylabel("True Positive Rate")
            plt.legend()
            plt.grid(alpha=0.3)
            plt.tight_layout()
            plt.show()


# ==========================================================
# 10. PREPARAZIONE DATI PER I GRAFICI TEMPORALI
# ==========================================================

df_plot = (
    df.dropna(subset=["timestamp_plot"])
      .sort_values("timestamp_plot")
      .copy()
)

df_plot["hydration_pct"] = (
    df_plot["waterDrunk"]
    / df_plot["waterGoal"].replace(0, np.nan)
) * 100

df_plot["label_name"] = df_plot["label"].map(
    {i: CLASS_NAMES[i] for i in labels}
)


# ==========================================================
# 11. CONSUMO DI ACQUA NEL TEMPO
# ==========================================================

if not df_plot.empty:

    plt.figure(figsize=(14, 6))

    plt.plot(
        df_plot["timestamp_plot"],
        df_plot["waterDrunk"],
        marker="o",
        label="Water Drunk"
    )

    plt.plot(
        df_plot["timestamp_plot"],
        df_plot["waterGoal"],
        linestyle="--",
        label="Daily Goal"
    )

    plt.title("Trends in Water Consumption Over Time")
    plt.xlabel("Date and hour")
    plt.ylabel("Water (ml)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()


# ==========================================================
# 12. ANDAMENTO PERCENTUALE IDRATAZIONE
# ==========================================================

if not df_plot.empty:

    plt.figure(figsize=(14, 6))

    plt.plot(
        df_plot["timestamp_plot"],
        df_plot["hydration_pct"],
        marker="o",
        alpha=0.6,
        label="Idratazione (%)"
    )

    # Media mobile su 5 campioni
    moving_average = df_plot["hydration_pct"].rolling(
        window=5,
        min_periods=1
    ).mean()

    plt.plot(
        df_plot["timestamp_plot"],
        moving_average,
        linewidth=2,
        label="Media mobile (5 campioni)"
    )

    plt.axhline(
        y=100,
        linestyle="--",
        label="Obiettivo raggiunto (100%)"
    )

    plt.title("Andamento Percentuale di Idratazione")
    plt.xlabel("Data e ora")
    plt.ylabel("Idratazione (%)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()


# ==========================================================
# 13. ANDAMENTO DELLA TEMPERATURA
# ==========================================================

if not df_plot.empty:

    plt.figure(figsize=(14, 6))

    plt.plot(
        df_plot["timestamp_plot"],
        df_plot["temperature"],
        marker="o",
        label="Temperatura"
    )

    plt.title("Andamento Temperatura nel Tempo")
    plt.xlabel("Data e ora")
    plt.ylabel("Temperatura (°C)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()


# ==========================================================
# 14. TEMPERATURA VS IDRATAZIONE
# ==========================================================

if not df_plot.empty:

    plt.figure(figsize=(10, 7))

    sns.scatterplot(
        data=df_plot,
        x="temperature",
        y="hydration_pct",
        hue="label_name",
        s=100
    )

    plt.title("Relazione tra Temperatura e Idratazione")
    plt.xlabel("Temperatura (°C)")
    plt.ylabel("Idratazione (%)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()


# ==========================================================
# 15. VERIFICA DEI PRIMI 15 CASI LIMITE
# ==========================================================

print("\n" + "=" * 60)
print("           VERIFICA DEI PRIMI 15 CASI LIMITE")
print("=" * 60)

for _, r in df.head(15).iterrows():

    esito = "OK" if r["label"] == r["pred"] else "ERR"

    print(
        f"[{esito}] {r['timestamp']} | "
        f"{r['waterDrunk']:4.0f}/{r['waterGoal']:4.0f} ml "
        f"({r['temperature']:4.1f}°C) -> "
        f"Atteso: {r['label']} | "
        f"Predetto: {r['pred']} | "
        f"{r['scenario']}"
    )


print("\nValutazione completata.")