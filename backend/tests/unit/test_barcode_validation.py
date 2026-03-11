"""Tests for barcode validation (UPC-A, EAN-13)."""

from shared.kernel.barcode import validate_barcode, validate_ean13, validate_upc


class TestValidateUpc:
    def test_valid_upc(self):
        assert validate_upc("042100005264") is True
        assert validate_upc("023456000073") is True
        assert validate_upc("212345678992") is True

    def test_invalid_upc_wrong_check_digit(self):
        assert validate_upc("042100005265") is False  # wrong last digit
        assert validate_upc("123456789013") is False  # invalid check digit

    def test_invalid_upc_wrong_length(self):
        assert validate_upc("1234567890") is False
        assert validate_upc("1234567890123") is False
        assert validate_upc("12345678901") is False

    def test_invalid_upc_non_digit(self):
        assert validate_upc("04210000526a") is False
        assert validate_upc("") is False
        assert validate_upc(None) is False


class TestValidateEan13:
    def test_valid_ean13(self):
        assert validate_ean13("5901234123457") is True

    def test_invalid_ean13_wrong_length(self):
        assert validate_ean13("590123412345") is False
        assert validate_ean13("59012341234578") is False

    def test_invalid_ean13_empty(self):
        assert validate_ean13("") is False
        assert validate_ean13(None) is False


class TestValidateBarcode:
    def test_valid_upc_returns_upc_format(self):
        valid, fmt = validate_barcode("042100005264")
        assert valid is True
        assert fmt == "UPC"

    def test_valid_ean13_returns_ean13_format(self):
        valid, fmt = validate_barcode("5901234123457")
        assert valid is True
        assert fmt == "EAN13"

    def test_alphanumeric_returns_code128(self):
        valid, fmt = validate_barcode("LUM-PIPE-000001")
        assert valid is True
        assert fmt == "CODE128"

        valid, fmt = validate_barcode("HDW-ITM-000042")
        assert valid is True
        assert fmt == "CODE128"

    def test_invalid_upc_check_digit_returns_false(self):
        valid, fmt = validate_barcode("042100005265")
        assert valid is False
        assert fmt is None

    def test_11_digits_returns_false(self):
        valid, fmt = validate_barcode("04210000526")
        assert valid is False
        assert fmt is None

    def test_empty_returns_false(self):
        valid, fmt = validate_barcode("")
        assert valid is False
        assert fmt is None
        valid, fmt = validate_barcode(None)
        assert valid is False
        assert fmt is None
