from rest_framework import serializers

temp_interval = {'min_value': -273.17, 'max_value': 90.0}
humidity_interval = {'min_value': 0, 'max_value': 100}

class ConditionSerializer(serializers.Serializer):
    code = serializers.IntegerField()
    text = serializers.CharField(max_length=200)
    icon = serializers.IntegerField()

class LocationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    region = serializers.CharField(max_length=200)
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

class HourlyForecastSerializer(serializers.Serializer):
    temp = serializers.FloatField(**temp_interval)
    humidity = serializers.FloatField(**humidity_interval)
    timestamp = serializers.IntegerField()
    condition = ConditionSerializer()

class DailyForecastSerializer(serializers.Serializer):
    min_temp = serializers.FloatField(**temp_interval)
    max_temp = serializers.FloatField(**temp_interval)
    humidity = serializers.FloatField(**humidity_interval)
    timestamp = serializers.IntegerField()
    condition = ConditionSerializer()

class WeatherDataSerializer(serializers.Serializer):
    last_updated = serializers.IntegerField()
    source = serializers.CharField(max_length=100)
    source_link = serializers.URLField()
    location = LocationSerializer()
    current = CurrentWeatherSerializer()
    next_24h = HourlyForecastSerializer(many=True)
    next_days = DailyForecastSerializer(many=True)