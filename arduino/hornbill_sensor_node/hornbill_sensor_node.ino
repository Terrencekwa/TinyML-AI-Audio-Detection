#include <M5Unified.h>
#include <Coconutmilk-project-1_inferencing.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#define SAMPLE_RATE  EI_CLASSIFIER_FREQUENCY
#define CHUNK_SIZE   512

// ── Networking Configuration ──────────────────────
const char* WIFI_SSID     = "Henny 2.4 GHz";
const char* WIFI_PASSWORD = "Kwa0162334113";
const char* MQTT_BROKER   = "broker.hivemq.com";
const char* MQTT_TOPIC    = "hornbill/telemetry/m5stack";
const char* DEVICE_ID     = "hornbill-m5stack-01";

WiFiClient espClient;
PubSubClient client(espClient);


// ── State ─────────────────────────────────────────
static int16_t  *audio_buffer     = nullptr;
static uint32_t  audio_buffer_pos = 0;
static bool      is_inferencing   = false;
static uint32_t  inference_count  = 0;
static bool      demo_mode        = false;
static int       W, H;

// ── Gauge geometry ────────────────────────────────
//    LovyanGFX angles: 0°=right, 90°=bottom, 180°=left, 270°=top
//    Gauge sweeps from 8-o'clock (150°) clockwise to 4-o'clock (390°)
static int         GCX, GCY;
static const int   GRO   = 68;        // outer radius
static const int   GRI   = 52;        // inner radius
static const float ARC_S = 150.0f;    // start angle (8 o'clock)
static const float ARC_W = 240.0f;    // sweep (degrees)

static uint16_t C_BG, C_BAR, C_LINE, C_TEXT, C_SUB, C_TEAL, C_AMBER, C_RED, C_TRK, C_GREEN;

void initColors() {
    C_BG   = M5.Display.color565(10, 10, 18);
    C_BAR  = M5.Display.color565(18, 20, 32);
    C_LINE = M5.Display.color565(0, 190, 160);
    C_TEXT = M5.Display.color565(240, 242, 250);
    C_SUB  = M5.Display.color565(80, 88, 112);
    C_TEAL = M5.Display.color565(0, 200, 168);
    C_AMBER= M5.Display.color565(255, 175, 35);
    C_RED  = M5.Display.color565(255, 50, 60);
    C_TRK  = M5.Display.color565(28, 30, 44);
    C_GREEN= M5.Display.color565(60, 230, 90);
}

// ── Print centred text ────────────────────────────
void textC(const char *s, int y, int sz, uint16_t fg, uint16_t bg) {
    M5.Display.setTextSize(sz);
    M5.Display.setTextColor(fg, bg);
    int px = (W - (int)strlen(s) * sz * 6) / 2;
    if (px < 0) px = 0;
    M5.Display.setCursor(px, y);
    M5.Display.print(s);
}

// ═══════════════════════════════════════════════════
//  GAUGE
// ═══════════════════════════════════════════════════
void drawGauge(float v, bool alert) {
    if (v < 0) v = 0;
    if (v > 1) v = 1;

    // Clear only the gauge circle area
    int c = GRO + 2;
    M5.Display.fillRect(GCX - c, GCY - c, c * 2, c * 2, C_BG);

    // Background track
    M5.Display.fillArc(GCX, GCY, GRO, GRI, ARC_S, ARC_S + ARC_W, C_TRK);

    // Filled arc — single solid colour based on state
    if (v > 0.005f) {
        float end = ARC_S + v * ARC_W;
        uint16_t col = C_TEAL;
        if (alert)       col = C_GREEN;
        else if (v > 0.5f) col = C_AMBER;
        M5.Display.fillArc(GCX, GCY, GRO, GRI, ARC_S, end, col);
    }

    // Value text — large, centred inside arc
    char buf[8];
    snprintf(buf, sizeof(buf), "%.1f", v * 100.0f);

    int tw = strlen(buf) * 18;                      // size-3 char width ≈ 18
    M5.Display.setTextSize(3);
    M5.Display.setTextColor(alert ? C_GREEN : C_TEXT, C_BG);
    M5.Display.setCursor(GCX - tw / 2, GCY - 14);
    M5.Display.print(buf);
}

// ═══════════════════════════════════════════════════
//  SPLASH
// ═══════════════════════════════════════════════════
void drawSplash() {
    M5.Display.fillScreen(C_BG);
    for (int r = 40; r > 5; r -= 5) {
        uint8_t b = map(r, 5, 40, 180, 15);
        M5.Display.drawCircle(W / 2, H / 2 - 20, r,
            M5.Display.color565(0, b, (int)(b * 0.85f)));
    }
    M5.Display.fillCircle(W / 2, H / 2 - 20, 7, C_LINE);
    textC("HORNBILL", H / 2 + 12, 3, C_TEXT, C_BG);
    textC("AI Bird Classifier", H / 2 + 42, 1, C_SUB, C_BG);
}

// ═══════════════════════════════════════════════════
//  SHELL  (static frame, drawn once)
// ═══════════════════════════════════════════════════
void drawShell() {
    M5.Display.fillScreen(C_BG);

    // ── Header ──
    M5.Display.fillRect(0, 0, W, 18, C_BAR);
    M5.Display.fillRect(0, 18, W, 2, C_LINE);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_LINE, C_BAR);
    M5.Display.setCursor(6, 5);
    M5.Display.print("Hornbill Detector");
    M5.Display.setTextColor(demo_mode ? C_AMBER : C_TEAL, C_BAR);
    M5.Display.setCursor(W - 24, 5);
    M5.Display.print(demo_mode ? "USB" : "MIC");

    // ── Footer ──
    M5.Display.fillRect(0, H - 16, W, 16, C_BAR);
    M5.Display.fillRect(0, H - 18, W, 1, C_TRK);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_SUB, C_BAR);
    M5.Display.setCursor(6, H - 12);
    M5.Display.print("Ready");

    // ── Empty gauge ──
    drawGauge(0, false);
    textC("Monitoring...", GCY + GRO / 2 + 18, 1, C_SUB, C_BG);
}

// ═══════════════════════════════════════════════════
//  UPDATE DISPLAY  (after each inference)
// ═══════════════════════════════════════════════════
void updateDisplay(ei_impulse_result_t &result) {
    // Find top prediction
    int   bx = 0;
    float bv = 0;
    for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
        if (result.classification[i].value > bv) {
            bv = result.classification[i].value;
            bx = i;
        }
    }

    const char *lbl = result.classification[bx].label;
    bool horn  = (strstr(lbl, "ornbill") || strstr(lbl, "ORNBILL"));
    bool current_is_hornbill = horn && bv > 0.8f;

    static int consecutive_hornbill = 0;
    if (current_is_hornbill) {
        consecutive_hornbill++;
    } else {
        consecutive_hornbill = 0;
    }

    // Only alert if we have detected it 2 times consecutively
    bool alert = (consecutive_hornbill >= 2);

    // Send MQTT Publish to Cloud Broker on first alert of a sequence
    if (alert && consecutive_hornbill == 2 && WiFi.status() == WL_CONNECTED && client.connected()) {
        StaticJsonDocument<200> doc;
        doc["device_id"] = String(DEVICE_ID);
        doc["species"] = String(lbl);
        doc["confidence"] = bv;
        doc["is_hornbill"] = true;
        doc["event_type"] = "AI_DETECTION"; // helps Python script distinguish

        char jsonBuffer[256];
        serializeJson(doc, jsonBuffer);

        if (client.publish(MQTT_TOPIC, jsonBuffer)) {
            Serial.println("MQTT Publish Success");
        } else {
            Serial.println("MQTT Publish Failed");
        }
    }

    // ── Gauge ──
    drawGauge(bv, alert);

    // ── Class name (size 1, centred below gauge) ──
    String name = String(lbl);
    if (name.length() > 0) name[0] = toupper(name[0]);
    if (name.length() > 20) name = name.substring(0, 20);

    int nameY = GCY + GRO / 2 + 12;
    M5.Display.fillRect(0, nameY - 2, W, 20, C_BG);
    textC(name.c_str(), nameY, 1, alert ? C_GREEN : C_TEXT, C_BG);

    // ── Status line (size 1, centred) ──
    const char *msg;
    if (alert)        msg = "Hornbill Call Detected";
    else if (bv > 0.5f) msg = "Sound Identified";
    else              msg = "Monitoring...";

    int msgY = nameY + 12;
    M5.Display.fillRect(0, msgY - 1, W, 12, C_BG);
    textC(msg, msgY, 1, alert ? C_GREEN : C_SUB, C_BG);

    // ── Footer ──
    inference_count++;
    M5.Display.fillRect(0, H - 16, W, 16, C_BAR);

    M5.Display.fillCircle(10, H - 8, 3, alert ? C_GREEN : C_TEAL);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(alert ? C_GREEN : C_TEXT, C_BAR);
    M5.Display.setCursor(18, H - 12);
    M5.Display.print(alert ? "ALERT" : (demo_mode ? "USB Demo" : "Listening"));
    M5.Display.setTextColor(C_SUB, C_BAR);
    M5.Display.setCursor(W - 80, H - 12);
    M5.Display.printf("#%d  %dms", inference_count,
        result.timing.dsp + result.timing.classification);
}

// ═══════════════════════════════════════════════════
//  SETUP
// ═══════════════════════════════════════════════════
void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    Serial.begin(115200);

    // Connect to WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20) {
        delay(500);
        Serial.print(".");
        retries++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi Connected!");
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
        client.setServer(MQTT_BROKER, 1883);
    } else {
        Serial.println("\nWiFi Connection Failed! (Continuing offline)");
    }

    W   = M5.Display.width();
    H   = M5.Display.height();
    M5.Display.setTextWrap(false);
    GCX = W / 2;
    GCY = H / 2 - 15;
    initColors();
    drawSplash();

    auto mc = M5.Mic.config();
    mc.sample_rate        = SAMPLE_RATE;
    mc.magnification      = 2;
    mc.noise_filter_level = 0;
    M5.Mic.config(mc);
    M5.Mic.begin();

    audio_buffer = (int16_t *)malloc(EI_CLASSIFIER_RAW_SAMPLE_COUNT * sizeof(int16_t));
    if (!audio_buffer) {
        Serial.println("ERR: alloc failed");
        M5.Display.setTextColor(C_RED);
        M5.Display.setCursor(10, H - 20);
        M5.Display.print("MEMORY ERROR");
        while (1) delay(100);
    }

    Serial.printf("Model: %d samples @ %d Hz\n",
        EI_CLASSIFIER_RAW_SAMPLE_COUNT, SAMPLE_RATE);
    delay(2000);
    drawShell();
}

// ═══════════════════════════════════════════════════
//  EDGE IMPULSE
// ═══════════════════════════════════════════════════
int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr) {
    numpy::int16_to_float(&audio_buffer[offset], out_ptr, length);
    return 0;
}

void run_inference() {
    is_inferencing = true;

    signal_t signal;
    signal.total_length = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
    signal.get_data     = &microphone_audio_signal_get_data;

    ei_impulse_result_t result = { 0 };
    EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);

    if (r != EI_IMPULSE_OK) {
        Serial.printf("ERR: classifier (%d)\n", r);
        is_inferencing = false;
        return;
    }

    Serial.printf("[#%d] DSP:%dms CLS:%dms | ", inference_count + 1,
        result.timing.dsp, result.timing.classification);
    for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++)
        Serial.printf("%s:%.2f ", result.classification[i].label,
            result.classification[i].value);
    Serial.println();

    updateDisplay(result);
    audio_buffer_pos = 0;
    is_inferencing   = false;
}

// ═══════════════════════════════════════════════════
//  LOOP
// ═══════════════════════════════════════════════════
void reconnect_mqtt() {
    if (client.connect(DEVICE_ID)) {
        Serial.println("Connected to MQTT Broker");
    }
}

void loop() {
    M5.update();

    if (WiFi.status() == WL_CONNECTED) {
        if (!client.connected()) {
            reconnect_mqtt();
        }
        client.loop();
    }

    // Button A: toggle MIC / USB
    if (M5.BtnA.wasPressed()) {
        demo_mode = !demo_mode;
        audio_buffer_pos = 0;
        drawShell();
        Serial.println(demo_mode ? "MODE:USB_DEMO" : "MODE:MIC_LIVE");
    }
    if (is_inferencing) return;

    // ── MIC mode ──
    if (!demo_mode) {
        int16_t tmp[CHUNK_SIZE];
        if (M5.Mic.record(tmp, CHUNK_SIZE, SAMPLE_RATE)) {
            for (int i = 0; i < CHUNK_SIZE; i++)
                if (audio_buffer_pos < EI_CLASSIFIER_RAW_SAMPLE_COUNT)
                    audio_buffer[audio_buffer_pos++] = tmp[i];
            if (audio_buffer_pos >= EI_CLASSIFIER_RAW_SAMPLE_COUNT)
                run_inference();
        }
    }

    // ── USB Demo mode ──
    if (demo_mode && Serial.available() > 0) {
        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line == "START") {
            Serial.println("ACK");
            M5.Display.fillRect(0, H - 16, W, 16, C_BAR);
            M5.Display.setTextSize(1);
            M5.Display.setTextColor(C_AMBER, C_BAR);
            M5.Display.setCursor(18, H - 12);
            M5.Display.print("Receiving...");

            uint32_t need = EI_CLASSIFIER_RAW_SAMPLE_COUNT * sizeof(int16_t);
            uint8_t *p = (uint8_t *)audio_buffer;
            uint32_t got = 0, t0 = millis();
            while (got < need && (millis() - t0) < 10000) {
                if (Serial.available() > 0) {
                    int n = Serial.available();
                    if (n > (int)(need - got)) n = need - got;
                    Serial.readBytes(p + got, n);
                    got += n;
                }
            }
            if (got >= need) {
                Serial.printf("OK %d bytes\n", got);
                audio_buffer_pos = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
                run_inference();
            } else {
                Serial.printf("TIMEOUT %d/%d\n", got, need);
            }
        }
    }
}
