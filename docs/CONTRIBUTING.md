# Contribuer — backend-vizhome

Merci de contribuer ! Ce guide résume les conventions et le workflow PR.

## Workflow

1. **Fork** le repo (ou crée une branche si membre de l'org)
2. **Clone + setup** : voir [DEVELOPMENT.md](./DEVELOPMENT.md)
3. **Branche** : `feature/ma-feature`, `fix/mon-bug`, `chore/mon-refactor`
4. **Commits atomiques** — un commit = une intention
5. **Tests** — couverture > 80% pour le nouveau code
6. **Lint + format** : `ruff check src/ && ruff format src/`
7. **PR** vers `main` avec description claire + lien vers issue

## Conventions de commit

[Conventional Commits](https://www.conventionalcommits.org/) :

```
feat(accounts): add 2FA TOTP setup endpoint
fix(renders): handle Gemini safety filter blocks
docs(api): update authentication examples
chore(deps): bump django to 5.2.14
refactor(billing): extract Stripe client config
test(projects): add presigned upload edge cases
```

Types : `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
`perf`, `ci`.

## Style Python

- **PEP 8** + **ruff** (config dans `pyproject.toml`)
- **Single quotes** pour les strings (ruff format gère)
- **f-strings** plutôt que `.format()` ou `%`
- **Type hints** sur les fonctions publiques :
  ```python
  def get_user(id: int) -> User | None:
      ...
  ```

## Style Django

- **CBV plutôt que FBV** — utiliser `generics.*` ou `APIView`
- **Pas de logique métier dans les views** — la logique va dans les
  serializers ou des services dédiés
- **Pas de query dans les templates** — toujours `select_related` /
  `prefetch_related` dans la view
- **Migrations atomiques** — un changement de model = une migration
- **Signaux pour la sync, pas pour la logique métier** — les signaux
  doivent être idempotents et rapides

## Tests obligatoires

Pour chaque PR :

- [ ] Nouveau modèle → test création + contraintes uniques
- [ ] Nouveau serializer → test validation (champs requis, formats)
- [ ] Nouvelle view → test succès + 401 + 403 + 404 + permissions
- [ ] Nouveau provider externe (Stripe, Gemini, …) → mocks
- [ ] Nouvelle commande management → test invocation

Exemple :

```python
@pytest.mark.django_db
class TestMyView:
    URL = '/api/v1/my-endpoint/'

    def test_unauthenticated_returns_401(self, api_client):
        r = api_client.get(self.URL)
        assert r.status_code == 401

    def test_authenticated_returns_data(self, auth_client):
        r = auth_client.get(self.URL)
        assert r.status_code == 200
        assert 'data' in r.data
```

## Lint avant push

Le CI rejette les PRs qui :
- ne passent pas `ruff check src/`
- ne passent pas `ruff format --check src/`
- ont des tests qui échouent
- baissent la couverture sous le seuil

Lance toujours en local **avant** de pousser :

```bash
docker compose exec api ruff check src/
docker compose exec api ruff format src/
docker compose exec api pytest
```

## Ouvrir une issue

Avant d'ouvrir une PR pour un gros changement, **ouvrir une issue
discussion** pour valider l'approche. Évite les PRs rejetées après 200
lignes de code.

Pour les **bugs** :
- Reproduction step-by-step
- Comportement attendu vs observé
- Stack trace complète
- Version Django + Python + OS

Pour les **features** :
- Cas d'usage
- Alternatives considérées
- Impact sur l'API (breaking change ?)

## Sécurité

::: warning
**Ne jamais commit** :
- Clés API (Stripe, Gemini, OAuth secrets…)
- `.env` (uniquement `.env.example`)
- Backups Postgres
- Données utilisateurs

Si tu as accidentellement push un secret : **rotate immédiatement** le
secret côté provider + force-push pour supprimer le commit.
:::

Vulnerabilités de sécurité : envoyer un email à `security@vizhome.fr`
plutôt que d'ouvrir une issue publique.

## Aide

- 💬 Discord : invitation sur GitHub Discussions
- 📧 dev@vizhome.fr
- 🐛 [GitHub Issues](https://github.com/VizHome/backend-vizhome/issues)
