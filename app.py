from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
import requests
from datetime import datetime, timedelta

# Initialize Flask app and configure it
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'
db = SQLAlchemy(app)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

# Define Location model
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    country_code = db.Column(db.String(10))
    __table_args__ = (db.UniqueConstraint('city', 'country_code', name='_city_country_uc'),)

# Initialize the database
with app.app_context():
    db.create_all()

API_KEY = 'API_KEY'

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        city = request.form.get('city')
        country_code = request.form.get('country')
        if city:
            city = city.title()  # Capitalize the first letter of each word
            country_code = country_code.upper() if country_code else None  # Convert country code to uppercase
            existing_location = Location.query.filter_by(city=city, country_code=country_code).first()
            if existing_location:
                return jsonify({'status': 'error', 'message': 'Location already exists!'})
            
            new_location = Location(city=city, country_code=country_code)
            db.session.add(new_location)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Location added successfully!'})

    locations = Location.query.all()
    weather_data = []

    for location in locations:
        weather = get_weather(location.city, location.country_code)
        if weather:
            weather_data.append(weather)

    return render_template('index.html', weather_data=weather_data)

@app.route('/delete', methods=['POST'])
def delete_location():
    city = request.form.get('city')
    country_code = request.form.get('country_code')
    if city:
        location = Location.query.filter_by(city=city, country_code=country_code).first()
        if location:
            db.session.delete(location)
            db.session.commit()
            flash('Location deleted successfully!')
        else:
            flash('Location not found!')
    else:
        flash('City not provided!')
    return redirect(url_for('index'))

@app.route('/location/<city>/<country_code>', methods=['GET'])
def location_detail(city, country_code=None):
    city = city.replace('_', ' ').title()
    country_code = country_code.upper() if country_code else None

    weather = get_weather(city, country_code)
    if not weather:
        return redirect(url_for('index'))

    hourly_forecast = get_hourly_forecast(city, country_code)
    three_hour_forecast = get_three_hour_forecast(city, country_code)

    print(f"Hourly Forecast: {hourly_forecast}")  # Debugging line
    print(f"Three Day Forecast: {three_hour_forecast}")    # Debugging line

    return render_template('location_detail.html', weather=weather, hourly_forecast=hourly_forecast, three_hour_forecast=three_hour_forecast)

def get_weather(city, country_code=None):
    cache_key = f'weather_data_{city}_{country_code}'
    cached_weather = cache.get(cache_key)
    if cached_weather:
        return cached_weather

    coordinates = get_coordinates(city, country_code)
    if not coordinates:
        print(f"Coordinates not found for city: {city}")
        return None

    lat, lon = coordinates
    url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        temperature_celsius = data['main']['temp']
        temperature_fahrenheit = (temperature_celsius * 9/5) + 32
        feels_like_celsius = data['main']['feels_like']
        feels_like_fahrenheit = (feels_like_celsius * 9/5) + 32
        sunrise_timestamp = data['sys']['sunrise']
        sunset_timestamp = data['sys']['sunset']
        
        # Convert sunrise and sunset to Eastern Standard Time (EST) and 12-hour format with AM/PM
        est_offset = timedelta(hours=-5)  # EST is UTC-5
        sunrise = (datetime.utcfromtimestamp(sunrise_timestamp) + est_offset).strftime('%I:%M %p')
        sunset = (datetime.utcfromtimestamp(sunset_timestamp) + est_offset).strftime('%I:%M %p')
        
        precipitation_chance = data.get('rain', {}).get('1h', 0)  # Use rain volume as a proxy for precipitation chance

        weather = {
            'city': city,
            'country_code': country_code,
            'temperature': temperature_celsius,
            'temperature_f': round(temperature_fahrenheit, 2),
            'feels_like': feels_like_celsius,
            'feels_like_f': round(feels_like_fahrenheit, 2),
            'description': data['weather'][0]['description'],
            'icon': data['weather'][0]['icon'],
            'humidity': data['main']['humidity'],
            'wind_speed': data['wind']['speed'],
            'sunrise': sunrise,
            'sunset': sunset,
            'precipitation_chance': precipitation_chance
        }
        cache.set(cache_key, weather, timeout=300)
        return weather
    else:
        print(f"Error fetching weather data for {city}: {response.status_code}")
    return None

def get_hourly_forecast(city, country_code=None):
    coordinates = get_coordinates(city, country_code)
    if not coordinates:
        print("Coordinates not found.")
        return None

    lat, lon = coordinates
    url = f'https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}&units=metric'
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print("API Response Data:", data)

        if 'list' not in data:
            print("No 'list' found in response data.")
            return None

        hourly_data = data['list']
        today = datetime.utcnow().date()
        hourly_forecast = []

        for entry in hourly_data:
            if 'dt' not in entry or 'main' not in entry or 'weather' not in entry:
                print("Missing keys in entry:", entry)
                continue

            timestamp = datetime.utcfromtimestamp(entry['dt'])
            if timestamp.date() == today:
                temperature_celsius = entry['main'].get('temp', 'N/A')
                feels_like_celsius = entry['main'].get('feels_like', 'N/A')
                description = entry['weather'][0].get('description', 'N/A')
                icon = entry['weather'][0].get('icon', '')
                humidity = entry['main'].get('humidity', 'N/A')
                wind_speed = entry['wind'].get('speed', 'N/A')
                precipitation_chance = entry.get('pop', 'N/A') * 100  # Probability of precipitation in percentage

                # Calculate Fahrenheit temperatures directly in the dictionary
                hourly_forecast.append({
                    'time': timestamp.strftime('%I:%M %p'),
                    'temperature': round(temperature_celsius, 2),
                    'temperature_f': round(temperature_celsius * 9/5 + 32, 2),
                    'feels_like': round(feels_like_celsius, 2),
                    'feels_like_f': round(feels_like_celsius * 9/5 + 32, 2),
                    'description': description,
                    'icon': icon,
                    'humidity': humidity,
                    'wind_speed': wind_speed,
                    'precipitation_chance': round(precipitation_chance, 2)
                })

        return hourly_forecast

    else:
        print(f"Request failed with status code {response.status_code}")
        return None

def get_three_hour_forecast(city, country_code=None):
    coordinates = get_coordinates(city, country_code)
    if not coordinates:
        return None

    lat, lon = coordinates
    url = f'https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}&units=metric'
    print(f"Request URL: {url}")  # Debugging line to check the request URL

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx and 5xx)
        data = response.json()
        forecast_list = data.get('list', [])
        three_hour_forecast = []
        today = datetime.utcnow().date()

        for i in range(3):  # Iterate over the next 3 days
            day_forecast = {
                'date': (today + timedelta(days=i)).strftime('%A, %B %d, %Y'),  # Format the date here
                'forecasts': []
            }
            for entry in forecast_list:
                timestamp = datetime.utcfromtimestamp(entry['dt'])
                entry_date = timestamp.date()
                if entry_date == (today + timedelta(days=i)):
                    day_forecast['forecasts'].append({
                        'time': timestamp.strftime('%I:%M %p'),
                        'temperature': round(entry['main']['temp'], 2),
                        'temperature_f': round(entry['main']['temp'] * 9/5 + 32, 2),
                        'feels_like': round(entry['main']['feels_like'], 2),
                        'feels_like_f': round(entry['main']['feels_like'] * 9/5 + 32, 2),
                        'description': entry['weather'][0]['description'],
                        'humidity': entry['main']['humidity'],
                        'wind_speed': round(entry['wind']['speed'], 2),
                        'precipitation_chance': round(entry.get('rain', {}).get('3h', 0) + entry.get('snow', {}).get('3h', 0), 2),
                        'icon': entry['weather'][0]['icon']
                    })
            three_hour_forecast.append(day_forecast)
        return three_hour_forecast
    except requests.exceptions.RequestException as e:
        print(f"Error fetching 3-hour forecast data: {e}")
    return None

def get_coordinates(city, country_code=None):
    if country_code:
        url = f'http://api.openweathermap.org/geo/1.0/direct?q={city},{country_code}&appid={API_KEY}'
    else:
        url = f'http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={API_KEY}'
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data:
            lat = data[0]['lat']
            lon = data[0]['lon']
            return lat, lon
    print(f"Error fetching coordinates for {city}: {response.status_code}")
    return None

if __name__ == '__main__':
    app.run(debug=True)

