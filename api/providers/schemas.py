from dataclasses import dataclass


@dataclass
class Condition:
    code: int
    text: str | None
    icon: int


@dataclass
class Location:
    name: str
    region: str
    country: str
    lat: float
    lon: float
    tz_id: str
    localtime_epoch: int
    localtime: str


@dataclass
class CurrentWeather:
    temp: float
    min_temp: float
    max_temp: float
    is_day: bool
    feels_like: float
    condition: Condition


@dataclass
class HourlyForecast:
    temp: float
    humidity: float
    timestamp: int
    is_day: bool
    condition: Condition


@dataclass
class DailyForecast:
    min_temp: float
    max_temp: float
    humidity: float
    timestamp: int
    is_day: bool
    condition: Condition


@dataclass
class WeatherData:
    last_updated: int
    source: str
    source_link: str
    location: Location
    current: CurrentWeather
    next_24h: list[HourlyForecast]
    next_days: list[DailyForecast]
