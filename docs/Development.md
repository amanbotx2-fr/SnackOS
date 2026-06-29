# SnackOS Development Guide

This guide explains how the repository is organized and how to make changes
without breaking the separation between firmware, API, and browser automation.

## Local Development

### Firmware

1. Install Arduino IDE.
2. Install the ESP32 Arduino core.
3. Install required libraries:
   - Adafruit GFX
   - Adafruit ST7789
   - ArduinoJson
4. Copy the local configuration:
   ```bash
   cp config.example.h config.h
   ```
5. Open `SnackOS.ino` and compile for your ESP32 board.

### Backend

```bash
cd server
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Run the API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Run a compile/import check:

```bash
python3 -m py_compile server/blinkit_automation.py server/main.py
server/.venv/bin/python -c "import sys; sys.path.insert(0, 'server'); import blinkit_automation, main; print('imports ok')"
```

## Project Architecture

SnackOS has three main layers:

| Layer | Files | Responsibility |
| --- | --- | --- |
| Firmware | `*.ino`, `*.cpp`, `*.h` at repo root | Button, display, Wi-Fi, HTTP request, UI states |
| API server | `server/main.py` | Request validation, response formatting, API lock |
| Shopping engine | `server/blinkit_automation.py` | Browser automation, product matching, quantity verification |

The ESP32 should never depend on browser selectors, product URLs, or Blinkit UI
details. Those belong behind the backend.

## Folder Responsibilities

| Folder/File | Responsibility |
| --- | --- |
| `api.cpp`, `api.h` | ESP32 HTTP POST and response parsing |
| `wifi.cpp`, `wifi.h` | Wi-Fi lifecycle |
| `display.cpp`, `display.h` | ST7789 setup and low-level drawing helpers |
| `ui.cpp`, `ui.h` | UI screens and rendering behavior |
| `button.cpp`, `button.h` | Debounced hardware button state |
| `state.h` | Firmware state definitions |
| `server/main.py` | FastAPI routes and Pydantic models |
| `server/blinkit_automation.py` | Playwright runtime and shopping engine |
| `docs/` | Public project documentation |
| `.github/` | GitHub issue and pull request templates |

## Coding Conventions

### Firmware

- Keep runtime logic non-blocking.
- Avoid `delay()` outside explicitly allowed boot/debug code.
- Keep rendering separate from state transitions.
- Keep pin assignments in `config.h`.
- Do not hardcode secrets or local IPs in source files intended for public use.

### Backend

- Keep FastAPI endpoints small.
- Keep browser automation details out of API models.
- Return structured errors that identify the failing stage and item.
- Use explicit logging around major runtime actions.
- Avoid broad rewrites of selectors unless live validation proves they are needed.

### Automation

- Prefer search-driven product selection over hardcoded product URLs.
- Prefer robust locators and UI discovery over brittle absolute selectors.
- Re-read UI state after every quantity change.
- Verify cart state before clicking checkout.
- Never click payment or final order placement controls.

## Adding Another Grocery Platform

SnackOS can support another grocery platform without changing ESP32 behavior if
the backend keeps the same request/response contract.

Recommended approach:

1. Define a platform adapter boundary:
   ```text
   Shopping request
     -> platform adapter
     -> search product
     -> set quantity
     -> verify cart
     -> safe checkout-ready state
   ```
2. Keep the `/order` API shape unchanged.
3. Add a new backend adapter module, for example:
   ```text
   server/platforms/instamart.py
   server/platforms/zepto.py
   server/platforms/bigbasket.py
   ```
4. Move shared concepts into backend-only helpers:
   - request item normalization
   - product scoring
   - structured result objects
   - safety guards
5. Keep platform-specific selectors and browser flows isolated.
6. Validate each platform with a manually logged-in persistent browser profile.

### Platform Notes

| Platform | Expected Work |
| --- | --- |
| Instamart | Search/card selectors, cart drawer, checkout boundary |
| Zepto | Search result parsing, location/login handling, cart verification |
| BigBasket | Product availability handling, cart page selectors, checkout guard |

Do not add platform names, selectors, or browser details to ESP32 firmware.

## Release Checklist

- [ ] `config.h` ignored
- [ ] `server/blinkit-profile/` ignored
- [ ] `.venv/` ignored
- [ ] No debug screenshots or HTML dumps
- [ ] Python compile/import check passes
- [ ] README links reviewed
- [ ] Security notes reviewed
- [ ] Live automation validated if browser logic changed

