"""
Tests for POST /api/orders endpoint.
"""
import pytest


VALID_ORDER_PAYLOAD = {
    "order_number": "TST-2025-0001",
    "customer": "Test Customer",
    "items": [{"sku": "PCB-001", "name": "Test Item", "quantity": 10, "unit_price": 24.99}],
    "status": "Processing",
    "order_date": "2025-06-15T10:00:00",
    "expected_delivery": "2025-06-29",
    "total_value": 249.90,
    "warehouse": None,
    "category": None,
}

RESTOCKING_ORDER_PAYLOAD = {
    "order_number": "RST-2025-0001",
    "customer": "Internal Restocking",
    "items": [
        {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 450, "unit_price": 0.0},
        {"sku": "PSU-501", "name": "5V 10A Switching Power Supply", "quantity": 252, "unit_price": 18.99},
    ],
    "status": "Processing",
    "order_date": "2025-06-15T10:00:00",
    "expected_delivery": "2025-06-29",
    "total_value": 4785.48,
    "warehouse": None,
    "category": None,
}


class TestCreateOrderEndpoint:
    """Test suite for POST /api/orders endpoint."""

    def test_create_order_returns_201(self, client):
        """POST a valid order payload returns 201 with an id field."""
        response = client.post("/api/orders", json=VALID_ORDER_PAYLOAD)
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert data["id"] is not None

    def test_create_order_appears_in_get_orders(self, client):
        """Order posted via POST /api/orders is retrievable via GET /api/orders."""
        order_number = "TST-2025-VERIFY"
        payload = {**VALID_ORDER_PAYLOAD, "order_number": order_number}

        client.post("/api/orders", json=payload)

        response = client.get("/api/orders")
        assert response.status_code == 200

        order_numbers = [o["order_number"] for o in response.json()]
        assert order_number in order_numbers

    def test_create_order_missing_required_field_returns_422(self, client):
        """POST body missing required field 'customer' returns 422."""
        payload = {k: v for k, v in VALID_ORDER_PAYLOAD.items() if k != "customer"}
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 422

    def test_create_restocking_order_structure(self, client):
        """Restocking order fields round-trip correctly through POST /api/orders."""
        response = client.post("/api/orders", json=RESTOCKING_ORDER_PAYLOAD)
        assert response.status_code == 201

        data = response.json()
        assert data["order_number"] == "RST-2025-0001"
        assert data["customer"] == "Internal Restocking"
        assert data["status"] == "Processing"
        assert data["order_date"] == "2025-06-15T10:00:00"
        assert data["expected_delivery"] == "2025-06-29"
        assert abs(data["total_value"] - 4785.48) < 0.01
        assert data["warehouse"] is None
        assert data["category"] is None

        # Verify items array round-trips intact
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 2
        skus = [item["sku"] for item in data["items"]]
        assert "WDG-001" in skus
        assert "PSU-501" in skus
