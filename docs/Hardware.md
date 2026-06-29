# SnackOS Hardware

SnackOS runs on an ESP32 with a small ST7789 TFT display and one physical
button. The current firmware targets a 240x135 ST7789 panel.

## Bill of Materials

| Part | Notes |
| --- | --- |
| ESP32 Dev Module | Arduino ESP32 core compatible |
| ST7789 TFT, 240x135 | SPI display |
| Momentary push button | Connected with internal pull-up |
| Breadboard or soldered wiring | For prototyping |
| USB cable | Power, flashing, and Serial Monitor |

## Display Wiring

| Display Pin | ESP32 GPIO |
| --- | --- |
| CS | GPIO15 |
| DC | GPIO2 |
| RST | GPIO4 |
| SCK | GPIO18 |
| MOSI | GPIO23 |
| VCC | 3.3V |
| GND | GND |

The display uses hardware SPI pins for clock and MOSI. The firmware initializes
the panel as a 135x240 ST7789 and rotates it to a 240x135 landscape UI.

## Button Wiring

| Button Side | Connection |
| --- | --- |
| Side A | GPIO27 |
| Side B | GND |

The firmware configures GPIO27 as `INPUT_PULLUP`, so:

```text
released = HIGH
pressed  = LOW
```

## Display/OLED Notes

SnackOS currently ships with ST7789 TFT rendering through Adafruit GFX. If you
adapt it to an OLED display, keep the same separation between state logic and
rendering, and replace only the display driver layer.

## Power

USB power is sufficient for development. For a standalone build, use a stable
5V USB supply or a regulated battery solution suitable for the ESP32 and display
current draw.

## Required Arduino Libraries

- Adafruit GFX
- Adafruit ST7789
- ArduinoJson
- WiFi, HTTPClient, and SPI from the ESP32 Arduino core

## Firmware Configuration

Copy the example config before building:

```bash
cp config.example.h config.h
```

Then set:

```cpp
constexpr const char* WIFI_SSID = "YOUR_WIFI_SSID";
constexpr const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
constexpr const char* SERVER_URL = "http://YOUR_LOCAL_IP:8000/order";
```

Do not commit `config.h`.

