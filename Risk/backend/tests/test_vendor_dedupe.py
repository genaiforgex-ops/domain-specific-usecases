from app.services.vendor_service import VendorService


def test_dedupe_hash_stable():
    svc = VendorService.__new__(VendorService)
    h1 = svc._dedupe_hash("Pending civil suit", "https://courts.gov/case/001")
    h2 = svc._dedupe_hash("Pending civil suit", "https://courts.gov/case/001")
    h3 = svc._dedupe_hash("Different case", "https://courts.gov/case/002")
    assert h1 == h2
    assert h1 != h3
