#include <Arduino.h>

#include "display.h"

SnackDisplay::SnackDisplay() : _tft(TFT_CS, TFT_DC, TFT_RST) {}

void SnackDisplay::begin() {
  SPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  _tft.init(DISPLAY_INIT_WIDTH, DISPLAY_INIT_HEIGHT);
  _tft.setRotation(DISPLAY_ROTATION);
  _tft.setTextWrap(false);
  clear();
}

void SnackDisplay::clear(uint16_t color) {
  _tft.fillScreen(color);
}

void SnackDisplay::clearContentArea() {
  _tft.fillRect(0,
                CONTENT_TOP,
                SCREEN_WIDTH,
                CONTENT_BOTTOM - CONTENT_TOP,
                COLOR_BACKGROUND);
}

void SnackDisplay::drawCenteredText(const String& text,
                                    int16_t centerY,
                                    uint8_t textSize,
                                    uint16_t color,
                                    uint16_t background) {
  configureText(textSize, color, background);

  int16_t x1 = 0;
  int16_t y1 = 0;
  uint16_t textW = 0;
  uint16_t textH = 0;
  _tft.getTextBounds(text.c_str(), 0, 0, &x1, &y1, &textW, &textH);

  const int16_t cursorX = ((SCREEN_WIDTH - textW) / 2) - x1;
  const int16_t cursorY = centerY - (textH / 2) - y1;
  _tft.setCursor(cursorX, cursorY);
  _tft.print(text);
}

void SnackDisplay::drawRoundedCard(int16_t x,
                                   int16_t y,
                                   int16_t w,
                                   int16_t h,
                                   uint16_t fill,
                                   uint16_t outline) {
  _tft.fillRoundRect(x, y, w, h, CARD_RADIUS, fill);
  _tft.drawRoundRect(x, y, w, h, CARD_RADIUS, outline);
}

void SnackDisplay::drawStatus(const String& label, uint16_t color) {
  constexpr int16_t cardW = 184;
  constexpr int16_t cardH = 40;
  constexpr int16_t cardX = (SCREEN_WIDTH - cardW) / 2;
  constexpr int16_t cardY = 55;

  drawRoundedCard(cardX, cardY, cardW, cardH, COLOR_SURFACE, COLOR_BORDER);
  _tft.fillCircle(cardX + 18, cardY + (cardH / 2), 4, color);

  const uint8_t textSize = label.length() > 12 ? 1 : 2;
  drawCenteredText(label, cardY + (cardH / 2) + 1, textSize, color, COLOR_SURFACE);
}

void SnackDisplay::drawProgressBar(int16_t x,
                                   int16_t y,
                                   int16_t w,
                                   int16_t h,
                                   uint8_t percent,
                                   uint16_t accent) {
  percent = constrain(percent, 0, 100);

  _tft.drawRoundRect(x, y, w, h, h / 2, COLOR_BORDER);
  const int16_t innerX = x + 2;
  const int16_t innerY = y + 2;
  const int16_t innerW = w - 4;
  const int16_t innerH = h - 4;
  const int16_t fillW = (innerW * percent) / 100;

  _tft.fillRoundRect(innerX, innerY, innerW, innerH, innerH / 2, COLOR_SURFACE_DARK);
  if (fillW > 0) {
    _tft.fillRoundRect(innerX, innerY, fillW, innerH, innerH / 2, accent);
  }
}

Adafruit_ST7789& SnackDisplay::raw() {
  return _tft;
}

void SnackDisplay::configureText(uint8_t textSize,
                                 uint16_t color,
                                 uint16_t background) {
  _tft.setTextSize(textSize);
  _tft.setTextColor(color, background);
}
