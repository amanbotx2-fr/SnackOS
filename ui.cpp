#include <Arduino.h>

#include "ui.h"

namespace {
constexpr int16_t BOOT_BAR_X = 40;
constexpr int16_t BOOT_BAR_Y = 106;
constexpr int16_t BOOT_BAR_W = 160;
constexpr int16_t BOOT_BAR_H = 12;

constexpr int16_t STATUS_CARD_X = 38;
constexpr int16_t STATUS_CARD_Y = 68;
constexpr int16_t STATUS_CARD_W = 164;
constexpr int16_t STATUS_CARD_H = 34;
constexpr int16_t STATUS_DOT_X = STATUS_CARD_X + 24;
constexpr int16_t STATUS_DOT_Y = STATUS_CARD_Y + (STATUS_CARD_H / 2);

constexpr int16_t WIFI_SPINNER_X = 120;
constexpr int16_t WIFI_SPINNER_Y = 78;
constexpr int16_t WIFI_SPINNER_RADIUS = 13;
constexpr int16_t WIFI_PANEL_X = 20;
constexpr int16_t WIFI_PANEL_Y = 50;
constexpr int16_t WIFI_PANEL_W = 200;
constexpr int16_t WIFI_PANEL_H = 58;
constexpr int16_t ORDER_SPINNER_X = 120;
constexpr int16_t ORDER_SPINNER_Y = 78;
constexpr int16_t ORDER_SPINNER_RADIUS = 14;

constexpr int16_t NOTICE_REGION_X = 8;
constexpr int16_t NOTICE_REGION_Y = 30;
constexpr int16_t NOTICE_REGION_W = 224;
constexpr int16_t NOTICE_REGION_H = 80;
constexpr int16_t NOTICE_CARD_X = 13;
constexpr int16_t NOTICE_CARD_START_Y = 32;
constexpr int16_t NOTICE_CARD_TARGET_Y = 51;
constexpr int16_t NOTICE_CARD_W = 214;
constexpr int16_t NOTICE_CARD_H = 54;
constexpr uint16_t NOTICE_SLIDE_MS = 240;
constexpr uint16_t UI_FRAME_MS = 33;

uint8_t easedOut(uint32_t elapsedMs, uint16_t durationMs) {
  if (elapsedMs >= durationMs) {
    return 255;
  }

  const uint32_t t = (elapsedMs * 255UL) / durationMs;
  const uint32_t inv = 255 - t;
  return 255 - ((inv * inv * inv) / (255UL * 255UL));
}
}  // namespace

SnackUI::SnackUI(SnackDisplay& display)
    : _display(display),
      _state(SnackState::BOOT),
      _stateStartedAt(0),
      _hasState(false),
      _lastBootProgress(255),
      _lastReadyPulse(255),
      _lastNoticeProgress(255),
      _lastNoticePulse(255),
      _lastWifiSpinnerStep(255),
      _lastOrderSpinnerStep(255),
      _lastErrorPulse(255),
      _lastNoticeY(INT16_MIN),
      _orderEta("Soon"),
      _errorTitle("Wi-Fi Failed"),
      _errorDetail("Retrying soon"),
      _errorFooter("Automatic retry") {}

void SnackUI::begin() {
  _display.begin();
}

void SnackUI::setWifiInfo(const String& ssid, const String& localIp) {
  _wifiSsid = ssid;
  _wifiIp = localIp;
}

void SnackUI::setOrderEta(const String& eta) {
  _orderEta = eta.length() ? eta : String("Soon");
}

void SnackUI::setErrorMessage(const String& title,
                              const String& detail,
                              const String& footer) {
  _errorTitle = title;
  _errorDetail = detail;
  _errorFooter = footer;
}

void SnackUI::setState(SnackState state, uint32_t nowMs) {
  if (_hasState && state == _state) {
    return;
  }

  _state = state;
  _stateStartedAt = nowMs;
  _hasState = true;
  resetAnimationState();

  switch (_state) {
    case SnackState::BOOT:
      renderBootBase();
      updateBoot(nowMs);
      break;
    case SnackState::READY:
      renderReadyBase();
      updateReady(nowMs);
      break;
    case SnackState::BUTTON_PRESSED:
      renderButtonPressedBase();
      updateButtonPressed(nowMs);
      break;
    case SnackState::CONNECTING_WIFI:
      renderConnectingWifiBase();
      updateConnectingWifi(nowMs);
      break;
    case SnackState::CONNECTED:
      renderConnectedBase();
      break;
    case SnackState::ORDERING:
      renderOrderingBase();
      updateOrdering(nowMs);
      break;
    case SnackState::SUCCESS:
      renderSuccessBase();
      break;
    case SnackState::ERROR:
      renderErrorBase();
      updateError(nowMs);
      break;
    case SnackState::CONNECTING_SERVER:
    default:
      renderReadyBase();
      break;
  }
}

void SnackUI::update(uint32_t nowMs) {
  if (!_hasState) {
    return;
  }

  switch (_state) {
    case SnackState::BOOT:
      updateBoot(nowMs);
      break;
    case SnackState::READY:
      updateReady(nowMs);
      break;
    case SnackState::BUTTON_PRESSED:
      updateButtonPressed(nowMs);
      break;
    case SnackState::CONNECTING_WIFI:
      updateConnectingWifi(nowMs);
      break;
    case SnackState::ERROR:
      updateError(nowMs);
      break;
    case SnackState::ORDERING:
      updateOrdering(nowMs);
      break;
    case SnackState::CONNECTED:
    case SnackState::CONNECTING_SERVER:
    case SnackState::SUCCESS:
    default:
      break;
  }
}

void SnackUI::resetAnimationState() {
  _lastBootProgress = 255;
  _lastReadyPulse = 255;
  _lastNoticeProgress = 255;
  _lastNoticePulse = 255;
  _lastWifiSpinnerStep = 255;
  _lastOrderSpinnerStep = 255;
  _lastErrorPulse = 255;
  _lastNoticeY = INT16_MIN;
}

void SnackUI::renderBootBase() {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillScreen(COLOR_BACKGROUND);
  drawLogo(43, 3, 3, COLOR_BACKGROUND);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_MUTED, COLOR_BACKGROUND);
  tft.setCursor(96, 73);
  tft.print("VERSION ");
  tft.print(SNACKOS_VERSION);

  tft.setTextColor(COLOR_LOADING, COLOR_BACKGROUND);
  tft.setCursor(93, 91);
  tft.print("STARTING");

  _display.drawProgressBar(BOOT_BAR_X,
                           BOOT_BAR_Y,
                           BOOT_BAR_W,
                           BOOT_BAR_H,
                           0,
                           COLOR_LOADING);
}

void SnackUI::renderReadyBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_SUCCESS);
  drawLogo(38, 3, 2, COLOR_READY_BACKGROUND);

  tft.fillRoundRect(STATUS_CARD_X,
                    STATUS_CARD_Y,
                    STATUS_CARD_W,
                    STATUS_CARD_H,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(STATUS_CARD_X,
                    STATUS_CARD_Y,
                    STATUS_CARD_W,
                    STATUS_CARD_H,
                    CARD_RADIUS,
                    COLOR_BORDER);

  tft.setTextSize(2);
  tft.setTextColor(COLOR_SUCCESS, COLOR_SURFACE);
  tft.setCursor(90, STATUS_CARD_Y + 10);
  tft.print("READY");

  drawFooter("Press Button", COLOR_READY_BACKGROUND);
}

void SnackUI::renderButtonPressedBase() {
  drawAppBackground(COLOR_LOADING);
  drawLogo(18, 2, 1, COLOR_HEADER);
  drawFooter("Returning to READY", COLOR_READY_BACKGROUND);
  clearNoticeRegion();
}

void SnackUI::renderConnectingWifiBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_LOADING);
  drawLogo(18, 2, 1, COLOR_HEADER);

  tft.fillRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_BORDER);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_TEXT, COLOR_SURFACE);
  tft.setCursor(66, 95);
  tft.print("Connecting Wi-Fi...");

  drawFooter("Network setup", COLOR_READY_BACKGROUND);
}

void SnackUI::renderConnectedBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_SUCCESS);
  drawLogo(18, 2, 1, COLOR_HEADER);

  tft.fillRoundRect(WIFI_PANEL_X,
                    43,
                    WIFI_PANEL_W,
                    70,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(WIFI_PANEL_X,
                    43,
                    WIFI_PANEL_W,
                    70,
                    CARD_RADIUS,
                    COLOR_SUCCESS);

  tft.fillCircle(39, 59, 7, COLOR_SUCCESS);
  tft.drawLine(35, 59, 38, 63, COLOR_SURFACE);
  tft.drawLine(38, 63, 45, 54, COLOR_SURFACE);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_SUCCESS, COLOR_SURFACE);
  tft.setCursor(54, 53);
  tft.print("Wi-Fi Connected");

  tft.setTextColor(COLOR_MUTED, COLOR_SURFACE);
  tft.setCursor(54, 76);
  tft.print("IP Address");

  tft.setTextColor(COLOR_TEXT, COLOR_SURFACE);
  tft.setCursor(54, 94);
  tft.print(_wifiIp.length() ? _wifiIp : String("-"));

  drawFooter("Starting interface", COLOR_READY_BACKGROUND);
}

void SnackUI::renderOrderingBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_LOADING);
  drawLogo(18, 2, 1, COLOR_HEADER);

  tft.fillRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_LOADING);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_TEXT, COLOR_SURFACE);
  tft.setCursor(76, 95);
  tft.print("Sending order...");

  drawFooter("Contacting server", COLOR_READY_BACKGROUND);
}

void SnackUI::renderSuccessBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_SUCCESS);
  drawLogo(18, 2, 1, COLOR_HEADER);

  tft.fillRoundRect(WIFI_PANEL_X,
                    43,
                    WIFI_PANEL_W,
                    70,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(WIFI_PANEL_X,
                    43,
                    WIFI_PANEL_W,
                    70,
                    CARD_RADIUS,
                    COLOR_SUCCESS);

  tft.fillCircle(39, 59, 7, COLOR_SUCCESS);
  tft.drawLine(35, 59, 38, 63, COLOR_SURFACE);
  tft.drawLine(38, 63, 45, 54, COLOR_SURFACE);

  tft.setTextSize(2);
  tft.setTextColor(COLOR_SUCCESS, COLOR_SURFACE);
  tft.setCursor(57, 52);
  tft.print("Order Placed");

  tft.setTextSize(1);
  tft.setTextColor(COLOR_MUTED, COLOR_SURFACE);
  tft.setCursor(57, 82);
  tft.print("ETA: ");
  tft.print(_orderEta);

  drawFooter("Returning to READY", COLOR_READY_BACKGROUND);
}

void SnackUI::renderErrorBase() {
  Adafruit_ST7789& tft = _display.raw();

  drawAppBackground(COLOR_ERROR);
  drawLogo(18, 2, 1, COLOR_HEADER);

  tft.fillRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(WIFI_PANEL_X,
                    WIFI_PANEL_Y,
                    WIFI_PANEL_W,
                    WIFI_PANEL_H,
                    CARD_RADIUS,
                    COLOR_ERROR);

  tft.setTextSize(2);
  tft.setTextColor(COLOR_ERROR, COLOR_SURFACE);
  tft.setCursor(55, 61);
  tft.print(_errorTitle);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_MUTED, COLOR_SURFACE);
  tft.setCursor(75, 91);
  tft.print(_errorDetail);

  drawFooter(_errorFooter, COLOR_READY_BACKGROUND);
}

void SnackUI::updateBoot(uint32_t nowMs) {
  uint32_t elapsed = nowMs - _stateStartedAt;
  if (elapsed > BOOT_DURATION_MS) {
    elapsed = BOOT_DURATION_MS;
  }

  const uint8_t progress = (elapsed * 100UL) / BOOT_DURATION_MS;
  drawBootProgress(progress);
}

void SnackUI::updateReady(uint32_t nowMs) {
  const uint8_t pulse = ((nowMs - _stateStartedAt) / 180) % 4;
  if (pulse == _lastReadyPulse) {
    return;
  }

  drawReadyIndicator(pulse);
  _lastReadyPulse = pulse;
}

void SnackUI::updateButtonPressed(uint32_t nowMs) {
  const uint32_t elapsed = nowMs - _stateStartedAt;
  const uint8_t eased = easedOut(elapsed, NOTICE_SLIDE_MS);
  const int16_t noticeY = NOTICE_CARD_START_Y +
                          (((NOTICE_CARD_TARGET_Y - NOTICE_CARD_START_Y) *
                            static_cast<int16_t>(eased)) /
                           255);
  uint32_t progressValue = (elapsed * 100UL) / BUTTON_NOTICE_MS;
  if (progressValue > 100) {
    progressValue = 100;
  }
  const uint8_t progress = progressValue;
  const uint8_t pulse = (elapsed / UI_FRAME_MS) % 6;

  if (noticeY == _lastNoticeY && progress == _lastNoticeProgress &&
      pulse == _lastNoticePulse) {
    return;
  }

  clearNoticeRegion();
  drawNoticeCard(noticeY, progress, pulse);
  _lastNoticeY = noticeY;
  _lastNoticeProgress = progress;
  _lastNoticePulse = pulse;
}

void SnackUI::updateConnectingWifi(uint32_t nowMs) {
  const uint8_t step = ((nowMs - _stateStartedAt) / 125) % 8;
  if (step == _lastWifiSpinnerStep) {
    return;
  }

  drawWifiSpinner(step);
  _lastWifiSpinnerStep = step;
}

void SnackUI::updateOrdering(uint32_t nowMs) {
  const uint8_t step = ((nowMs - _stateStartedAt) / 110) % 8;
  if (step == _lastOrderSpinnerStep) {
    return;
  }

  drawOrderSpinner(step);
  _lastOrderSpinnerStep = step;
}

void SnackUI::updateError(uint32_t nowMs) {
  const uint8_t pulse = ((nowMs - _stateStartedAt) / 220) % 4;
  if (pulse == _lastErrorPulse) {
    return;
  }

  drawErrorPulse(pulse);
  _lastErrorPulse = pulse;
}

void SnackUI::drawAppBackground(uint16_t accent) {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillScreen(COLOR_READY_BACKGROUND);
  tft.fillRect(0, 0, SCREEN_WIDTH, CONTENT_TOP, COLOR_HEADER);
  tft.fillRect(0, 0, SCREEN_WIDTH, 4, accent);
  tft.drawFastHLine(0, CONTENT_TOP, SCREEN_WIDTH, COLOR_SURFACE_DARK);
}

void SnackUI::drawBootProgress(uint8_t percent) {
  if (percent == _lastBootProgress) {
    return;
  }

  _display.drawProgressBar(BOOT_BAR_X,
                           BOOT_BAR_Y,
                           BOOT_BAR_W,
                           BOOT_BAR_H,
                           percent,
                           COLOR_LOADING);
  _lastBootProgress = percent;
}

void SnackUI::drawReadyIndicator(uint8_t pulse) {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillRect(STATUS_DOT_X - 13,
               STATUS_DOT_Y - 13,
               26,
               26,
               COLOR_SURFACE);
  tft.drawCircle(STATUS_DOT_X,
                 STATUS_DOT_Y,
                 8 + (pulse % 3),
                 pulse == 0 ? COLOR_SUCCESS_SOFT : COLOR_SURFACE_LIGHT);
  tft.fillCircle(STATUS_DOT_X, STATUS_DOT_Y, 6, COLOR_SUCCESS);
  tft.fillCircle(STATUS_DOT_X - 2, STATUS_DOT_Y - 2, 2, COLOR_SUCCESS_SOFT);
}

void SnackUI::drawNoticeCard(int16_t y, uint8_t progress, uint8_t pulse) {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillRoundRect(NOTICE_CARD_X + 2,
                    y + 4,
                    NOTICE_CARD_W,
                    NOTICE_CARD_H,
                    CARD_RADIUS,
                    COLOR_SURFACE_DARK);
  tft.fillRoundRect(NOTICE_CARD_X,
                    y,
                    NOTICE_CARD_W,
                    NOTICE_CARD_H,
                    CARD_RADIUS,
                    COLOR_SURFACE);
  tft.drawRoundRect(NOTICE_CARD_X,
                    y,
                    NOTICE_CARD_W,
                    NOTICE_CARD_H,
                    CARD_RADIUS,
                    COLOR_LOADING);

  const int16_t iconX = NOTICE_CARD_X + 22;
  const int16_t iconY = y + 27;
  tft.drawCircle(iconX, iconY, 10 + (pulse % 2), COLOR_LOADING);
  tft.fillCircle(iconX, iconY, 7, COLOR_LOADING);
  tft.fillRect(iconX - 1, iconY - 5, 3, 8, COLOR_SURFACE);
  tft.fillRect(iconX - 1, iconY + 5, 3, 2, COLOR_SURFACE);

  tft.setTextSize(2);
  tft.setTextColor(COLOR_TEXT, COLOR_SURFACE);
  tft.setCursor(NOTICE_CARD_X + 47, y + 15);
  tft.print("Button Detected");

  constexpr int16_t barX = NOTICE_CARD_X + 47;
  constexpr int16_t barW = 150;
  constexpr int16_t barH = 4;
  const int16_t fillW = (barW * progress) / 100;
  tft.fillRoundRect(barX,
                    y + NOTICE_CARD_H - 12,
                    barW,
                    barH,
                    2,
                    COLOR_SURFACE_DARK);
  if (fillW > 0) {
    tft.fillRoundRect(barX,
                      y + NOTICE_CARD_H - 12,
                      fillW,
                      barH,
                      2,
                      COLOR_LOADING);
  }
}

void SnackUI::drawWifiSpinner(uint8_t step) {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillRect(WIFI_SPINNER_X - WIFI_SPINNER_RADIUS - 4,
               WIFI_SPINNER_Y - WIFI_SPINNER_RADIUS - 4,
               (WIFI_SPINNER_RADIUS + 4) * 2,
               (WIFI_SPINNER_RADIUS + 4) * 2,
               COLOR_SURFACE);

  for (uint8_t i = 0; i < 8; i++) {
    const uint8_t phase = (i + 8 - step) % 8;
    const uint16_t color =
        phase == 0 ? COLOR_LOADING
                   : (phase < 3 ? COLOR_ACCENT : COLOR_SURFACE_LIGHT);
    const float angle = (i * 0.78539816f) - 1.57079633f;
    const int16_t x = WIFI_SPINNER_X + cos(angle) * WIFI_SPINNER_RADIUS;
    const int16_t y = WIFI_SPINNER_Y + sin(angle) * WIFI_SPINNER_RADIUS;
    tft.fillCircle(x, y, phase == 0 ? 3 : 2, color);
  }
}

void SnackUI::drawOrderSpinner(uint8_t step) {
  Adafruit_ST7789& tft = _display.raw();

  tft.fillRect(ORDER_SPINNER_X - ORDER_SPINNER_RADIUS - 4,
               ORDER_SPINNER_Y - ORDER_SPINNER_RADIUS - 4,
               (ORDER_SPINNER_RADIUS + 4) * 2,
               (ORDER_SPINNER_RADIUS + 4) * 2,
               COLOR_SURFACE);

  for (uint8_t i = 0; i < 8; i++) {
    const uint8_t phase = (i + 8 - step) % 8;
    const uint16_t color =
        phase == 0 ? COLOR_LOADING
                   : (phase < 3 ? COLOR_ACCENT : COLOR_SURFACE_LIGHT);
    const float angle = (i * 0.78539816f) - 1.57079633f;
    const int16_t x = ORDER_SPINNER_X + cos(angle) * ORDER_SPINNER_RADIUS;
    const int16_t y = ORDER_SPINNER_Y + sin(angle) * ORDER_SPINNER_RADIUS;
    tft.fillCircle(x, y, phase == 0 ? 3 : 2, color);
  }
}

void SnackUI::drawErrorPulse(uint8_t pulse) {
  Adafruit_ST7789& tft = _display.raw();
  constexpr int16_t iconX = 40;
  constexpr int16_t iconY = 72;

  tft.fillRect(iconX - 14, iconY - 14, 28, 28, COLOR_SURFACE);
  tft.drawCircle(iconX, iconY, 9 + (pulse % 2), COLOR_ERROR);
  tft.fillCircle(iconX, iconY, 7, COLOR_ERROR);
  tft.fillRect(iconX - 1, iconY - 5, 3, 8, COLOR_SURFACE);
  tft.fillRect(iconX - 1, iconY + 5, 3, 2, COLOR_SURFACE);
}

void SnackUI::clearNoticeRegion() {
  _display.raw().fillRect(NOTICE_REGION_X,
                          NOTICE_REGION_Y,
                          NOTICE_REGION_W,
                          NOTICE_REGION_H,
                          COLOR_READY_BACKGROUND);
}

void SnackUI::drawFooter(const String& text, uint16_t background) {
  Adafruit_ST7789& tft = _display.raw();

  tft.drawFastHLine(0, CONTENT_BOTTOM, SCREEN_WIDTH, COLOR_SURFACE_DARK);
  tft.setTextSize(1);
  tft.setTextColor(COLOR_MUTED, background);

  int16_t x1 = 0;
  int16_t y1 = 0;
  uint16_t textW = 0;
  uint16_t textH = 0;
  tft.getTextBounds(text.c_str(), 0, 0, &x1, &y1, &textW, &textH);
  tft.setCursor((SCREEN_WIDTH - textW) / 2, 125);
  tft.print(text);
}

void SnackUI::drawLogo(int16_t centerY,
                       uint8_t textSize,
                       uint8_t markScale,
                       uint16_t background) {
  Adafruit_ST7789& tft = _display.raw();

  const int16_t markW = 10 * markScale;
  const int16_t markH = 12 * markScale;
  const int16_t gap = 8;
  const int16_t textW = strlen(SNACKOS_NAME) * 6 * textSize;
  const int16_t groupW = markW + gap + textW;
  const int16_t startX = (SCREEN_WIDTH - groupW) / 2;
  const int16_t markY = centerY - (markH / 2);
  const int16_t textY = centerY - (4 * textSize);

  drawLogoMark(startX, markY, markScale);
  tft.setTextSize(textSize);
  tft.setTextColor(COLOR_TEXT, background);
  tft.setCursor(startX + markW + gap, textY);
  tft.print(SNACKOS_NAME);
}

void SnackUI::drawLogoMark(int16_t x, int16_t y, uint8_t scale) {
  Adafruit_ST7789& tft = _display.raw();

  const int16_t w = 10 * scale;
  const int16_t h = 12 * scale;
  const int16_t radius = (scale > 1) ? (2 * scale) : 2;

  tft.fillRoundRect(x, y, w, h, radius, COLOR_CHOCOLATE);
  tft.drawRoundRect(x, y, w, h, radius, COLOR_CHOCOLATE_HI);

  for (uint8_t row = 0; row < 2; row++) {
    for (uint8_t col = 0; col < 2; col++) {
      const int16_t cellX = x + (2 * scale) + (col * 4 * scale);
      const int16_t cellY = y + (2 * scale) + (row * 5 * scale);
      tft.drawRoundRect(cellX,
                        cellY,
                        3 * scale,
                        3 * scale,
                        scale,
                        COLOR_CHOCOLATE_HI);
    }
  }

  tft.drawLine(x + (7 * scale),
               y + scale,
               x + (9 * scale),
               y + (3 * scale),
               COLOR_TEXT);
}
