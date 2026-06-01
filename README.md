# Weather API Service

API Django REST Framework fournissant des données météorologiques actuelles et des prévisions, basées sur des coordonnées géographiques, un nom de ville ou l'adresse IP du client.

## Fonctionnalités

- Conditions météo actuelles + prévisions 24h et multi-jours
- Support multilingue des descriptions de conditions (`lang_iso`)
- Localisation par coordonnées, ville ou adresse IP
- Architecture multi-providers avec fallback automatique
- Cache Redis (production) ou mémoire (développement)
- Authentification par clé API

## Prérequis

- Python 3.10+
- Django 4.2+
- Django REST Framework 3.16+

## Installation

1. Clonez le dépôt :
   ```bash
   git clone https://github.com/Crisxzu/weather-api.git
   cd weather-api
   ```

2. Créez un environnement virtuel et activez-le :
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows : .venv\Scripts\activate
   ```

3. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

4. Créez un fichier `.env` à la racine du projet :
   ```env
   # WeatherAPI (provider principal)
   WEATHER_API_KEY=votre_clé_api
   WEATHER_API_BASE_URL=http://api.weatherapi.com/v1
   WEATHER_API_SOURCE_NAME="Weather API"
   WEATHER_API_SOURCE_LINK="https://www.weatherapi.com/"

   # Providers
   WEATHER_PRIMARY_PROVIDER=weatherapi
   WEATHER_FALLBACK_PROVIDER=openmeteo

   # Django
   DJANGO_SECRET_KEY=votre_clé_secrète
   DJANGO_DEBUG=1

   # Cache (optionnel — LocMemCache si absent)
   REDIS_URL=redis://localhost:6379/0
   WEATHER_CACHE_TTL=3600
   ```

5. Effectuez les migrations :
   ```bash
   python manage.py migrate
   ```

6. Créez une clé API :
   ```bash
   python manage.py create_api_key --name "nom-de-la-clé"
   ```

7. Lancez le serveur :
   ```bash
   python manage.py runserver
   ```

## Utilisation

### Endpoint

```
GET /api/weather
```

**Authentification :** header `Authorization: Api-Key <votre_clé>`

### Paramètres

| Paramètre  | Description                                    | Exemple          |
|------------|------------------------------------------------|------------------|
| `position` | Coordonnées `latitude,longitude`               | `48.8566,2.3522` |
| `city`     | Nom de la ville                                | `Paris`          |
| `lang_iso` | Code langue ISO pour les conditions (défaut: `en`) | `fr`         |

Si aucun paramètre n'est fourni, l'API utilise l'adresse IP du client. Les paramètres sont prioritaires dans l'ordre : `position` > `city` > IP.

### Exemple de réponse

```json
{
  "last_updated": 1748771400,
  "source": "Weather API",
  "source_link": "https://www.weatherapi.com/",
  "location": {
    "name": "Paris",
    "region": "Ile-de-France",
    "country": "France",
    "lat": 48.86,
    "lon": 2.35,
    "tz_id": "Europe/Paris",
    "localtime_epoch": 1748772000,
    "localtime": "2025-06-01 12:00"
  },
  "current": {
    "temp": 18.0,
    "min_temp": 12.1,
    "max_temp": 23.5,
    "is_day": true,
    "feels_like": 17.2,
    "condition": {
      "code": 1000,
      "text": "Ensoleillé",
      "icon": 113
    }
  },
  "next_24h": [
    {
      "temp": 19.5,
      "humidity": 60,
      "timestamp": 1748775600,
      "is_day": true,
      "condition": {
        "code": 1000,
        "text": "Ensoleillé",
        "icon": 113
      }
    }
  ],
  "next_days": [
    {
      "min_temp": 12.1,
      "max_temp": 23.5,
      "humidity": 58,
      "timestamp": 1748736000,
      "is_day": true,
      "condition": {
        "code": 1000,
        "text": "Ensoleillé",
        "icon": 113
      }
    }
  ]
}
```

### Codes d'erreur

| HTTP | Cas |
|------|-----|
| `400` | Paramètres invalides ou localisation introuvable |
| `403` | Clé API manquante ou invalide |
| `503` | Provider météo indisponible (et fallback aussi en échec) |

## Architecture multi-providers

L'API supporte plusieurs sources météo configurables via les variables d'environnement `WEATHER_PRIMARY_PROVIDER` et `WEATHER_FALLBACK_PROVIDER`.

| Provider | Valeur | Gratuit | Clé requise | Source des données |
|----------|--------|---------|-------------|-------------------|
| WeatherAPI | `weatherapi` | 100k req/mois | Oui | WeatherAPI.com |
| Open-Meteo | `openmeteo` | 300k req/mois (non-commercial) | Non | Open-Meteo.com |

**Logique de fallback :** si le provider principal retourne une erreur réseau ou de timeout, le fallback prend le relais automatiquement. Les erreurs déterministes (clé invalide, quota dépassé) ne déclenchent pas le fallback.

### Services tiers utilisés par Open-Meteo

- **Open-Meteo Geocoding API** — résolution ville → coordonnées
- **ip-api.com** — résolution IP → coordonnées (requêtes IP uniquement)
- **Nominatim (OpenStreetMap)** — reverse geocoding coordonnées → nom de ville

## Structure du projet

```
WeatherAppApi/
├── api/
│   ├── providers/
│   │   ├── base.py          # WeatherProvider (ABC) + exceptions
│   │   ├── weatherapi.py    # WeatherAPIProvider
│   │   ├── openmeteo.py     # OpenMeteoProvider
│   │   ├── registry.py      # Sélection primary/fallback via env vars
│   │   └── schemas.py       # Dataclasses du contrat de données
│   ├── utils/
│   │   ├── conditions.py    # Lookup conditions + mapping WMO
│   │   ├── timezone.py      # Helper timezone
│   │   └── ip_geolocation.py # Résolution IP → coordonnées
│   ├── tests/
│   │   ├── fixtures/        # Réponses mock JSON pour les tests
│   │   ├── test_utils.py
│   │   ├── test_weatherapi.py
│   │   ├── test_openmeteo.py
│   │   └── test_views.py
│   ├── serializers.py
│   └── views.py
├── conditions.json           # Codes conditions + traductions (20+ langues)
├── wmo_conditions.json       # Mapping codes WMO → codes internes
├── manage.py
└── requirements.txt
```

## Tests

```bash
python manage.py test api.tests
```

49 tests couvrant les providers, les utilitaires et la couche vue (cache, fallback, authentification).

## Licence

[Voir ici](https://github.com/Crisxzu/weather-api/blob/main/LICENSE)

## Auteurs

Chris Kouassi

## Crédits

- Données météo principales : [WeatherAPI](https://www.weatherapi.com/)
- Données météo fallback : [Open-Meteo](https://open-meteo.com/)
