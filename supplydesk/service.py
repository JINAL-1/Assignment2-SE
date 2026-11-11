
"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def _product_lookup(self, state):
        """Create a dictionary for finding products by ID."""
        return {
            product["product_id"]: product
            for product in state["catalog"]
        }

    def _prepare_quote(self, state, customer_type, items, fulfillment):
        """Validate an order request and calculate its price."""

        if customer_type not in ("regular", "student"):
            raise ValueError("Customer type must be regular or student.")

        if fulfillment not in ("pickup", "delivery", "express"):
            raise ValueError(
                "Fulfillment must be pickup, delivery, or express."
            )

        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")

        products = self._product_lookup(state)
        requested = {}
        lines = []
        subtotal = 0

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(
                    "Each item must contain a product_id and quantity."
                )

            product_id = item.get("product_id")
            product = products.get(product_id)

            if product is None:
                raise ValueError("Unknown product.")

            quantity = item.get("quantity")

            if type(quantity) is not int or quantity < 1 or quantity > 99:
                raise ValueError(
                    "Quantity must be an integer from 1 to 99."
                )

            requested[product_id] = (
                requested.get(product_id, 0) + quantity
            )

            if requested[product_id] > product["stock"]:
                raise ValueError(
                    "Not enough stock for " + product_id + "."
                )

            line_total = product["unit_price_cents"] * quantity
            subtotal += line_total

            lines.append({
                "product_id": product_id,
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "quantity": quantity,
                "line_total_cents": line_total,
            })

        # Student discount applies to merchandise only.
        discount = 0

        if customer_type == "student" and subtotal >= 5000:
            discount = (subtotal * 10 + 50) // 100

        # CR-01: Express delivery always costs 1200 cents.
        delivery = 0

        if fulfillment == "express":
            delivery = 1200
        elif fulfillment == "delivery" and subtotal - discount < 10000:
            delivery = 600

        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    def _update_stock(self, state, lines, direction):
        """Deduct or restore product stock."""
        products = self._product_lookup(state)

        for line in lines:
            product = products.get(line["product_id"])

            if product is not None:
                product["stock"] += direction * line["quantity"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()

        return self._prepare_quote(
            state, customer_type, items, fulfillment
        )

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()

        details = self._prepare_quote(
            state, customer_type, items, fulfillment
        )

        order = {
            "order_id": "ORD-" + str(
                state["next_order_number"]
            ).zfill(4),
            "status": "placed",
            **details,
        }

        self._update_stock(state, details["items"], -1)

        state["next_order_number"] += 1
        state["orders"].append(order)

        self.store.save(state)
        return order

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()

        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order

        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = None

        for candidate in state["orders"]:
            if candidate["order_id"] == order_id:
                order = candidate
                break

        if order is None:
            raise ValueError("Unknown order: " + order_id)

        # Prevent repeated cancellation from restoring stock twice.
        if order["status"] == "cancelled":
            return order

        self._update_stock(state, order["items"], 1)

        order["status"] = "cancelled"
        self.store.save(state)

        return order
