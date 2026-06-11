# Benchmarks performance: backend VizHome

Ce dossier regroupe les bench performance du backend Django. Deux familles
complementaires :

1. **Load tests HTTP** (`locustfile.py`) : on simule N users qui martyrisent
   l'API en parallele (login, list projects, list renders, POST renders, etc.)
   pour mesurer la latence p50/p95/p99 et le throughput sous charge.
2. **Microbenchmarks Python** (`test_perf.py`) : on isole une fonction
   critique (serialisation Project, generation JWT, hash password, sanitisation
   HTML...) et on mesure son temps d'execution en repetant N fois via
   `pytest-benchmark`.

## A quoi ca sert

> Detecter les regressions de perf **avant** la prod.

Concretement :
- les microbench se lancent en CI sur `main`. Si on ajoute une N+1 query
  dans `ProjectDetailSerializer`, le bench saute du simple au triple et le
  workflow ouvre une alerte.
- le load test Locust se lance en **local** (ou ponctuellement en CI manuelle
  via `workflow_dispatch`). Permet de mettre en evidence les bottlenecks DB
  ou les endpoints qui s'effondrent au-dela de 50 users concurrents.

## Pre-requis

```bash
# Depuis la racine du repo backend
pip install -r src/requirements-dev.txt
```

Les deps ajoutees pour les bench :
- `locust>=2.31.0`
- `pytest-benchmark>=5.1.0`

## Lancer en local

### Load test Locust (UI interactive)

```bash
make bench-local
# puis ouvrir http://localhost:8089
```

L'UI Locust permet de choisir le nombre de users simules + le spawn rate.
Pour un dev solo, viser ~20 users avec spawn rate de 2/s suffit a voir si
un endpoint repond < 200 ms p95.

### Load test Locust (headless, sans UI)

```bash
make bench-headless
```

Equivalent a `locust ... --headless -u 50 -t 2m`. Tourne 2 minutes avec
50 users puis affiche le rapport texte en stdout. Pratique pour scripts CI.

### Microbenchmarks

```bash
make bench-micro
```

Lance `pytest benchmarks/test_perf.py --benchmark-only`. Stocke la run dans
`.benchmarks/` sous le nom `baseline` pour comparaison ulterieure.

### Comparer une nouvelle run au baseline

```bash
make bench-compare
```

Imprime un diff perf (mean, stddev, ops) entre la run courante et la
baseline. Si plus de 20 % de regression sur une fonction, c'est un signal
d'alerte (verifier les queries SQL emises, profiler avec
`django-debug-toolbar` ou `cProfile`).

## Interpreter les resultats

### Locust

Trois metriques cles :
- **Median (p50)** : temps de reponse typique. Doit etre < 100 ms sur les
  endpoints lecture (list projects, fetch /me/).
- **95th percentile (p95)** : 5 % des requetes sont au-dessus. Cible :
  < 300 ms sur la lecture, < 500 ms sur les POST.
- **Failures (%)** : doit rester a 0. Une montee de 4xx/5xx indique soit un
  throttle qui se declenche (normal au-dela de 120 req/min/user), soit un
  vrai bug.

Le rapport HTML genere par Locust (`locust --html report.html`) est
joint en artifact dans le workflow GitHub Actions.

### pytest-benchmark

Colonnes du rapport :
- `Mean` : moyenne sur N rounds (par defaut 5+). C'est la metrique de
  reference.
- `StdDev` : ecart-type. Si > 30 % du mean, la mesure est bruitee
  (probablement un GC qui se declenche, relancer).
- `Median` : moins sensible aux outliers, bon complement.
- `OPS` : operations par seconde. Plus c'est haut, mieux c'est.

Les seuils p95 par fonction sont definis comme constantes en tete de
`test_perf.py` (ex: `P95_PROJECT_SERIALIZE_MS = 50`). Les assertions sont
**non bloquantes** au demarrage (`continue-on-error: true` cote CI) pour
laisser le temps de calibrer un baseline.

## Ou sont les baselines

- En local : `.benchmarks/Linux-CPython-3.13-64bit/0001_baseline.json`
  (genere par `--benchmark-save=baseline`).
- En CI : artefact `benchmark-results` du workflow `.github/workflows/benchmarks.yml`
  (retention 90 jours). Le workflow telecharge la baseline du commit
  precedent et compare.

## Add a new benchmark

1. **Microbench** : ajouter une fonction `test_bench_xxx(benchmark, ...)`
   dans `test_perf.py`, decorer avec `@pytest.mark.benchmark(group="...")`.
2. **Load test** : ajouter une classe `XxxUser(HttpUser)` avec
   `wait_time`, `host` et au moins une `@task`. Importer en haut du fichier
   si besoin.

## Liens

- [Doc Locust](https://docs.locust.io/)
- [Doc pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
- `docs/DEVELOPMENT.md` : workflow dev global du backend
