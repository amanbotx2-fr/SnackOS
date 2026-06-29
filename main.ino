#include <Arduino.h>

#include "button.h"
#include "api.h"
#include "config.h"
#include "display.h"
#include "state.h"
#include "ui.h"
#include "wifi.h"

class SnackOSApp {
 public:
  void begin() {
    Serial.begin(115200);
    Serial.println();
    Serial.println("========================");
    Serial.println("SnackOS Boot");
    Serial.println("========================");
    Serial.println("Connecting to WiFi...");
    Serial.print("SSID: ");
    Serial.println(WIFI_SSID);

    _ui.begin();
    _button.begin();
    _wifi.begin();

    setState(SnackState::BOOT, millis());
  }

  void update() {
    const uint32_t nowMs = millis();
    _button.update(nowMs);
    _ui.update(nowMs);

    if (_state == SnackState::READY) {
      if (_button.wasPressed()) {
        Serial.println("Button Pressed");
        Serial.println("Sending request...");
        setState(SnackState::ORDERING, nowMs);
      }
    } else {
      _button.wasPressed();
      _button.wasReleased();
    }

    updateStateTimers(nowMs);
  }

  void setState(SnackState nextState, uint32_t nowMs) {
    if (_stateInitialized && nextState == _state) {
      return;
    }

    _state = nextState;
    _stateInitialized = true;
    _stateStartedAt = nowMs;

    if (_state == SnackState::CONNECTING_WIFI) {
      _errorMode = SnackErrorMode::NONE;
      _wifi.startConnect(nowMs);
    }

    if (_state == SnackState::ORDERING) {
      _errorMode = SnackErrorMode::NONE;
      _api.beginOrder(nowMs);
    }

    if (_state == SnackState::READY || _state == SnackState::SUCCESS) {
      _api.reset();
    }

    _ui.setState(_state, nowMs);
  }

 private:
  enum class SnackErrorMode : uint8_t {
    NONE,
    WIFI,
    SERVER
  };

  void updateStateTimers(uint32_t nowMs) {
    switch (_state) {
      case SnackState::BOOT:
        if ((nowMs - _stateStartedAt) >= BOOT_DURATION_MS) {
          setState(SnackState::CONNECTING_WIFI, nowMs);
        }
        break;

      case SnackState::CONNECTING_WIFI:
        _wifi.update(nowMs);
        if (_wifi.isConnected()) {
          _ui.setWifiInfo(_wifi.ssid(), _wifi.localIp());
          Serial.println("WiFi Connected!");
          Serial.print("IP Address: ");
          Serial.println(_wifi.localIp());
          Serial.println();
          Serial.println("Server:");
          Serial.println(SERVER_URL);
          setState(SnackState::CONNECTED, nowMs);
        } else if (_wifi.hasTimedOut(nowMs)) {
          _wifi.stop();
          _errorMode = SnackErrorMode::WIFI;
          _ui.setErrorMessage("Wi-Fi Failed",
                              "Retrying soon",
                              "Automatic retry");
          setState(SnackState::ERROR, nowMs);
        }
        break;

      case SnackState::CONNECTED:
        if ((nowMs - _stateStartedAt) >= WIFI_CONNECTED_NOTICE_MS) {
          setState(SnackState::READY, nowMs);
        }
        break;

      case SnackState::BUTTON_PRESSED:
        if ((nowMs - _stateStartedAt) >= BUTTON_NOTICE_MS) {
          setState(SnackState::READY, nowMs);
        }
        break;

      case SnackState::ORDERING:
        _api.update(nowMs);
        if (_api.isComplete()) {
          if (_api.succeeded()) {
            _ui.setOrderEta(_api.eta());
            setState(SnackState::SUCCESS, nowMs);
          } else {
            _errorMode = SnackErrorMode::SERVER;
            _ui.setErrorMessage("Server Offline",
                                _api.errorDetail(),
                                "Check API server");
            setState(SnackState::ERROR, nowMs);
          }
        }
        break;

      case SnackState::SUCCESS:
        if ((nowMs - _stateStartedAt) >= ORDER_SUCCESS_NOTICE_MS) {
          setState(SnackState::READY, nowMs);
        }
        break;

      case SnackState::ERROR:
        if (_errorMode == SnackErrorMode::WIFI &&
            (nowMs - _stateStartedAt) >= WIFI_RETRY_MS) {
          setState(SnackState::CONNECTING_WIFI, nowMs);
        }
        break;

      case SnackState::READY:
      case SnackState::CONNECTING_SERVER:
      default:
        break;
    }
  }

  SnackDisplay _display;
  SnackUI _ui{_display};
  SnackButton _button{BUTTON_PIN};
  SnackWiFi _wifi;
  SnackApi _api;
  SnackState _state{SnackState::BOOT};
  SnackErrorMode _errorMode{SnackErrorMode::NONE};
  bool _stateInitialized{false};
  uint32_t _stateStartedAt{0};
};

SnackOSApp app;

void setup() {
  app.begin();
}

void loop() {
  app.update();
}
