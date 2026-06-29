#include <Arduino.h>
#include <WiFi.h>

#include "config.h"
#include "wifi.h"

namespace {
const char* wifiStatusName(int status) {
  switch (status) {
    case WL_IDLE_STATUS:
      return "idle";
    case WL_NO_SSID_AVAIL:
      return "ssid unavailable";
    case WL_SCAN_COMPLETED:
      return "scan completed";
    case WL_CONNECTED:
      return "connected";
    case WL_CONNECT_FAILED:
      return "connect failed";
    case WL_CONNECTION_LOST:
      return "connection lost";
    case WL_DISCONNECTED:
      return "disconnected";
    default:
      return "unknown";
  }
}
}  // namespace

void SnackWiFi::begin() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);

  Serial.println("[WiFi] Station mode initialized");
}

void SnackWiFi::startConnect(uint32_t nowMs) {
  _startedAt = nowMs;
  _connecting = true;
  _lastStatus = -1;

  Serial.print("[WiFi] Connecting to SSID: ");
  Serial.println(WIFI_SSID);
  Serial.print("[WiFi] Connect timeout ms: ");
  Serial.println(WIFI_CONNECT_TIMEOUT_MS);

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] Disconnecting existing Wi-Fi session");
    WiFi.disconnect(false);
  }

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void SnackWiFi::update(uint32_t nowMs) {
  const int status = WiFi.status();
  if (status != _lastStatus) {
    Serial.print("[WiFi] Status: ");
    Serial.print(status);
    Serial.print(" (");
    Serial.print(wifiStatusName(status));
    Serial.print("), elapsed ms: ");
    Serial.println(nowMs - _startedAt);
    _lastStatus = status;
  }

  if (_connecting && status == WL_CONNECTED) {
    _connecting = false;
    Serial.print("[WiFi] Connected. Local IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WiFi] RSSI: ");
    Serial.println(WiFi.RSSI());
  }
}

void SnackWiFi::stop() {
  _connecting = false;
  Serial.println("[WiFi] Stopping Wi-Fi connection attempt");
  WiFi.disconnect(false);
}

bool SnackWiFi::isConnected() const {
  return WiFi.status() == WL_CONNECTED;
}

bool SnackWiFi::hasTimedOut(uint32_t nowMs) const {
  return _connecting && ((nowMs - _startedAt) >= WIFI_CONNECT_TIMEOUT_MS);
}

String SnackWiFi::ssid() const {
  return WiFi.SSID();
}

String SnackWiFi::localIp() const {
  return WiFi.localIP().toString();
}
