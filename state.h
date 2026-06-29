#ifndef SNACKOS_STATE_H
#define SNACKOS_STATE_H

#include <Arduino.h>
#include "config.h"

enum class SnackState : uint8_t {
  BOOT,
  READY,
  BUTTON_PRESSED,
  CONNECTING_WIFI,
  CONNECTED,
  CONNECTING_SERVER,
  ORDERING,
  SUCCESS,
  ERROR
};

inline const char* stateLabel(SnackState state) {
  switch (state) {
    case SnackState::BOOT:
      return "BOOT";
    case SnackState::READY:
      return "READY";
    case SnackState::BUTTON_PRESSED:
      return "Button Detected";
    case SnackState::CONNECTING_WIFI:
      return "CONNECTING WI-FI";
    case SnackState::CONNECTED:
      return "CONNECTED";
    case SnackState::CONNECTING_SERVER:
      return "CONNECTING SERVER";
    case SnackState::ORDERING:
      return "ORDERING";
    case SnackState::SUCCESS:
      return "SUCCESS";
    case SnackState::ERROR:
      return "ERROR";
    default:
      return "UNKNOWN";
  }
}

inline uint16_t stateColor(SnackState state) {
  switch (state) {
    case SnackState::READY:
    case SnackState::CONNECTED:
    case SnackState::SUCCESS:
      return COLOR_SUCCESS;
    case SnackState::ERROR:
      return COLOR_ERROR;
    case SnackState::BOOT:
    case SnackState::BUTTON_PRESSED:
    case SnackState::CONNECTING_WIFI:
    case SnackState::ORDERING:
    case SnackState::CONNECTING_SERVER:
    default:
      return COLOR_LOADING;
  }
}

#endif
