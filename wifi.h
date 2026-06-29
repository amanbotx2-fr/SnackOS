#ifndef SNACKOS_WIFI_H
#define SNACKOS_WIFI_H

#include <Arduino.h>
#if defined(ESP32)
#include_next <WiFi.h>
#endif

class SnackWiFi {
 public:
  void begin();
  void startConnect(uint32_t nowMs);
  void update(uint32_t nowMs);
  void stop();

  bool isConnected() const;
  bool hasTimedOut(uint32_t nowMs) const;
  String ssid() const;
  String localIp() const;

 private:
  bool _connecting{false};
  uint32_t _startedAt{0};
  int _lastStatus{-1};
};

#endif
