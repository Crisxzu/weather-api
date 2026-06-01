import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        from django.conf import settings
        backend = settings.CACHES['default']['BACKEND']
        if 'redis' in backend.lower():
            logger.info('Cache backend: Redis (%s)', settings.CACHES['default'].get('LOCATION'))
        else:
            logger.info('Cache backend: LocMemCache (in-process memory)')
