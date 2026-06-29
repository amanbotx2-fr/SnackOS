# Contributing to SnackOS

Thanks for helping improve SnackOS. This project touches embedded firmware, a
Python API, and browser automation, so changes should be small, explicit, and
easy to validate.

## Local Setup

1. Install the Arduino IDE and the ESP32 Arduino core.
2. Install the firmware dependencies:
   - Adafruit GFX
   - Adafruit ST7789
   - ArduinoJson
3. Create a local firmware config:
   ```bash
   cp config.example.h config.h
   ```
4. Install the Python backend:
   ```bash
   cd server
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

## Coding Style

- Keep firmware state transitions explicit and non-blocking.
- Do not add `delay()` to runtime firmware logic.
- Keep display rendering separate from state/network logic.
- Keep Blinkit selectors and browser-specific logic inside `server/blinkit_automation.py`.
- Keep the FastAPI request/response contract stable unless the change is proposed first.
- Prefer small helpers over broad rewrites.

## Pull Request Guidelines

- Open one focused pull request per change.
- Include a short summary of what changed and why.
- Include validation steps:
  - Arduino compile target and board
  - Python compile/import check
  - Live automation result, if automation behavior changed
- Do not include generated screenshots, browser profiles, cookies, credentials, or `.venv`.
- Do not commit `config.h`; use `config.example.h` for public defaults.

## Issue Reporting

When reporting a bug, include:

- Hardware board and display model
- ESP32 Arduino core version
- Python version
- Operating system
- Backend log output
- The failing stage, if known
- Sanitized screenshots or HTML snippets when selector discovery fails

Never attach browser profiles, cookies, access tokens, or private order/account data.

