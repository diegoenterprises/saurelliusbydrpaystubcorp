"""
Weather and Location Service
Provides real-time weather, season, and timezone data
"""

import requests
import os
from datetime import datetime
import pytz
from typing import Dict, Optional

class WeatherService:
    def __init__(self):
        self.openweather_api_key = os.getenv('OPENWEATHER_API_KEY')
        self.ipgeo_api_key = os.getenv('IPGEOLOCATION_API_KEY')
        self.openweather_base = 'https://api.openweathermap.org/data/2.5'
        self.ipgeo_base = 'https://api.ipgeolocation.io/ipgeo'
    
    def get_location_from_ip(self, ip_address: str) -> Optional[Dict]:
        """Get user location from IP address"""
        try:
            response = requests.get(
                self.ipgeo_base,
                params={
                    'apiKey': self.ipgeo_api_key,
                    'ip': ip_address
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'city': data.get('city'),
                    'state': data.get('state_prov'),
                    'country': data.get('country_name'),
                    'latitude': float(data.get('latitude', 0)),
                    'longitude': float(data.get('longitude', 0)),
                    'timezone': data.get('time_zone', {}).get('name', 'UTC'),
                    'timezone_offset': data.get('time_zone', {}).get('offset', 0)
                }
        except Exception as e:
            print(f"❌ Location lookup failed: {e}")
            return None
    
    def get_weather(self, latitude: float, longitude: float) -> Optional[Dict]:
        """Get current weather and forecast"""
        try:
            # Current weather
            current_response = requests.get(
                f'{self.openweather_base}/weather',
                params={
                    'lat': latitude,
                    'lon': longitude,
                    'appid': self.openweather_api_key,
                    'units': 'imperial'
                },
                timeout=5
            )
            
            # 5-day forecast
            forecast_response = requests.get(
                f'{self.openweather_base}/forecast',
                params={
                    'lat': latitude,
                    'lon': longitude,
                    'appid': self.openweather_api_key,
                    'units': 'imperial',
                    'cnt': 8  # Next 24 hours (3-hour intervals)
                },
                timeout=5
            )
            
            if current_response.status_code == 200 and forecast_response.status_code == 200:
                current = current_response.json()
                forecast = forecast_response.json()
                
                return {
                    'current': {
                        'temperature': round(current['main']['temp']),
                        'feels_like': round(current['main']['feels_like']),
                        'humidity': current['main']['humidity'],
                        'description': current['weather'][0]['description'].title(),
                        'icon': current['weather'][0]['icon'],
                        'wind_speed': round(current['wind']['speed']),
                        'pressure': current['main']['pressure'],
                        'visibility': current.get('visibility', 0) / 1000  # km
                    },
                    'forecast': [
                        {
                            'time': item['dt_txt'],
                            'temperature': round(item['main']['temp']),
                            'description': item['weather'][0]['description'].title(),
                            'icon': item['weather'][0]['icon'],
                            'pop': round(item.get('pop', 0) * 100)  # Probability of precipitation
                        }
                        for item in forecast['list'][:8]
                    ]
                }
        except Exception as e:
            print(f"❌ Weather lookup failed: {e}")
            return None
    
    def get_season(self, latitude: float) -> str:
        """Determine current season based on location"""
        month = datetime.now().month
        
        # Northern Hemisphere
        if latitude >= 0:
            if month in [12, 1, 2]:
                return 'Winter'
            elif month in [3, 4, 5]:
                return 'Spring'
            elif month in [6, 7, 8]:
                return 'Summer'
            elif month in [9, 10, 11]:
                return 'Autumn'
        # Southern Hemisphere
        else:
            if month in [6, 7, 8]:
                return 'Winter'
            elif month in [9, 10, 11]:
                return 'Spring'
            elif month in [12, 1, 2]:
                return 'Summer'
            elif month in [3, 4, 5]:
                return 'Autumn'
        return 'Unknown'

    def get_time_and_timezone(self, timezone_name: str) -> Dict:
        """Get current time and timezone info"""
        try:
            tz = pytz.timezone(timezone_name)
            now = datetime.now(tz)
            return {
                'current_time': now.strftime('%H:%M:%S'),
                'current_date': now.strftime('%Y-%m-%d'),
                'timezone_name': timezone_name,
                'timezone_abbr': now.strftime('%Z')
            }
        except pytz.exceptions.UnknownTimeZoneError:
            return {
                'current_time': 'N/A',
                'current_date': 'N/A',
                'timezone_name': timezone_name,
                'timezone_abbr': 'N/A'
            }

    def get_full_weather_data(self, ip_address: str) -> Dict:
        """
        Main function to get all weather and location data.
        This will be called by the dashboard route.
        """
        location_data = self.get_location_from_ip(ip_address)
        
        if not location_data:
            return {
                'status': 'error',
                'message': 'Could not determine location from IP address.'
            }

        weather_data = self.get_weather(
            location_data['latitude'],
            location_data['longitude']
        )
        
        time_data = self.get_time_and_timezone(location_data['timezone'])
        
        season = self.get_season(location_data['latitude'])
        
        return {
            'status': 'success',
            'location': location_data,
            'weather': weather_data,
            'time': time_data,
            'season': season
        }

if __name__ == '__main__':
    # Example usage for testing
    # Note: This will use the sandbox's IP address, which may not be accurate
    # for a real user.
    # Replace with a known IP for testing, or rely on the client's IP in the Flask app.
    
    # Set dummy environment variables for local testing
    os.environ['OPENWEATHER_API_KEY'] = 'YOUR_OPENWEATHER_API_KEY'
    os.environ['IPGEOLOCATION_API_KEY'] = 'YOUR_IPGEOLOCATION_API_KEY'
    
    service = WeatherService()
    
    # Use a dummy IP for demonstration (e.g., Google's public DNS)
    test_ip = '8.8.8.8' 
    
    print(f"Fetching data for IP: {test_ip}")
    data = service.get_full_weather_data(test_ip)
    
    import json
    print(json.dumps(data, indent=4))
