# SnackOS Server

FastAPI backend for SnackOS.

## Run

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn main:app --host 0.0.0.0 --port 8000
```

Blinkit login is preserved in the persistent profile directory
`server/blinkit-profile`. Run the server once with a desktop session available,
complete Blinkit login in the opened Chromium window, and then future calls can
reuse that session.

Set the ESP32 `SERVER_URL` to:

```cpp
constexpr const char* SERVER_URL = "http://<server-ip>:8000/order";
```

## API

`GET /`

Returns:

```json
"SnackOS Server Running"
```

`POST /order`

Request:

```json
{
  "device": "SnackOS",
  "button": "pressed"
}
```

Response:

```json
{
  "success": true,
  "eta": "Blinkit Checkout Ready"
}
```

The automation adds the requested products to the Blinkit cart and verifies the
cart, but it does not click the final place-order or payment button.
