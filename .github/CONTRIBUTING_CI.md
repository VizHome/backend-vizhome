# CI/CD — guide d'utilisation

## Conventions de commit (obligatoire)

Tous les commits **et titres de PR** doivent suivre [Conventional Commits](https://www.conventionalcommits.org/) :

```
<type>(<scope>): <subject minuscule>

[body optionnel]

[footer optionnel, ex: BREAKING CHANGE: …]
```

**Types autorisés** :

| Type       | Quand                              | Bump version            |
|------------|------------------------------------|-------------------------|
| `feat`     | Nouvelle feature                   | **minor**               |
| `fix`      | Bug fix                            | **patch**               |
| `perf`     | Amélioration perf                  | **patch**               |
| `refactor` | Refactoring sans changement comportement | none |
| `docs`     | Documentation uniquement           | none                    |
| `test`     | Ajout/modif de tests               | none                    |
| `build`    | Build system / deps                | none                    |
| `ci`       | CI/CD                              | none                    |
| `chore`    | Tâche divers                       | none                    |
| `revert`   | Revert d'un commit                 | none                    |
| `security` | Fix de sécurité                    | **patch**               |

**Breaking change** : ajouter `BREAKING CHANGE: …` dans le footer ou un `!` après le type :
```
feat(api)!: change /me/subscription response shape
```
→ bump **major**.

**Exemples** :
```
feat(auth): ajoute le login Google via id_token
fix(billing): handle stripe webhook 200 even on no-op
perf(forum): cache topics list 60s in Redis
docs(setup): clarify .env.example for OAuth
refactor(useUser): split fetchMe and fetchPreferences
ci: bump python to 3.13 in test matrix
chore(deps): bump dj-stripe to 2.10.3
```

## Workflow git

```
   main  ←──────── release-please PR ─────────┐
    ↑                                          │
    │ (PR « release X.Y.Z »)                  │
    │                                          │
   dev  ←──── PRs feat/fix/... ────── feature/* branches
                ↑
                │
             ta branche locale
```

- Tout dev se passe sur des branches `feat/foo`, `fix/bar`, etc.
- PR vers `dev` → ouvre les checks CI + PR-checks (titre conventional, taille, secrets)
- Merge sur `dev` → push une image `ghcr.io/.../vizhome-backend:dev-<sha>` + GitHub Pre-Release
- Quand tu veux releaser une stable : PR `dev → main`
- Sur merge sur `main`, **release-please** ouvre automatiquement une PR « chore(main): release X.Y.Z » avec le CHANGELOG généré depuis les commits conventional
- Merger cette PR → tag `vX.Y.Z` + GitHub Release + image `ghcr.io/.../vizhome-backend:X.Y.Z` + `:latest`

## Workflows

| Workflow              | Déclencheurs                    | Rôle                                          |
|-----------------------|----------------------------------|-----------------------------------------------|
| `ci.yml`              | push main/dev, PR                | lint, typecheck, tests, build Docker, Trivy   |
| `release.yml`         | push main                        | release-please, push image stable + SBOM      |
| `pre-release.yml`     | push dev                         | push image dev-<sha>, GitHub Pre-Release      |
| `pr-checks.yml`       | pull_request                     | titre conventional, size label, secret leaks  |
| `sonarqube.yml`       | push main, PR                    | analyse code statique SonarQube               |

## Secrets nécessaires (GitHub Settings → Secrets and variables → Actions)

- `SONAR_TOKEN` — Token SonarCloud/SonarQube (récupéré sur Sonar)
- `SONAR_HOST_URL` — URL de l'instance Sonar (ex: `https://sonarcloud.io`)
- `CODECOV_TOKEN` — Optionnel, pour upload coverage Codecov

Le `GITHUB_TOKEN` est fourni automatiquement par Actions, **pas à configurer**.

## Setup SonarCloud (one-shot)

1. Crée un compte sur https://sonarcloud.io
2. Connecte ton organisation GitHub
3. Importe le repo `backend-vizhome` (et `frontend-vizhome`)
4. Récupère le `SONAR_TOKEN` dans **My Account → Security**
5. Ajoute-le dans GitHub Settings → Secrets → `SONAR_TOKEN`
6. Met aussi `SONAR_HOST_URL=https://sonarcloud.io`

## Run en local (act)

Pour tester un workflow localement avant push :

```bash
# Installe act : https://github.com/nektos/act
brew install act  # ou winget install nektos.act

# Liste les jobs
act -l

# Run le job `lint` du ci.yml
act -j lint

# Run en mode push sur main
act push -e .github/test-events/push-main.json
```
