"""Microbenchmarks pytest-benchmark sur fonctions Python critiques.

On isole ici les fonctions identifiees comme chemins chauds du backend :

- Serialisation d'un Project (lourd: nested Scene + ImportedModel + Annotation)
- Mapping UserStats dans le UserSerializer (`/me/`)
- Generation + verification d'un JWT (chaque requete authentifiee)
- Hash de password (login)
- Sanitisation de contenu HTML forum (rendu de Topic/Reply cote backend)

Chaque test enregistre un seuil p95 sous forme de constante nommee
(`P95_*_MS`). Les assertions sont non bloquantes en demarrage (CI :
`continue-on-error: true`) le temps de calibrer un baseline.

Lancer :
    pytest benchmarks/test_perf.py --benchmark-only --benchmark-save=baseline
Comparer :
    pytest benchmarks/test_perf.py --benchmark-compare
"""

from __future__ import annotations

import html

import pytest

# ─── Seuils p95 (en ms) ─────────────────────────────────────────────────────
# Calibres a la louche sur une machine dev (Ryzen + SSD NVMe). Ces valeurs
# servent de garde-fou anti-regression: si une PR fait sauter une fonction
# au-dela du seuil, le bench le signale (sans bloquer le merge pour l'instant).

P95_PROJECT_SERIALIZE_MS = 50.0
"""Serialiser un Project avec 5 ImportedModel + scene + 3 annotations."""

P95_USER_STATS_MAP_MS = 5.0
"""Mapper un dict UserStats vers le serializer DRF."""

P95_JWT_ENCODE_MS = 10.0
"""Generer un access + refresh token via simplejwt RefreshToken.for_user."""

P95_JWT_VERIFY_MS = 5.0
"""Decoder et valider un access token via AccessToken(...)."""

P95_PASSWORD_HASH_MS = 500.0
"""Hash PBKDF2 d'un password Django (volontairement lent : ~390000 iterations)."""

P95_PASSWORD_VERIFY_MS = 500.0
"""Verify d'un password Django (meme cout que le hash, par design)."""

P95_HTML_SANITIZE_MS = 5.0
"""Sanitisation HTML d'un contenu forum de ~1 KB."""

# Taille du sample HTML utilise pour le bench sanitize : 1 KB de texte +
# quelques balises a echapper.
SAMPLE_HTML_SIZE_BYTES = 1024


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def bench_user(db):
    """User minimal pour les bench (sans stats ni preferences)."""
    from apps.accounts.models import User

    return User.objects.create_user(
        email='bench@vizhome.test',
        password='BenchPassw0rd!',
        pseudo='benchuser',
        first_name='Bench',
        last_name='User',
    )


@pytest.fixture
def bench_project(bench_user):
    """Project avec scene + 5 ImportedModel + 3 annotations.

    Volontairement non-trivial pour exercer ProjectDetailSerializer (qui
    declenche du nested + des comptes related: c'est le scenario le plus
    representatif d'une page projet en prod).
    """
    from apps.projects.models import Annotation, ImportedModel, Project, Scene

    project = Project.objects.create(
        user=bench_user,
        title='Bench Project',
        description='Projet de bench (5 modeles + scene + 3 annotations)',
    )
    Scene.objects.create(
        project=project,
        data={
            'camera': {'position': [10.0, 5.0, 10.0], 'target': [0, 0, 0]},
            'lighting': {'preset': 'day', 'ambient_intensity': 0.5},
            'weather': {'mode': 'clear'},
            'meshes': [{'id': i, 'material': f'wood-{i}'} for i in range(20)],
        },
    )
    for i in range(5):
        ImportedModel.objects.create(
            project=project,
            name=f'model-{i}.glb',
            format=ImportedModel.Format.GLB,
            file=f'projects/models/2026/06/model-{i}.glb',
            file_size_bytes=1024 * 1024 * (i + 1),
        )
    for i in range(3):
        Annotation.objects.create(
            project=project,
            type=Annotation.Type.NOTE,
            position={'x': float(i), 'y': 0.0, 'z': 0.0},
            content=f'Annotation #{i}',
            color='#ff0000',
        )
    return project


@pytest.fixture
def sample_html() -> str:
    """Echantillon HTML d'environ 1 KB pour le bench sanitize.

    Mix de texte, balises autorisees (p, strong, em), balises a stripper
    (script, iframe), et entites a echapper. Representatif d'un post forum.
    """
    base = (
        '<p>Bonjour, voici un <strong>message</strong> avec du <em>HTML</em>. '
        '<script>alert("xss")</script> '
        '<iframe src="http://evil.example/" /> '
        'Et des entites: <>&"\' '
    )
    # On repete jusqu'a depasser 1 KB
    out: list[str] = []
    while sum(len(s) for s in out) < SAMPLE_HTML_SIZE_BYTES:
        out.append(base)
    return ''.join(out)


# ─── Microbench : serialisation Project ──────────────────────────────────────


@pytest.mark.benchmark(group='serialize')
@pytest.mark.django_db
def test_bench_project_detail_serializer(benchmark, bench_project) -> None:
    """Mesure le cout d'un ProjectDetailSerializer avec nested complet."""
    from apps.projects.serializers import ProjectDetailSerializer

    def _serialize() -> dict:
        return ProjectDetailSerializer(bench_project).data

    result = benchmark(_serialize)
    assert result['title'] == 'Bench Project'
    assert len(result['imported_models']) == 5
    # Seuil non bloquant en demarrage : on log seulement.
    _assert_p95_soft(benchmark, P95_PROJECT_SERIALIZE_MS)


@pytest.mark.benchmark(group='serialize')
@pytest.mark.django_db
def test_bench_project_list_serializer(benchmark, bench_project) -> None:
    """Mesure le cout du serializer "compact" utilise en list."""
    from apps.projects.serializers import ProjectListSerializer

    def _serialize() -> dict:
        return ProjectListSerializer(bench_project).data

    result = benchmark(_serialize)
    assert result['title'] == 'Bench Project'


# ─── Microbench : mapping UserStats ──────────────────────────────────────────


@pytest.mark.benchmark(group='serialize')
@pytest.mark.django_db
def test_bench_user_serializer_with_stats(benchmark, bench_user) -> None:
    """Mesure le cout du UserSerializer (`/me/`) avec stats + preferences.

    `bench_user` declenche les signaux post_save accounts qui creent
    automatiquement UserStats et UserPreferences (cf. signals.py).
    """
    from apps.accounts.serializers import UserSerializer

    def _serialize() -> dict:
        return UserSerializer(bench_user).data

    result = benchmark(_serialize)
    assert result['email'] == 'bench@vizhome.test'
    _assert_p95_soft(benchmark, P95_USER_STATS_MAP_MS)


# ─── Microbench : JWT generation + verify ────────────────────────────────────


@pytest.mark.benchmark(group='jwt')
@pytest.mark.django_db
def test_bench_jwt_encode(benchmark, bench_user) -> None:
    """Cout de la generation d'un couple access+refresh JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken

    def _encode() -> tuple[str, str]:
        refresh = RefreshToken.for_user(bench_user)
        return str(refresh.access_token), str(refresh)

    access, refresh = benchmark(_encode)
    assert access
    assert refresh
    _assert_p95_soft(benchmark, P95_JWT_ENCODE_MS)


@pytest.mark.benchmark(group='jwt')
@pytest.mark.django_db
def test_bench_jwt_verify(benchmark, bench_user) -> None:
    """Cout de la verification d'un access token (chaque requete protegee).

    On precalcule le token hors du bench pour ne mesurer que le decode.
    """
    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

    refresh = RefreshToken.for_user(bench_user)
    access_str = str(refresh.access_token)

    def _verify() -> int:
        token = AccessToken(access_str)
        return int(token['user_id'])

    user_id = benchmark(_verify)
    assert user_id == bench_user.pk
    _assert_p95_soft(benchmark, P95_JWT_VERIFY_MS)


# ─── Microbench : password hash + verify ─────────────────────────────────────


@pytest.mark.benchmark(group='password')
def test_bench_password_hash(benchmark) -> None:
    """Cout du hash PBKDF2 d'un password (par design > 100ms)."""
    from django.contrib.auth.hashers import make_password

    def _hash() -> str:
        return make_password('BenchPassw0rd!')

    hashed = benchmark(_hash)
    assert hashed.startswith('pbkdf2_')
    _assert_p95_soft(benchmark, P95_PASSWORD_HASH_MS)


@pytest.mark.benchmark(group='password')
def test_bench_password_verify(benchmark) -> None:
    """Cout du verify : meme cout que le hash, par symetrie PBKDF2."""
    from django.contrib.auth.hashers import check_password, make_password

    hashed = make_password('BenchPassw0rd!')

    def _verify() -> bool:
        return check_password('BenchPassw0rd!', hashed)

    ok = benchmark(_verify)
    assert ok is True
    _assert_p95_soft(benchmark, P95_PASSWORD_VERIFY_MS)


# ─── Microbench : sanitisation HTML forum ────────────────────────────────────


@pytest.mark.benchmark(group='html')
def test_bench_html_sanitize(benchmark, sample_html: str) -> None:
    """Sanitisation d'un contenu HTML d'environ 1 KB.

    Le backend VizHome n'embarque pas Bleach (le sanitize est cote frontend
    via isomorphic-dompurify, cf. CLAUDE.md frontend). On benche neanmoins
    `html.escape` qui est le filet de securite minimal cote serveur (utilise
    par les templates Django par defaut et par DRF dans les BrowsableAPIRenderer).
    Si Bleach ou nh3 est ajoute plus tard, remplacer ici.
    """

    def _sanitize() -> str:
        return html.escape(sample_html)

    out = benchmark(_sanitize)
    assert '&lt;script&gt;' in out
    _assert_p95_soft(benchmark, P95_HTML_SANITIZE_MS)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _assert_p95_soft(benchmark, threshold_ms: float) -> None:
    """Verifie le seuil p95 en mode soft : log un warning, ne fait pas planter.

    `pytest-benchmark` expose `benchmark.stats` (objet stats du run courant).
    On lit `.stats.percentiles[95]` quand dispo, sinon on retombe sur le
    mean comme proxy.

    Le but est de **signaler** une regression sans bloquer la CI tant qu'on
    n'a pas calibre des baselines stables. Pour passer en mode bloquant,
    remplacer le warning par un `assert`.
    """
    stats = benchmark.stats
    p95_seconds = getattr(stats, 'stats', stats).mean
    # Certaines versions de pytest-benchmark exposent percentiles[95]
    percentiles = getattr(stats, 'percentiles', None)
    if percentiles and 95 in percentiles:
        p95_seconds = percentiles[95]
    p95_ms = p95_seconds * 1000
    if p95_ms > threshold_ms:
        import warnings

        warnings.warn(
            f'p95 = {p95_ms:.2f} ms > seuil {threshold_ms:.2f} ms',
            UserWarning,
            stacklevel=2,
        )
