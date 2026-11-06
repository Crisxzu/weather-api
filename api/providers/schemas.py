from dataclasses import dataclass

# v2 fields are optional (default None) and appended after the v1 fields:
# a provider that cannot supply a value leaves it at None, and v1 clients
# simply ignore the extra keys.


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
    # v2
    humidity: float | None = None
    wind_kph: float | None = None
    wind_degree: float | None = None
    gust_kph: float | None = None
    uv: float | None = None
    precip_mm: float | None = None
    cloud_cover: float | None = None
    visibility_km: float | None = None


@dataclass
class HourlyForecast:
    temp: float
    humidity: float
    timestamp: int
    is_day: bool
    condition: Condition
    # v2
    chance_of_rain: float | None = None
    chance_of_snow: float | None = None
    precip_mm: float | None = None
    feels_like: float | None = None
    wind_kph: float | None = None
    uv: float | None = None
    cloud_cover: float | None = None
    visibility_km: float | None = None
    snow_cm: float | None = None


@dataclass
class DailyForecast:
    min_temp: float
    max_temp: float
    humidity: float
    timestamp: int
    is_day: bool
    condition: Condition
    # v2
    chance_of_rain: float | None = None
    chance_of_snow: float | None = None
    total_precip_mm: float | None = None
    max_wind_kph: float | None = None
    uv: float | None = None
    sunrise: int | None = None
    sunset: int | None = None
    total_snow_cm: float | None = None


@dataclass
class MinutelyPrecipitation:
    timestamp: int
    precip_mm: float | None


@dataclass
class WeatherAlert:
    event: str
    headline: str
    severity: str
    effective: int | None
    expires: int | None


@dataclass
class WeatherData:
    last_updated: int
    source: str
    source_link: str
    location: Location
    current: CurrentWeather
    next_24h: list[HourlyForecast]
    next_days: list[DailyForecast]
    # v2 — None means "this provider does not support it", not "nothing to report".
    next_minutes: list[MinutelyPrecipitation] | None = None
    alerts: list[WeatherAlert] | None = None
