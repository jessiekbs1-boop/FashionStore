import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode_address(address, timeout=5):
    """Return (lat, lon) for the address using Nominatim, or None on failure."""
    if not address:
        return None
    try:
        headers = {'User-Agent': 'FashionStore/1.0 (contact@example.com)'}
        params = {'q': address, 'format': 'json', 'limit': 1}
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        lat = float(data[0]['lat'])
        lon = float(data[0]['lon'])
        return (lat, lon)
    except Exception:
        return None
