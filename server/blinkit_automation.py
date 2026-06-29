import asyncio
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable

from playwright.async_api import Locator, Page, TimeoutError, async_playwright


logger = logging.getLogger("snackos.blinkit")

BLINKIT_HOME_URL = "https://blinkit.com/"
CART_URL = "https://blinkit.com/cart"
PROFILE_DIR = Path(
    os.getenv(
        "SNACKOS_BLINKIT_PROFILE",
        str(Path(__file__).resolve().parent / "blinkit-profile"),
    )
)
HEADLESS = os.getenv("SNACKOS_BLINKIT_HEADLESS", "false").lower() == "true"

CART_ITEM_SELECTOR = "article,li,[data-testid*='cart' i],div"
ADD_LABEL_PATTERN = re.compile(r"\badd(?:\s+to\s+cart)?\b", re.I)
CHECKOUT_LABEL_PATTERN = re.compile(r"\b(proceed|continue|checkout)\b", re.I)
CART_SUMMARY_PATTERN = re.compile(
    r"\b\d+\s+items?\b.*(?:₹|Rs\.?)|(?:₹|Rs\.?).*\b\d+\s+items?\b",
    re.I | re.S,
)
FORBIDDEN_CLICK_PATTERN = re.compile(
    r"place\s+order|proceed\s+to\s+pay|pay\s+now|payment|upi|card|net\s*banking",
    re.I,
)
LAST_SUCCESSFUL_STEP = "startup"


class BlinkitAutomationError(RuntimeError):
    pass


class AddressSelectionError(BlinkitAutomationError):
    pass


@dataclass(frozen=True)
class ProductTarget:
    index: int
    query: str
    expected_price: int
    quantity: int
    title_terms: tuple[str, ...]
    cart_terms: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.query

    def request_item(self) -> dict[str, object]:
        return {
            "query": self.query,
            "price": self.expected_price,
            "quantity": self.quantity,
        }


class ShoppingEngineError(BlinkitAutomationError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        item: dict[str, object] | None = None,
        items: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.item = item
        self.items = items or []

    def to_response(self) -> dict[str, object]:
        response: dict[str, object] = {
            "success": False,
            "checkout_ready": False,
            "stage": self.stage,
            "error": str(self),
            "items": self.items,
        }
        if self.item is not None:
            response["failed_item"] = self.item
        return response


QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "bar",
    "buy",
    "for",
    "free",
    "of",
    "pack",
    "the",
    "to",
    "with",
}


def derive_item_terms(query: str) -> tuple[str, ...]:
    terms = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) <= 2 or token in QUERY_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return tuple(terms) or (query.lower().strip(),)


def build_product_targets(items: Iterable[dict[str, object]]) -> tuple[ProductTarget, ...]:
    targets: list[ProductTarget] = []
    for index, item in enumerate(items):
        query = re.sub(r"\s+", " ", str(item.get("query", "")) or "").strip()
        price = int(item.get("price", 0))
        quantity = int(item.get("quantity", 0))
        if not query:
            raise BlinkitAutomationError(f"Item {index + 1} is missing query.")
        if price <= 0:
            raise BlinkitAutomationError(f"Item {index + 1} has invalid price: {price}.")
        if quantity <= 0:
            raise BlinkitAutomationError(
                f"Item {index + 1} has invalid quantity: {quantity}."
            )
        terms = derive_item_terms(query)
        targets.append(
            ProductTarget(
                index=index,
                query=query,
                expected_price=price,
                quantity=quantity,
                title_terms=terms,
                cart_terms=terms,
            )
        )
    if not targets:
        raise BlinkitAutomationError("Shopping list must contain at least one item.")
    return tuple(targets)


DEBUG_TARGETS = build_product_targets(
    (
        {
            "query": "Uncle Chipps Spicy Treat",
            "price": 20,
            "quantity": 2,
        },
        {
            "query": "Cadbury Dairy Milk Fruit & Nut",
            "price": 50,
            "quantity": 2,
        },
    )
)


def log_step(message: str) -> None:
    logger.info(message)
    print(f"[Blinkit] {message}", flush=True)


def timeline(action: str, message: str, successful: bool = False) -> None:
    global LAST_SUCCESSFUL_STEP
    line = f"{action}: {message}"
    logger.info(line)
    print(line, flush=True)
    if successful or action in {"FOUND", "SUCCESS"}:
        LAST_SUCCESSFUL_STEP = message


async def test_blinkit_automation() -> dict[str, object]:
    result: dict[str, object] = {
        "logged_in": False,
        "uncle_chips_page": False,
        "dairy_milk_page": False,
        "cart_opened": False,
        "items": [],
        "success": False,
    }

    log_step("SAFE TEST MODE: launching Playwright Chromium")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=HEADLESS,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(10_000)
        context_closed_by_user = False

        try:
            await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
            await wait_for_page(page)
            result["logged_in"] = await is_logged_in_without_clicking(page)
            log_step(f"Logged in: {result['logged_in']}")
            if result["logged_in"]:
                await ensure_delivery_address_selected(page)

            uncle = await find_best_product(
                page,
                DEBUG_TARGETS[0].query,
                DEBUG_TARGETS[0].expected_price,
                DEBUG_TARGETS[0].title_terms,
            )
            result["uncle_chips_page"] = bool(uncle)
            result["uncle_chips"] = uncle

            chocolate = await find_best_product(
                page,
                DEBUG_TARGETS[1].query,
                DEBUG_TARGETS[1].expected_price,
                DEBUG_TARGETS[1].title_terms,
            )
            result["dairy_milk_page"] = bool(chocolate)
            result["dairy_milk"] = chocolate

            log_step("SAFE TEST MODE: opening cart by direct URL")
            await page.goto(CART_URL, wait_until="domcontentloaded")
            await wait_for_page(page)
            result["cart_opened"] = True

            cart_snapshot = await inspect_cart_without_clicking(page)
            result["items"] = cart_snapshot["items"]
            result["cart_total"] = cart_snapshot["cart_total"]
            log_cart_snapshot(cart_snapshot)

            result["success"] = bool(
                result["logged_in"]
                and result["uncle_chips_page"]
                and result["dairy_milk_page"]
                and result["cart_opened"]
            )
            return result
        except Exception as exc:
            result["error"] = str(exc)
            await handle_automation_failure(page, exc)
            await save_failure_artifacts(page, "safe_test_failure")
            log_step(f"SAFE TEST MODE failed: {exc}")
            print(
                "Chromium is open for manual inspection. "
                "Close the browser window when finished.",
                flush=True,
            )
            await wait_for_browser_close(context)
            context_closed_by_user = True
            return result
        finally:
            if not context_closed_by_user:
                log_step("SAFE TEST MODE: closing Playwright browser context")
                await context.close()


async def login_blinkit() -> None:
    log_step("Launching Playwright Chromium for manual Blinkit login")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    playwright_manager = async_playwright()
    playwright = await playwright_manager.start()

    try:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(10_000)
        await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")

        message = (
            "Please log into Blinkit manually. "
            "Close the browser window when finished."
        )
        logger.info(message)
        print(message, flush=True)

        await wait_for_browser_close(context)
        log_step("Blinkit login browser was closed by the user")
    finally:
        await playwright.stop()


async def run_blinkit_order(
    items: Iterable[dict[str, object]],
) -> dict[str, object]:
    log_step("Launching request-driven Blinkit shopping engine")
    targets = build_product_targets(items)
    result = await prepare_cart_with_search(targets, proceed=True)
    if not result["success"] or not result["verified"] or not result["checkout_ready"]:
        raise BlinkitAutomationError(str(result))
    return result


async def stage2_add_products() -> dict[str, object]:
    log_step("STAGE 2: launching search-driven cart preparation")
    return await prepare_cart_with_search(DEBUG_TARGETS, proceed=False)


async def debug_search_flow() -> None:
    log_step("DEBUG STEP MODE: launching Playwright Chromium")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    playwright = await async_playwright().start()
    context = None
    page = None
    context_closed = False

    try:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(10_000)

        log_step("STAGE 1: verifying login and opening Blinkit home")
        await verify_logged_in(page)
        await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
        await wait_for_page(page)
        await ensure_delivery_address_selected(page)
        await save_stage_screenshot(page, "stage1_home.png")
        await debug_pause("=== STAGE 1 COMPLETE ===")

        selected_product = await debug_search_stage(
            page,
            DEBUG_TARGETS[0],
            "STAGE 2",
            "stage2_search_results.png",
        )
        await debug_pause("=== STAGE 2 COMPLETE ===")

        await debug_product_stage(
            page,
            selected_product,
            "STAGE 3",
            "stage3_product.png",
        )
        await debug_pause("=== STAGE 3 COMPLETE ===")

        await debug_add_once_stage(
            page,
            DEBUG_TARGETS[0],
            "STAGE 4",
            "stage4_added.png",
        )
        await debug_pause("=== STAGE 4 COMPLETE ===")

        await debug_quantity_stage(
            page,
            DEBUG_TARGETS[0],
            "STAGE 5",
            "stage5_quantity.png",
        )
        await debug_pause("=== STAGE 5 COMPLETE ===")

        log_step("STAGE 6: returning to Blinkit home")
        await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
        await wait_for_page(page)
        await save_stage_screenshot(page, "stage6_home.png")
        await debug_pause("=== STAGE 6 HOME COMPLETE ===")

        selected_product = await debug_search_stage(
            page,
            DEBUG_TARGETS[1],
            "STAGE 6 SEARCH",
            "stage6_search_results.png",
        )
        await debug_pause("=== STAGE 6 SEARCH COMPLETE ===")

        await debug_product_stage(
            page,
            selected_product,
            "STAGE 6 PRODUCT",
            "stage6_product.png",
        )
        await debug_pause("=== STAGE 6 PRODUCT COMPLETE ===")

        await debug_add_once_stage(
            page,
            DEBUG_TARGETS[1],
            "STAGE 6 ADD",
            "stage6_added.png",
        )
        await debug_pause("=== STAGE 6 ADD COMPLETE ===")

        await debug_quantity_stage(
            page,
            DEBUG_TARGETS[1],
            "STAGE 6 QUANTITY",
            "stage6_quantity.png",
        )
        await debug_pause("=== STAGE 6 QUANTITY COMPLETE ===")

        await debug_cart_stage(page, "stage7_cart.png")
        await debug_pause("=== STAGE 7 COMPLETE ===")

        await debug_checkout_stage(page, "stage8_checkout_button.png")
        print("Checkout button found.", flush=True)
        print("Stopping here.", flush=True)
        log_step("DEBUG STEP MODE: leaving Chromium open")

        await wait_for_browser_close(context)
        context_closed = True
    except Exception as exc:
        log_step(f"DEBUG STEP MODE stopped: {exc}")
        if page is not None:
            await handle_automation_failure(page, exc)
            await save_failure_artifacts(page, "debug_search_flow_failure")
        if context is not None:
            print(
                "Debug flow stopped. Chromium is open for inspection. "
                "Close the browser window when finished.",
                flush=True,
            )
            await wait_for_browser_close(context)
            context_closed = True
        raise
    finally:
        if context is None or context_closed:
            await playwright.stop()


async def prepare_cart_with_search(
    targets: Iterable[ProductTarget],
    proceed: bool,
) -> dict[str, object]:
    targets = tuple(targets)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    playwright_manager = async_playwright()
    playwright = await playwright_manager.start()
    context = None
    page = None
    context_closed = False

    try:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=HEADLESS,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(10_000)

        await verify_logged_in(page)
        await ensure_delivery_address_selected(page)

        item_results: list[dict[str, object]] = []
        selected_products: list[dict[str, object]] = []
        for target in targets:
            try:
                product = await find_best_product(
                    page,
                    target.query,
                    target.expected_price,
                    target.title_terms,
                )
                selected_products.append(product)
                await open_product(page, product)
                await set_quantity_exact(page, target.quantity, target.name)
            except Exception as exc:
                raise ShoppingEngineError(
                    f"Failed to add requested item {target.query!r}: {exc}",
                    stage="add_item",
                    item=target.request_item(),
                    items=item_results,
                ) from exc

            item_results.append(
                {
                    "query": target.query,
                    "matched_title": product["title"],
                    "price": target.expected_price,
                    "quantity": target.quantity,
                    "status": "added",
                }
            )
            timeline("WAITING", "returning to Blinkit home")
            await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
            await wait_for_page(page)
            timeline("SUCCESS", "returned to Blinkit home")

        await open_cart(page, targets)

        await verify_cart(page, targets, item_results)
        cart_snapshot = await inspect_cart_without_clicking(page)
        log_cart_snapshot(cart_snapshot)

        checkout_ready = False
        if proceed:
            await proceed_to_checkout(page)
            checkout_ready = True

        timeline("SUCCESS", "cart prepared successfully")
        await context.close()
        context_closed = True
        return {
            "success": True,
            "checkout_ready": checkout_ready,
            "verified": True,
            "items": item_results,
            "cart_total": cart_snapshot["cart_total"],
            "message": "Cart prepared successfully.",
        }
    except Exception as exc:
        if page is not None:
            await handle_automation_failure(page, exc)
        if context is not None:
            if isinstance(exc, AddressSelectionError):
                print(
                    "Address selection failed. Chromium is open for inspection. "
                    "Close the browser window when finished.",
                    flush=True,
                )
                await wait_for_browser_close(context)
            else:
                await context.close()
            context_closed = True
        raise
    finally:
        if context is None or context_closed:
            await playwright.stop()
        elif context is not None:
            await context.close()
            await playwright.stop()


async def verify_logged_in(page: Page) -> None:
    log_step("Opening Blinkit homepage")
    await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
    await wait_for_page(page)
    if not await is_logged_in_without_clicking(page):
        raise BlinkitAutomationError(
            "Blinkit login is required. Run login_blinkit(), log in manually, "
            "then retry the automation."
        )
    log_step("Blinkit login verified")


async def ensure_delivery_address_selected(page: Page) -> None:
    timeline("WAITING", "delivery address selection")
    await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
    await wait_for_page(page)
    await dismiss_overlays(page)

    initial_address = await read_active_delivery_address(page)
    entrypoint = await find_address_selection_entrypoint(page)
    if entrypoint is None:
        await fail_address_selection(
            page,
            "Could not find the Blinkit delivery address selector.",
        )

    await clear_debug_highlights(page)
    await highlight_locator(entrypoint, "delivery address control")
    timeline("CLICKING", "delivery address control")
    await retry_click(entrypoint, "delivery address control")
    await wait_for_page(page)

    address_area = await find_address_selection_area(page)
    if address_area is None:
        await fail_address_selection(
            page,
            "Could not detect the Blinkit address selection panel.",
        )

    await clear_debug_highlights(page)
    await highlight_locator(address_area, "address selection area")
    print("Please select the desired delivery address in Blinkit.", flush=True)
    print(
        "SnackOS will continue automatically after the active address is detected.",
        flush=True,
    )
    await wait_for_delivery_address_selection(page, initial_address)
    await wait_for_page(page)

    active_address = await read_active_delivery_address(page)
    if not active_address:
        await fail_address_selection(
            page,
            "No active delivery address could be detected after address selection.",
        )

    active_locator = page.locator("[data-snackos-active-address='true']").first
    try:
        if await active_locator.count() and await active_locator.is_visible(timeout=1_000):
            await clear_debug_highlights(page)
            await highlight_locator(active_locator, "active delivery address")
    except Exception as exc:
        timeline("WAITING", f"active address highlight skipped: {exc}")

    log_step(f"Selected delivery address: {active_address}")
    timeline("SUCCESS", "active delivery address confirmed")


async def wait_for_delivery_address_selection(
    page: Page,
    initial_address: str | None,
) -> None:
    timeline("WAITING", "user address selection in Blinkit")
    handle = await page.wait_for_function(
        """
        ({ initialAddress }) => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const insideChooser = (el) =>
            !!el.closest(
              "[role='dialog'],[aria-modal='true'],[data-snackos-address-selection-area='true']"
            );

          const pickerVisible = () => {
            const selectors = [
              "[data-snackos-address-selection-area='true']",
              "[role='dialog']",
              "[aria-modal='true']",
              "[class*='modal' i]",
              "[class*='popup' i]",
              "[class*='drawer' i]",
              "[class*='location' i]",
              "[class*='address' i]",
              "[data-testid*='location' i]",
              "[data-testid*='address' i]"
            ];

            return Array.from(document.querySelectorAll(selectors.join(",")))
              .some((el) => {
                if (!visible(el)) {
                  return false;
                }
                const text = normalize(el.innerText || el.textContent || "");
                return text.length >= 8 &&
                  /(address|location|deliver|saved|pincode|pin code|current)/i
                    .test(text);
              });
          };

          const extractAddress = (text) => {
            const lines = (text || "")
              .split(/\\n+/)
              .map((line) => normalize(line))
              .filter(Boolean);
            const details = lines.filter((line) =>
              !/(delivery\\s+in|deliver(?:ing)?\\s+to|change|select|location|address|login|search|cart|minutes?|^\\d+\\s*mins?$)/i
                .test(line)
            );
            if (details.length) {
              return details.slice(0, 2).join(" ");
            }
            if (lines.length > 1) {
              return lines.slice(1, 3).join(" ");
            }
            return "";
          };

          const activeAddress = () => {
            document
              .querySelectorAll("[data-snackos-active-address='true']")
              .forEach((el) => el.removeAttribute("data-snackos-active-address"));

            const selectors = [
              "header",
              "[role='banner']",
              "[data-testid*='location' i]",
              "[data-testid*='address' i]",
              "[class*='location' i]",
              "[class*='address' i]",
              "button",
              "[role='button']",
              "div",
              "span"
            ];
            const seen = new Set();
            const candidates = [];

            Array.from(document.querySelectorAll(selectors.join(","))).forEach((el) => {
              if (seen.has(el) || insideChooser(el) || !visible(el)) {
                return;
              }
              seen.add(el);

              const text = normalize(el.innerText || el.textContent || "");
              if (
                text.length < 6 ||
                text.length > 360 ||
                !/(delivery\\s+in|deliver(?:ing)?\\s+to|current\\s+location|selected\\s+location|address|location)/i
                  .test(text)
              ) {
                return;
              }
              if (/(login|sign in|search|cart|payment|order)/i.test(text)) {
                return;
              }

              const address = extractAddress(el.innerText || el.textContent || "");
              if (!address || address.length < 3) {
                return;
              }

              const rect = el.getBoundingClientRect();
              let score = 0;
              if (/delivery\\s+in|deliver(?:ing)?\\s+to/i.test(text)) {
                score += 45;
              }
              if (/address|location/i.test(text)) {
                score += 20;
              }
              if (rect.top >= 0 && rect.top < 180) {
                score += 35;
              }
              if (rect.left >= 0 && rect.left < window.innerWidth * 0.7) {
                score += 15;
              }
              if (el.tagName.toLowerCase() === "header" || el.getAttribute("role") === "banner") {
                score += 10;
              }
              score -= Math.min(text.length, 360) / 100;

              candidates.push({ node: el, address, score });
            });

            candidates.sort((a, b) => b.score - a.score);
            const selected = candidates[0];
            if (!selected || selected.score < 25) {
              return null;
            }

            selected.node.setAttribute("data-snackos-active-address", "true");
            return selected.address;
          };

          const currentAddress = activeAddress();
          if (!currentAddress) {
            return false;
          }

          const current = normalize(currentAddress).toLowerCase();
          const initial = normalize(initialAddress).toLowerCase();
          const pickerIsVisible = pickerVisible();

          if (!initial) {
            return {
              reason: "delivery address became active",
              address: currentAddress,
              picker_visible: pickerIsVisible
            };
          }

          if (current !== initial) {
            return {
              reason: "delivery address changed",
              address: currentAddress,
              picker_visible: pickerIsVisible
            };
          }

          if (!pickerIsVisible) {
            return {
              reason: "address picker disappeared with active address visible",
              address: currentAddress,
              picker_visible: pickerIsVisible
            };
          }

          return false;
        }
        """,
        arg={"initialAddress": initial_address or ""},
        timeout=0,
    )
    result = await handle.json_value()
    if not result or not isinstance(result, dict):
        await fail_address_selection(
            page,
            "Address selection wait ended without a valid delivery address.",
        )

    log_step(
        "Address selection detected: "
        f"{result.get('reason')} | address={result.get('address')!r}"
    )


async def find_address_selection_entrypoint(page: Page) -> Locator | None:
    timeline("WAITING", "discovering delivery address control")
    details = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const labelFor = (el) => normalize([
            el.innerText,
            el.textContent,
            el.getAttribute("aria-label"),
            el.getAttribute("title"),
            String(el.className || "")
          ].filter(Boolean).join(" "));

          document
            .querySelectorAll("[data-snackos-address-entrypoint='true']")
            .forEach((el) => el.removeAttribute("data-snackos-address-entrypoint"));

          const selectors = [
            "header",
            "[role='banner']",
            "button",
            "[role='button']",
            "a[href]",
            "[data-testid*='location' i]",
            "[data-testid*='address' i]",
            "[class*='location' i]",
            "[class*='address' i]",
            "div",
            "span"
          ];

          const seen = new Set();
          const candidates = [];

          Array.from(document.querySelectorAll(selectors.join(","))).forEach((el) => {
            if (seen.has(el) || !visible(el)) {
              return;
            }
            seen.add(el);

            const label = labelFor(el);
            const labelLower = label.toLowerCase();
            if (
              label.length < 4 ||
              label.length > 260 ||
              !/(deliver|delivery|location|address|pincode|pin code|change)/i
                .test(label)
            ) {
              return;
            }
            if (/(login|sign in|cart|search|payment|order)/i.test(label)) {
              return;
            }

            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            let score = 0;
            if (/delivery\\s+in|deliver(?:ing)?\\s+to/i.test(label)) {
              score += 45;
            }
            if (/location|address/i.test(label)) {
              score += 25;
            }
            if (/change|select/i.test(label)) {
              score += 10;
            }
            if (rect.top >= 0 && rect.top < 180) {
              score += 25;
            }
            if (rect.left >= 0 && rect.left < window.innerWidth * 0.65) {
              score += 15;
            }
            if (el.tagName.toLowerCase() === "button" || el.getAttribute("role") === "button") {
              score += 15;
            }
            if (style.cursor === "pointer") {
              score += 10;
            }
            if (style.position === "fixed" || style.position === "sticky") {
              score += 5;
            }
            score -= Math.min(label.length, 260) / 80;

            candidates.push({
              node: el,
              label,
              score,
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute("role") || "",
              top: Math.round(rect.top),
              left: Math.round(rect.left)
            });
          });

          candidates.sort((a, b) => b.score - a.score);
          const selected = candidates[0];
          if (!selected || selected.score < 20) {
            return null;
          }

          selected.node.setAttribute("data-snackos-address-entrypoint", "true");
          return {
            label: selected.label,
            score: selected.score,
            tag: selected.tag,
            role: selected.role,
            top: selected.top,
            left: selected.left,
            count: candidates.length
          };
        }
        """
    )

    if not details:
        timeline("WAITING", "no delivery address control candidate found")
        return None

    log_step(
        "Selected delivery address control: "
        f"text={details['label']!r}, tag={details['tag']}, "
        f"role={details['role']!r}, score={float(details['score']):.1f}, "
        f"candidates={details['count']}"
    )
    return page.locator("[data-snackos-address-entrypoint='true']").first


async def find_address_selection_area(page: Page) -> Locator | None:
    timeline("WAITING", "detecting address chooser or location picker")
    details = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          document
            .querySelectorAll("[data-snackos-address-selection-area='true']")
            .forEach((el) => el.removeAttribute("data-snackos-address-selection-area"));

          const selectors = [
            "[role='dialog']",
            "[aria-modal='true']",
            "[class*='modal' i]",
            "[class*='popup' i]",
            "[class*='drawer' i]",
            "[class*='location' i]",
            "[class*='address' i]",
            "[data-testid*='location' i]",
            "[data-testid*='address' i]",
            "section",
            "aside",
            "div"
          ];

          const seen = new Set();
          const candidates = [];

          Array.from(document.querySelectorAll(selectors.join(","))).forEach((el) => {
            if (seen.has(el) || !visible(el)) {
              return;
            }
            seen.add(el);

            const text = normalize(el.innerText || el.textContent || "");
            if (
              text.length < 8 ||
              text.length > 1800 ||
              !/(address|location|deliver|saved|pincode|pin code|current)/i.test(text)
            ) {
              return;
            }

            const rect = el.getBoundingClientRect();
            const role = el.getAttribute("role") || "";
            const ariaModal = el.getAttribute("aria-modal") || "";
            let score = 0;
            if (role === "dialog" || ariaModal === "true") {
              score += 70;
            }
            if (/select\\s+(delivery\\s+)?location|choose\\s+address|saved\\s+addresses/i.test(text)) {
              score += 60;
            }
            if (/detect\\s+current\\s+location|use\\s+current\\s+location|enter\\s+(area|pincode|pin code|location)/i.test(text)) {
              score += 45;
            }
            if (/address|location/i.test(text)) {
              score += 20;
            }
            if (rect.width > 260 && rect.height > 160) {
              score += 20;
            }
            if (rect.top > 40 && rect.top < window.innerHeight * 0.9) {
              score += 10;
            }
            if (text.length > 900) {
              score -= 20;
            }

            candidates.push({
              node: el,
              text,
              score,
              tag: el.tagName.toLowerCase(),
              role,
              top: Math.round(rect.top),
              left: Math.round(rect.left),
              width: Math.round(rect.width),
              height: Math.round(rect.height)
            });
          });

          candidates.sort((a, b) => b.score - a.score);
          const selected = candidates[0];
          if (!selected || selected.score < 45) {
            return null;
          }

          selected.node.setAttribute("data-snackos-address-selection-area", "true");
          return {
            text: selected.text.slice(0, 220),
            score: selected.score,
            tag: selected.tag,
            role: selected.role,
            top: selected.top,
            left: selected.left,
            width: selected.width,
            height: selected.height,
            count: candidates.length
          };
        }
        """
    )

    if not details:
        timeline("WAITING", "no address chooser or location picker detected")
        return None

    log_step(
        "Address selection area detected: "
        f"tag={details['tag']}, role={details['role']!r}, "
        f"score={float(details['score']):.1f}, text={details['text']!r}"
    )
    return page.locator("[data-snackos-address-selection-area='true']").first


async def read_active_delivery_address(page: Page) -> str | None:
    timeline("VERIFYING", "active delivery address")
    details = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const insideChooser = (el) =>
            !!el.closest(
              "[role='dialog'],[aria-modal='true'],[data-snackos-address-selection-area='true']"
            );

          const extractAddress = (text) => {
            const lines = (text || "")
              .split(/\\n+/)
              .map((line) => normalize(line))
              .filter(Boolean);
            const details = lines.filter((line) =>
              !/(delivery\\s+in|deliver(?:ing)?\\s+to|change|select|location|address|login|search|cart|minutes?|^\\d+\\s*mins?$)/i
                .test(line)
            );
            if (details.length) {
              return details.slice(0, 2).join(" ");
            }
            if (lines.length > 1) {
              return lines.slice(1, 3).join(" ");
            }
            return "";
          };

          document
            .querySelectorAll("[data-snackos-active-address='true']")
            .forEach((el) => el.removeAttribute("data-snackos-active-address"));

          const selectors = [
            "header",
            "[role='banner']",
            "[data-testid*='location' i]",
            "[data-testid*='address' i]",
            "[class*='location' i]",
            "[class*='address' i]",
            "button",
            "[role='button']",
            "div",
            "span"
          ];
          const seen = new Set();
          const candidates = [];

          Array.from(document.querySelectorAll(selectors.join(","))).forEach((el) => {
            if (seen.has(el) || insideChooser(el) || !visible(el)) {
              return;
            }
            seen.add(el);

            const text = normalize(el.innerText || el.textContent || "");
            if (
              text.length < 6 ||
              text.length > 360 ||
              !/(delivery\\s+in|deliver(?:ing)?\\s+to|current\\s+location|selected\\s+location|address|location)/i
                .test(text)
            ) {
              return;
            }
            if (/(login|sign in|search|cart|payment|order)/i.test(text)) {
              return;
            }

            const address = extractAddress(el.innerText || el.textContent || "");
            if (!address || address.length < 3) {
              return;
            }

            const rect = el.getBoundingClientRect();
            let score = 0;
            if (/delivery\\s+in|deliver(?:ing)?\\s+to/i.test(text)) {
              score += 45;
            }
            if (/address|location/i.test(text)) {
              score += 20;
            }
            if (rect.top >= 0 && rect.top < 180) {
              score += 35;
            }
            if (rect.left >= 0 && rect.left < window.innerWidth * 0.7) {
              score += 15;
            }
            if (el.tagName.toLowerCase() === "header" || el.getAttribute("role") === "banner") {
              score += 10;
            }
            score -= Math.min(text.length, 360) / 100;

            candidates.push({
              node: el,
              text,
              address,
              score,
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute("role") || ""
            });
          });

          candidates.sort((a, b) => b.score - a.score);
          const selected = candidates[0];
          if (!selected || selected.score < 25) {
            return null;
          }

          selected.node.setAttribute("data-snackos-active-address", "true");
          return {
            address: selected.address,
            text: selected.text,
            score: selected.score,
            tag: selected.tag,
            role: selected.role,
            count: candidates.length
          };
        }
        """
    )

    if not details:
        timeline("WAITING", "no active delivery address detected")
        return None

    log_step(
        "Active delivery address detected: "
        f"text={details['address']!r}, score={float(details['score']):.1f}, "
        f"source_tag={details['tag']}, source_role={details['role']!r}"
    )
    return str(details["address"])


async def fail_address_selection(page: Page, message: str) -> None:
    await save_failure_artifacts(page, "address_selection_failure")
    raise AddressSelectionError(message)


async def search_product(page: Page, query: str) -> list[dict[str, object]]:
    timeline("WAITING", f"opening Blinkit home before search: {query}")
    await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
    await wait_for_page(page)
    await dismiss_overlays(page)
    timeline("SUCCESS", "Blinkit home rendered")

    search_box = await find_search_box(page)
    await clear_and_type_search(page, search_box, query)
    await wait_for_search_results(page, query)

    products = await find_product_cards(page)
    timeline("FOUND", f"visible product cards: {len(products)}")
    for product in products:
        print("Product:", flush=True)
        print(f"Title: {product['title']}", flush=True)
        print(f"Price: {product['price_text']}", flush=True)
        print(f"Availability: {product['availability']}", flush=True)
        print(f"Add button present: {product['add_button_present']}", flush=True)
        print(f"Bounding box: {product['bounding_box']}", flush=True)
        print(f"Visible: {product['visible']}", flush=True)
    return products


async def find_best_product(
    page: Page,
    query: str,
    expected_price: int,
    required_terms: Iterable[str],
) -> dict[str, object]:
    products = await search_product(page, query)
    product = select_best_product(products, query, expected_price, required_terms)
    timeline(
        "FOUND",
        "selected product: "
        f"{product['title']!r}, {product['price_text']!r}, "
        f"score={product['score']:.0f}",
    )
    await clear_debug_highlights(page)
    await highlight_locator(
        page.locator(f"[data-snackos-product-index='{product['product_index']}']"),
        "selected product card",
    )
    await save_stage_screenshot(page, "stage_product_selection.png")
    return product


def select_best_product(
    products: list[dict[str, object]],
    query: str,
    expected_price: int,
    required_terms: Iterable[str],
) -> dict[str, object]:
    ranked = rank_product_cards(products, query, expected_price, required_terms)
    print("Product ranking:", flush=True)
    for product in ranked:
        print(f"Score {product['score']:.0f}", flush=True)
        print(product["price_text"] or "price unavailable", flush=True)
        print(product["title"], flush=True)

    if not ranked:
        raise BlinkitAutomationError(
            f"No visible product matched query={query!r}, "
            f"expected_price=₹{expected_price}."
        )

    best = ranked[0]
    if best.get("price_value") != expected_price:
        raise BlinkitAutomationError(
            f"No visible product for query={query!r} matched "
            f"expected price ₹{expected_price}. Best candidate was "
            f"{best['title']!r} at {best.get('price_text') or 'unknown price'}."
        )
    if float(best["score"]) < 60.0:
        raise BlinkitAutomationError(
            f"No confident product match for query={query!r}. "
            f"Best candidate was {best['title']!r} with score "
            f"{float(best['score']):.0f}."
        )

    return best


def rank_product_cards(
    products: list[dict[str, object]],
    query: str,
    expected_price: int,
    required_terms: Iterable[str],
) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for product in products:
        scored_product = dict(product)
        scored_product["score"] = score_product_card(
            product,
            query,
            expected_price,
            required_terms,
        )
        ranked.append(scored_product)

    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return ranked


def score_product_card(
    product: dict[str, object],
    query: str,
    expected_price: int,
    required_terms: Iterable[str],
) -> float:
    title = str(product.get("title", ""))
    text = str(product.get("text", ""))
    searchable = f"{title} {text}".lower()
    required = tuple(term.lower() for term in required_terms)
    keyword_matches = sum(1 for term in required if term in searchable)
    keyword_score = keyword_matches / max(len(required), 1)
    exact_price_score = 1.0 if product.get("price_value") == expected_price else 0.0
    availability_score = 1.0
    if "out" in str(product.get("availability", "")).lower():
        availability_score = 0.0
    return (
        score_product(title, query) * 45.0
        + exact_price_score * 35.0
        + keyword_score * 15.0
        + availability_score * 5.0
    )


async def open_product(page: Page, product: dict[str, object]) -> None:
    timeline("CLICKING", f"opening selected product: {product['title']}")
    card = await locate_selected_product_card(page, product)
    title = str(product["title"])

    try:
        title_locator = card.get_by_text(re.compile(re.escape(title), re.I)).first
        if await title_locator.is_visible(timeout=1_000):
            await retry_click(title_locator, "selected product title")
        else:
            await retry_click(card, "selected product card")
    except Exception:
        await retry_click(card, "selected product card")

    await wait_for_page(page)
    await assert_product_page_loaded(page, product)
    timeline("SUCCESS", f"product page opened: {product['title']}")


async def locate_selected_product_card(
    page: Page,
    product: dict[str, object],
) -> Locator:
    marker = page.locator(f"[data-snackos-product-index='{product['product_index']}']")
    try:
        if await marker.count() and await marker.first.is_visible(timeout=750):
            return marker.first
    except Exception:
        pass

    timeline("WAITING", "selected product marker was stale; rediscovering cards")
    await wait_for_selected_product_card(page, product)
    products = await find_product_cards(page)
    target_title = normalize_text(str(product["title"])).lower()
    target_price = product.get("price_value")

    best_match: dict[str, object] | None = None
    best_score = -1.0
    for candidate in products:
        title = normalize_text(str(candidate["title"])).lower()
        price_bonus = 1.0 if candidate.get("price_value") == target_price else 0.0
        title_score = SequenceMatcher(None, title, target_title).ratio()
        score = title_score + price_bonus
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_match is None or best_score < 1.35:
        raise BlinkitAutomationError(
            f"Could not re-locate selected product card for {product['title']!r}."
        )

    timeline(
        "FOUND",
        f"re-located selected product card: {best_match['title']} "
        f"score={best_score:.2f}",
    )
    product["product_index"] = best_match["product_index"]
    return page.locator(
        f"[data-snackos-product-index='{best_match['product_index']}']"
    )


async def wait_for_selected_product_card(
    page: Page,
    product: dict[str, object],
) -> None:
    target_price = product.get("price_value")
    tokens = [
        token
        for token in tokenize(str(product["title"]))
        if len(token) > 2 and token not in {"with", "and", "the", "bar", "pack"}
    ][:6]
    try:
        await page.wait_for_function(
            """
            ({ tokens, targetPrice }) => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== "hidden" &&
                  style.display !== "none";
              };
              const normalize = (value) =>
                (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
              const priceValue = (text) => {
                const match = text.match(/(?:₹|Rs\\.?\\s*)\\s*(\\d+)(?:\\.\\d{1,2})?/i);
                return match ? Number(match[1]) : null;
              };
              const selectors = [
                "article",
                "li",
                "[role='listitem']",
                "[data-testid*='product' i]",
                "[class*='product' i]",
                "div"
              ];
              const minMatches = Math.min(Math.max(tokens.length, 1), 2);
              return Array.from(document.querySelectorAll(selectors.join(",")))
                .some((node) => {
                  if (!visible(node)) {
                    return false;
                  }
                  const text = normalize(node.innerText || node.textContent || "");
                  if (text.length < 12 || text.length > 900) {
                    return false;
                  }
                  if (targetPrice !== null && priceValue(text) !== targetPrice) {
                    return false;
                  }
                  const matches = tokens.filter((token) =>
                    text.includes(String(token).toLowerCase())
                  ).length;
                  return matches >= minMatches;
                });
            }
            """,
            arg={"tokens": tokens, "targetPrice": target_price},
            timeout=12_000,
        )
        await wait_for_page(page)
    except TimeoutError as exc:
        raise BlinkitAutomationError(
            f"Selected product card did not re-render for {product['title']!r}."
        ) from exc


async def set_quantity_exact(page: Page, quantity: int, product_name: str) -> None:
    current_quantity = await read_visible_quantity(page)
    log_step(f"Current quantity for {product_name}: {current_quantity}")

    if current_quantity is None:
        log_step(f"{product_name} is not in cart from product page; clicking Add")
        await click_add(page)
        current_quantity = await wait_for_any_product_quantity(page, product_name)

    while current_quantity < quantity:
        next_quantity = current_quantity + 1
        log_step(
            f"Increasing {product_name} quantity "
            f"from {current_quantity} to {next_quantity}"
        )
        await click_increment(page)
        current_quantity = await wait_for_product_quantity(
            page, next_quantity, product_name
        )

    while current_quantity > quantity:
        next_quantity = current_quantity - 1
        log_step(
            f"Decreasing {product_name} quantity "
            f"from {current_quantity} to {next_quantity}"
        )
        await click_decrement(page)
        current_quantity = await wait_for_product_quantity(
            page, next_quantity, product_name
        )

    if current_quantity != quantity:
        raise BlinkitAutomationError(
            f"{product_name} quantity verification failed on product page. "
            f"Expected {quantity}, got {current_quantity}."
        )

    log_step(f"{product_name} quantity is exactly {quantity}")


async def verify_cart(
    page: Page,
    targets: Iterable[ProductTarget],
    item_results: list[dict[str, object]],
) -> None:
    log_step("Verifying cart contents and quantities")
    cart_snapshot = await inspect_cart_without_clicking(page)
    items_by_index = {
        int(index): item for index, item in enumerate(item_results)
    }

    for target in targets:
        item_result = items_by_index.get(target.index)
        matched_title = (
            str(item_result.get("matched_title", "")) if item_result else target.query
        )
        matched_item = find_matching_cart_item(
            cart_snapshot["items"],
            target,
            matched_title,
        )

        if matched_item is None:
            raise ShoppingEngineError(
                f"Cart item missing for {target.query!r}.",
                stage="verify_cart",
                item=target.request_item(),
                items=item_results,
            )

        if matched_item["quantity"] != target.quantity:
            raise ShoppingEngineError(
                f"Could not verify quantity {target.quantity} for {target.name}. "
                f"Detected quantity: {matched_item['quantity']}. "
                f"Visible cart items: {cart_snapshot['items']!r}",
                stage="verify_cart",
                item=target.request_item(),
                items=item_results,
            )

        log_step(f"Verified {target.name}: quantity {target.quantity}")


def find_matching_cart_item(
    cart_items: Iterable[dict[str, object]],
    target: ProductTarget,
    matched_title: str,
) -> dict[str, object] | None:
    best_item: dict[str, object] | None = None
    best_score = 0.0
    for item in cart_items:
        product_name = str(item.get("product_name", ""))
        product_name_lower = product_name.lower()
        price_value = parse_price_value(str(item.get("price_text", "")))
        term_matches = sum(
            1 for term in target.cart_terms if term.lower() in product_name_lower
        )
        term_score = term_matches / max(len(target.cart_terms), 1)
        score = (
            score_product(product_name, matched_title) * 55.0
            + score_product(product_name, target.query) * 25.0
            + term_score * 10.0
        )
        if price_value == target.expected_price:
            score += 10.0

        if score > best_score:
            best_score = score
            best_item = item

    if best_item is None or best_score < 45.0:
        return None
    return best_item


def parse_price_value(price_text: str) -> int | None:
    match = re.search(r"(?:₹|Rs\.?\s*)\s*(\d+)(?:\.\d{1,2})?", price_text, re.I)
    return int(match.group(1)) if match else None


async def open_cart(page: Page, targets: Iterable[ProductTarget]) -> None:
    timeline("WAITING", "opening cart from visible cart summary")
    await page.goto(BLINKIT_HOME_URL, wait_until="domcontentloaded")
    await wait_for_page(page)
    await dismiss_overlays(page)
    cart_button = await find_cart_summary_control(page)
    timeline("CLICKING", "cart summary control")
    await assert_safe_to_click(cart_button, "cart summary control")
    await retry_click(cart_button, "cart summary control")
    await wait_for_cart_contents(page, targets)
    timeline("SUCCESS", "cart contents opened")


async def find_cart_summary_control(page: Page) -> Locator:
    timeline("WAITING", "discovering cart summary control")
    candidates = await collect_control_candidates(page)
    matches = [
        candidate
        for candidate in candidates
        if candidate["visible"]
        and candidate["enabled"]
        and CART_SUMMARY_PATTERN.search(str(candidate["label"]))
        and not FORBIDDEN_CLICK_PATTERN.search(str(candidate["label"]))
    ]

    def score_cart_candidate(candidate: dict[str, object]) -> float:
        outer_html = str(candidate.get("outerHTML", ""))
        label = normalize_text(str(candidate["label"]))
        score = 0.0
        if "CartButton__Button" in outer_html:
            score += 100.0
        if "CartButton__Container" in outer_html:
            score += 70.0
        if "Header__HeaderRight" in outer_html:
            score -= 30.0
        if len(label) <= 80:
            score += 20.0
        score -= min(len(label), 500) / 100.0
        return score

    matches.sort(key=score_cart_candidate, reverse=True)

    print("Trying selector:", flush=True)
    print("multi-strategy control discovery + cart summary predicate", flush=True)
    print("Count:", flush=True)
    print(len(matches), flush=True)
    print("Visible:", flush=True)
    print(bool(matches), flush=True)
    print("Enabled:", flush=True)
    print(bool(matches), flush=True)

    if not matches:
        await diagnose_control_failure(
            page,
            "cart summary control",
            "multi-strategy control discovery",
            candidates,
        )
        raise BlinkitAutomationError("Could not find visible cart summary control.")

    selected = matches[0]
    log_step(
        f"Selected cart summary control: text={selected['label']!r}, "
        f"tag={selected['tag']}, role={selected['role']!r}, "
        f"score={score_cart_candidate(selected):.1f}"
    )
    return page.locator(
        f"[data-snackos-control-index='{selected['control_index']}']"
    )


async def wait_for_cart_contents(
    page: Page,
    targets: Iterable[ProductTarget],
    timeout_ms: int = 12_000,
) -> None:
    target_count = len(tuple(targets))
    try:
        await page.wait_for_function(
            """
            ({ targetCount }) => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== "hidden" &&
                  style.display !== "none";
              };
              const productRows = Array.from(
                document.querySelectorAll(
                  "[class*='CartProduct__Container' i], [class*='DefaultProductCard__Container' i]"
                )
              ).filter(visible);
              const text = document.body.innerText || "";
              return /my\\s+cart/i.test(text) &&
                productRows.length >= Math.max(1, targetCount);
            }
            """,
            arg={"targetCount": target_count},
            timeout=timeout_ms,
        )
        await wait_for_page(page)
    except TimeoutError as exc:
        raise BlinkitAutomationError(
            "Cart contents did not become visible after clicking the cart summary."
        ) from exc


async def proceed_to_checkout(page: Page) -> None:
    timeline("WAITING", "safe checkout proceed/continue control")
    checkout_button = await find_checkout_button(page)
    timeline("CLICKING", "checkout proceed/continue control")
    await assert_safe_to_click(checkout_button, "checkout proceed/continue control")
    await retry_click(checkout_button, "checkout proceed/continue control")
    await wait_for_page(page)
    timeline("SUCCESS", "stopped after safe checkout proceed/continue action")


async def debug_search_stage(
    page: Page,
    target: ProductTarget,
    stage_name: str,
    screenshot_path: str,
) -> dict[str, object]:
    log_step(f"{stage_name}: searching for {target.query}")
    products = await search_product(page, target.query)
    if not products:
        raise BlinkitAutomationError(f"{stage_name}: no product cards detected.")

    await clear_debug_highlights(page)
    await highlight_product_cards(page, products)

    print(f"{stage_name}: product cards = {len(products)}", flush=True)
    for product in products:
        score = score_product(str(product["title"]), target.query)
        print(
            "Product card:",
            flush=True,
        )
        print(f"title = {product['title']}", flush=True)
        print(f"price = {product['price_text']}", flush=True)
        print(f"similarity = {score:.3f}", flush=True)

    selected = select_best_product(
        products,
        target.query,
        target.expected_price,
        target.title_terms,
    )
    print("selected winner:", flush=True)
    print(f"title = {selected['title']}", flush=True)
    print(f"price = {selected['price_text']}", flush=True)
    print(
        f"similarity = {score_product(str(selected['title']), target.query):.3f}",
        flush=True,
    )

    await save_stage_screenshot(page, screenshot_path)
    return selected


async def debug_product_stage(
    page: Page,
    product: dict[str, object],
    stage_name: str,
    screenshot_path: str,
) -> None:
    log_step(f"{stage_name}: opening selected product")
    await open_product(page, product)
    await clear_debug_highlights(page)

    title_locator = await find_visible_product_title(page, str(product["title"]))
    price_locator = await find_visible_price(page, int(product["price_value"]))
    add_locator = await find_add_button_for_debug(page)

    await highlight_locator(title_locator, "product title")
    await highlight_locator(price_locator, "product price")
    await highlight_locator(add_locator, "add button")
    await print_product_page_selectors(page, product)
    await save_stage_screenshot(page, screenshot_path)


async def debug_add_once_stage(
    page: Page,
    target: ProductTarget,
    stage_name: str,
    screenshot_path: str,
) -> None:
    log_step(f"{stage_name}: clicking Add exactly once for {target.name}")
    await click_add(page)
    quantity = await wait_for_product_quantity(page, 1, target.name)
    controls = await find_quantity_controls(page)
    await clear_debug_highlights(page)
    await highlight_locator(controls["minus"], "minus quantity control")
    await highlight_locator(controls["quantity"], "quantity value")
    await highlight_locator(controls["plus"], "plus quantity control")
    print(f"Detected quantity: {quantity}", flush=True)
    await save_stage_screenshot(page, screenshot_path)


async def debug_quantity_stage(
    page: Page,
    target: ProductTarget,
    stage_name: str,
    screenshot_path: str,
) -> None:
    log_step(f"{stage_name}: increasing {target.name} quantity to exactly 2")
    current_quantity = await read_visible_quantity(page)
    if current_quantity is None:
        raise BlinkitAutomationError(
            f"{stage_name}: no visible quantity control for {target.name}."
        )
    if current_quantity > target.quantity:
        raise BlinkitAutomationError(
            f"{stage_name}: quantity is already {current_quantity}; "
            f"debug mode only increases to {target.quantity}."
        )

    while current_quantity < target.quantity:
        print(f"Quantity {current_quantity}", flush=True)
        print("Click +", flush=True)
        await click_increment(page)
        current_quantity = await wait_for_product_quantity(
            page,
            current_quantity + 1,
            target.name,
        )

    print(f"Quantity {current_quantity}", flush=True)
    if current_quantity != target.quantity:
        raise BlinkitAutomationError(
            f"{stage_name}: expected quantity {target.quantity}, "
            f"got {current_quantity}."
        )

    controls = await find_quantity_controls(page)
    await clear_debug_highlights(page)
    await highlight_locator(controls["minus"], "minus quantity control")
    await highlight_locator(controls["quantity"], "quantity value")
    await highlight_locator(controls["plus"], "plus quantity control")
    await save_stage_screenshot(page, screenshot_path)


async def debug_cart_stage(page: Page, screenshot_path: str) -> None:
    log_step("STAGE 7: opening and verifying cart")
    await open_cart(page, DEBUG_TARGETS)
    await clear_debug_highlights(page)

    cart_items = await collect_cart_debug_items(page)
    print("STAGE 7 cart items:", flush=True)
    for item in cart_items:
        print(f"title = {item['product_name']}", flush=True)
        print(f"quantity = {item['quantity']}", flush=True)
        print(f"price = {item['price_text']}", flush=True)

    for target in DEBUG_TARGETS:
        item = find_debug_cart_match(cart_items, target)
        if item is None:
            raise BlinkitAutomationError(f"STAGE 7: missing cart item {target.name}.")
        if item["quantity"] != target.quantity:
            raise BlinkitAutomationError(
                f"STAGE 7: {target.name} expected quantity {target.quantity}, "
                f"got {item['quantity']}."
            )
        await highlight_locator(
            page.locator(CART_ITEM_SELECTOR).nth(int(item["source_index"])),
            f"cart item {target.name}",
        )

    await save_stage_screenshot(page, screenshot_path)


async def debug_checkout_stage(page: Page, screenshot_path: str) -> None:
    log_step("STAGE 8: locating checkout button without clicking")
    await clear_debug_highlights(page)
    checkout = await find_checkout_button_for_debug(page)
    await highlight_locator(checkout, "checkout button")
    await save_stage_screenshot(page, screenshot_path)


async def debug_pause(stage_message: str) -> None:
    print(stage_message, flush=True)
    print("Press ENTER in terminal to continue...", flush=True)
    await asyncio.to_thread(input)


async def wait_for_browser_close(context) -> None:
    try:
        if not context.pages:
            return
    except Exception:
        return

    try:
        await context.wait_for_event("close", timeout=0)
    except Exception:
        return


async def save_stage_screenshot(page: Page, screenshot_path: str) -> None:
    await page.screenshot(path=screenshot_path, full_page=True)
    log_step(f"Saved stage screenshot: {screenshot_path}")


async def clear_debug_highlights(page: Page) -> None:
    await page.evaluate(
        """
        () => {
          document
            .querySelectorAll("[data-snackos-debug-highlight='true']")
            .forEach((el) => {
              el.style.outline = "";
              el.style.boxShadow = "";
              el.style.position = el.getAttribute("data-snackos-original-position") || "";
              el.removeAttribute("data-snackos-original-position");
              el.removeAttribute("data-snackos-debug-highlight");
            });
        }
        """
    )


async def highlight_locator(locator: Locator, label: str) -> None:
    if not await locator.is_visible(timeout=2_000):
        raise BlinkitAutomationError(f"Could not highlight invisible {label}.")
    await locator.scroll_into_view_if_needed(timeout=2_000)
    await locator.evaluate(
        """
        (el, label) => {
          if (!el.hasAttribute("data-snackos-original-position")) {
            el.setAttribute(
              "data-snackos-original-position",
              window.getComputedStyle(el).position
            );
          }
          if (window.getComputedStyle(el).position === "static") {
            el.style.position = "relative";
          }
          el.setAttribute("data-snackos-debug-highlight", "true");
          el.style.outline = "4px solid #ff0000";
          el.style.boxShadow = "0 0 0 5px rgba(255, 0, 0, 0.25)";
          el.style.zIndex = "2147483647";
          el.dataset.snackosDebugLabel = label;
        }
        """,
        label,
    )
    log_step(f"Highlighted {label}")


async def highlight_product_cards(
    page: Page,
    products: list[dict[str, object]],
) -> None:
    for product in products:
        await highlight_locator(
            page.locator(f"[data-snackos-product-index='{product['product_index']}']"),
            f"product card: {product['title']}",
        )


async def find_visible_product_title(page: Page, title: str) -> Locator:
    patterns = [re.compile(re.escape(title), re.I)]
    title_tokens = [token for token in tokenize(title) if len(token) > 3]
    if title_tokens:
        patterns.append(re.compile(r".*".join(map(re.escape, title_tokens[:4])), re.I))

    for pattern in patterns:
        locator = page.get_by_text(pattern)
        count = await locator.count()
        for index in range(max(1, min(count, 8))):
            candidate = locator if count == 0 else locator.nth(index)
            try:
                if await candidate.is_visible(timeout=750):
                    return candidate
            except Exception:
                continue

    raise BlinkitAutomationError(f"Could not find visible product title: {title!r}.")


async def find_visible_price(page: Page, price: int) -> Locator:
    price_pattern = re.compile(rf"(?:₹|Rs\.?\s*)\s*{price}(?:\D|$)", re.I)
    locator = page.get_by_text(price_pattern)
    count = await locator.count()
    for index in range(max(1, min(count, 12))):
        candidate = locator if count == 0 else locator.nth(index)
        try:
            if await candidate.is_visible(timeout=750):
                return candidate
        except Exception:
            continue

    raise BlinkitAutomationError(f"Could not find visible price: ₹{price}.")


async def find_add_button_for_debug(page: Page) -> Locator:
    return await find_add_button(page)


async def find_checkout_button_for_debug(page: Page) -> Locator:
    return await find_checkout_button(page)


async def find_add_button(page: Page) -> Locator:
    return await find_control_for_debug(
        page,
        lambda label: bool(ADD_LABEL_PATTERN.search(label)),
        "Add button",
    )


async def find_checkout_button(page: Page) -> Locator:
    return await find_control_for_debug(
        page,
        lambda label: bool(CHECKOUT_LABEL_PATTERN.search(label)),
        "checkout button",
    )


async def find_control_for_debug(
    page: Page,
    predicate: Callable[[str], bool],
    description: str,
) -> Locator:
    timeline("WAITING", f"discovering {description}")
    candidates = await collect_control_candidates(page)
    matches = [
        candidate
        for candidate in candidates
        if candidate["visible"]
        and candidate["enabled"]
        and predicate(str(candidate["label"]))
        and not FORBIDDEN_CLICK_PATTERN.search(str(candidate["label"]))
    ]
    matches.sort(key=score_control_candidate, reverse=True)

    print("Trying selector:", flush=True)
    print(f"multi-strategy control discovery + {description} predicate", flush=True)
    print("Count:", flush=True)
    print(len(matches), flush=True)
    print("Visible:", flush=True)
    print(bool(matches), flush=True)
    print("Enabled:", flush=True)
    print(bool(matches), flush=True)

    if not matches:
        await diagnose_control_failure(
            page,
            description,
            "multi-strategy control discovery",
            candidates,
        )
        raise BlinkitAutomationError(f"Could not find visible {description}.")

    selected = matches[0]
    print(
        f"Selected {description}: index={selected['index']} "
        f"strategy={selected['strategy']} text={selected['label']!r}",
        flush=True,
    )
    timeline("FOUND", f"{description}: {selected['label']!r}")
    return page.locator(f"[data-snackos-control-index='{selected['control_index']}']")


async def print_product_page_selectors(
    page: Page,
    product: dict[str, object],
) -> None:
    candidates = await collect_control_candidates(page)
    print("Detected selectors:", flush=True)
    print(
        f"title = get_by_text(/{re.escape(str(product['title']))}/i)",
        flush=True,
    )
    print(
        f"price = get_by_text(/(?:₹|Rs\\\\.?\\\\s*)\\\\s*{product['price_value']}/i)",
        flush=True,
    )
    for candidate in candidates:
        label = str(candidate["label"])
        if candidate["visible"] and ADD_LABEL_PATTERN.search(label):
            print("add selector candidate:", flush=True)
            print(
                "selector = "
                f"[data-snackos-control-index='{candidate['control_index']}']",
                flush=True,
            )
            print(f"text = {label}", flush=True)
            print(f"role = {candidate['role'] or candidate['tag']}", flush=True)
            print(f"outerHTML = {candidate['outerHTML']}", flush=True)


async def find_quantity_controls(page: Page) -> dict[str, Locator]:
    timeline("WAITING", "discovering quantity controls")
    if await mark_icon_quantity_controls(page):
        timeline("FOUND", "icon quantity stepper controls")
        return {
            "minus": page.locator("[data-snackos-qty-minus='true']").first,
            "quantity": page.locator("[data-snackos-qty-value='true']").first,
            "plus": page.locator("[data-snackos-qty-plus='true']").first,
        }

    candidates = await collect_control_candidates(page)

    def choose(
        predicate: Callable[[str], bool],
        description: str,
    ) -> dict[str, object]:
        matches = [
            candidate
            for candidate in candidates
            if candidate["visible"]
            and candidate["enabled"]
            and predicate(str(candidate["label"]))
        ]
        matches.sort(key=score_control_candidate, reverse=True)
        if not matches:
            raise BlinkitAutomationError(f"Could not find visible {description}.")
        return matches[0]

    minus = choose(
        lambda label: bool(re.search(r"(^|\s)[-−](\s|$)|minus|decrease", label, re.I)),
        "minus quantity control",
    )
    plus = choose(
        lambda label: bool(re.search(r"(^|\s)\+(\s|$)|plus|increase", label, re.I)),
        "plus quantity control",
    )
    quantity = choose(
        lambda label: bool(re.fullmatch(r"\s*\d{1,2}\s*", label)),
        "quantity value",
    )
    timeline(
        "FOUND",
        "quantity controls: "
        f"minus={minus['label']!r}, quantity={quantity['label']!r}, "
        f"plus={plus['label']!r}",
    )

    return {
        "minus": page.locator(
            f"[data-snackos-control-index='{minus['control_index']}']"
        ),
        "quantity": page.locator(
            f"[data-snackos-control-index='{quantity['control_index']}']"
        ),
        "plus": page.locator(
            f"[data-snackos-control-index='{plus['control_index']}']"
        ),
    }


async def mark_icon_quantity_controls(page: Page) -> bool:
    return bool(
        await page.evaluate(
            """
            () => {
              const visible = (el) => {
                if (!el) {
                  return false;
                }
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== "hidden" &&
                  style.display !== "none";
              };

              const normalize = (value) =>
                (value || "").replace(/\\s+/g, " ").trim();

              document
                .querySelectorAll(
                  "[data-snackos-qty-minus]," +
                  "[data-snackos-qty-plus]," +
                  "[data-snackos-qty-value]"
                )
                .forEach((el) => {
                  el.removeAttribute("data-snackos-qty-minus");
                  el.removeAttribute("data-snackos-qty-plus");
                  el.removeAttribute("data-snackos-qty-value");
                });

              const containers = Array.from(
                document.querySelectorAll("[role='button'],div")
              )
                .filter(visible)
                .map((el) => {
                  const minusIcon = el.querySelector(".icon-minus,[class*='minus' i]");
                  const plusIcon = el.querySelector(".icon-plus,[class*='plus' i]");
                  const quantityEl = Array.from(el.querySelectorAll("div,span"))
                    .find((child) =>
                      visible(child) &&
                      /^\\d{1,2}$/.test(normalize(child.innerText || child.textContent))
                    );
                  const rect = el.getBoundingClientRect();
                  return {
                    el,
                    minusIcon,
                    plusIcon,
                    quantityEl,
                    area: rect.width * rect.height,
                    top: rect.top
                  };
                })
                .filter((item) => item.minusIcon && item.plusIcon && item.quantityEl);

              containers.sort((a, b) => {
                const aVisible = a.top > 80 && a.top < window.innerHeight * 0.9 ? 1 : 0;
                const bVisible = b.top > 80 && b.top < window.innerHeight * 0.9 ? 1 : 0;
                return bVisible - aVisible || a.area - b.area;
              });

              if (!containers.length) {
                return false;
              }

              const selected = containers[0];
              const minusControl =
                selected.minusIcon.closest("button,[role='button']") ||
                selected.minusIcon;
              const plusControl =
                selected.plusIcon.closest("button,[role='button']") ||
                selected.plusIcon;

              minusControl.setAttribute("data-snackos-qty-minus", "true");
              plusControl.setAttribute("data-snackos-qty-plus", "true");
              selected.quantityEl.setAttribute("data-snackos-qty-value", "true");
              return true;
            }
            """
        )
    )


async def collect_control_candidates(page: Page) -> list[dict[str, object]]:
    return await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const fullLabel = (el) => normalize([
            el.innerText,
            el.textContent,
            el.getAttribute("aria-label"),
            el.getAttribute("title"),
            el.className,
            Array.from(el.querySelectorAll("[class]"))
              .map((child) => child.className)
              .join(" ")
          ].filter(Boolean).join(" "));

          const strategies = [
            ["button elements", "button"],
            ["role button", "[role='button']"],
            ["aria-labelled elements", "[aria-label]"],
            ["interactive links", "a[href]"],
            ["compact text controls", "div,span"]
          ];
          const seen = new Set();
          const candidates = [];

          strategies.forEach(([strategy, selector]) => {
            Array.from(document.querySelectorAll(selector)).forEach((el) => {
              if (seen.has(el)) {
                return;
              }
              seen.add(el);
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              const controlIndex = candidates.length;
              el.setAttribute("data-snackos-control-index", String(controlIndex));
              candidates.push({
                index: controlIndex,
                control_index: controlIndex,
                strategy,
                label: fullLabel(el),
                visible: visible(el),
                enabled: !el.disabled &&
                  el.getAttribute("aria-disabled") !== "true" &&
                  style.pointerEvents !== "none",
                top: rect.top,
                tag: el.tagName.toLowerCase(),
                role: el.getAttribute("role") || "",
                position: style.position,
                outerHTML: el.outerHTML.slice(0, 500)
              });
            });
          });

          return candidates;
        }
        """
    )


async def collect_cart_debug_items(page: Page) -> list[dict[str, object]]:
    return await page.evaluate(
        """
        ({ selector }) => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const priceText = (text) => {
            const match = text.match(/(?:₹|Rs\\.?\\s*)\\s*\\d+(?:\\.\\d{1,2})?/i);
            return match ? match[0].replace(/\\s+/g, " ").trim() : "";
          };

          const quantityFromText = (text) => {
            const patterns = [
              /(?:qty|quantity)\\s*:?\\s*(\\d{1,2})/i,
              /(?:^|\\s)(\\d{1,2})\\s*x(?:\\s|$)/i,
              /(?:^|\\n|\\s)\\+\\s*(\\d{1,2})\\s*[-−](?:\\n|\\s|$)/i,
              /(?:^|\\n|\\s)[-−]\\s*(\\d{1,2})\\s*\\+(?:\\n|\\s|$)/i
            ];

            for (const pattern of patterns) {
              const match = text.match(pattern);
              if (match) {
                return Number(match[1]);
              }
            }

            const standalone = text
              .split(/\\n+/)
              .map((line) => line.trim())
              .filter((line) => /^\\d{1,2}$/.test(line))
              .map(Number)
              .filter((value) => value > 0 && value <= 20);

            return standalone.length ? standalone[0] : null;
          };

          const nodes = Array.from(document.querySelectorAll(selector));
          const seen = new Set();
          const items = [];

          nodes.forEach((node, sourceIndex) => {
            if (!visible(node)) {
              return;
            }

            const text = normalize(node.innerText || node.textContent || "");
            if (
              text.length < 8 ||
              text.length > 800 ||
              !/(?:₹|Rs\\.?)/i.test(text) ||
              /place order|proceed to pay|pay now|payment/i.test(text)
            ) {
              return;
            }

            const lines = text
              .split(/\\n+/)
              .map((line) => normalize(line))
              .filter(Boolean);

            const name = lines.find((line) =>
              !/(?:₹|Rs\\.?|qty|quantity|total|delivery|discount|bill|add|[-−+]|^\\d{1,2}$)/i
                .test(line)
            );
            if (!name) {
              return;
            }

            const key = `${name.toLowerCase()}|${priceText(text)}`;
            if (seen.has(key)) {
              return;
            }
            seen.add(key);

            items.push({
              source_index: sourceIndex,
              product_name: name,
              quantity: quantityFromText(text),
              price_text: priceText(text),
              text
            });
          });

          return items;
        }
        """,
        {"selector": CART_ITEM_SELECTOR},
    )


def find_debug_cart_match(
    cart_items: list[dict[str, object]],
    target: ProductTarget,
) -> dict[str, object] | None:
    for item in cart_items:
        name = str(item["product_name"]).lower()
        if all(term in name for term in target.cart_terms):
            return item
    return None


def score_control_candidate(candidate: dict[str, object]) -> float:
    label = str(candidate["label"])
    value = 0.0
    if str(candidate["tag"]) == "button" or str(candidate["role"]).lower() == "button":
        value += 40
    if re.fullmatch(r"\s*add\s*", label, re.I):
        value += 30
    if re.search(r"add\s+to\s+cart", label, re.I):
        value += 25
    if len(label) <= 40:
        value += 10
    top = float(candidate["top"])
    if 80 < top < 765:
        value += 20
    if str(candidate["position"]) in {"fixed", "sticky"}:
        value -= 20
    return value


async def find_search_box(page: Page, allow_launcher: bool = True) -> Locator:
    timeline("WAITING", "Blinkit UI render before search box discovery")
    await wait_for_page(page)
    await page.locator("body").wait_for(state="visible", timeout=10_000)
    if "/s" in page.url:
        try:
            await page.locator(
                "input[placeholder*='search' i],input,textarea,"
                "[contenteditable='true'],[contenteditable='']"
            ).first.wait_for(state="visible", timeout=8_000)
            timeline("FOUND", "search page input rendered")
        except TimeoutError:
            timeline("WAITING", "search page input did not render before discovery")

    strategies: tuple[tuple[str, Locator], ...] = (
        ("role=searchbox", page.get_by_role("searchbox")),
        ("role=combobox", page.get_by_role("combobox")),
        (
            "placeholder contains Search",
            page.get_by_placeholder(re.compile("Search")),
        ),
        (
            "placeholder contains search",
            page.get_by_placeholder(re.compile("search", re.I)),
        ),
        ("input[type=search]", page.locator("input[type='search']")),
        ("visible input elements", page.locator("input")),
        ("textarea", page.locator("textarea")),
        (
            "contenteditable search elements",
            page.locator(
                "[contenteditable='true'],[contenteditable=''],"
                "[role='searchbox'][contenteditable],"
                "[aria-label*='search' i][contenteditable]"
            ),
        ),
    )

    for strategy, locator in strategies:
        timeline("WAITING", f"search box strategy: {strategy}")
        try:
            count = await locator.count()
            for index in range(count):
                candidate = locator.nth(index)
                details = await inspect_locator_candidate(candidate, strategy)
                print_search_candidate(details)
                if (
                    details["visible"]
                    and details["enabled"]
                    and details["editable"]
                ):
                    timeline("FOUND", f"search box via {strategy}")
                    return candidate
        except Exception as exc:
            timeline("WAITING", f"search strategy failed: {strategy}: {exc}")
            continue

    if allow_launcher:
        launcher = await find_search_launcher(page)
        if launcher is not None:
            timeline("CLICKING", "homepage search launcher")
            await retry_click(launcher, "homepage search launcher")
            await wait_for_page(page)
            timeline("SUCCESS", "search page opened from homepage launcher")
            return await find_search_box(page, allow_launcher=False)

    await print_search_box_diagnostics(page)
    await save_failure_artifacts(page, "search_box_failure")
    raise BlinkitAutomationError("Could not find Blinkit search box.")


async def find_search_launcher(page: Page) -> Locator | None:
    timeline("WAITING", "homepage search launcher")
    locators = (
        page.get_by_role("link", name=re.compile(r"search", re.I)),
        page.locator("a[href^='/s']").filter(has_text=re.compile(r"search", re.I)),
        page.locator("a[href='/s/']"),
    )
    for locator in locators:
        try:
            count = await locator.count()
            for index in range(count):
                candidate = locator.nth(index)
                if await candidate.is_visible(timeout=750):
                    timeline("FOUND", "homepage search launcher")
                    return candidate
        except Exception:
            continue
    return None


async def clear_and_type_search(page: Page, search_box: Locator, query: str) -> None:
    print("Searching:", flush=True)
    print(query, flush=True)
    timeline("CLICKING", "search box")
    await retry_click(search_box, "search box")
    await wait_for_locator_focus(page, search_box)
    timeline("VERIFYING", "search box has focus")

    modifier = "Meta+A" if os.uname().sysname == "Darwin" else "Control+A"
    timeline("TYPING", f"clearing search box with {modifier} and Backspace")
    await page.keyboard.press(modifier)
    await page.keyboard.press("Backspace")
    if not await is_search_field_empty(search_box):
        await page.keyboard.press(modifier)
        await page.keyboard.press("Delete")
    if not await is_search_field_empty(search_box):
        await search_box.fill("")
    if not await is_search_field_empty(search_box):
        raise BlinkitAutomationError("Search box could not be cleared.")
    timeline("SUCCESS", "search box cleared")

    timeline("TYPING", f"search query slowly: {query}")
    await page.keyboard.type(query, delay=60)
    timeline("VERIFYING", "waiting for natural search results")
    try:
        await wait_for_product_grid(page, timeout_ms=5_000)
        timeline("SUCCESS", "search results appeared without pressing Enter")
    except BlinkitAutomationError:
        timeline("TYPING", "pressing Enter because results did not render naturally")
        await page.keyboard.press("Enter")
        await wait_for_product_grid(page, timeout_ms=12_000)
        timeline("SUCCESS", "search results appeared after pressing Enter")


async def wait_for_locator_focus(page: Page, locator: Locator) -> None:
    handle = await locator.element_handle(timeout=3_000)
    if handle is None:
        raise BlinkitAutomationError("Search box disappeared before focus check.")
    await page.wait_for_function(
        """
        (el) => {
          const active = document.activeElement;
          return active === el || el.contains(active);
        }
        """,
        arg=handle,
        timeout=3_000,
    )


async def is_search_field_empty(locator: Locator) -> bool:
    value = await locator.evaluate(
        """
        (el) => {
          if ("value" in el) {
            return el.value || "";
          }
          return el.textContent || "";
        }
        """
    )
    return normalize_text(str(value)) == ""


async def inspect_locator_candidate(locator: Locator, strategy: str) -> dict[str, object]:
    visible = False
    enabled = False
    editable = False
    try:
        visible = await locator.is_visible(timeout=500)
    except Exception:
        pass
    try:
        enabled = await locator.is_enabled(timeout=500)
    except Exception:
        pass
    try:
        editable = await locator.is_editable(timeout=500)
    except Exception:
        pass

    attrs: dict[str, object] = {
        "strategy": strategy,
        "placeholder": "",
        "aria_label": "",
        "role": "",
        "visible": visible,
        "enabled": enabled,
        "editable": editable,
    }
    for attr, key in (
        ("placeholder", "placeholder"),
        ("aria-label", "aria_label"),
        ("role", "role"),
    ):
        try:
            attrs[key] = await locator.get_attribute(attr, timeout=500) or ""
        except Exception:
            attrs[key] = ""
    return attrs


def print_search_candidate(details: dict[str, object]) -> None:
    print("Search candidate:", flush=True)
    print(f"locator strategy = {details['strategy']}", flush=True)
    print(f"placeholder = {details['placeholder']}", flush=True)
    print(f"aria-label = {details['aria_label']}", flush=True)
    print(f"role = {details['role']}", flush=True)
    print(f"visibility = {details['visible']}", flush=True)
    print(f"enabled = {details['enabled']}", flush=True)
    print(f"editable = {details['editable']}", flush=True)


async def print_search_box_diagnostics(page: Page) -> None:
    timeline("VERIFYING", "search box diagnostics for visible editable candidates")
    diagnostics = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };
          const nodes = Array.from(document.querySelectorAll(
            "input,textarea,[role='combobox'],[contenteditable='true'],[contenteditable='']"
          ));
          return nodes
            .filter(visible)
            .map((el) => ({
              tag: el.tagName.toLowerCase(),
              placeholder: el.getAttribute("placeholder") || "",
              aria_label: el.getAttribute("aria-label") || "",
              role: el.getAttribute("role") || "",
              value: "value" in el ? el.value : (el.textContent || ""),
              outerHTML: el.outerHTML.slice(0, 800)
            }));
        }
        """
    )
    for item in diagnostics:
        print("Visible search diagnostic:", flush=True)
        print(f"tag = {item['tag']}", flush=True)
        print(f"placeholder = {item['placeholder']}", flush=True)
        print(f"aria-label = {item['aria_label']}", flush=True)
        print(f"role = {item['role']}", flush=True)
        print(f"value = {item['value']}", flush=True)
        print(f"outerHTML = {item['outerHTML']}", flush=True)


async def wait_for_search_results(page: Page, query: str) -> None:
    timeline("WAITING", f"search results for {query}")
    await wait_for_product_grid(page, timeout_ms=12_000)
    query_tokens = [token.lower() for token in tokenize(query) if len(token) > 2]
    try:
        await page.wait_for_function(
            """
            ({ tokens }) => {
              const text = (document.body.innerText || "").toLowerCase();
              const hasQueryToken = tokens.some((token) => text.includes(token));
              const hasPrice = /(?:₹|rs\\.?\\s*)\\s*\\d+/i.test(text);
              return hasQueryToken && hasPrice;
            }
            """,
            arg={"tokens": query_tokens},
            timeout=12_000,
        )
    except TimeoutError as exc:
        raise BlinkitAutomationError(
            f"Search results did not render for query {query!r}."
        ) from exc
    await wait_for_page(page)
    timeline("SUCCESS", f"search results rendered for {query}")


async def wait_for_product_grid(page: Page, timeout_ms: int = 10_000) -> None:
    try:
        await page.wait_for_function(
            """
            () => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== "hidden" &&
                  style.display !== "none";
              };
              const hasPrice = (text) => /(?:₹|Rs\\.?\\s*)\\s*\\d+/i.test(text || "");
              const selectors = [
                "article",
                "li",
                "[role='listitem']",
                "[data-testid*='product' i]",
                "[class*='product' i]",
                "div"
              ];
              const nodes = Array.from(document.querySelectorAll(selectors.join(",")));
              return nodes.some((node) => {
                const text = node.innerText || node.textContent || "";
                return visible(node) &&
                  text.length > 10 &&
                  text.length < 1000 &&
                  hasPrice(text);
              });
            }
            """,
            timeout=timeout_ms,
        )
    except TimeoutError as exc:
        raise BlinkitAutomationError("Product grid did not become visible.") from exc


async def find_product_cards(page: Page) -> list[dict[str, object]]:
    timeline("WAITING", "discovering visible product cards")
    return await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const priceValue = (text) => {
            const match = text.match(/(?:₹|Rs\\.?\\s*)\\s*(\\d+)(?:\\.\\d{1,2})?/i);
            return match ? Number(match[1]) : null;
          };

          const priceText = (text) => {
            const match = text.match(/(?:₹|Rs\\.?\\s*)\\s*\\d+(?:\\.\\d{1,2})?/i);
            return match ? match[0].replace(/\\s+/g, " ").trim() : "";
          };

          const titleFromText = (text) => {
            const lines = text
              .split(/\\n+/)
              .map((line) => normalize(line))
              .filter(Boolean);

            const title = lines.find((line) =>
              line.length > 3 &&
              !/(?:₹|Rs\\.?|add|off|discount|delivery|minute|qty|quantity|^\\d+$|[-−+])/i
                .test(line)
            );

            return title || lines[0] || "";
          };

          const availabilityFromText = (text) => {
            if (/out\\s+of\\s+stock|sold\\s+out|unavailable/i.test(text)) {
              return "unavailable";
            }
            if (/\\badd(?:\\s+to\\s+cart)?\\b/i.test(text)) {
              return "available";
            }
            return "unknown";
          };

          const hasAddButton = (node) => {
            const controls = Array.from(
              node.querySelectorAll("button,[role='button'],[aria-label],div,span")
            );
            return controls.some((control) =>
              visible(control) &&
              /\\badd(?:\\s+to\\s+cart)?\\b/i.test(
                [
                  control.innerText,
                  control.textContent,
                  control.getAttribute("aria-label"),
                  control.getAttribute("title")
                ].filter(Boolean).join(" ")
              )
            );
          };

          const selectors = [
            "article",
            "li",
            "[role='listitem']",
            "[data-testid*='product' i]",
            "[class*='product' i]",
            "div"
          ];
          const nodes = Array.from(document.querySelectorAll(selectors.join(",")));
          const seen = new Set();
          const products = [];

          nodes.forEach((node, sourceIndex) => {
            if (!visible(node)) {
              return;
            }

            const text = normalize(node.innerText || node.textContent || "");
            if (text.length < 12 || text.length > 900) {
              return;
            }

            const value = priceValue(text);
            if (value === null) {
              return;
            }

            const title = titleFromText(text);
            if (!title || title.length < 3) {
              return;
            }

            const key = `${title.toLowerCase()}|${value}`;
            if (seen.has(key)) {
              return;
            }
            seen.add(key);
            const rect = node.getBoundingClientRect();
            const productIndex = products.length;
            node.setAttribute("data-snackos-product-index", String(productIndex));

            products.push({
              product_index: productIndex,
              source_index: sourceIndex,
              title,
              price_value: value,
              price_text: priceText(text),
              text,
              availability: availabilityFromText(text),
              add_button_present: hasAddButton(node),
              visible: true,
              bounding_box: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
              }
            });
          });

          return products;
        }
        """
    )


async def collect_visible_products(page: Page) -> list[dict[str, object]]:
    return await find_product_cards(page)


async def assert_product_page_loaded(page: Page, product: dict[str, object]) -> None:
    body_text = await page.locator("body").inner_text(timeout=5_000)
    normalized = normalize_text(body_text).lower()
    title_tokens = [
        token for token in tokenize(str(product["title"])) if len(token) > 2
    ]
    if not any(token in normalized for token in title_tokens):
        raise BlinkitAutomationError(
            f"Product page did not load after selecting {product['title']!r}."
        )


async def wait_for_product_quantity(
    page: Page,
    expected_quantity: int,
    product_name: str,
) -> int:
    last_quantity: int | None = None
    for _ in range(20):
        try:
            await page.wait_for_function(
                """
                ({ expectedQuantity }) => {
                  const text = document.body.innerText || "";
                  const lines = text
                    .split(/\\n+/)
                    .map((line) => line.trim())
                    .filter((line) => /^\\d{1,2}$/.test(line))
                    .map(Number);
                  return lines.includes(expectedQuantity);
                }
                """,
                arg={"expectedQuantity": expected_quantity},
                timeout=500,
            )
        except TimeoutError:
            pass
        last_quantity = await read_visible_quantity(page)
        if last_quantity == expected_quantity:
            await wait_for_page(page)
            return last_quantity

    raise BlinkitAutomationError(
        f"Timed out waiting for {product_name} quantity to become "
        f"{expected_quantity}. Last visible quantity: {last_quantity}."
    )


async def wait_for_any_product_quantity(page: Page, product_name: str) -> int:
    last_quantity: int | None = None
    for _ in range(20):
        last_quantity = await read_visible_quantity(page)
        if last_quantity is not None:
            await wait_for_page(page)
            return last_quantity
        try:
            await page.wait_for_function(
                """
                () => {
                  const text = document.body.innerText || "";
                  return text
                    .split(/\\n+/)
                    .map((line) => line.trim())
                    .some((line) => /^\\d{1,2}$/.test(line));
                }
                """,
                timeout=500,
            )
        except TimeoutError:
            pass

    raise BlinkitAutomationError(
        f"Timed out waiting for {product_name} quantity controls. "
        f"Last visible quantity: {last_quantity}."
    )


async def is_logged_in_without_clicking(page: Page) -> bool:
    login_prompt = page.get_by_text(
        re.compile(r"log\s*in|login|sign\s*in|enter\s+mobile", re.I)
    )

    try:
        if await login_prompt.first.is_visible(timeout=1_000):
            return False
    except TimeoutError:
        pass

    page_text = await page.locator("body").inner_text(timeout=3_000)
    normalized = normalize_text(page_text).lower()
    if "enter mobile" in normalized or "login" in normalized:
        return False

    return True


async def inspect_cart_without_clicking(page: Page) -> dict[str, object]:
    return await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const priceText = (text) => {
            const match = text.match(/(?:₹|Rs\\.?\\s*)\\s*\\d+(?:\\.\\d{1,2})?/i);
            return match ? match[0].replace(/\\s+/g, " ").trim() : "";
          };

          const quantityFromText = (text) => {
            const patterns = [
              /(?:qty|quantity)\\s*:?\\s*(\\d{1,2})/i,
              /(?:^|\\s)(\\d{1,2})\\s*x(?:\\s|$)/i,
              /(?:^|\\n|\\s)\\+\\s*(\\d{1,2})\\s*[-−](?:\\n|\\s|$)/i,
              /(?:^|\\n|\\s)[-−]\\s*(\\d{1,2})\\s*\\+(?:\\n|\\s|$)/i
            ];

            for (const pattern of patterns) {
              const match = text.match(pattern);
              if (match) {
                return Number(match[1]);
              }
            }

            const standalone = text
              .split(/\\n+/)
              .map((line) => line.trim())
              .filter((line) => /^\\d{1,2}$/.test(line))
              .map(Number)
              .filter((value) => value > 0 && value <= 20);

            return standalone.length ? standalone[0] : null;
          };

          const quantityFromStepper = (node) => {
            const steppers = Array.from(
              node.querySelectorAll("[class*='AddToCart__UpdatedButtonContainer' i]")
            );
            for (const stepper of steppers) {
              if (!visible(stepper)) {
                continue;
              }
              const childText = Array.from(stepper.childNodes)
                .map((child) => normalize(child.textContent || ""))
                .filter((text) => /^\\d{1,2}$/.test(text))
                .map(Number)
                .filter((value) => value > 0 && value <= 20);
              if (childText.length) {
                return childText[0];
              }
              const text = stepper.innerText || stepper.textContent || "";
              const quantity = quantityFromText(text);
              if (quantity !== null) {
                return quantity;
              }
            }
            return null;
          };

          const titleFromCartNode = (node, rawText) => {
            const title = node.querySelector("[class*='ProductTitle' i]");
            if (title && normalize(title.innerText || title.textContent)) {
              return normalize(title.innerText || title.textContent);
            }
            const image = node.querySelector("img[alt]");
            if (image && normalize(image.getAttribute("alt"))) {
              return normalize(image.getAttribute("alt"));
            }
            const lines = rawText
              .split(/\\n+/)
              .map((line) => normalize(line))
              .filter(Boolean);
            return lines.find((line) =>
              !/(?:₹|Rs\\.?|qty|quantity|total|delivery|discount|bill|add|[-−+]|^\\d{1,2}$|^\\d+\\s*g$)/i
                .test(line)
            ) || "";
          };

          const cartProductNodes = Array.from(
            document.querySelectorAll(
              "[class*='CartProduct__Container' i], [class*='DefaultProductCard__Container' i]"
            )
          ).filter(visible);

          const seen = new Set();
          const items = [];

          for (const node of cartProductNodes) {
            const rawText = node.innerText || node.textContent || "";
            const normalized = normalize(rawText);
            if (
              normalized.length < 5 ||
              !/(?:₹|Rs\\.?)/i.test(normalized) ||
              /place order|proceed to pay|pay now/i.test(normalized)
            ) {
              continue;
            }

            const name = titleFromCartNode(node, rawText);
            const key = `${name.toLowerCase()}|${priceText(normalized)}`;
            if (!name || seen.has(key)) {
              continue;
            }

            seen.add(key);
            items.push({
              product_name: name,
              quantity: quantityFromStepper(node) ?? quantityFromText(rawText),
              price_text: priceText(normalized),
            });
          }

          const bodyText = document.body.innerText || "";
          const totalMatch = bodyText.match(
            /(?:grand\\s+total|total|to\\s+pay|pay)\\s*[^\\n₹]*(₹\\s*\\d+(?:\\.\\d{1,2})?)/i
          );

          return {
            items,
            cart_total: totalMatch ? totalMatch[1] : null
          };
        }
        """
    )


async def wait_for_page(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except TimeoutError:
        log_step("Network idle wait timed out; continuing with visible page state")


async def dismiss_overlays(page: Page) -> None:
    for locator in (
        page.get_by_role("button", name=re.compile(r"close|dismiss|not now", re.I)),
        page.locator("[aria-label*='close' i]"),
    ):
        try:
            if await locator.count():
                candidate = locator.first
                if await candidate.is_visible(timeout=500):
                    log_step("Dismissing overlay")
                    await retry_click(candidate, "overlay close control", timeout_ms=1_500)
        except Exception:
            continue


async def read_visible_quantity(page: Page) -> int | None:
    stepper_quantity = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none";
          };

          const normalize = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();

          const nodes = Array.from(document.querySelectorAll("[role='button'],div"));
          const steppers = nodes
            .filter(visible)
            .map((el) => {
              const hasMinus = !!el.querySelector(".icon-minus,[class*='minus' i]");
              const hasPlus = !!el.querySelector(".icon-plus,[class*='plus' i]");
              const text = normalize(el.innerText || el.textContent || "");
              const numbers = text
                .split(/\\s+/)
                .filter((part) => /^\\d{1,2}$/.test(part))
                .map(Number)
                .filter((value) => value > 0 && value <= 20);
              const rect = el.getBoundingClientRect();
              return {
                hasMinus,
                hasPlus,
                numbers,
                top: rect.top,
                area: rect.width * rect.height
              };
            })
            .filter((item) => item.hasMinus && item.hasPlus && item.numbers.length);

          steppers.sort((a, b) => {
            const aVisibleScore = a.top > 80 && a.top < window.innerHeight * 0.9 ? 1 : 0;
            const bVisibleScore = b.top > 80 && b.top < window.innerHeight * 0.9 ? 1 : 0;
            return bVisibleScore - aVisibleScore || a.area - b.area;
          });

          return steppers.length ? steppers[0].numbers[0] : null;
        }
        """
    )
    if stepper_quantity is not None:
        return int(stepper_quantity)

    candidates = await collect_control_candidates(page)
    numeric: list[tuple[float, int]] = []
    for candidate in candidates:
        label = normalize_text(str(candidate["label"]))
        if not candidate["visible"] or not re.fullmatch(r"\d{1,2}", label):
            continue
        value = int(label)
        if value <= 0 or value > 20:
            continue
        score = 10.0 if 80 < float(candidate["top"]) < 765 else 0.0
        if str(candidate["position"]) in {"fixed", "sticky"}:
            score -= 2.0
        numeric.append((score, value))
    numeric.sort(key=lambda item: item[0], reverse=True)
    return numeric[0][1] if numeric else None


async def click_add(page: Page) -> None:
    add_button = await find_add_button(page)
    timeline("CLICKING", "ADD button")
    await assert_safe_to_click(add_button, "ADD button")
    await retry_click(add_button, "ADD button")


async def click_increment(page: Page) -> None:
    controls = await find_quantity_controls(page)
    timeline("CLICKING", "quantity increment control")
    await retry_click(controls["plus"], "quantity increment control")


async def click_decrement(page: Page) -> None:
    controls = await find_quantity_controls(page)
    timeline("CLICKING", "quantity decrement control")
    await retry_click(controls["minus"], "quantity decrement control")


async def click_control_by_predicate(
    page: Page,
    predicate,
    description: str,
) -> None:
    candidates = await collect_control_candidates(page)
    matches = [
        candidate
        for candidate in candidates
        if candidate["visible"]
        and candidate["enabled"]
        and predicate(str(candidate["label"]))
        and not FORBIDDEN_CLICK_PATTERN.search(str(candidate["label"]))
    ]

    matches.sort(key=score_control_candidate, reverse=True)

    print("Trying selector:", flush=True)
    print(f"multi-strategy control discovery + {description} predicate", flush=True)
    print("Count:", flush=True)
    print(len(matches), flush=True)
    print("Visible:", flush=True)
    print(bool(matches), flush=True)
    print("Enabled:", flush=True)
    print(bool(matches), flush=True)

    if not matches:
        await diagnose_control_failure(
            page,
            description,
            "multi-strategy control discovery",
            candidates,
        )
        raise BlinkitAutomationError(f"Could not find visible {description}")

    match = matches[0]
    log_step(
        f"Selected {description}: text={match['label']!r}, "
        f"tag={match['tag']}, role={match['role']!r}, "
        f"score={score_control_candidate(match):.1f}"
    )
    locator = page.locator(f"[data-snackos-control-index='{match['control_index']}']")
    await assert_safe_to_click(locator, description)
    await locator.scroll_into_view_if_needed(timeout=2_000)
    await retry_click(locator, description)


async def click_first_visible(
    locators: Iterable[Locator],
    description: str,
    timeout_ms: int = 10_000,
) -> None:
    last_error: Exception | None = None
    for locator in locators:
        try:
            count = await locator.count()
            for index in range(max(1, min(count, 8))):
                candidate = locator if count == 0 else locator.nth(index)
                if await candidate.is_visible(timeout=500):
                    await assert_safe_to_click(candidate, description)
                    await retry_click(candidate, description, timeout_ms=timeout_ms)
                    return
        except Exception as exc:
            last_error = exc

    if last_error:
        raise BlinkitAutomationError(
            f"Could not click {description}: {last_error}"
        ) from last_error
    raise BlinkitAutomationError(f"Could not find visible {description}")


async def retry_click(
    locator: Locator,
    description: str,
    timeout_ms: int = 10_000,
) -> None:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            await locator.click(timeout=timeout_ms)
            log_step(f"Clicked {description}")
            return
        except Exception as exc:
            last_error = exc
            log_step(f"Click failed for {description} on attempt {attempt + 1}: {exc}")
            if attempt == 0:
                if "intercepts pointer events" in str(exc):
                    await dismiss_product_zoom_overlay(locator.page)
                await locator.page.wait_for_load_state("domcontentloaded")

    raise BlinkitAutomationError(
        f"Could not click {description} after retry: {last_error}"
    )


async def dismiss_product_zoom_overlay(page: Page) -> None:
    timeline("WAITING", "dismissing product image zoom overlay")
    try:
        await page.mouse.move(8, 8)
        await page.keyboard.press("Escape")
        await page.wait_for_function(
            """
            () => {
              const overlays = Array.from(
                document.querySelectorAll("[class*='ZoomedImage' i],#portal")
              );
              return overlays.every((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width === 0 ||
                  rect.height === 0 ||
                  style.display === "none" ||
                  style.visibility === "hidden" ||
                  style.pointerEvents === "none";
              });
            }
            """,
            timeout=2_000,
        )
        timeline("SUCCESS", "product image zoom overlay dismissed")
    except Exception as exc:
        timeline("WAITING", f"zoom overlay did not fully disappear: {exc}")


async def assert_safe_to_click(locator: Locator, description: str) -> None:
    texts: list[str] = []
    for getter in (locator.inner_text, locator.text_content):
        try:
            value = await getter(timeout=500)
            if value:
                texts.append(value)
        except Exception:
            continue

    try:
        aria_label = await locator.get_attribute("aria-label", timeout=500)
        if aria_label:
            texts.append(aria_label)
    except Exception:
        pass

    label = " ".join(texts)
    if FORBIDDEN_CLICK_PATTERN.search(label):
        raise BlinkitAutomationError(
            f"Refusing to click forbidden checkout/payment control while "
            f"handling {description}: {label!r}"
        )


async def diagnose_control_failure(
    page: Page,
    description: str,
    selector: str,
    candidates: list[dict[str, object]],
) -> None:
    log_step(f"{description} diagnostics: selector did not produce a clickable match")
    print(f"page.url = {page.url}", flush=True)
    try:
        print(f"page.title = {await page.title()}", flush=True)
    except Exception as exc:
        print(f"page.title = <unavailable: {exc}>", flush=True)

    for candidate in candidates:
        if candidate["visible"]:
            print("Button:", flush=True)
            print(f"text = {candidate['label']}", flush=True)
            print(f"role = {candidate['role'] or candidate['tag']}", flush=True)
            print(f"outerHTML = {candidate['outerHTML']}", flush=True)

    await save_failure_artifacts(page, f"{safe_filename(description)}_failure")


async def handle_automation_failure(page: Page, exc: Exception) -> None:
    print("Current URL", flush=True)
    print(page.url, flush=True)
    print("Current title", flush=True)
    try:
        print(await page.title(), flush=True)
    except Exception as title_exc:
        print(f"<unavailable: {title_exc}>", flush=True)
    print("Last successful step", flush=True)
    print(LAST_SUCCESSFUL_STEP, flush=True)
    print("Failure", flush=True)
    print(str(exc), flush=True)
    await save_failure_artifacts(page, "failure")


async def save_failure_artifacts(page: Page, prefix: str) -> None:
    screenshot_path = Path(f"{prefix}.png")
    html_path = Path(f"{prefix}.html")

    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
        log_step(f"Saved screenshot: {screenshot_path}")
    except Exception as exc:
        log_step(f"Failed to save screenshot: {exc}")

    try:
        html_path.write_text(await page.content(), encoding="utf-8")
        log_step(f"Saved page HTML: {html_path}")
    except Exception as exc:
        log_step(f"Failed to save page HTML: {exc}")


def log_cart_snapshot(cart_snapshot: dict[str, object]) -> None:
    items = cart_snapshot.get("items", [])
    if not items:
        log_step("Cart item: no visible cart items detected")
    for item in items:
        log_step(f"Cart item: {item['product_name']} | Quantity: {item['quantity']}")
    log_step(f"Cart total: {cart_snapshot.get('cart_total') or 'not visible'}")


def score_product(title: str, query: str) -> float:
    title_norm = normalize_text(title).lower()
    query_norm = normalize_text(query).lower()
    title_tokens = set(tokenize(title_norm))
    query_tokens = set(tokenize(query_norm))
    overlap = len(title_tokens & query_tokens) / max(len(query_tokens), 1)
    similarity = SequenceMatcher(None, title_norm, query_norm).ratio()
    return (overlap * 0.7) + (similarity * 0.3)


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "blinkit"
