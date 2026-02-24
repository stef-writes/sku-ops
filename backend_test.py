#!/usr/bin/env python3
"""
Hardware Store API Test Suite
Tests all backend functionality including auth, departments, inventory, POS, vendors, and reports
"""

import requests
import sys
import json
from datetime import datetime, timezone
import uuid

class HardwareStoreAPITester:
    def __init__(self, base_url="https://hardware-pos-stripe.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test data storage
        self.department_ids = {}
        self.vendor_ids = {}
        self.product_ids = {}
        self.sale_ids = {}

    def log_result(self, test_name, success, message="", data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name} - {message}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "data": data
        })

    def make_request(self, method, endpoint, data=None, expected_status=200):
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except:
                response_data = {"text": response.text}

            return success, response_data, response.status_code

        except Exception as e:
            return False, {"error": str(e)}, 0

    # ==================== AUTHENTICATION TESTS ====================

    def test_register(self):
        """Test user registration"""
        user_data = {
            "email": "admin@store.com",
            "password": "admin123",
            "name": "Store Admin",
            "role": "admin"
        }
        
        success, response, status = self.make_request("POST", "/auth/register", user_data, 200)
        if success and "token" in response:
            self.token = response["token"]
            self.user = response["user"]
            self.log_result("User Registration", True)
            return True
        else:
            self.log_result("User Registration", False, f"Status: {status}, Response: {response}")
            return False

    def test_login(self):
        """Test user login"""
        login_data = {
            "email": "admin@store.com",
            "password": "admin123"
        }
        
        success, response, status = self.make_request("POST", "/auth/login", login_data, 200)
        if success and "token" in response:
            self.token = response["token"]
            self.user = response["user"]
            self.log_result("User Login", True)
            return True
        else:
            self.log_result("User Login", False, f"Status: {status}, Response: {response}")
            return False

    def test_get_profile(self):
        """Test getting user profile"""
        success, response, status = self.make_request("GET", "/auth/me", expected_status=200)
        if success and "email" in response:
            self.log_result("Get User Profile", True)
            return True
        else:
            self.log_result("Get User Profile", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== DEPARTMENT TESTS ====================

    def test_seed_departments(self):
        """Test seeding standard departments"""
        success, response, status = self.make_request("POST", "/seed/departments", expected_status=200)
        if success:
            self.log_result("Seed Departments", True, f"Seeded departments: {response.get('message', '')}")
            return True
        else:
            self.log_result("Seed Departments", False, f"Status: {status}, Response: {response}")
            return False

    def test_get_departments(self):
        """Test getting departments list"""
        success, response, status = self.make_request("GET", "/departments", expected_status=200)
        if success and isinstance(response, list):
            # Check for expected 8 departments
            expected_codes = ['LUM', 'PLU', 'ELE', 'PNT', 'TOL', 'HDW', 'GDN', 'APP']
            found_codes = [dept.get('code') for dept in response]
            
            # Store department IDs for later use
            for dept in response:
                self.department_ids[dept['code']] = dept['id']
            
            if len(response) >= 8 and all(code in found_codes for code in expected_codes):
                self.log_result("Get Departments", True, f"Found {len(response)} departments with expected codes")
                return True
            else:
                self.log_result("Get Departments", False, f"Expected 8 departments with codes {expected_codes}, found {found_codes}")
                return False
        else:
            self.log_result("Get Departments", False, f"Status: {status}, Response: {response}")
            return False

    def test_create_department(self):
        """Test creating a new department"""
        dept_data = {
            "name": "Test Department",
            "code": "TST",
            "description": "Test department for testing"
        }
        
        success, response, status = self.make_request("POST", "/departments", dept_data, 200)
        if success and "id" in response:
            self.department_ids["TST"] = response["id"]
            self.log_result("Create Department", True)
            return True
        else:
            self.log_result("Create Department", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== VENDOR TESTS ====================

    def test_create_vendor(self):
        """Test creating a vendor"""
        vendor_data = {
            "name": "Test Hardware Supplier",
            "contact_name": "John Doe",
            "email": "john@testvendor.com",
            "phone": "(555) 123-4567",
            "address": "123 Supply St, Hardware City"
        }
        
        success, response, status = self.make_request("POST", "/vendors", vendor_data, 200)
        if success and "id" in response:
            self.vendor_ids["test_vendor"] = response["id"]
            self.log_result("Create Vendor", True)
            return True
        else:
            self.log_result("Create Vendor", False, f"Status: {status}, Response: {response}")
            return False

    def test_get_vendors(self):
        """Test getting vendors list"""
        success, response, status = self.make_request("GET", "/vendors", expected_status=200)
        if success and isinstance(response, list):
            self.log_result("Get Vendors", True, f"Found {len(response)} vendors")
            return True
        else:
            self.log_result("Get Vendors", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== PRODUCT TESTS ====================

    def test_create_product(self):
        """Test creating a product with SKU generation"""
        if "LUM" not in self.department_ids:
            self.log_result("Create Product", False, "No LUM department ID available")
            return False
            
        product_data = {
            "name": "Test 2x4 Pine Board",
            "description": "8-foot pine board for testing",
            "price": 15.99,
            "cost": 12.00,
            "quantity": 50,
            "min_stock": 10,
            "department_id": self.department_ids["LUM"],
            "vendor_id": self.vendor_ids.get("test_vendor"),
            "barcode": "123456789012"
        }
        
        success, response, status = self.make_request("POST", "/products", product_data, 200)
        if success and "id" in response and "sku" in response:
            # Verify SKU format: LUM-XXXXX
            sku = response["sku"]
            if sku.startswith("LUM-") and len(sku) == 9:
                self.product_ids["test_product"] = response["id"]
                self.log_result("Create Product", True, f"Created product with SKU: {sku}")
                return True
            else:
                self.log_result("Create Product", False, f"Invalid SKU format: {sku}")
                return False
        else:
            self.log_result("Create Product", False, f"Status: {status}, Response: {response}")
            return False

    def test_get_products(self):
        """Test getting products list"""
        success, response, status = self.make_request("GET", "/products", expected_status=200)
        if success and isinstance(response, list):
            self.log_result("Get Products", True, f"Found {len(response)} products")
            return True
        else:
            self.log_result("Get Products", False, f"Status: {status}, Response: {response}")
            return False

    def test_search_products(self):
        """Test product search functionality"""
        success, response, status = self.make_request("GET", "/products?search=pine", expected_status=200)
        if success and isinstance(response, list):
            self.log_result("Search Products", True, f"Search returned {len(response)} products")
            return True
        else:
            self.log_result("Search Products", False, f"Status: {status}, Response: {response}")
            return False

    def test_filter_products_by_department(self):
        """Test filtering products by department"""
        if "LUM" not in self.department_ids:
            self.log_result("Filter Products by Department", False, "No LUM department ID available")
            return False
            
        success, response, status = self.make_request("GET", f"/products?department_id={self.department_ids['LUM']}", expected_status=200)
        if success and isinstance(response, list):
            self.log_result("Filter Products by Department", True, f"Found {len(response)} products in LUM department")
            return True
        else:
            self.log_result("Filter Products by Department", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== POS/SALES TESTS ====================

    def test_create_sale(self):
        """Test creating a sale (POS functionality)"""
        if "test_product" not in self.product_ids:
            self.log_result("Create Sale", False, "No test product available for sale")
            return False
        
        # First get product details
        success, product, status = self.make_request("GET", f"/products/{self.product_ids['test_product']}", expected_status=200)
        if not success:
            self.log_result("Create Sale", False, "Could not fetch product details")
            return False
        
        sale_data = {
            "items": [
                {
                    "product_id": product["id"],
                    "sku": product["sku"],
                    "name": product["name"],
                    "quantity": 2,
                    "price": product["price"],
                    "subtotal": product["price"] * 2
                }
            ],
            "payment_method": "cash",
            "customer_name": "Test Customer"
        }
        
        success, response, status = self.make_request("POST", "/sales", sale_data, 200)
        if success and "id" in response:
            self.sale_ids["test_sale"] = response["id"]
            expected_subtotal = product["price"] * 2
            expected_tax = expected_subtotal * 0.08
            expected_total = expected_subtotal + expected_tax
            
            if (abs(response["subtotal"] - expected_subtotal) < 0.01 and 
                abs(response["tax"] - expected_tax) < 0.01 and 
                abs(response["total"] - expected_total) < 0.01):
                self.log_result("Create Sale", True, f"Sale created with total: ${response['total']:.2f}")
                return True
            else:
                self.log_result("Create Sale", False, f"Incorrect sale calculations: {response}")
                return False
        else:
            self.log_result("Create Sale", False, f"Status: {status}, Response: {response}")
            return False

    def test_get_sales(self):
        """Test getting sales list"""
        success, response, status = self.make_request("GET", "/sales", expected_status=200)
        if success and isinstance(response, list):
            self.log_result("Get Sales", True, f"Found {len(response)} sales")
            return True
        else:
            self.log_result("Get Sales", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== REPORTS TESTS ====================

    def test_sales_report(self):
        """Test sales report generation"""
        success, response, status = self.make_request("GET", "/reports/sales", expected_status=200)
        if success and "total_revenue" in response:
            self.log_result("Sales Report", True, f"Revenue: ${response['total_revenue']:.2f}, Transactions: {response['total_transactions']}")
            return True
        else:
            self.log_result("Sales Report", False, f"Status: {status}, Response: {response}")
            return False

    def test_inventory_report(self):
        """Test inventory report generation"""
        success, response, status = self.make_request("GET", "/reports/inventory", expected_status=200)
        if success and "total_products" in response:
            self.log_result("Inventory Report", True, f"Products: {response['total_products']}, Value: ${response['total_retail_value']:.2f}")
            return True
        else:
            self.log_result("Inventory Report", False, f"Status: {status}, Response: {response}")
            return False

    def test_dashboard_stats(self):
        """Test dashboard statistics"""
        success, response, status = self.make_request("GET", "/dashboard/stats", expected_status=200)
        if success and "today_revenue" in response:
            self.log_result("Dashboard Stats", True, f"Today's Revenue: ${response['today_revenue']:.2f}")
            return True
        else:
            self.log_result("Dashboard Stats", False, f"Status: {status}, Response: {response}")
            return False

    # ==================== TEST RUNNER ====================

    def run_all_tests(self):
        """Run all test suites"""
        print(f"🚀 Starting Hardware Store API Tests")
        print(f"📡 Base URL: {self.base_url}")
        print("=" * 60)

        # Test authentication
        print("\n📋 AUTHENTICATION TESTS")
        if not self.test_register():
            # Try login if registration fails (user might already exist)
            if not self.test_login():
                print("❌ Cannot authenticate - stopping tests")
                return False
        
        self.test_get_profile()

        # Test departments
        print("\n🏪 DEPARTMENT TESTS")
        self.test_seed_departments()
        self.test_get_departments()
        self.test_create_department()

        # Test vendors
        print("\n🚛 VENDOR TESTS")
        self.test_create_vendor()
        self.test_get_vendors()

        # Test products
        print("\n📦 PRODUCT TESTS")
        self.test_create_product()
        self.test_get_products()
        self.test_search_products()
        self.test_filter_products_by_department()

        # Test POS/Sales
        print("\n💳 POS/SALES TESTS")
        self.test_create_sale()
        self.test_get_sales()

        # Test reports
        print("\n📊 REPORTS TESTS")
        self.test_sales_report()
        self.test_inventory_report()
        self.test_dashboard_stats()

        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY")
        print(f"✅ Passed: {self.tests_passed}/{self.tests_run}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        # List failed tests
        failed_tests = [r for r in self.test_results if not r["success"]]
        if failed_tests:
            print(f"\n❌ FAILED TESTS ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['test']}: {test['message']}")

        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = HardwareStoreAPITester()
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())