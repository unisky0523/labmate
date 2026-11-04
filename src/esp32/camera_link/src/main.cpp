#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <driver/spi_slave.h>
#include <driver/uart.h>
#include <driver/pcnt.h>
#include <esp_heap_caps.h>

#ifndef LM_USB_TEST
#define LM_USB_TEST 0
#endif

#ifndef LINK_SPI_TOKEN
#define LINK_SPI_TOKEN 0
#endif
#if LINK_SPI_TOKEN
static volatile uint32_t readyToken = 1;
static void IRAM_ATTR tokenReady(spi_slave_transaction_t *) {
    // Requeueing after a spurious CS pulse must not consume a host token.
    gpio_set_level(gpio_num_t(LM_SPI_READY), readyToken);
}
#endif

// Transport GPIOs are ESP32 pins, NOT Zynq package-pin names.
static constexpr size_t MAX_JPEG = 32768;
static constexpr size_t SPI_BYTES = 1024;
static const char *AP_NAME = "LabMate-Camera";
static const char *AP_PASSWORD = "LabMate-2026";
static const uint8_t MAGIC[] = {'L','M','J','P','E','G','0','1'};
static uint8_t *incoming, *latest, *frozen;
static size_t latestLen = 0, frozenLen = 0;
static uint32_t latestSeq = 0, frozenSeq = 0, revision = 0, lastFrameMs = 0;
static bool isFrozen = false;
static String annotations = "[]";
static SemaphoreHandle_t stateLock;
static QueueHandle_t uartEvents;
#if LINK_SPI
static volatile uint32_t spiCompleted = 0;
static volatile uint32_t spiLastBits = 0;
static volatile bool spiInitialized = false;
#endif
#if LINK_SPI_TOKEN
static volatile bool pulseCountersReady = false;
static volatile uint32_t spiFullTransactions = 0;
static volatile uint32_t spiZeroTransactions = 0;
static volatile uint32_t spiShortTransactions = 0;
static void startPulseCounter(pcnt_unit_t unit, int pulse, int control) {
    pcnt_config_t config = {};
    config.pulse_gpio_num = pulse;
    config.ctrl_gpio_num = control;
    config.unit = unit;
    config.channel = PCNT_CHANNEL_0;
    config.pos_mode = PCNT_COUNT_INC;
    config.neg_mode = PCNT_COUNT_DIS;
    config.lctrl_mode = PCNT_MODE_KEEP;
    config.hctrl_mode = control < 0 ? PCNT_MODE_KEEP : PCNT_MODE_DISABLE;
    config.counter_h_lim = 32767;
    config.counter_l_lim = -32768;
    ESP_ERROR_CHECK(pcnt_unit_config(&config));
    ESP_ERROR_CHECK(pcnt_counter_pause(unit));
    ESP_ERROR_CHECK(pcnt_counter_clear(unit));
    ESP_ERROR_CHECK(pcnt_filter_disable(unit));
    ESP_ERROR_CHECK(pcnt_counter_resume(unit));
}
#endif
static WebServer server(80);
extern const char pageStart[] asm("_binary_web_index_html_start");

static uint32_t load32(const uint8_t *p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
static void store32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; ++i) p[i] = (v >> (8 * i)) & 255;
}
static uint32_t checksum(const uint8_t *p, size_t n) {
    uint32_t crc = 0xffffffff;
    for (size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (int b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1)));
    }
    return ~crc;
}
static void ack(uint8_t *out, uint32_t sequence, uint32_t status) {
    memcpy(out, "LMAK", 4);
    store32(out + 4, sequence);
    store32(out + 8, status);
}

class Receiver {
    uint8_t header[20] = {};
    size_t headerPos = 0, used = 0, length = 0;
    uint32_t sequence = 0, crc = 0;
    unsigned long lastByte = 0;
public:
    void reset() { headerPos = used = length = 0; }
    bool push(uint8_t byte, uint8_t *reply) {
        unsigned long now = millis();
        if (now - lastByte > 2000) reset();
        lastByte = now;
        if (headerPos < 8) {
            if (byte == MAGIC[headerPos]) header[headerPos++] = byte;
            else headerPos = byte == MAGIC[0] ? 1 : 0;
            return false;
        }
        if (headerPos < sizeof(header)) {
            header[headerPos++] = byte;
            if (headerPos == sizeof(header)) {
                sequence = load32(header + 8);
                length = load32(header + 12);
                crc = load32(header + 16);
                if (length < 4 || length > MAX_JPEG) {
                    ack(reply, sequence, 2);
                    reset();
                    return true;
                }
            }
            return false;
        }
        incoming[used++] = byte;
        if (used != length) return false;
        uint32_t status = 1;
        if (incoming[0] == 0xff && incoming[1] == 0xd8 &&
            incoming[length-2] == 0xff && incoming[length-1] == 0xd9 &&
            checksum(incoming, length) == crc) {
            xSemaphoreTake(stateLock, portMAX_DELAY);
            memcpy(latest, incoming, length);
            latestLen = length;
            latestSeq = sequence;
            if (!isFrozen) revision++;
            lastFrameMs = millis();
            xSemaphoreGive(stateLock);
            status = 0;
        }
        ack(reply, sequence, status);
        reset();
        return true;
    }
};

static void receiveTask(void *) {
    Receiver receiver;
    uint8_t reply[12] = {};
#if LINK_SPI
    // DMA requires aligned, DMA-capable buffers and transactions divisible by four.
    auto rx = static_cast<uint8_t *>(heap_caps_calloc(1, SPI_BYTES, MALLOC_CAP_DMA));
    auto tx = static_cast<uint8_t *>(heap_caps_calloc(1, SPI_BYTES, MALLOC_CAP_DMA));
    if (!rx || !tx) { Serial.println("SPI buffer allocation failed"); vTaskDelete(nullptr); return; }
    pinMode(LM_SPI_READY, OUTPUT);
    gpio_set_direction(gpio_num_t(LM_SPI_READY), GPIO_MODE_INPUT_OUTPUT);
    digitalWrite(LM_SPI_READY, LOW);
    spi_bus_config_t bus = {};
    bus.mosi_io_num = LM_SPI_MOSI;
    bus.miso_io_num = LM_SPI_MISO;
    bus.sclk_io_num = LM_SPI_SCLK;
    bus.quadwp_io_num = -1;
    bus.quadhd_io_num = -1;
    bus.max_transfer_sz = SPI_BYTES;
    spi_slave_interface_config_t config = {};
    config.spics_io_num = LM_SPI_CS;
    config.mode = LINK_SPI_TOKEN ? 1 : 0;
    config.queue_size = 1;
#if LINK_SPI_TOKEN
    config.post_setup_cb = tokenReady;
#else
    config.post_setup_cb = [](spi_slave_transaction_t *) { gpio_set_level(gpio_num_t(LM_SPI_READY), 1); };
    config.post_trans_cb = [](spi_slave_transaction_t *) { gpio_set_level(gpio_num_t(LM_SPI_READY), 0); };
#endif
#if LINK_SPI_TOKEN
    // Hardware counters observe the input pads without high-rate GPIO ISRs.
    // Start before SPI init so its GPIO configuration remains authoritative.
    startPulseCounter(PCNT_UNIT_0, LM_SPI_SCLK, -1);
    startPulseCounter(PCNT_UNIT_1, LM_SPI_CS, -1);
    startPulseCounter(PCNT_UNIT_2, LM_SPI_SCLK, LM_SPI_CS);
    pulseCountersReady = true;
#endif
    ESP_ERROR_CHECK(spi_slave_initialize(VSPI_HOST, &bus, &config, SPI_DMA_CH_AUTO));
    spiInitialized = true;
    Serial.printf("SPI initialized: mode=%d SCLK=%d MOSI=%d MISO=%d CS=%d READY=%d token=%d bytes=%u\n",
                  config.mode, LM_SPI_SCLK, LM_SPI_MOSI, LM_SPI_MISO, LM_SPI_CS,
                  LM_SPI_READY, LINK_SPI_TOKEN, unsigned(SPI_BYTES));
    while (true) {
        spi_slave_transaction_t transaction = {};
        transaction.length = SPI_BYTES * 8;
        transaction.tx_buffer = tx;
        transaction.rx_buffer = rx;
        ESP_ERROR_CHECK(spi_slave_transmit(VSPI_HOST, &transaction, portMAX_DELAY));
        spiLastBits = transaction.trans_len;
        spiCompleted++;
#if LINK_SPI_TOKEN
        if (transaction.trans_len == 0) {
            // Nothing was clocked: preserve parser state AND the pending ACK.
            spiZeroTransactions++;
            continue;
        }
        if (transaction.trans_len != SPI_BYTES * 8) {
            spiShortTransactions++;
            receiver.reset();
            memset(tx, 0, SPI_BYTES);
            // Keep the token unchanged so the host stops on an incomplete packet.
            continue;
        }
        spiFullTransactions++;
        if (spiCompleted <= 4) {
            Serial.printf("SPI transaction %lu: bits=%u rx_prefix=%02x%02x%02x%02x\n",
                          (unsigned long)spiCompleted, unsigned(transaction.trans_len),
                          rx[0], rx[1], rx[2], rx[3]);
        }
#endif
        memset(tx, 0, SPI_BYTES);
        if (transaction.trans_len == SPI_BYTES * 8 && !memcmp(rx, "LMCK", 4)) {
            size_t length = rx[4] | size_t(rx[5]) << 8;
            if (length <= SPI_BYTES - 8 && rx[6] == 0 && rx[7] == 0) {
                for (size_t i = 0; i < length; ++i) {
                    if (receiver.push(rx[8+i], reply)) memcpy(tx, reply, sizeof(reply));
                }
            } else receiver.reset();
        } else if (transaction.trans_len != SPI_BYTES * 8) receiver.reset();
        // Keep READY low long enough for the Linux master to observe completion.
#if !LINK_SPI_TOKEN
        vTaskDelay(pdMS_TO_TICKS(20));
#else
        // Publish the next token only after processing and queueing a full packet.
        readyToken ^= 1;
#endif
    }
#else
#if LM_USB_TEST
    // USB/CH340 test only: close the serial monitor before sending images.
    while (true) {
        while (Serial.available()) {
            if (receiver.push(uint8_t(Serial.read()), reply)) Serial.write(reply, sizeof(reply));
        }
        vTaskDelay(1);
    }
#else
    uart_config_t config = {};
    config.baud_rate = LM_UART_BAUD;
    config.data_bits = UART_DATA_8_BITS;
    config.parity = UART_PARITY_DISABLE;
    config.stop_bits = UART_STOP_BITS_1;
    config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_2, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_2, LM_UART_TX, LM_UART_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_2, 4096, 0, 16, &uartEvents, 0));
    uint8_t data[512];
    while (true) {
        uart_event_t event;
        if (xQueueReceive(uartEvents, &event, pdMS_TO_TICKS(100))) {
            if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
                event.type == UART_PARITY_ERR || event.type == UART_FRAME_ERR) {
                uart_flush_input(UART_NUM_2);
                xQueueReset(uartEvents);
                receiver.reset();
                continue;
            }
        }
        int count = uart_read_bytes(UART_NUM_2, data, sizeof(data), pdMS_TO_TICKS(20));
        for (int i = 0; i < count; ++i) {
            if (receiver.push(data[i], reply)) uart_write_bytes(UART_NUM_2, reply, sizeof(reply));
        }
    }
#endif
#endif
}

static void noCache() { server.sendHeader("Cache-Control", "no-store"); }
// Caller holds stateLock so metadata and pixels describe the same revision.
static void describeState(JsonDocument &doc) {
    doc["frozen"] = isFrozen;
    doc["has_frame"] = isFrozen ? frozenLen > 0 : latestLen > 0;
    doc["sequence"] = isFrozen ? frozenSeq : latestSeq;
    doc["revision"] = revision;
    doc["age_ms"] = latestLen ? millis() - lastFrameMs : 0;
    doc["transport"] = LINK_SPI ? "spi" : "uart";
    doc["simulated"] = false;
    DynamicJsonDocument shapes(4096);
    deserializeJson(shapes, annotations);
    doc["annotations"] = shapes.as<JsonArray>();
}

static void state() {
    DynamicJsonDocument doc(6144);
    xSemaphoreTake(stateLock, portMAX_DELAY);
    describeState(doc);
    xSemaphoreGive(stateLock);
    String output;
    serializeJson(doc, output);
    noCache();
    server.send(200, "application/json", output);
}

static void snapshot() {
    DynamicJsonDocument doc(6144);
    xSemaphoreTake(stateLock, portMAX_DELAY);
    describeState(doc);
    size_t length = isFrozen ? frozenLen : latestLen;
    bool unchanged = server.hasArg("sequence") && server.hasArg("revision") &&
        server.arg("sequence") == String(isFrozen ? frozenSeq : latestSeq) &&
        server.arg("revision") == String(revision);
    if (unchanged) length = 0;
    auto copy = length ? static_cast<uint8_t *>(malloc(length)) : nullptr;
    if (copy) memcpy(copy, isFrozen ? frozen : latest, length);
    xSemaphoreGive(stateLock);
    if (length && !copy) { server.send(503, "text/plain", "No snapshot buffer"); return; }
    doc["jpeg_bytes"] = length;
    String metadata;
    serializeJson(doc, metadata);
    uint8_t prefix[4];
    store32(prefix, metadata.length());
    noCache();
    // Small metadata writes must not wait for a TCP delayed ACK before the JPEG.
    server.client().setNoDelay(true);
    server.setContentLength(sizeof(prefix) + metadata.length() + length);
    server.send(200, "application/octet-stream", "");
    server.sendContent(reinterpret_cast<const char *>(prefix), sizeof(prefix));
    server.sendContent(metadata.c_str(), metadata.length());
    if (length) server.sendContent(reinterpret_cast<const char *>(copy), length);
    free(copy);
}

static void image() {
    xSemaphoreTake(stateLock, portMAX_DELAY);
    size_t length = isFrozen ? frozenLen : latestLen;
    uint32_t sequence = isFrozen ? frozenSeq : latestSeq;
    uint32_t rev = revision;
    auto copy = length ? static_cast<uint8_t *>(malloc(length)) : nullptr;
    if (copy) memcpy(copy, isFrozen ? frozen : latest, length);
    xSemaphoreGive(stateLock);
    if (!copy) { server.send(length ? 503 : 404, "text/plain", "No frame / no buffer"); return; }
    // Bind the image to the state revision; never draw old labels on a new image.
    if ((server.hasArg("sequence") && server.arg("sequence").toInt() != sequence) ||
        (server.hasArg("revision") && server.arg("revision").toInt() != rev)) {
        free(copy);
        server.send(409, "text/plain", "Frame changed");
        return;
    }
    noCache();
    server.setContentLength(length);
    server.send(200, "image/jpeg", "");
    server.sendContent(reinterpret_cast<const char *>(copy), length);
    free(copy);
}

static void freezeFrame() {
    xSemaphoreTake(stateLock, portMAX_DELAY);
    if (!latestLen) {
        xSemaphoreGive(stateLock);
        server.send(409, "text/plain", "No frame");
        return;
    }
    if (!isFrozen) {
        memcpy(frozen, latest, latestLen);
        frozenLen = latestLen;
        frozenSeq = latestSeq;
        isFrozen = true;
        annotations = "[]";
        revision++;
    }
    xSemaphoreGive(stateLock);
    state();
}

static void annotate() {
    String body = server.arg("plain");
    if (body.length() > 4096) { server.send(413, "text/plain", "Too large"); return; }
    DynamicJsonDocument doc(6144);
    if (deserializeJson(doc, body) || !doc["revision"].is<uint32_t>() ||
        !doc["annotations"].is<JsonArray>()) {
        server.send(400, "text/plain", "Invalid annotations"); return;
    }
    auto shapes = doc["annotations"].as<JsonArray>();
    if (shapes.size() > 24) { server.send(400, "text/plain", "Too many shapes"); return; }
    for (JsonObject shape : shapes) {
        const char *kind = shape["kind"] | "";
        bool valid = !strcmp(kind, "arrow") || !strcmp(kind, "box");
        for (auto key : {"x1", "y1", "x2", "y2"}) {
            if (!shape[key].is<float>()) valid = false;
            float value = shape[key] | -1.0f;
            if (!isfinite(value) || value < 0 || value > 1) valid = false;
        }
        if (!valid) { server.send(400, "text/plain", "Invalid shape"); return; }
    }
    xSemaphoreTake(stateLock, portMAX_DELAY);
    if (!isFrozen || doc["revision"].as<uint32_t>() != revision) {
        xSemaphoreGive(stateLock);
        server.send(409, "text/plain", "State changed; reload");
        return;
    }
    annotations = "";
    serializeJson(shapes, annotations);
    revision++;
    xSemaphoreGive(stateLock);
    state();
}

void setup() {
    Serial.setRxBufferSize(4096);
    Serial.begin(115200);
#if LINK_SPI
    Serial.printf("LabMate spi-preview-perf-v8-responsive-20261104 (token-v3 compatible): transport=SPI token=%d\n", LINK_SPI_TOKEN);
#else
    Serial.printf("LabMate spi-diag-20261104: transport=UART usb_test=%d\n", LM_USB_TEST);
#endif
    incoming = static_cast<uint8_t *>(malloc(MAX_JPEG));
    latest = static_cast<uint8_t *>(malloc(MAX_JPEG));
    frozen = static_cast<uint8_t *>(malloc(MAX_JPEG));
    stateLock = xSemaphoreCreateMutex();
    if (!incoming || !latest || !frozen || !stateLock) {
        Serial.println("Not enough memory; preview stopped");
        while (true) delay(1000);
    }
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(AP_NAME, AP_PASSWORD, 1, false, 3)) {
        Serial.println("Wi-Fi AP failed"); while (true) delay(1000);
    }
    Serial.print("Preview URL: http://"); Serial.println(WiFi.softAPIP());
    server.on("/", HTTP_GET, []() { server.send_P(200, "text/html; charset=utf-8", pageStart); });
    server.on("/api/state", HTTP_GET, state);
    server.on("/api/frame", HTTP_GET, image);
    server.on("/api/snapshot", HTTP_GET, snapshot);
    server.on("/api/freeze", HTTP_POST, freezeFrame);
    server.on("/api/live", HTTP_POST, []() {
        xSemaphoreTake(stateLock, portMAX_DELAY);
        isFrozen = false; annotations = "[]"; revision++;
        xSemaphoreGive(stateLock);
        state();
    });
    server.on("/api/annotations", HTTP_POST, annotate);
    server.onNotFound([]() { server.send(404, "text/plain", "Not found"); });
    server.begin();
    if (xTaskCreate(receiveTask, "camera_link", 4096, nullptr, 2, nullptr) != pdPASS) {
        Serial.println("Receiver task failed"); while (true) delay(1000);
    }
}

void loop() {
    server.handleClient();
#if LINK_SPI
    static unsigned long lastDiagnostic = 0;
    if (millis() - lastDiagnostic >= 2000) {
        lastDiagnostic = millis();
        Serial.printf("SPI diag: initialized=%d READY_pin=%d CS_pin=%d completed=%lu last_bits=%lu",
                      spiInitialized, gpio_get_level(gpio_num_t(LM_SPI_READY)),
                      gpio_get_level(gpio_num_t(LM_SPI_CS)),
                      (unsigned long)spiCompleted, (unsigned long)spiLastBits);
#if LINK_SPI_TOKEN
        Serial.printf(" token=%lu", (unsigned long)readyToken);
        Serial.printf(" full_tx=%lu zero_tx=%lu short_tx=%lu",
                      (unsigned long)spiFullTransactions, (unsigned long)spiZeroTransactions,
                      (unsigned long)spiShortTransactions);
        if (pulseCountersReady) {
            int16_t clocks = 0, selects = 0, selectedClocks = 0;
            pcnt_get_counter_value(PCNT_UNIT_0, &clocks);
            pcnt_get_counter_value(PCNT_UNIT_1, &selects);
            pcnt_get_counter_value(PCNT_UNIT_2, &selectedClocks);
            Serial.printf(" sclk_rises=%d cs_rises=%d clocks_cs_low=%d (mod32767)",
                          clocks, selects, selectedClocks);
        }
#endif
        Serial.println();
    }
#endif
    delay(2);
}
