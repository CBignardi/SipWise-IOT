// ============================================================
//  LIBRARIES
// ============================================================
#include <Arduino.h>
#include <BluetoothSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <HX711.h>
#include <Adafruit_AHTX0.h>
#include <sys/time.h>


// ============================================================
//  PIN LAYOUT
// ============================================================

// Pin for the l'HX711 (load cell)
#define HX711_DOUT 16
#define HX711_SCK 4

// Pin fpr the shared bus I2C by MPU9250, AHT20 and the display
#define SDA_PIN 21
#define SCL_PIN 22


// ============================================================
//  SETTINGS DISPLAY OLED
// ============================================================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 32
#define OLED_RESET -1


// ============================================================
//  COSTANTS
// ============================================================

#define THRESHOLD_MOVEMENT_LOW 0.3f   // Soft movement
#define THRESHOLD_MOVEMENT_HIGH 1.5f  // Hard movement

#define WAIT_AFTER_MOV 2000UL   // 2 sec, wait after a big movement
#define INTERVAL_READ 10000UL   // 10 sec, interval between the mesurement
#define WAIT_AFTER_READ 5000UL  // 5 sec, wait for the visualizzation of the results


#define CALIBRATION_FACTOR 208.0f  // Calibration factor for the scale

#define WATERGOAL_STANDARD 2000.0f


// ============================================================
//  REGISTER MPU9250 (direct comunication I2C)
// ============================================================
#define MPU9250_ADDR 0x68
#define ACCEL_XOUT_H 0x3B
#define PWR_MGMT_1 0x6B

// ============================================================
//  GLOBAL OBJECT
// ============================================================
BluetoothSerial SerialBT;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
HX711 scale;
Adafruit_AHTX0 aht;

// ============================================================
//  VARIABLES
// ============================================================
float weightPerson_kg = 0.0f;
int agePerson = 0;

float weightBottle_g = 0.0f;
float weightStart_g = 0.0f;
float waterDrinked_ml = 0.0f;
float waterGoal_ml = 2000.0f;
bool goalAutoUpdate = true;  // true -> automatic update; false -> value defined by user

bool clockSynced = false;
int actualDay = -1;

bool btConnected = false;

struct Timer {
  unsigned long tsStart = 0;
  unsigned long delay_ = 0;

  void startTimer(unsigned long delay) {
    tsStart = millis();
    delay_ = delay;
  }

  bool isOver() {
    if (millis() - tsStart >= delay_) {
      return true;
    }
    return false;
  }
};

Timer timer;


// ============================================================
//  DEFINITION ENUM
// ============================================================

enum State {
  WAIT_CONNECTION,
  DISPLAY_CONNECTED,
  CHECK_MOVEMENT,
  AFTER_MOVEMENT,
  READING_IN_PROGRESS,
  SAVE_WEIGHT,
  WAIT_5_SEC,
  CMD_ARRIVED,
  REQUEST_TARE,
  TARE_MEASUREMENT,
  TARE_DISPLAY,
  GOAL_CHANGED
};

// Actual state
State state = WAIT_CONNECTION;
State prevState;


// ============================================================
//  DEFINITIONS OF THE FUNCTIONS
// ============================================================
void inizializeMPU9250();
float readAcceleration();
float calculateWaterGoal(float weight_kg, int age, float temp_C);
void updateDisplay(const char* r1, const char* r2 = "", const char* r3 = "");
void manageBT();
void sendStateBT();
void sendDailyWater(float ml);
void doTare();
time_t getEpochNow();
int getDayNumber(time_t epoch);
void checkReset24h();
void changeState(State newState);


// ============================================================
//  SETUP
// ============================================================
void setup() {

  Serial.begin(115200);

  // Initialize the bus I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // Initialize display OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED not find!");
    while (true)
      ;
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  updateDisplay("SipWise", "Starting...");
  delay(1000);

  // Initialize HX711
  scale.begin(HX711_DOUT, HX711_SCK);
  scale.set_scale(CALIBRATION_FACTOR);
  scale.tare();
  Serial.println("HX711 ready, tare done.");

  // Initialize AHT20
  if (!aht.begin()) {
    Serial.println("AHT20 not found!");
    updateDisplay("ERROR", "AHT20 not found");
    while (true)
      ;
  }
  Serial.println("AHT20 ready.");

  // Initialize MPU9250
  inizializeMPU9250();
  Serial.println("MPU9250 ready.");

  // Initialize Bluetooth
  SerialBT.begin("SipWise");
  SerialBT.setTimeout(100);
  Serial.println("BT started: 'SipWise'");

  changeState(WAIT_CONNECTION);
}


// ============================================================
//  LOOP
// ============================================================
void loop() {

  // Is something in the BT
  if (SerialBT.available()) {
    prevState = state;
    changeState(CMD_ARRIVED);
  }

  // manageBT();

  bool connected = SerialBT.connected();

  // Disconnection BT detected
  if (!connected && btConnected) {
    btConnected = false;
    Serial.println("Bluetooth disconnected.");
    changeState(WAIT_CONNECTION);
  }

  // Reset if we changed day
  if (clockSynced) {
    checkReset24h();
  }

  switch (state) {

    case WAIT_CONNECTION:
      // New connection BT detected
      if (connected && !btConnected) {
        btConnected = true;
        Serial.println("Bluetooth connected.");
        changeState(DISPLAY_CONNECTED);
      }
      break;

    case DISPLAY_CONNECTED:
      if (timer.isOver()) {
        changeState(CHECK_MOVEMENT);
      }
      break;


    case CHECK_MOVEMENT:
      {
        float acc = readAcceleration();

        //Serial.printf("DBG Movement: %.2f g\n", acc);

        if (acc > THRESHOLD_MOVEMENT_HIGH) {
          Serial.printf("Movement: %.2f g\n", acc);
          changeState(AFTER_MOVEMENT);

        } else if (acc > THRESHOLD_MOVEMENT_LOW) {
          timer.startTimer(INTERVAL_READ);  // Reset the timer for the reading

        } else {
          // Bottle not moving
          if (timer.isOver()) {
            changeState(READING_IN_PROGRESS);
          }
        }
        break;
      }


    case AFTER_MOVEMENT:
      if (timer.isOver()) {
        changeState(READING_IN_PROGRESS);
      }

      break;

    case READING_IN_PROGRESS:
      {
        float acc = readAcceleration();
        if (acc > THRESHOLD_MOVEMENT_LOW) {
          changeState(CHECK_MOVEMENT);
        } else {
          if (timer.isOver()) {
            changeState(SAVE_WEIGHT);
          }
        }
        break;
      }

    case SAVE_WEIGHT:
      {
        weightBottle_g = scale.get_units(5);

        if (weightBottle_g < 0) {
          weightBottle_g = 0;
        }

        // Calculate the water drinked
        float difference = weightStart_g - weightBottle_g;
        if (difference > 0) {
          waterDrinked_ml += difference;
        }
        weightStart_g = weightBottle_g;

        // Read the temperature and humidity
        sensors_event_t hum_ev, temp_ev;
        aht.getEvent(&hum_ev, &temp_ev);
        float tempC = temp_ev.temperature;
        float humidity = hum_ev.relative_humidity;

        // Calculate the water goal if it is specified
        if (goalAutoUpdate) {
          if (weightPerson_kg > 0 && agePerson > 0) {
            waterGoal_ml = calculateWaterGoal(weightPerson_kg, agePerson, tempC);
          } else {
            waterGoal_ml = WATERGOAL_STANDARD;
          }
        }

        // 3 rows for the display:
        //   Row 1: "Drink:XXX/YYYml"
        //   Row 2: "T:XX.XC H:XX%"
        //   Row 3: "Weight:XXXg"
        char r1[22], r2[22], r3[22];
        snprintf(r1, sizeof(r1), "Drink:%.0f/%.0fml", waterDrinked_ml, waterGoal_ml);
        snprintf(r2, sizeof(r2), "T:%.1fC H:%.0f%%", tempC, humidity);
        snprintf(r3, sizeof(r3), "Weight:%.0fg", weightBottle_g);
        updateDisplay(r1, r2, r3);

        // Send the report
        sendStateBT();

        // Log on the serial port
        Serial.printf("[Save] Weight:%.0fg | Water today:%.0f/%.0fml | T:%.1fC H:%.0f%%\n",
                      weightBottle_g, waterDrinked_ml, waterGoal_ml, tempC, humidity);

        changeState(WAIT_5_SEC);
        break;
      }


    case WAIT_5_SEC:
      if (timer.isOver()) {
        changeState(CHECK_MOVEMENT);
      }
      break;


    case CMD_ARRIVED:
      {
        String msg = SerialBT.readStringUntil('\n');
        msg.trim();

        // Log on the serial display
        Serial.printf("BT recived: %s\n", msg.c_str());

        // ── Command WEIGHT ──────────────────────────────────────────
        if (msg.startsWith("WEIGHT:")) {
          weightPerson_kg = msg.substring(7).toFloat();
          changeState(prevState);
        }

        // ── Command AGE ───────────────────────────────────────────
        else if (msg.startsWith("AGE:")) {
          agePerson = msg.substring(4).toInt();
          Serial.printf("Age: %d years old\n", agePerson);
          changeState(prevState);
        }

        // ── Command GOAL ─────────────────────────────────────
        else if (msg.startsWith("GOAL:")) {
          if (msg.substring(5, 6) == "0") {
            goalAutoUpdate = false;
            waterGoal_ml = msg.substring(7).toFloat();

          } else {
            goalAutoUpdate = true;
            sensors_event_t hum_ev, temp_ev;
            aht.getEvent(&hum_ev, &temp_ev);
            float tempC = temp_ev.temperature;
            waterGoal_ml = calculateWaterGoal(weightPerson_kg, agePerson, tempC);
          }
          SerialBT.println("OK:GOAL," + String(waterGoal_ml, 0));
          Serial.printf("Water goal: %.0f ml/day\n", waterGoal_ml);

          changeState(GOAL_CHANGED);
        }

        // ── Command TIME ──────────────────────────────────────────
        else if (msg.startsWith("TIME:")) {

          time_t epoch = (time_t)msg.substring(5).toDouble();

          // Sanity check: values Unix below 1.000.000.000 correspond to dates prior to September 2001 → almost certainly a data entry error
          if (epoch > 1000000000L) {
            struct timeval tv = { .tv_sec = epoch, .tv_usec = 0 };
            settimeofday(&tv, nullptr);

            clockSynced = true;
            actualDay = getDayNumber(epoch);
            SerialBT.println("OK:TIME");
            Serial.printf("RTC sincronized: epoch=%lld | day=%d\n", (long long)epoch, actualDay);
          } else {
            // Timestamp not valid
            SerialBT.println("ERR:TIME");
          }
          changeState(prevState);
        }

        // ── Command TARE ──────────────────────────────────────────
        else if (msg == "TARE") {
          changeState(REQUEST_TARE);
        }

        // ── Command SEND ─────────────────────────────────────────
        else if (msg == "SEND") {
          sendStateBT();
          changeState(prevState);
        }

        // ── Command SEND_DAY ───────────────────────────────────
        else if (msg == "SEND_DAY") {
          sendDailyWater(waterDrinked_ml);
          changeState(prevState);
        }
      }
      break;


    case REQUEST_TARE:
      if (timer.isOver()) {
        changeState(TARE_MEASUREMENT);
      }
      break;


    case TARE_MEASUREMENT:
      {
        float acc = readAcceleration();
        if (acc > THRESHOLD_MOVEMENT_LOW) {
          // The bottle is moving
          updateDisplay("Tare...", "Do not move the bottle!");
        } else {
          // The bottle is not moving
          doTare();
          changeState(TARE_DISPLAY);
        }
        break;
      }

    case TARE_DISPLAY:
      if (timer.isOver()) {
        changeState(CHECK_MOVEMENT);
      }
      break;


    case GOAL_CHANGED:
      if (timer.isOver()) {
        changeState(CHECK_MOVEMENT);
      }
      break;

    default:
      break;
  }
}


// ============================================================
//  FUNCTIONS
// ============================================================

void changeState(State newState) {
  state = newState;

  switch (newState) {

    case WAIT_CONNECTION:
      updateDisplay("Bluetooth", "Not connected", "Check app...");
      break;

    case DISPLAY_CONNECTED:
      timer.startTimer(2000UL);  // Start timer 2 sec
      updateDisplay("BT Connected!", "Starting...");
      break;

    case CHECK_MOVEMENT:
      timer.startTimer(INTERVAL_READ);  // Start the timer for the reading
      updateDisplay("");

      break;

    case AFTER_MOVEMENT:
      timer.startTimer(WAIT_AFTER_MOV);  // Set the timer for the interval before the reading
      updateDisplay("Movement detected", "Waiting...");
      break;

    case SAVE_WEIGHT:
      //updateDisplay("Reading weight now");
      break;

    case READING_IN_PROGRESS:
      timer.startTimer(2000UL);  // Set the timer for 2 s
      updateDisplay("Reading soon...");
      break;

    case WAIT_5_SEC:
      // Mantain the precedent display
      timer.startTimer(WAIT_AFTER_READ);  // Set the timer after the reading
      break;


    case REQUEST_TARE:
      timer.startTimer(1500UL);  // Set the timer to 1,5 sec
      updateDisplay("Tare requested", "Do not move!");
      break;

    case TARE_MEASUREMENT:
      updateDisplay("Checking...", "Hold it still!");
      break;

    case TARE_DISPLAY:
      timer.startTimer(2000UL);  // Start the timer for 2 sec
      updateDisplay("Tare done!");
      break;


    case GOAL_CHANGED:
      {
        timer.startTimer(1500UL);  // Start the timer for the display
        char r2[22];
        snprintf(r2, sizeof(r2), "%.0f ml/day", waterGoal_ml);
        updateDisplay("Goal:", r2);
        break;
      }


    default:
      break;
  }
}



void inizializeMPU9250() {
  Wire.beginTransmission(MPU9250_ADDR);
  Wire.write(PWR_MGMT_1);
  Wire.write(0x00);
  Wire.endTransmission(true);
  delay(100);
}



float readAcceleration() {
  Wire.beginTransmission(MPU9250_ADDR);
  Wire.write(ACCEL_XOUT_H);
  Wire.endTransmission(false);

  // Request 2 byte per axes: (X_H, X_L, Y_H, Y_L, Z_H, Z_L)
  Wire.requestFrom((uint8_t)MPU9250_ADDR, (uint8_t)6, (uint8_t) true);

  if (Wire.available() < 6) {
    return 0.0f;
  }

  // Combine the two bytes in a single variable
  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();

  // Convert the raw values in "g"
  float gx = ax / 16384.0f;
  float gy = ay / 16384.0f;
  float gz = az / 16384.0f;

  // Calculate the amplitude of the acceleration vector and subtract 1 g (the contribution of gravity)
  float net = sqrtf(gx * gx + gy * gy + gz * gz) - 1.0f;

  return fabsf(net);
}


float calculateWaterGoal(float weight_kg, int age, float temp_C) {
  float ml = weight_kg * 35.0f;  // Basic Formula

  if (age > 55) ml *= 0.90f;

  temp_C = round(temp_C);
  if (temp_C > 27.0f)
    ml += (temp_C - 27.0f) * 200.0f;

  return ml;
}



void updateDisplay(const char* r1, const char* r2, const char* r3) {
  display.clearDisplay();  // "Clean the display"
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(r1);  // Row 1
  display.setCursor(0, 11);
  display.print(r2);  // Row 2
  display.setCursor(0, 22);
  display.print(r3);  // Row 3
  display.display();  // "Write" in the real display
}


time_t getEpochNow() {
  if (!clockSynced) {
    return 0;  // Do not read, it isn't sincronized
  }
  return time(nullptr);  // Read the RTC
}


int getDayNumber(time_t epoch) {
  return (int)(epoch / 86400L);  // 86400 (seconds in a day) = 60 (seconds) * 60 (minutes) * 24 (hours)
}


void checkReset24h() {
  int today = getDayNumber(getEpochNow());  // Number of today

  // Initialize the reference day
  if (actualDay < 0) {
    actualDay = today;
    return;
  }

  if (today != actualDay) {
    Serial.printf("Changed day! Total water: %.0f ml. Reset in progress...\n", waterDrinked_ml);

    // Send to the app the daily report
    sendDailyWater(waterDrinked_ml);

    waterDrinked_ml = 0.0f;
    actualDay = today;
  }
}


void sendDailyWater(float ml) {
  if (!btConnected) return;

  String payload = "DAY,";
  payload += String(ml, 0);
  SerialBT.println(payload);
  Serial.printf("BT sended report: %s\n", payload.c_str());
}


void sendStateBT() {
  if (!btConnected) return;


  sensors_event_t hum_ev, temp_ev;
  aht.getEvent(&hum_ev, &temp_ev);


  String payload = "DATA,";
  payload += String(waterDrinked_ml, 0);
  payload += ",";
  payload += String(waterGoal_ml, 0);
  payload += ",";
  payload += String(weightBottle_g, 0);
  payload += ",";
  payload += String(temp_ev.temperature, 1);
  payload += ",";
  payload += String(hum_ev.relative_humidity, 0);

  SerialBT.println(payload);
  Serial.printf("BT sended: %s\n", payload.c_str());
}


void doTare() {
  scale.tare();
  weightBottle_g = 0.0f;
  weightStart_g = 0.0f;
  SerialBT.println("OK:TARE");
  Serial.println("Tare done.");
}
