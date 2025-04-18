# Weather API Service

Ce projet est une API Django REST Framework qui fournit des données météorologiques actuelles et des prévisions basées sur la position géographique ou l'adresse IP de l'utilisateur.

## Fonctionnalités

- Récupération des données météorologiques actuelles
- Prévisions pour les prochaines 24 heures
- Prévisions pour les prochains jours
- Support multilingue pour les descriptions des conditions météorologiques
- Localisation par coordonnées géographiques ou adresse IP

## Prérequis

- Python 3.10+
- Django 4.2+
- Django REST Framework 3.16+
- Autres dépendances listées dans `requirements.txt`

## Installation

1. Clonez le dépôt:
   ```bash
   git clone https://github.com/Crisxzu/weather-api.git
   cd weather-api
   ```

2. Créez un environnement virtuel et activez-le:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows: venv\Scripts\activate
   ```

3. Installez les dépendances:
   ```bash
   pip install -r requirements.txt
   ```

4. Créez un fichier `.env` à la racine du projet avec les variables suivantes:
   ```
   WEATHER_API_KEY=votre_clé_api_météo
   WEATHER_API_BASE_URL=url_de_base_de_l_api_météo
   WEATHER_API_SOURCE_NAME=nom_de_la_source
   WEATHER_API_SOURCE_LINK=lien_vers_la_source
   DJANGO_SECRET_KEY=votre_clé_secrète_django
   ```

5. Effectuez les migrations:
   ```bash
   python manage.py migrate
   ```

6. Lancez le serveur de développement:
   ```bash
   python manage.py runserver
   ```

## Utilisation

### Endpoint principal

```
GET /api/weather/
```

### Paramètres de requête

| Paramètre | Description                                                 | Exemple          |
|-----------|-------------------------------------------------------------|------------------|
| position  | Coordonnées géographiques (latitude,longitude)              | `48.8566,2.3522` |
| lang_iso  | Code de langue ISO pour les descriptions (par défaut: 'en') | `fr`             |

Si aucune position n'est fournie, l'API tentera d'utiliser l'adresse IP du client pour déterminer sa localisation.

### Exemple de réponse

```json
{
  "last_updated": 1615970400,
  "source": "WeatherAPI.com",
  "source_link": "https://www.weatherapi.com/",
  "location": {
    "name": "Paris",
    "region": "Ile-de-France",
    "country": "France",
    "lat": 48.86,
    "lon": 2.35,
    "tz_id": "Europe/Paris",
    "localtime_epoch": 1615970700,
    "localtime": "2021-03-17 10:45"
  },
  "current": {
    "temp": 12.0,
    "min_temp": 8.5,
    "max_temp": 15.2,
    "is_day": 1,
    "feels_like": 10.3,
    "condition": {
      "code": 1000,
      "text": "Ensoleillé"
    }
  },
  "next_24h": [
    {
      "temp": 12.0,
      "humidity": 75,
      "timestamp": 1615971600,
      "condition": {
        "code": 1000,
        "text": "Ensoleillé"
      }
    },
    // ... autres heures
  ],
  "next_days": [
    {
      "min_temp": 8.5,
      "max_temp": 15.2,
      "humidity": 78,
      "timestamp": 1615939200,
      "condition": {
        "code": 1000,
        "text": "Ensoleillé"
      }
    },
    // ... autres jours
  ]
}
```

## Structure du projet

```
weather-api-/
├── api/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── WeatherAppApi/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── migrations/
│   ├── models.py
│   ├── serializers.py
│   ├── tests.py
│   └── views.py
├── conditions.json
├── .env
├── .gitignore
├── manage.py
└── requirements.txt
```

## Fichier conditions.json

Le fichier `conditions.json` contient les mappages des codes de condition météorologique vers leurs descriptions textuelles dans différentes langues. Il doit être placé à la racine du projet.

## Développement

### Utilisation des serializers

Le projet utilise les serializers de Django REST Framework pour valider et structurer les données. Les serializers sont définis dans `api/serializers.py`.

### Ajout de nouvelles fonctionnalités

1. Pour ajouter de nouveaux endpoints, créez de nouvelles classes de vues dans `views.py` et ajoutez-les aux URLs.
2. Pour modifier la structure des données, mettez à jour les serializers appropriés.

## Licence

[Voir ici](https://github.com/Crisxzu/weather-api/blob/main/LICENSE)

## Auteurs

Chris Kouassi

## Crédits

Ce projet utilise les données de [WeatherAPI](https://www.weatherapi.com/), accessible via leur API.