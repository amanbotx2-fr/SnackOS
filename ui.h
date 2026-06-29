#ifndef SNACKOS_UI_H
#define SNACKOS_UI_H

#include <Arduino.h>

#include "display.h"
#include "state.h"

class SnackUI {
 public:
  explicit SnackUI(SnackDisplay& display);

  void begin();
  void setWifiInfo(const String& ssid, const String& localIp);
  void setOrderEta(const String& eta);
  void setErrorMessage(const String& title,
                       const String& detail,
                       const String& footer);
  void setState(SnackState state, uint32_t nowMs);
  void update(uint32_t nowMs);

 private:
  SnackDisplay& _display;
  SnackState _state;
  uint32_t _stateStartedAt;
  bool _hasState;
  uint8_t _lastBootProgress;
  uint8_t _lastReadyPulse;
  uint8_t _lastNoticeProgress;
  uint8_t _lastNoticePulse;
  uint8_t _lastWifiSpinnerStep;
  uint8_t _lastOrderSpinnerStep;
  uint8_t _lastErrorPulse;
  int16_t _lastNoticeY;
  String _wifiSsid;
  String _wifiIp;
  String _orderEta;
  String _errorTitle;
  String _errorDetail;
  String _errorFooter;

  void resetAnimationState();

  void renderBootBase();
  void renderReadyBase();
  void renderButtonPressedBase();
  void renderConnectingWifiBase();
  void renderConnectedBase();
  void renderOrderingBase();
  void renderSuccessBase();
  void renderErrorBase();

  void updateBoot(uint32_t nowMs);
  void updateReady(uint32_t nowMs);
  void updateButtonPressed(uint32_t nowMs);
  void updateConnectingWifi(uint32_t nowMs);
  void updateOrdering(uint32_t nowMs);
  void updateError(uint32_t nowMs);

  void drawAppBackground(uint16_t accent);
  void drawBootProgress(uint8_t percent);
  void drawReadyIndicator(uint8_t pulse);
  void drawNoticeCard(int16_t y, uint8_t progress, uint8_t pulse);
  void drawWifiSpinner(uint8_t step);
  void drawOrderSpinner(uint8_t step);
  void drawErrorPulse(uint8_t pulse);
  void clearNoticeRegion();
  void drawFooter(const String& text, uint16_t background);
  void drawLogo(int16_t centerY,
                uint8_t textSize,
                uint8_t markScale,
                uint16_t background);
  void drawLogoMark(int16_t x, int16_t y, uint8_t scale);
};

#endif
