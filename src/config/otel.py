"""Setup OpenTelemetry tracing pour Django + Celery.

Auto-instrumente :
- Django (HTTP request/response, vues, middlewares)
- Celery (tasks workers + producers)
- Psycopg (toutes les requêtes PostgreSQL)
- Redis (cache + broker Celery + locks)
- Requests (HTTP sortant vers Stripe, Gemini, GitHub OAuth, etc.)

Activé seulement si la variable d'environnement
`OTEL_EXPORTER_OTLP_ENDPOINT` est définie. Sinon `init_otel()` est un
no-op total (pas d'instrumentation, pas d'overhead), utile en dev local
et en CI.

Endpoints OTLP compatibles : Grafana Tempo, Honeycomb, Jaeger,
n'importe quel collector OpenTelemetry standard.

Idempotent : appeler `init_otel()` plusieurs fois ne casse rien, mais
les instrumenteurs interceptent les appels qu'une seule fois.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_INITIALIZED = False


def init_otel() -> None:
    """Initialise OTel si un endpoint OTLP est configuré, sinon no-op."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', '').strip()
    if not endpoint:
        return  # OTel désactivé tant qu'aucun endpoint n'est fourni.

    # Imports paresseux : si OTel n'est jamais activé, on évite de payer
    # le coût d'import des SDKs (Django apps_ready se fait plus vite).
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning('OpenTelemetry packages not installed, tracing disabled: %s', exc)
        return

    service_name = os.getenv('OTEL_SERVICE_NAME', 'vizhome-backend')
    environment = os.getenv('OTEL_ENVIRONMENT', 'production')

    resource = Resource.create(
        {
            'service.name': service_name,
            'service.namespace': 'vizhome',
            'deployment.environment': environment,
        }
    )

    provider = TracerProvider(resource=resource)
    # `insecure=True` pour endpoints HTTP (collector local), détecté
    # automatiquement par le schéma de l'URL.
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith('http://'),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrumentations, à appeler APRÈS set_tracer_provider().
    DjangoInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    PsycopgInstrumentor().instrument()
    RedisInstrumentor().instrument()
    RequestsInstrumentor().instrument()

    _INITIALIZED = True
    logger.info(
        'OpenTelemetry tracing initialized (service=%s, env=%s, endpoint=%s)',
        service_name,
        environment,
        endpoint,
    )
