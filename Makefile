# Makefile : raccourcis pour les benchmarks performance VizHome backend.
#
# Le projet tourne en Docker (cf. CLAUDE.md), mais les benchmarks se lancent
# en local sur la machine du dev (Locust UI a besoin d'un browser ouvert,
# pytest-benchmark veut un environnement stable, pas un container ephemere).
#
# Conventions :
#   > pas de tirets cadratins (banni dans le repo)
#   > targets prefixes `bench-` pour rester groupes
#   > `make help` liste les targets

PYTHON ?= python
PYTEST ?= pytest
LOCUST ?= locust

LOCUST_FILE   := benchmarks/locustfile.py
LOCUST_HOST   ?= http://localhost:8000
LOCUST_USERS  ?= 50
LOCUST_TIME   ?= 2m

MICRO_FILE    := benchmarks/test_perf.py
BENCH_DIR     := .benchmarks

.PHONY: help bench-local bench-headless bench-micro bench-compare bench-clean

help:
	@echo "Targets disponibles :"
	@echo "  bench-local      : Locust UI sur http://localhost:8089"
	@echo "  bench-headless   : Locust headless (50 users, 2 min)"
	@echo "  bench-micro      : microbench pytest, save baseline"
	@echo "  bench-compare    : compare la run courante au dernier baseline"
	@echo "  bench-clean      : supprime les baselines locaux ($(BENCH_DIR))"

bench-local:
	@echo ">> Locust UI : ouvrir http://localhost:8089 pour configurer la run"
	$(LOCUST) -f $(LOCUST_FILE) --host $(LOCUST_HOST)

bench-headless:
	@echo ">> Locust headless : $(LOCUST_USERS) users, duree $(LOCUST_TIME)"
	$(LOCUST) -f $(LOCUST_FILE) --host $(LOCUST_HOST) \
		--headless -u $(LOCUST_USERS) -r 5 -t $(LOCUST_TIME) \
		--only-summary

bench-micro:
	@echo ">> Microbench pytest (save baseline)"
	$(PYTEST) $(MICRO_FILE) \
		--benchmark-only \
		--benchmark-save=baseline \
		--benchmark-columns=min,mean,median,max,stddev,ops

bench-compare:
	@echo ">> Comparaison vs dernier baseline"
	$(PYTEST) $(MICRO_FILE) \
		--benchmark-only \
		--benchmark-compare \
		--benchmark-compare-fail=mean:20%

bench-clean:
	@echo ">> Suppression $(BENCH_DIR)/"
	rm -rf $(BENCH_DIR)
