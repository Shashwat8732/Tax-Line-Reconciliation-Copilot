from app.services.ingestion import _clean_amount

test_cases = [
    ("Rs. 4783.95", 4783.95),
    ("Rs. 4,783.95", 4783.95),
    ("INR 12,000", 12000.0),
    ("$1,234.56", 1234.56),
    ("(500.00)", -500.0),
    ("-500", -500.0),
    ("1,23,456.78", 123456.78),
    ("  9999  ", 9999.0),
    ("", 0.0),
    (5000, 5000.0),
]

all_pass = True
for raw, expected in test_cases:
    result = _clean_amount(raw)
    status = "PASS" if abs(result - expected) < 0.01 else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(status, "input=", repr(raw), "-> got=", result, "expected=", expected)

print()
print("ALL PASS" if all_pass else "SOME FAILED")
