# SnackOS API

The SnackOS backend is a local FastAPI service. It exposes a small API designed
for ESP32 firmware and local testing.

## Base URL

```text
http://<server-ip>:8000
```

When calling from the ESP32, use the LAN IP address of the machine running the
backend.

## `GET /`

Health check endpoint.

### Response

```text
SnackOS Server Running
```

## `POST /order`

Submits a shopping list to the backend. The backend controls all Blinkit
automation details.

### Request Body

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | array | yes | One or more requested products |
| `items[].query` | string | yes | Human-readable product search query |
| `items[].price` | integer | yes | Expected unit price in rupees |
| `items[].quantity` | integer | yes | Desired final cart quantity |

### Example Request

```bash
curl -X POST http://localhost:8000/order \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "query": "Uncle Chipps Spicy Treat",
        "price": 20,
        "quantity": 2
      },
      {
        "query": "Cadbury Dairy Milk Fruit & Nut",
        "price": 50,
        "quantity": 2
      }
    ]
  }'
```

### Success Response

```json
{
  "success": true,
  "checkout_ready": true,
  "items": [
    {
      "query": "Uncle Chipps Spicy Treat",
      "matched_title": "Uncle Chipps Spicy Treat Flavour Potato Chips 53 g ₹20 2",
      "price": 20,
      "quantity": 2,
      "status": "added"
    },
    {
      "query": "Cadbury Dairy Milk Fruit & Nut",
      "matched_title": "Cadbury Dairy Milk Fruit & Nut Chocolate Bar Cricket Pack 36 g ₹50 2",
      "price": 50,
      "quantity": 2,
      "status": "added"
    }
  ],
  "eta": "Blinkit Checkout Ready",
  "cart_total": "₹140",
  "message": "Cart prepared successfully."
}
```

### Error Response

```json
{
  "success": false,
  "checkout_ready": false,
  "stage": "verify_cart",
  "failed_item": {
    "query": "Uncle Chipps Spicy Treat",
    "price": 20,
    "quantity": 2
  },
  "items": [
    {
      "query": "Uncle Chipps Spicy Treat",
      "matched_title": "Uncle Chipps Spicy Treat Flavour Potato Chips 53 g ₹20 2",
      "price": 20,
      "quantity": 2,
      "status": "added"
    }
  ],
  "error": "Cart item missing for 'Cadbury Dairy Milk Fruit & Nut'.",
  "eta": "Cart item missing for 'Cadbury Dairy Milk Fruit & Nut'."
}
```

## Notes

- The API is intended for local network use.
- The API does not expose Blinkit selectors or product URLs.
- The backend serializes order handling with an async lock.
- The automation requires a manually logged-in persistent Chromium profile.

