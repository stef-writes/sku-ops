#!/usr/bin/env python3
"""
Stripe Payment Integration Tests.

- TestAuthorizationChecks: Runs in-process via TestClient (no network). Always runs.
- Other classes: E2E tests against live server. Skip unless RUN_E2E=1.
"""

import pytest
import requests
import os
import uuid

# E2E tests require explicit opt-in to avoid hitting remote when it's down
RUN_E2E = os.environ.get("RUN_E2E", "").lower() in ("1", "true", "yes")

# Backend URL: config provides env-aware default; override with E2E_BACKEND_URL or REACT_APP_BACKEND_URL
from shared.infrastructure.config import E2E_BACKEND_URL
API_URL = f"{E2E_BACKEND_URL.rstrip('/')}/api"

CONTRACTOR_CREDS = {"email": "contractor@test.com", "password": "password123"}
ADMIN_CREDS = {"email": "admin@test.com", "password": "password123"}


@pytest.fixture(scope="module")
def contractor_token():
    """Get contractor authentication token"""
    response = requests.post(f"{API_URL}/auth/login", json=CONTRACTOR_CREDS)
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Contractor login failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{API_URL}/auth/login", json=ADMIN_CREDS)
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def contractor_user():
    """Get contractor user data"""
    response = requests.post(f"{API_URL}/auth/login", json=CONTRACTOR_CREDS)
    if response.status_code == 200:
        return response.json().get("user")
    pytest.skip("Could not get contractor user data")


@pytest.fixture(scope="module")
def test_product(contractor_token):
    """Get a test product for withdrawal testing"""
    headers = {"Authorization": f"Bearer {contractor_token}"}
    response = requests.get(f"{API_URL}/products", headers=headers)
    if response.status_code == 200:
        products = response.json()
        # Find a product with stock
        for p in products:
            if p.get("quantity", 0) > 0:
                return p
    pytest.skip("No products available for testing")


@pytest.mark.skipif(not RUN_E2E, reason="E2E: set RUN_E2E=1 to run against live server")
class TestWithdrawalCreation:
    """Test withdrawal creation for both 'Charge to Account' and 'Pay Now' flows"""

    def test_create_withdrawal_charge_to_account(self, contractor_token, test_product):
        """Test creating a withdrawal with 'Charge to Account' - should be marked unpaid"""
        headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"TEST-JOB-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "123 Test Street, Test City",
            "notes": "Test withdrawal - Charge to Account"
        }
        
        response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=headers)
        
        # Assert status code
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Assert response data
        data = response.json()
        assert "id" in data, "Withdrawal should have an ID"
        assert data["payment_status"] == "unpaid", f"Expected payment_status 'unpaid', got '{data.get('payment_status')}'"
        assert "total" in data, "Withdrawal should have a total"
        assert data["total"] > 0, "Total should be greater than 0"
        
        # Verify tax calculation (8%)
        expected_tax = round(data["subtotal"] * 0.08, 2)
        assert abs(data["tax"] - expected_tax) < 0.01, f"Tax calculation incorrect: expected {expected_tax}, got {data['tax']}"
        
        print(f"✓ Withdrawal created: ID={data['id']}, Total=${data['total']}, Status={data['payment_status']}")
        return data

    def test_withdrawal_persisted(self, contractor_token):
        """Verify withdrawal was persisted by fetching withdrawals list"""
        headers = {"Authorization": f"Bearer {contractor_token}"}
        
        response = requests.get(f"{API_URL}/withdrawals", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list of withdrawals"
        print(f"✓ Found {len(data)} withdrawals for contractor")


@pytest.mark.skipif(not RUN_E2E, reason="E2E: set RUN_E2E=1 to run against live server")
class TestStripePaymentEndpoints:
    """Test Stripe payment integration endpoints"""

    def test_create_checkout_session_requires_valid_withdrawal(self, contractor_token):
        """Test that payment checkout requires a valid withdrawal ID"""
        headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        
        # Try with non-existent withdrawal ID
        payment_data = {
            "withdrawal_id": "nonexistent-id-12345",
            "origin_url": "http://localhost:3000"
        }
        
        response = requests.post(f"{API_URL}/payments/create-checkout", json=payment_data, headers=headers)
        
        assert response.status_code == 404, f"Expected 404 for invalid withdrawal, got {response.status_code}"
        print("✓ Payment endpoint correctly rejects invalid withdrawal ID")

    def test_create_checkout_session_for_valid_withdrawal(self, contractor_token, test_product):
        """Test creating a Stripe checkout session for a valid withdrawal"""
        headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        
        # First create a withdrawal
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"TEST-PAY-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "456 Payment Test Ave",
            "notes": "Test withdrawal - Pay Now flow"
        }
        
        withdrawal_response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=headers)
        assert withdrawal_response.status_code == 200, f"Withdrawal creation failed: {withdrawal_response.text}"
        
        withdrawal = withdrawal_response.json()
        withdrawal_id = withdrawal["id"]
        
        # Now create payment checkout
        payment_data = {
            "withdrawal_id": withdrawal_id,
            "origin_url": "http://localhost:3000"
        }
        
        response = requests.post(f"{API_URL}/payments/create-checkout", json=payment_data, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checkout_url" in data, "Response should contain checkout_url"
        assert "session_id" in data, "Response should contain session_id"
        assert data["checkout_url"].startswith("https://"), f"checkout_url should be a valid URL: {data['checkout_url']}"
        
        print(f"✓ Stripe checkout created: session_id={data['session_id']}")
        print(f"  checkout_url={data['checkout_url'][:80]}...")
        
        return data

    def test_payment_status_endpoint(self, contractor_token, test_product):
        """Test checking payment status endpoint"""
        headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        
        # First create a withdrawal and payment session
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"TEST-STATUS-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "789 Status Check Lane",
            "notes": "Test for payment status check"
        }
        
        withdrawal_response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=headers)
        withdrawal = withdrawal_response.json()
        
        # Create payment session
        payment_data = {
            "withdrawal_id": withdrawal["id"],
            "origin_url": "http://localhost:3000"
        }
        
        checkout_response = requests.post(f"{API_URL}/payments/create-checkout", json=payment_data, headers=headers)
        assert checkout_response.status_code == 200, f"Checkout creation failed: {checkout_response.text}"
        
        session_id = checkout_response.json()["session_id"]
        
        # Check payment status
        status_response = requests.get(f"{API_URL}/payments/status/{session_id}", headers=headers)
        
        assert status_response.status_code == 200, f"Expected 200, got {status_response.status_code}: {status_response.text}"
        
        status_data = status_response.json()
        assert "status" in status_data, "Response should contain status"
        assert "payment_status" in status_data, "Response should contain payment_status"
        
        # For a new unpaid session, status should be open or unpaid
        assert status_data["status"] in ["open", "complete", "expired"], f"Unexpected status: {status_data['status']}"
        
        print(f"✓ Payment status retrieved: status={status_data['status']}, payment_status={status_data['payment_status']}")
        
        return status_data

    def test_cannot_pay_already_paid_withdrawal(self, contractor_token, admin_token, test_product):
        """Test that we cannot create a payment for an already paid withdrawal"""
        contractor_headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Create a withdrawal
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"TEST-PAID-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "999 Already Paid Blvd",
            "notes": "Test for already paid check"
        }
        
        withdrawal_response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=contractor_headers)
        withdrawal = withdrawal_response.json()
        
        # Mark it as paid (admin only)
        mark_paid_response = requests.put(f"{API_URL}/withdrawals/{withdrawal['id']}/mark-paid", headers=admin_headers)
        assert mark_paid_response.status_code == 200, f"Mark paid failed: {mark_paid_response.text}"
        
        # Now try to create payment for it
        payment_data = {
            "withdrawal_id": withdrawal["id"],
            "origin_url": "http://localhost:3000"
        }
        
        response = requests.post(f"{API_URL}/payments/create-checkout", json=payment_data, headers=contractor_headers)
        
        assert response.status_code == 400, f"Expected 400 for already paid, got {response.status_code}"
        print("✓ Payment endpoint correctly rejects already paid withdrawal")


@pytest.mark.skipif(not RUN_E2E, reason="E2E: set RUN_E2E=1 to run against live server")
class TestPaymentMethodToggle:
    """Test that payment method selection affects checkout flow correctly"""

    def test_charge_to_account_flow(self, contractor_token, test_product):
        """Test the 'Charge to Account' flow - withdrawal only, no Stripe"""
        headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"CHARGE-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "Charge Account Address",
            "notes": "Charge to Account flow test"
        }
        
        response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["payment_status"] == "unpaid"
        
        # Verify the withdrawal exists
        get_response = requests.get(f"{API_URL}/withdrawals/{data['id']}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["payment_status"] == "unpaid"
        
        print("✓ Charge to Account flow works correctly - withdrawal logged as unpaid")


@pytest.mark.skipif(not RUN_E2E, reason="E2E: set RUN_E2E=1 to run against live server")
class TestAdminPaymentFeatures:
    """Test admin-specific payment features"""

    def test_admin_can_mark_withdrawal_paid(self, admin_token, contractor_token, test_product):
        """Test that admin can mark a withdrawal as paid"""
        contractor_headers = {"Authorization": f"Bearer {contractor_token}", "Content-Type": "application/json"}
        admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Create a withdrawal as contractor
        withdrawal_data = {
            "items": [{
                "product_id": test_product["id"],
                "sku": test_product["sku"],
                "name": test_product["name"],
                "quantity": 1,
                "price": test_product["price"],
                "cost": test_product.get("cost", 0),
                "subtotal": test_product["price"]
            }],
            "job_id": f"ADMIN-MARK-{uuid.uuid4().hex[:8].upper()}",
            "service_address": "Admin Mark Test",
            "notes": "Test admin mark paid"
        }
        
        withdrawal_response = requests.post(f"{API_URL}/withdrawals", json=withdrawal_data, headers=contractor_headers)
        assert withdrawal_response.status_code == 200
        
        withdrawal = withdrawal_response.json()
        assert withdrawal["payment_status"] == "unpaid"
        
        # Admin marks as paid
        mark_response = requests.put(f"{API_URL}/withdrawals/{withdrawal['id']}/mark-paid", headers=admin_headers)
        assert mark_response.status_code == 200
        
        marked = mark_response.json()
        assert marked["payment_status"] == "paid", f"Expected 'paid', got '{marked.get('payment_status')}'"
        assert "paid_at" in marked, "Should have paid_at timestamp"
        
        print(f"✓ Admin marked withdrawal as paid: paid_at={marked.get('paid_at')}")

    def test_financial_summary_includes_payments(self, admin_token):
        """Test that financial summary correctly shows paid/unpaid totals"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{API_URL}/financials/summary", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "total_unpaid" in data, "Should have total_unpaid"
        assert "total_paid" in data, "Should have total_paid"
        assert "total_revenue" in data, "Should have total_revenue"
        
        print(f"✓ Financial summary: Unpaid=${data.get('total_unpaid', 0)}, Paid=${data.get('total_paid', 0)}, Revenue=${data.get('total_revenue', 0)}")


class TestAuthorizationChecks:
    """Test that payment endpoints require authentication. Uses in-process TestClient."""

    def test_payment_requires_auth(self, client):
        """Payment create-checkout requires authentication."""
        response = client.post("/api/payments/create-checkout", json={
            "withdrawal_id": "test",
            "origin_url": "https://test.com",
        })
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"

    def test_status_requires_auth(self, client):
        """Payment status endpoint requires authentication."""
        response = client.get("/api/payments/status/test-session")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
