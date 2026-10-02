import os
import json
import httpx
from typing import Tuple, Dict, Any

class LocationError(Exception):
    """Raised when geocoding fails or returns empty results."""
    pass

class WeatherError(Exception):
    """Raised when weather fetch fails or is forced to fail."""
    pass

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

def geocode(city: str) -> Tuple[float, float, str]:
    """
    Returns (latitude, longitude, resolved_name).
    """
    if os.getenv("WEATHER_MODE", "live") == "fixture":
        fixture_name = os.getenv("WEATHER_FIXTURE") or city.lower()
        path = f"evals/fixtures/{fixture_name}.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            return (data.get("latitude", 0), data.get("longitude", 0), f"{city.title()}, Madhya Pradesh, India" if "bhopal" in fixture_name else f"{city.title()}, Simulated")
        else:
            raise LocationError(f"Fixture not found for {fixture_name}")

    try:
        res = httpx.get(GEO_URL, params={"name": city, "count": 1}, timeout=5.0)
        res.raise_for_status()
        data = res.json()
        
        if not data.get("results"):
            raise LocationError(f"Location not found: {city}")
            
        result = data["results"][0]
        
        parts = [result.get("name"), result.get("admin1"), result.get("country")]
        full_name = ", ".join(p for p in parts if p)
        
        return (result["latitude"], result["longitude"], full_name)
    except (httpx.HTTPError, ValueError) as e:
        raise LocationError(f"Geocoding request failed: {e}")


def fetch_weather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetches the weather data using the fixed wide field superset.
    """
    if os.getenv("WEATHER_FORCE_FAIL", "0") == "1":
        raise WeatherError("Forced weather failure")
        
    if os.getenv("WEATHER_MODE", "live") == "fixture":
        fixture_name = os.getenv("WEATHER_FIXTURE")
        if fixture_name:
            path = f"evals/fixtures/{fixture_name}.json"
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
                    
        fixtures_dir = "evals/fixtures"
        if os.path.exists(fixtures_dir):
            for fname in os.listdir(fixtures_dir):
                if fname.endswith(".json"):
                    with open(os.path.join(fixtures_dir, fname), "r") as f:
                        data = json.load(f)
                        if abs(data.get("latitude", 0) - lat) < 0.01 and abs(data.get("longitude", 0) - lon) < 0.01:
                            return data
        raise WeatherError("No fixture matched these coordinates")

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m,uv_index",
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m,uv_index,visibility",
        "daily": "precipitation_sum,precipitation_hours,weather_code,wind_gusts_10m_max,uv_index_max,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 2
    }
    
    try:
        res = httpx.get(WEATHER_URL, params=params, timeout=5.0)
        res.raise_for_status()
        data = res.json()
        
        if not all(k in data for k in ["current", "hourly", "daily"]):
            raise WeatherError("Missing required data blocks in weather response")
            
        return data
    except (httpx.HTTPError, ValueError) as e:
        raise WeatherError(f"Weather fetch failed: {e}")
