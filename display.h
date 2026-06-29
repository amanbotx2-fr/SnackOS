#ifndef SNACKOS_DISPLAY_H
#define SNACKOS_DISPLAY_H

#include <Arduino.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <SPI.h>
#include "config.h"

class SnackDisplay {
 public:
  SnackDisplay();

  void begin();
  void clear(uint16_t color = COLOR_BACKGROUND);
  void clearContentArea();

  void drawCenteredText(const String& text,
                        int16_t centerY,
                        uint8_t textSize,
                        uint16_t color,
                        uint16_t background = COLOR_BACKGROUND);
  void drawRoundedCard(int16_t x,
                       int16_t y,
                       int16_t w,
                       int16_t h,
                       uint16_t fill = COLOR_SURFACE,
                       uint16_t outline = COLOR_BORDER);
  void drawStatus(const String& label, uint16_t color);
  void drawProgressBar(int16_t x,
                       int16_t y,
                       int16_t w,
                       int16_t h,
                       uint8_t percent,
                       uint16_t accent = COLOR_LOADING);

  Adafruit_ST7789& raw();

 private:
  Adafruit_ST7789 _tft;

  void configureText(uint8_t textSize,
                     uint16_t color,
                     uint16_t background);
};

#endif
