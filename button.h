#ifndef SNACKOS_BUTTON_H
#define SNACKOS_BUTTON_H

#include <Arduino.h>
#include "config.h"

class SnackButton {
 public:
  explicit SnackButton(uint8_t pin = BUTTON_PIN,
                       uint16_t debounceMs = BUTTON_DEBOUNCE_MS);

  void begin();
  void update(uint32_t nowMs = millis());

  bool isPressed() const;
  bool wasPressed();
  bool wasReleased();

 private:
  bool readPressed() const;

  uint8_t _pin;
  uint16_t _debounceMs;
  bool _stablePressed;
  bool _lastRawPressed;
  bool _pressedEvent;
  bool _releasedEvent;
  uint32_t _lastRawChangeAt;
};

#endif
