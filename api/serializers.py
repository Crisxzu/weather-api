from rest_framework import serializers

temp_interval = {'min_value': -273.17, 'max_value': 90.0}
humidity_interval = {'min_value': 0, 'max_value': 100}

# v2 fields: always nullable, and only lower-bounded where a negative value is
# physically impossible. The view validates its own output, so an over-strict
# bound here would turn an unusual provider value into a 500.
_percent = {'min_value': 0, 'max_value': 100, 'allow_null': True}
_non_negative = {'min_value': 0, 'allow_null': True}


def _nullable_temp():
    return serializers.FloatField(**temp_interval, allow_null=True)


class ConditionSerializer(serializers.Serializer):
    code = serializers.IntegerField()
    text = serializers.CharField(max_length=200)
    icon = serializers.IntegerField()

class LocationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    region = serializers.CharField(max_length=200, allow_blank=True)
    country = serializers.CharField(max_length=200)
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    lon = serializers.FloatField(min_value=-180.0, max_value=180.0)
    tz_id = serializers.CharField(max_length=50)
    localtime_epoch = serializers.IntegerField()
    localtime = serializers.CharField(max_length=20)

class CurrentWeatherSerializer(serializers.Serializer):
    temp = serializers.FloatField(**temp_interval)
    min_temp = serializers.FloatField(**temp_interval)
    max_temp = serializers.FloatField(**temp_interval)
    is_day = serializers.BooleanField()
    feels_like = serializers.FloatField(**temp_interval)
    condition = ConditionSerializer()
    # v2
    humidity = serializers.FloatField(**_percent)
    wind_kph = serializers.FloatField(**_non_negative)
    wind_degree = serializers.FloatField(min_value=0, max_value=360, allow_null=True)
    gust_kph = serializers.FloatField(**_non_negative)
    uv = serializers.FloatField(**_non_negative)
    precip_mm = serializers.FloatField(**_non_negative)
    cloud_cover = serializers.FloatField(**_percent)
    visibility_km = serializers.FloatField(**_non_negative)

class HourlyForecastSerializer(serializers.Serializer):
    temp = serializers.FloatField(**temp_interval)
    humidity = serializers.FloatField(**humidity_interval)
    timestamp = serializers.IntegerField()
    is_day = serializers.BooleanField()
    condition = ConditionSerializer()
    # v2
    chance_of_rain = serializers.FloatField(**_percent)
    chance_of_snow = serializers.FloatField(**_percent)
    precip_mm = serializers.FloatField(**_non_negative)
    feels_like = _nullable_temp()
    wind_kph = serializers.FloatField(**_non_negative)
    uv = serializers.FloatField(**_non_negative)
    cloud_cover = serializers.FloatField(**_percent)
    visibility_km = serializers.FloatField(**_non_negative)
    snow_cm = serializers.FloatField(**_non_negative)

class DailyForecastSerializer(serializers.Serializer):
    min_temp = serializers.FloatField(**temp_interval)
    max_temp = serializers.FloatField(**temp_interval)
    humidity = serializers.FloatField(**humidity_interval)
    timestamp = serializers.IntegerField()
    is_day = serializers.BooleanField()
    condition = ConditionSerializer()
    # v2
    chance_of_rain = serializers.FloatField(**_percent)
    chance_of_snow = serializers.FloatField(**_percent)
    total_precip_mm = serializers.FloatField(**_non_negative)
    max_wind_kph = serializers.FloatField(**_non_negative)
    uv = serializers.FloatField(**_non_negative)
    sunrise = serializers.IntegerField(allow_null=True)
    sunset = serializers.IntegerField(allow_null=True)
    total_snow_cm = serializers.FloatField(**_non_negative)

class YesterdayWeatherSerializer(serializers.Serializer):
    min_temp = _nullable_temp()
    max_temp = _nullable_temp()
    temp_same_hour = _nullable_temp()
    condition = ConditionSerializer(allow_null=True)

class MinutelyPrecipitationSerializer(serializers.Serializer):
    timestamp = serializers.IntegerField()
    precip_mm = serializers.FloatField(**_non_negative)

class WeatherAlertSerializer(serializers.Serializer):
    event = serializers.CharField(allow_blank=True)
    headline = serializers.CharField(allow_blank=True)
    severity = serializers.CharField(allow_blank=True)
    effective = serializers.IntegerField(allow_null=True)
    expires = serializers.IntegerField(allow_null=True)

class PollenSerializer(serializers.Serializer):
    alder = serializers.FloatField(**_non_negative)
    birch = serializers.FloatField(**_non_negative)
    grass = serializers.FloatField(**_non_negative)
    mugwort = serializers.FloatField(**_non_negative)
    olive = serializers.FloatField(**_non_negative)
    ragweed = serializers.FloatField(**_non_negative)

class AirQualityValuesSerializer(serializers.Serializer):
    european_aqi = serializers.FloatField(**_non_negative)
    us_aqi = serializers.FloatField(**_non_negative)
    pm2_5 = serializers.FloatField(**_non_negative)
    pm10 = serializers.FloatField(**_non_negative)
    ozone = serializers.FloatField(**_non_negative)
    nitrogen_dioxide = serializers.FloatField(**_non_negative)
    pollen = PollenSerializer(allow_null=True)

class AirQualityDaySerializer(AirQualityValuesSerializer):
    timestamp = serializers.IntegerField(allow_null=True)

class AirQualitySerializer(serializers.Serializer):
    current = AirQualityValuesSerializer()
    days = AirQualityDaySerializer(many=True)

class WeatherDataSerializer(serializers.Serializer):
    last_updated = serializers.IntegerField()
    source = serializers.CharField(max_length=100)
    source_link = serializers.URLField()
    location = LocationSerializer()
    current = CurrentWeatherSerializer()
    next_24h = HourlyForecastSerializer(many=True)
    next_days = DailyForecastSerializer(many=True)
    # v2 — null = not supported by the provider that answered
    next_minutes = MinutelyPrecipitationSerializer(many=True, allow_null=True)
    alerts = WeatherAlertSerializer(many=True, allow_null=True)
    yesterday = YesterdayWeatherSerializer(allow_null=True)
    air_quality = AirQualitySerializer(allow_null=True)
