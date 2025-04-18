from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('weather', views.WeatherDataView.as_view(), name='weather'),
]