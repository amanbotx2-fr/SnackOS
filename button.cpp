#include <Arduino.h>

#include "button.h"

SnackButton::SnackButton(uint8_t pin, uint16_t debounceMs)
    : _pin(pin),
      _debounceMs(debounceMs),
      _stablePressed(false),
      _lastRawPressed(false),
      _pressedEvent(false),
      _releasedEvent(false),
      _lastRawChangeAt(0) {}

void SnackButton::begin() {
  pinMode(_pin, INPUT_PULLUP);
  _stablePressed = readPressed();
  _lastRawPressed = _stablePressed;
  _lastRawChangeAt = millis();
}

void SnackButton::update(uint32_t nowMs) {
  const bool rawPressed = readPressed();

  if (rawPressed != _lastRawPressed) {
    _lastRawPressed = rawPressed;
    _lastRawChangeAt = nowMs;
  }

  if ((nowMs - _lastRawChangeAt) < _debounceMs) {
    return;
  }

  if (rawPressed != _stablePressed) {
    _stablePressed = rawPressed;

    if (_stablePressed) {
      _pressedEvent = true;   // Falling edge: HIGH -> LOW.
    } else {
      _releasedEvent = true;  // Rising edge: LOW -> HIGH.
    }
  }
}

bool SnackButton::isPressed() const {
  return _stablePressed;
}

bool SnackButton::wasPressed() {
  const bool event = _pressedEvent;
  _pressedEvent = false;
  return event;
}

bool SnackButton::wasReleased() {
  const bool event = _releasedEvent;
  _releasedEvent = false;
  return event;
}

bool SnackButton::readPressed() const {
  return digitalRead(_pin) == LOW;
}
