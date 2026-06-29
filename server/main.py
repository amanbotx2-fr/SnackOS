import logging
import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from blinkit_automation import (
    BlinkitAutomationError,
    ShoppingEngineError,
    run_blinkit_order,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("snackos.server")
order_lock = asyncio.Lock()

app = FastAPI(
    title="SnackOS Server",
    version="1.0.0",
    description="REST API for SnackOS devices.",
)


class ShoppingItemRequest(BaseModel):
    query: str = Field(..., min_length=1, examples=["Uncle Chipps Spicy Treat"])
    price: int = Field(..., gt=0, examples=[20])
    quantity: int = Field(..., gt=0, le=20, examples=[2])


class OrderRequest(BaseModel):
    items: list[ShoppingItemRequest] = Field(..., min_length=1)


class ShoppingItemResponse(BaseModel):
    query: str
    matched_title: str
    price: int
    quantity: int
    status: str


class OrderResponse(BaseModel):
    success: bool
    checkout_ready: bool
    items: list[ShoppingItemResponse]
    eta: str | None = None
    cart_total: str | None = None
    message: str | None = None


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    logger.info("Health check requested")
    return "SnackOS Server Running"


@app.post("/order", response_model=OrderResponse)
async def create_order(order: OrderRequest) -> OrderResponse | JSONResponse:
    logger.info("Snack request received items=%d", len(order.items))
    print("Snack request received")

    order_items = [
        item.model_dump() if hasattr(item, "model_dump") else item.dict()
        for item in order.items
    ]

    async with order_lock:
        try:
            result = await run_blinkit_order(order_items)
            return OrderResponse(
                success=True,
                checkout_ready=bool(result["checkout_ready"]),
                items=result["items"],
                eta="Blinkit Checkout Ready",
                cart_total=result.get("cart_total"),
                message=str(result.get("message", "Cart prepared successfully.")),
            )
        except ShoppingEngineError as exc:
            content = exc.to_response()
            logger.warning("Shopping engine failed: %s", content)
            print(f"Shopping engine failed: {content}")
            content["eta"] = str(exc)
            return JSONResponse(status_code=500, content=content)
        except BlinkitAutomationError as exc:
            message = f"Blinkit automation failed: {exc}"
            logger.warning(message)
            print(message)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "checkout_ready": False,
                    "items": [],
                    "eta": message,
                    "error": message,
                },
            )
        except Exception as exc:
            message = f"Unexpected Blinkit automation error: {exc}"
            logger.exception(message)
            print(message)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "checkout_ready": False,
                    "items": [],
                    "eta": message,
                    "error": message,
                },
            )
