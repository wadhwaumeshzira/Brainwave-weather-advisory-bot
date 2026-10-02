import os
import sys
import httpx
from app.weather import geocode, fetch_weather, LocationError, WeatherError

def test_fixes():
    print("--- 1. Normal Call ---")
    try:
        lat, lon, name = geocode("Bhopal")
        print(f"Geocoded: {name} (Lat: {lat}, Lon: {lon})")
    except Exception as e:
        print("Failed:", e)

    print("\n--- 2. Forced Fail ---")
    os.environ["WEATHER_FORCE_FAIL"] = "1"
    try:
        geocode("Bhopal")
    except WeatherError as e:
        print("Caught expected WeatherError:", e)
    os.environ["WEATHER_FORCE_FAIL"] = "0"

    print("\n--- 3. Nonexistent City ---")
    try:
        geocode("fakemakecity123456")
    except LocationError as e:
        print("Caught expected LocationError:", e)

    print("\n--- 4. Simulated HTTP 500 ---")
    original_get = httpx.get
    
    def mock_get(*args, **kwargs):
        # Return a mocked 500 response
        return httpx.Response(500, request=httpx.Request("GET", args[0]))
    
    httpx.get = mock_get
    try:
        geocode("Bhopal")
    except LocationError as e:
        print("Caught expected LocationError on 500:", e)
    finally:
        httpx.get = original_get

if __name__ == "__main__":
    # We must set dummy LLM vars just so app.config doesn't crash on import if we import it, 
    # but we don't import app.config here directly, wait app.weather imports config?
    # No, we removed app.config import from app.weather!
    test_fixes()
