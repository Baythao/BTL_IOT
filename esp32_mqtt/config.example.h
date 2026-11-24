#pragma once
// Thay theo Wi-Fi va MQTT cua ban, sau do luu thanh config.h (KHONG dua len Git).
const char WIFI_SSID[] = "TEN_WIFI_2_4_GHZ";
const char WIFI_PASS[] = "MAT_KHAU_WIFI";
const char MQTT_HOST[] = "192.168.0.102"; // IP may tinh chay Mosquitto
const int MQTT_PORT = 1883;
const bool MQTT_TLS = false;
const char MQTT_USER[] = "esp32-device";
const char MQTT_PASS[] = "MAT_KHAU_MQTT_ESP32";
const char DEVICE_ID[] = "esp32-tang1";
const char MQTT_ROOT_CA[] = R"PEM(
-----BEGIN CERTIFICATE-----
DAN_ROOT_CA_PEM_CUA_BROKER_VAO_DAY
-----END CERTIFICATE-----
)PEM";
