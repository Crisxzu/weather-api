# Weather API Service

[![Tests](https://github.com/Crisxzu/weather-api/actions/workflows/tests.yml/badge.svg)](https://github.com/Crisxzu/weather-api/actions/workflows/tests.yml)

API Django REST Framework fournissant des données météorologiques actuelles et des prévisions, basées sur des coordonnées géographiques, un nom de ville ou l'adresse IP du client.

## Fonctionnalités

- Conditions météo actuelles + prévisions 24h et multi-jours
- Support multilingue des descriptions de conditions (`lang_iso`)
- Localisation par coordonnées, ville ou adresse IP
- Recherche de villes multilingue (`/api/v1/search`)
- Architecture multi-providers avec fallback automatique
- Cache Redis (production) ou mémoire (développement)
- Authentification par clé API

## Prérequis

- Python 3.13
- Django 5.2 LTS
- Django REST Framework 3.18+

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
   # WeatherAPI (provider de secours)
   WEATHER_API_KEY=votre_clé_api
   WEATHER_API_BASE_URL=http://api.weatherapi.com/v1
   WEATHER_API_SOURCE_NAME="Weather API"
   WEATHER_API_SOURCE_LINK="https://www.weatherapi.com/"

   # Providers
   WEATHER_PRIMARY_PROVIDER=openmeteo
   WEATHER_FALLBACK_PROVIDER=weatherapi
   WEATHER_FORECAST_DAYS=7          # 1 à 16, défaut 7 (WeatherAPI en renvoie 3 sur le plan actuel)

   # Django
   DJANGO_SECRET_KEY=votre_clé_secrète
   DJANGO_DEBUG=1

   # Cache (optionnel — LocMemCache si absent)
   REDIS_URL=redis://localhost:6379/0
   WEATHER_CACHE_TTL=3600
   WEATHER_NOWCAST_CACHE_TTL=900    # TTL quand la réponse contient next_minutes

   # Alertes météo (récupérées à part si le provider n'en fournit pas)
   WEATHER_ALERTS_PROVIDER=weatherapi   # vide = désactivé
   WEATHER_ALERTS_CACHE_TTL=1800

   # Qualité de l'air et pollens (Open-Meteo Air Quality API, appel séparé)
   WEATHER_AIR_QUALITY_PROVIDER=openmeteo   # vide = désactivé
   WEATHER_AIR_QUALITY_CACHE_TTL=3600

   # Recherche de villes
   WEATHER_SEARCH_CACHE_TTL=86400

   # Nominatim (reverse geocoding Open-Meteo) — User-Agent identifiable exigé
   NOMINATIM_USER_AGENT="WeatherAppApi/1.0 (+https://github.com/Crisxzu/weather-api)"
   ```

5. Effectuez les migrations :
   ```bash
   python manage.py migrate
   ```

6. Créez une clé API :
   ```bash
   python manage.py shell -c "from rest_framework_api_key.models import APIKey; print(APIKey.objects.create_key(name='nom-de-la-clé')[1])"
   ```
   La clé n'est affichée qu'une fois : conservez-la. Les clés se gèrent aussi depuis l'admin Django (`/admin/`).

7. Lancez le serveur :
   ```bash
   python manage.py runserver
   ```

## Utilisation

### Endpoint

```
GET /api/v1/weather
```

**Authentification :** header `Authorization: Api-Key <votre_clé>`

### Paramètres

| Paramètre      | Description                                          | Exemple          |
|----------------|------------------------------------------------------|------------------|
| `position`     | Coordonnées `latitude,longitude`, arrondies à 2 décimales (~1 km) avant cache et appel au provider | `48.8566,2.3522` |
| `city`         | Nom de la ville                                      | `Paris`          |
| `country_code` | Code pays ISO 3166-1 alpha-2 pour lever l'ambiguïté entre des villes homonymes (optionnel, utilisé avec `city`) | `FR` |
| `lang_iso`     | Code langue ISO pour les conditions (défaut: `en`)   | `fr`             |

Si aucun paramètre n'est fourni, l'API utilise l'adresse IP du client. Les paramètres sont prioritaires dans l'ordre : `position` > `city` > IP.

**Exemple avec `country_code` :**
```
GET /api/v1/weather?city=Paris&country_code=FR&lang_iso=fr
```

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
    },
    "humidity": 62,
    "wind_kph": 14.4,
    "wind_degree": 250,
    "gust_kph": 22.3,
    "uv": 6.0,
    "precip_mm": 0.0,
    "cloud_cover": 25,
    "visibility_km": 24.14
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
      },
      "chance_of_rain": 20,
      "chance_of_snow": null,
      "precip_mm": 0.1,
      "feels_like": 18.7,
      "wind_kph": 13.0,
      "uv": 6.0,
      "cloud_cover": 30,
      "visibility_km": 24.14,
      "snow_cm": 0.0
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
      },
      "chance_of_rain": 10,
      "chance_of_snow": null,
      "total_precip_mm": 0.0,
      "max_wind_kph": 18.0,
      "uv": 7.0,
      "sunrise": 1748749620,
      "sunset": 1748807400,
      "total_snow_cm": 0.0
    }
  ],
  "next_minutes": [
    { "timestamp": 1748772000, "precip_mm": 0.0 },
    { "timestamp": 1748772900, "precip_mm": 0.4 }
  ],
  "alerts": [],
  "yesterday": {
    "min_temp": 11.0,
    "max_temp": 20.5,
    "temp_same_hour": 16.0,
    "condition": { "code": 1183, "text": "Pluie légère", "icon": 296 }
  },
  "air_quality": {
    "current": {
      "european_aqi": 40, "us_aqi": 55, "pm2_5": 10.0, "pm10": 20.0,
      "ozone": 60.0, "nitrogen_dioxide": 15.0,
      "pollen": { "alder": 0.0, "birch": 12.0, "grass": 35.0, "mugwort": 0.0, "olive": 0.0, "ragweed": 0.0 }
    },
    "days": [
      {
        "european_aqi": 45, "us_aqi": 60, "pm2_5": 12.0, "pm10": 24.0,
        "ozone": 80.0, "nitrogen_dioxide": 20.0,
        "pollen": { "alder": 0.0, "birch": 30.0, "grass": 60.0, "mugwort": 0.0, "olive": 0.0, "ragweed": 0.0 },
        "timestamp": 1748736000
      }
    ]
  }
}
```

### Champs v2

Tous les champs ajoutés pour la v2 sont **nullables** : un provider qui ne sait pas fournir une valeur renvoie `null`. Les clients v1 ignorent ces clés.

- Températures en °C, vent en km/h, précipitations en mm, probabilités en %, timestamps en epoch secondes.
- `next_days[].timestamp` vaut minuit **UTC** de la date (même convention pour les deux providers). `sunrise` / `sunset` sont de vrais instants.
- `next_days` contient 7 jours par défaut (`WEATHER_FORECAST_DAYS`), mais **moins** quand WeatherAPI répond en secours (3 jours sur le plan actuel) : la longueur est variable.
- En fin de période, certaines valeurs peuvent manquer : dans `air_quality.days`, les pollens s'arrêtent vers le 5ᵉ jour et les indices vers le 6ᵉ (valeurs `null`).
- `chance_of_snow` vaut `null` avec Open-Meteo (pas de probabilité de neige).
- `cloud_cover` en %, `visibility_km` en km, neige (`snow_cm`, `total_snow_cm`) en cm.
- `yesterday` : météo de la veille (`min_temp`, `max_temp`, `condition`) et `temp_same_hour`, la température d'hier à l'heure locale actuelle, pour des messages comme « 6° de plus qu'hier ». Open-Meteo : même requête (`past_days=1`). WeatherAPI : appel séparé à `history.json`, `null` s'il échoue.
- `air_quality` : toujours demandé à l'Air Quality API d'Open-Meteo (données CAMS), quel que soit le provider météo, avec son propre cache par zone de ~1 km (`WEATHER_AIR_QUALITY_CACHE_TTL`). `null` si indisponible.
  - `current` : valeurs actuelles. `days[]` : **maxima** de chaque journée, `timestamp` à minuit UTC comme `next_days`.
  - `european_aqi` (EAQI) et `us_aqi` sont des indices ; `pm2_5`, `pm10`, `ozone`, `nitrogen_dioxide` en µg/m³.
  - `pollen` en grains/m³ (aulne, bouleau, graminées, armoise, olivier, ambroisie), **Europe uniquement** : `null` hors zone couverte, `0` = pas de pollen (hors saison). Les seuils d'alerte dépendent de l'espèce : c'est à l'app de traduire en niveaux.
- `next_minutes` : précipitations par pas de 15 min sur les 2 prochaines heures. `null` avec WeatherAPI. Données réellement au quart d'heure seulement en Europe centrale et Amérique du Nord, ailleurs interpolées depuis l'horaire : à présenter avec prudence.
- `alerts` : `[]` = aucune alerte en cours, `null` = alertes indisponibles (service désactivé ou en échec). Chaque alerte : `event`, `headline`, `severity`, `effective`, `expires`.
  Quand le provider qui a répondu n'a pas d'alertes (Open-Meteo), elles sont demandées à part à l'endpoint `alerts.json` de WeatherAPI, avec leur propre cache (par zone de ~1 km, toutes langues confondues, `WEATHER_ALERTS_CACHE_TTL`). Un échec n'affecte pas la réponse météo. La couverture dépend des pays (bonne aux États-Unis et en Europe) : `[]` ne garantit pas l'absence d'alerte officielle partout.

### Codes d'erreur

| HTTP | Cas |
|------|-----|
| `400` | Paramètres invalides ou localisation introuvable |
| `403` | Clé API manquante ou invalide |
| `503` | Provider météo indisponible (et fallback aussi en échec) |

## Recherche de villes

```
GET /api/v1/search?q=sain&lang_iso=fr&limit=10
```

Même authentification que la météo. Sert à l'écran Positions : l'app enregistre `lat` / `lon` de la ville choisie et interroge ensuite la météo avec `position=` (pas d'ambiguïté entre homonymes, cache partagé avec les utilisateurs GPS de la zone).

| Paramètre      | Description | Défaut |
|----------------|-------------|--------|
| `q`            | Texte tapé (100 caractères max). Moins de 2 caractères → `[]`. Open-Meteo ne fait de recherche approximative qu'à partir de 3 caractères (2 = correspondance exacte). | — |
| `lang_iso`     | Langue des noms (« Londres » / « London »). `zh_tw` → `zh`. | `en` |
| `limit`        | Nombre de résultats, ramené entre 1 et 20. | `10` |
| `country_code` | Filtre par pays (ISO 3166-1 alpha-2). | — |

Réponse : liste de villes dans l'ordre d'Open-Meteo (pertinence puis population, « Paris, France » avant « Paris, Texas ») :

```json
[
  {
    "id": 2988507,
    "name": "Paris",
    "region": "Île-de-France",
    "country": "France",
    "country_code": "FR",
    "lat": 48.85341,
    "lon": 2.3488,
    "population": 2138551,
    "timezone": "Europe/Paris"
  }
]
```

- `id` : identifiant GeoNames, stable, pour dédoublonner côté app.
- `region` peut être vide, `population` peut être `null`.
- Résultats mis en cache 24 h (`WEATHER_SEARCH_CACHE_TTL`) par requête normalisée (casse et espaces), langue et pays, toutes valeurs de `limit` confondues. Les recherches sans résultat sont aussi mises en cache.
- `503` si le géocodage d'Open-Meteo est indisponible ou lent (> 5 s) : l'app peut réessayer. Côté app, attendre ~300 ms après la dernière frappe avant de chercher.

## Architecture multi-providers

L'API supporte plusieurs sources météo configurables via les variables d'environnement `WEATHER_PRIMARY_PROVIDER` et `WEATHER_FALLBACK_PROVIDER`.

| Provider | Valeur | Gratuit | Clé requise | Source des données |
|----------|--------|---------|-------------|-------------------|
| Open-Meteo | `openmeteo` | ~10k req/jour (non-commercial, CC BY 4.0) | Non | Open-Meteo.com |
| WeatherAPI | `weatherapi` | 100k req/mois | Oui | WeatherAPI.com |

Configuration recommandée : Open-Meteo en principal (prévisions jusqu'à 16 jours, pluie au quart d'heure), WeatherAPI en secours. Les alertes viennent toujours de WeatherAPI (`WEATHER_ALERTS_PROVIDER`), ce qui garde la clé WeatherAPI nécessaire.

**Logique de fallback :** si le provider principal retourne une erreur réseau ou de timeout, le fallback prend le relais automatiquement. Les erreurs déterministes (clé invalide, quota dépassé) ne déclenchent pas le fallback.

### Services tiers utilisés par Open-Meteo

- **Open-Meteo Air Quality API** — qualité de l'air et pollens (appelée pour toutes les requêtes, quel que soit le provider météo)
- **Open-Meteo Geocoding API** — recherche de villes et résolution ville → coordonnées (données GeoNames)
- **ip-api.com** — résolution IP → coordonnées (requêtes IP uniquement)
- **Nominatim (OpenStreetMap)** — reverse geocoding coordonnées → nom de ville

## Mise à jour des conditions météo

`conditions.json` (textes et traductions des conditions) vient de la liste publiée par WeatherAPI, qui ajoute des codes de temps en temps. Pour la rafraîchir :

```bash
python manage.py update_conditions            # télécharge, valide, écrit si ça a changé
python manage.py update_conditions --dry-run  # affiche les changements sans rien écrire
```

- Le fichier téléchargé est validé (structure, codes uniques, nombre minimal d'entrées) puis écrit de façon atomique.
- Une liste qui **retire** des codes existants est refusée, sauf avec `--allow-removals`.
- Les langues retirées sont signalées : si des clients envoient encore ces codes, ajoutez un alias dans `_LANG_ALIASES` (`api/utils/conditions.py`). Les anciens codes chinois (`zh`, `zh_hsn`, `zh_wuu`, `zh_yue`) y sont déjà.
- Le serveur recharge le fichier tout seul (vérification toutes les 60 s), sans redémarrage.
- Code de sortie non nul en cas d'échec, pour que le cron le signale.

Exemple de cron hebdomadaire sur l'hôte Docker :

```cron
0 4 * * 1  docker exec <conteneur> python manage.py update_conditions
```

Dans un conteneur, la mise à jour est perdue au prochain déploiement (l'image repart du fichier versionné) : pensez à lancer la commande en local de temps en temps et à commiter le résultat.

Si WeatherAPI renvoie un code encore absent du fichier, l'API utilise le texte (en anglais) fourni par WeatherAPI au lieu d'échouer.

## Structure du projet

```
WeatherAppApi/
├── api/
│   ├── providers/
│   │   ├── base.py          # WeatherProvider (ABC) + exceptions
│   │   ├── weatherapi.py    # WeatherAPIProvider
│   │   ├── openmeteo.py     # OpenMeteoProvider
│   │   ├── registry.py      # Sélection primary/fallback via env vars
│   │   ├── alerts.py        # Alertes WeatherAPI quand le provider n'en a pas
│   │   ├── air_quality.py   # Qualité de l'air et pollens (Open-Meteo Air Quality API)
│   │   └── schemas.py       # Dataclasses du contrat de données
│   ├── management/commands/
│   │   └── update_conditions.py  # Rafraîchit conditions.json depuis WeatherAPI
│   ├── utils/
│   │   ├── conditions.py    # Lookup conditions + mapping WMO
│   │   ├── timezone.py      # Helper timezone
│   │   ├── geocoding.py     # Géocodage Open-Meteo (recherche + ville → coordonnées)
│   │   └── ip_geolocation.py # Résolution IP → coordonnées
│   ├── tests/
│   │   ├── fixtures/        # Réponses mock JSON pour les tests
│   │   ├── test_utils.py
│   │   ├── test_weatherapi.py
│   │   ├── test_openmeteo.py
│   │   ├── test_alerts.py
│   │   ├── test_air_quality.py
│   │   ├── test_search.py
│   │   ├── test_update_conditions.py
│   │   └── test_views.py
│   ├── serializers.py
│   └── views.py
├── conditions.json           # Codes conditions + traductions (20+ langues)
├── wmo_conditions.json       # Mapping codes WMO → codes internes
├── manage.py
└── requirements.txt
```

## Mise à jour des dépendances

Les dépendances directes sont listées dans `requirements.in` ; `requirements.txt` (toutes les versions figées) en est généré :

```bash
uv pip compile requirements.in --python-version 3.13 --upgrade -o requirements.txt
```

Gunicorn est installé à part dans le `Dockerfile`.

## Tests

```bash
python manage.py test api.tests
```

183 tests couvrant les providers, les utilitaires et la couche vue (cache, fallback, authentification, `country_code`, champs v2, arrondi des positions, alertes, météo de la veille, qualité de l'air, mise à jour des conditions, recherche de villes).

## Licence

[Voir ici](https://github.com/Crisxzu/weather-api/blob/main/LICENSE)

## Auteurs

Chris Kouassi

## Crédits

- Données météo principales : [Open-Meteo](https://open-meteo.com/) (CC BY 4.0)
- Données météo fallback et alertes : [WeatherAPI](https://www.weatherapi.com/)
- Qualité de l'air et pollens : [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api), contient des informations modifiées du Copernicus Atmosphere Monitoring Service (CAMS) — à créditer dans l'app.
- Recherche de villes : [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api), données [GeoNames](https://www.geonames.org/) (CC BY 4.0) — à créditer dans l'app.
