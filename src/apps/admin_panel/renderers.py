"""Renderers DRF custom — export CSV des listes paginées admin.

Usage : `?format=csv` sur n'importe quel endpoint admin list pour
télécharger un CSV au lieu du JSON. Fonctionne avec DRF content
negotiation native (Accept header ou query param via DEFAULT_CONTENT_NEGOTIATION).
"""

from __future__ import annotations

import csv
import io
from typing import Any

from rest_framework.renderers import BaseRenderer


class CSVRenderer(BaseRenderer):
    """Renderer DRF qui transforme une réponse paginée en CSV.

    Détecte automatiquement la structure paginée DRF `{count, results: [...]}`
    et exporte uniquement `results`. Pour une réponse non-paginée (liste
    plate), exporte tout.

    Les colonnes sont auto-détectées depuis les keys du premier item.
    Les valeurs nested (dict/list) sont serializées en JSON inline.
    """

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if not data:
            return ""

        # Détecte la structure paginée DRF
        rows: list[dict[str, Any]] = []
        if (
            isinstance(data, dict)
            and "results" in data
            and isinstance(data["results"], list)
        ):
            rows = data["results"]
        elif isinstance(data, list):
            rows = data
        else:
            # Réponse non-itérable : retourne juste les keys
            rows = [data]

        if not rows:
            return "count\n0\n"

        # Colonnes = union des keys de toutes les lignes (préserve l'ordre du 1er)
        seen = list(rows[0].keys())
        for row in rows[1:]:
            for key in row:
                if key not in seen:
                    seen.append(key)

        # Sérialise les valeurs nested en JSON pour les flatten
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=seen, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _flatten(row.get(k)) for k in seen})

        # Set filename sur la réponse HTTP via le context
        if renderer_context:
            response = renderer_context.get("response")
            if response is not None:
                view = renderer_context.get("view")
                name = getattr(view, "csv_filename", "export") if view else "export"
                response["Content-Disposition"] = f'attachment; filename="{name}.csv"'

        return buf.getvalue()


def _flatten(value: Any) -> Any:
    """Convertit les dict/list en string JSON-like pour qu'ils tiennent dans une cellule."""
    if value is None:
        return ""
    if isinstance(value, dict | list):
        import json

        return json.dumps(value, ensure_ascii=False)
    return value
