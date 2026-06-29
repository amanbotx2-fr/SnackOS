#ifndef SNACKOS_CONFIG_H
#define SNACKOS_CONFIG_H

#include <Arduino.h>

// SnackOS identity
constexpr const char* SNACKOS_NAME = "SnackOS";
constexpr const char* SNACKOS_VERSION = "1.0";

// Wi-Fi credentials. Copy this file to config.h and fill these locally.
constexpr const char* WIFI_SSID = "YOUR_WIFI_SSID";
constexpr const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
constexpr uint16_t WIFI_CONNECT_TIMEOUT_MS = 15000;
constexpr uint16_t WIFI_RETRY_MS = 5000;
constexpr uint16_t WIFI_CONNECTED_NOTICE_MS = 2000;

// REST API endpoint. Use the LAN IP address of the machine running FastAPI.
constexpr const char* SERVER_URL = "http://192.168.1.4:8000/order";
constexpr uint16_t API_HTTP_TIMEOUT_MS = 5000;
constexpr uint16_t ORDER_SUCCESS_NOTICE_MS = 5000;

// ESP32 Dev Module -> ST7789 pin mapping
constexpr uint8_t TFT_CS = 15;
constexpr uint8_t TFT_DC = 2;
constexpr uint8_t TFT_RST = 4;
constexpr uint8_t TFT_SCK = 18;
constexpr uint8_t TFT_MOSI = 23;

// Button wiring: INPUT_PULLUP, pressed == LOW
constexpr uint8_t BUTTON_PIN = 27;
constexpr uint16_t BUTTON_DEBOUNCE_MS = 35;
constexpr uint16_t BOOT_DURATION_MS = 2000;
constexpr uint16_t BUTTON_NOTICE_MS = 1000;

// 1.14" ST7789 panel. Init dimensions are portrait; rotation makes it 240x135.
constexpr uint16_t DISPLAY_INIT_WIDTH = 135;
constexpr uint16_t DISPLAY_INIT_HEIGHT = 240;
constexpr uint8_t DISPLAY_ROTATION = 3;
constexpr uint16_t SCREEN_WIDTH = 240;
constexpr uint16_t SCREEN_HEIGHT = 135;

// RGB565 palette tuned for a small TFT dashboard.
constexpr uint16_t COLOR_BACKGROUND = 0x0000;
constexpr uint16_t COLOR_READY_BACKGROUND = 0x0841;
constexpr uint16_t COLOR_HEADER = 0x10A2;
constexpr uint16_t COLOR_SURFACE = 0x18E3;
constexpr uint16_t COLOR_SURFACE_DARK = 0x1082;
constexpr uint16_t COLOR_SURFACE_LIGHT = 0x2965;
constexpr uint16_t COLOR_BORDER = 0x39E7;
constexpr uint16_t COLOR_TEXT = 0xFFFF;
constexpr uint16_t COLOR_MUTED = 0xA514;
constexpr uint16_t COLOR_SUCCESS = 0x07E0;
constexpr uint16_t COLOR_SUCCESS_SOFT = 0x4FEA;
constexpr uint16_t COLOR_ERROR = 0xF800;
constexpr uint16_t COLOR_LOADING = 0xFD20;
constexpr uint16_t COLOR_ACCENT = 0x04FF;
constexpr uint16_t COLOR_CHOCOLATE = 0x6200;
constexpr uint16_t COLOR_CHOCOLATE_HI = 0xA2C0;

// Layout constants
constexpr int16_t CONTENT_TOP = 24;
constexpr int16_t CONTENT_BOTTOM = 118;
constexpr int16_t CARD_RADIUS = 8;

#endif

