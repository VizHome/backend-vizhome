"""Configuration pytest pour les benchmarks.

Ce conftest assure que `pytest benchmarks/...` fonctionne meme depuis la
racine du repo (le path `src/` doit etre dans `sys.path` pour importer
`apps.*` et `config.*`). Le `pyproject.toml` declare deja `pythonpath = ["src"]`
mais le rappeler ici rend le dossier auto-portant si on l'exporte.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / 'src'

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Settings de test si pas deja defini par l'env
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
