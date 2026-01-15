FROM python:3.10-slim

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

RUN pip install "gunicorn:23.0.0"

CMD ["gunicorn", "WeatherAppApi.wsgi:application", "--bind", "0.0.0.0:8000"]