import requests
import time

BASE_URL = "http://localhost:8000"

def test_health():
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    print(f"✅ Health OK (version: {body.get('version', '?')})")

def test_classify():
    data = {
        "descrizioni": ["Olio extravergine", "Farina 00", "Sale fino"],
        "fornitori": None,
        "iva": None,
        "hint": None,
        "user_id": "test_user"
    }
    start = time.time()
    r = requests.post(f"{BASE_URL}/api/classify", json=data)
    elapsed = (time.time() - start) * 1000
    result = r.json()
    assert result["count"] == 3
    assert "categorie" in result
    print(f"✅ Classify OK: {result['categorie'][:2]}... ({result['elapsed_ms']:.0f}ms)")

def test_parse():
    # Crea XML test
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>TEST</FatturaElettronica>'''
    files = {'file': ('test.xml', xml_content, 'application/xml')}
    data = {'user_id': 'test_user'}
    r = requests.post(f"{BASE_URL}/api/parse", files=files, data=data)
    result = r.json()
    assert result["count"] >= 0
    print(f"✅ Parse OK: {result['count']} fatture")

if __name__ == "__main__":
    print("🚀 TESTING WORKER...")
    test_health()
    test_classify()
    test_parse()
    print("🎉 TUTTI TEST PASSATI!")
