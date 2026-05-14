from app import app

client = app.test_client()

def post(path, data):
    res = client.post(path, json=data)
    print(path, res.status_code)
    try:
        print(res.get_json())
        return res.get_json() or {}
    except Exception:
        print(res.data[:500])
        return {}

pickup = post("/api/map/search", {"query": "Nebo Street Wanaheda"})
dropoff = post("/api/map/search", {"query": "Grove Mall Windhoek"})

p = (pickup.get("results") or pickup.get("places") or pickup.get("result") or [{}])
d = (dropoff.get("results") or dropoff.get("places") or dropoff.get("result") or [{}])
if isinstance(p, dict): p = [p]
if isinstance(d, dict): d = [d]
p0, d0 = p[0], d[0]

quote = post("/api/quote/estimate", {
    "pickup_text": p0.get("display_name") or "Nebo Street Wanaheda",
    "dropoff_text": d0.get("display_name") or "Grove Mall Windhoek",
    "pickup_lat": p0.get("lat"),
    "pickup_lng": p0.get("lng") or p0.get("lon"),
    "dropoff_lat": d0.get("lat"),
    "dropoff_lng": d0.get("lng") or d0.get("lon"),
    "vehicle_type": "sedan",
    "service_type": "once_off",
    "passengers": 1,
    "luggage_count": 0,
    "save": True
})

assert quote.get("ok", True) is not False
q = quote.get("quote") or quote
assert float(q.get("final_price") or q.get("amount") or 0) > 0
print("✅ Quick Book flow passed")
