
"""Additional tests for Campus Supply Desk and CR-01 Express Delivery."""

import tempfile
import unittest
from pathlib import Path

from supplydesk.service import OrderService


class OrderSafetyTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    # 1. Normal behavior: multiple products
    def test_order_with_multiple_products(self):
        order = self.service.place_order(
            "regular",
            [
                {"product_id": "notebook", "quantity": 1},
                {"product_id": "mug", "quantity": 1}
            ]
        )

        self.assertEqual(order["subtotal_cents"], 2000)
        self.assertEqual(order["total_cents"], 2000)
        self.assertEqual(order["status"], "placed")
        self.assertEqual(len(order["items"]), 2)

    # 2. Boundary: student discount at exactly $50
    def test_student_discount_at_threshold(self):
        quote = self.service.quote(
            "student",
            [{"product_id": "bag", "quantity": 2}]
        )

        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    # 3. Boundary: free delivery at exactly $100
    def test_free_delivery_at_threshold(self):
        quote = self.service.quote(
            "regular",
            [{"product_id": "bag", "quantity": 4}],
            "delivery"
        )

        self.assertEqual(quote["subtotal_cents"], 10000)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 10000)

    # 4. Invalid: boolean quantity
    def test_boolean_quantity_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote(
                "regular",
                [{"product_id": "notebook", "quantity": True}]
            )

    # 5. Invalid: unsupported customer type
    def test_invalid_customer_type_rejected(self):
        with self.assertRaises(ValueError):
            self.service.place_order(
                "guest",
                [{"product_id": "notebook", "quantity": 1}]
            )

        self.assertEqual(self.service.list_orders(), [])

    # 6. Preserve behavior: order IDs increase
    def test_order_ids_increase(self):
        first = self.service.place_order(
            "regular",
            [{"product_id": "notebook", "quantity": 1}]
        )

        second = self.service.place_order(
            "regular",
            [{"product_id": "mug", "quantity": 1}]
        )

        self.assertEqual(first["order_id"], "ORD-0001")
        self.assertEqual(second["order_id"], "ORD-0002")
        self.assertEqual(len(self.service.list_orders()), 2)

    # 7. Preserve behavior: invalid order does not
    # affect an earlier successful order
    def test_invalid_order_preserves_previous_order(self):
        first = self.service.place_order(
            "regular",
            [{"product_id": "notebook", "quantity": 1}]
        )

        stock_before = self.service.catalog()

        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [{"product_id": "notebook", "quantity": 0}]
            )

        self.assertEqual(self.service.catalog(), stock_before)
        self.assertEqual(len(self.service.list_orders()), 1)
        self.assertEqual(
            self.service.get_order(first["order_id"]),
            first
        )

        next_order = self.service.place_order(
            "regular",
            [{"product_id": "mug", "quantity": 1}]
        )

        self.assertEqual(next_order["order_id"], "ORD-0002")

    # 8. CR-01: Regular customer express delivery
    def test_express_regular_quote(self):
        quote = self.service.quote(
            "regular",
            [{"product_id": "notebook", "quantity": 2}],
            "express"
        )

        self.assertEqual(quote["fulfillment"], "express")
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 2200)

    # 9. CR-01: Student discount with express delivery
    def test_express_student_discount(self):
        quote = self.service.quote(
            "student",
            [{"product_id": "hoodie", "quantity": 2}],
            "express"
        )

        self.assertEqual(quote["fulfillment"], "express")
        self.assertEqual(quote["subtotal_cents"], 8000)
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 8400)

    # 10. CR-01: Express delivery is never free
    def test_express_fee_not_waived(self):
        items = [{"product_id": "hoodie", "quantity": 3}]

        standard = self.service.quote(
            "regular", items, "delivery"
        )

        express = self.service.quote(
            "regular", items, "express"
        )

        self.assertEqual(standard["delivery_cents"], 0)
        self.assertEqual(standard["total_cents"], 12000)
        self.assertEqual(express["delivery_cents"], 1200)
        self.assertEqual(express["total_cents"], 13200)

    # 11. CR-01: Express order persistence and cancellation
    def test_express_order_persistence(self):
        items = [{"product_id": "mug", "quantity": 1}]

        stock_before = self.service.catalog()

        quote = self.service.quote(
            "regular", items, "express"
        )

        order = self.service.place_order(
            "regular", items, "express"
        )

        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["fulfillment"], "express")
        self.assertEqual(order["items"], quote["items"])
        self.assertEqual(
            order["discount_cents"],
            quote["discount_cents"]
        )
        self.assertEqual(order["delivery_cents"], 1200)
        self.assertEqual(
            order["total_cents"],
            quote["total_cents"]
        )

        reopened = OrderService(self.path)
        saved = reopened.get_order(order["order_id"])

        self.assertEqual(saved, order)

        cancelled = reopened.cancel_order(order["order_id"])

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["fulfillment"], "express")
        self.assertEqual(cancelled["items"], quote["items"])
        self.assertEqual(
            cancelled["discount_cents"],
            quote["discount_cents"]
        )
        self.assertEqual(cancelled["delivery_cents"], 1200)
        self.assertEqual(
            cancelled["total_cents"],
            quote["total_cents"]
        )
        self.assertEqual(reopened.catalog(), stock_before)

    # 12. CR-01: Invalid fulfillment rejected
    def test_invalid_fulfillment_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote(
                "regular",
                [{"product_id": "notebook", "quantity": 1}],
                "overnight"
            )

        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [{"product_id": "notebook", "quantity": 1}],
                "overnight"
            )

        self.assertEqual(self.service.list_orders(), [])


if __name__ == "__main__":
    unittest.main()
