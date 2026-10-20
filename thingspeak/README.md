# ThingSpeak Client

Client da riga di comando per leggere e inviare dati ai canali ThingSpeak tramite le operazioni `GET` e `POST`.

## Indice

- [Parametri](#1-parametri)
- [Operazioni GET e POST](#2-operazioni-get-e-post)
- [Riepilogo dei canali](#3-riepilogo-dei-canali)
- [Gestione degli errori e controlli](#4-gestione-degli-errori-e-controlli)
- [Risposte a schermo](#5-risposte-a-schermo)

## 1. Parametri

Il programma accetta i seguenti parametri da riga di comando:

| Parametro | Obbligatorio | Descrizione |
|---|---|---|
| `<CANALE>` | Sì | Canale ThingSpeak su cui eseguire l'operazione. I valori ammessi sono `DATA`, `TREND` e `HUMAN`. |
| `<METODO>` | Sì | Operazione da eseguire: `GET` per leggere i dati oppure `POST` per inviare un nuovo dato. |
| `<VALORE>` | Solo per `POST` | Valore numerico da inviare al campo `field1`. Se omesso, il programma invia `0` per impostazione predefinita. |

### Sintassi generale

```bash
./thingspeak_client <CANALE> <METODO> [VALORE]
```

## 2. Operazioni GET e POST

### 2.1 Lettura dei dati (`GET`)

L'operazione `GET` interroga il canale ThingSpeak selezionato e restituisce in formato JSON il feed più recente disponibile.

Il programma utilizza automaticamente l'URL di lettura preconfigurato per il canale scelto. Tale URL include la chiave API di sola lettura e il parametro `results=1`, che limita la risposta all'ultimo dato disponibile.

**Sintassi:**

```bash
./thingspeak_client <CANALE> GET
```

**Esempio:**

```bash
./thingspeak_client DATA GET
```

Questo comando legge l'ultimo feed disponibile del canale `DATA`.

### 2.2 Invio dei dati (`POST`)

L'operazione `POST` invia un nuovo valore numerico al canale ThingSpeak selezionato, associandolo al campo `field1`.

Il programma invia una richiesta HTTP `POST` all'endpoint di aggiornamento:

```text
https://api.thingspeak.com/update
```

I dati della richiesta (`postData`) includono:
1. La chiave API di scrittura specifica del canale selezionato.
2. Il valore numerico fornito da riga di comando, associato al parametro `field1`.

**Sintassi:**

```bash
./thingspeak_client <CANALE> POST <VALORE_DA_INVIARE>
```

**Esempi:**

```bash
./thingspeak_client TREND POST 23.5
./thingspeak_client HUMAN POST 1
```

I comandi inviano rispettivamente `23.5` e `1` al campo `field1` dei canali `TREND` e `HUMAN`.

Se il valore viene omesso durante una chiamata `POST`, il programma invia `0` per impostazione predefinita.

## 3. Riepilogo dei canali

| Canale | Operazione `GET` (lettura) | Operazione `POST` (scrittura) |
|---|---|---|
| `DATA` | Legge l'ultimo dato dal canale ID `3201982`. | Invia un valore a `field1` usando la chiave API di scrittura del canale `DATA`. |
| `TREND` | Legge l'ultimo dato dal canale ID `3273136`. | Invia un valore a `field1` usando la chiave API di scrittura del canale `TREND`. |
| `HUMAN` | Legge l'ultimo dato dal canale ID `3287534`. | Invia un valore a `field1` usando la chiave API di scrittura del canale `HUMAN`. |

Le chiavi API sono configurate nel programma e vengono selezionate automaticamente in base al canale indicato.

## 4. Gestione degli errori e controlli

Il programma esegue alcuni controlli preliminari per ridurre gli errori durante l'esecuzione.

### Parametri mancanti o insufficienti

Se il programma viene avviato senza gli argomenti necessari, stampa una guida rapida con la sintassi corretta.

### Canale non valido

Sono accettati esclusivamente i canali `DATA`, `TREND` e `HUMAN`. Ad esempio:

```bash
./thingspeak_client PROVA GET
```

produce il seguente errore:

```text
Errore: Canale 'PROVA' non valido! Scegli tra DATA, TREND, HUMAN.
```

### Metodo non valido

I metodi supportati sono esclusivamente `GET` e `POST`. Se viene specificato un metodo diverso, come `PUT` o `DELETE`, il programma interrompe l'operazione e segnala un errore.

## 5. Risposte a schermo

### Risposta a una chiamata `GET`

Il programma stampa il payload JSON restituito da ThingSpeak, contenente i dettagli del canale e del feed più recente disponibile.

### Risposta a una chiamata `POST`

Il programma stampa l'ID progressivo della nuova entry creata. Ad esempio:

```text
124
```

Se il valore restituito è `0`, l'aggiornamento non è riuscito. Una possibile causa è il mancato rispetto dell'intervallo minimo tra aggiornamenti previsto da ThingSpeak: nei piani gratuiti, normalmente è necessario attendere almeno 15 secondi tra due aggiornamenti.

---

## Note

- `<CANALE>` e `<METODO>` devono essere sostituiti con i valori supportati indicati in questa documentazione.
- `<VALORE>` è un dato numerico destinato al campo `field1` ed è necessario per specificare il valore da inviare con `POST`.
- Le chiavi API di lettura e scrittura sono gestite dal programma in base al canale selezionato.
