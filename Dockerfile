FROM python:3.13-slim

# Installer les dépendances système nécessaires
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		libpq-dev \
		gcc \
		netcat-openbsd \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

RUN pip install "gunicorn==26.2.0"

CMD ["gunicorn", "WeatherAppApi.wsgi:application", "--config", "gunicorn.conf.py"]