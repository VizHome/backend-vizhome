# Bruno collection — VizHome Backend API

Collection [Bruno](https://www.usebruno.com/) pour tester les 48 endpoints
du backend Django + DRF en local ou en prod.

## Installation

1. Installer Bruno : https://www.usebruno.com/downloads
2. Lancer Bruno → **Open Collection** → sélectionner ce dossier (`bruno/`)
3. En haut à droite, choisir l'environnement **Local** ou **Production**

## Pré-requis

Le backend doit tourner :

```bash
cd ..              # racine backend-vizhome
docker compose up -d
```

Vérifier que c'est vivant : exécute la requête `01-Health > Readiness`.
Doit retourner `{"status":"ok"}`.

## Workflow conseillé (happy path)

Les requêtes sont ordonnées (`seq:`) pour pouvoir être exécutées dans
l'ordre, chaque appel met à jour les variables d'environnement
nécessaires pour la suivante :

1. **02-Auth > Register** → crée un user + stocke `accessToken`, `refreshToken`, `userId`
2. **03-Me > Get Me** → vérifie que le token fonctionne
3. **04-Projects > Create Project** → stocke `projectId`
4. **04-Projects > Models > Get Presigned URL** → stocke `presignedKey`
5. *(le PUT vers MinIO se fait manuellement avec un vrai fichier — voir note dans la requête)*
6. **04-Projects > Models > Confirm Presigned Upload** → stocke `modelId`
7. **04-Projects > Annotations > Create Annotation** → stocke `annotationId`
8. **05-Renders > Create Render (prompt)** → stocke `renderId`
9. **05-Renders > Get Render** (à exécuter en boucle pour le polling)
10. **04-Projects > Sharing > Create Share Link** → stocke `shareToken`
11. **04-Projects > Sharing > Get Shared Project (public)** → vérifie l'accès non-authentifié
12. **02-Auth > Logout** → révoque la session

## Variables d'environnement

Définies dans `environments/Local.bru` et `Production.bru` :

| Variable | Auto-rempli par | Usage |
|---|---|---|
| `baseUrl` | (manuel) | Préfixe de toutes les URLs |
| `accessToken` | Login / Register / Refresh | `Authorization: Bearer ...` |
| `refreshToken` | Login / Register | Pour `POST /auth/refresh` et `/logout` |
| `userId` | Login / Register | Référence à l'utilisateur courant |
| `projectId` | Create Project / List Projects | Toutes les routes `/projects/{id}/*` |
| `modelId` | Confirm Presigned / Upload Model | Routes `/projects/{id}/models/{model_id}` |
| `annotationId` | Create Annotation | Routes `/projects/{id}/annotations/{annotation_id}` |
| `shareId` | Create Share Link | Route `/projects/{id}/share/{share_id}` (DELETE) |
| `shareToken` | Create Share Link | Route publique `/shared/{token}` |
| `renderId` | Create Render / List Renders | Routes `/renders/{id}` |
| `sessionId` | List Sessions | Route `/me/sessions/{id}` (DELETE) |
| `challengeToken` | Login (si 2FA) | Pour `POST /auth/2fa/verify` |
| `twoFactorSecret` | 2FA Setup | À mettre dans une app TOTP pour générer un `code` |

Les tokens sensibles (`accessToken`, `refreshToken`) sont marqués `secret`.

## Endpoints couverts (48 au total)

- **01-Health** (2) — liveness, readiness
- **02-Auth** (8) — register, login, refresh, logout, forgot/reset password, 2FA verify, OAuth
- **03-Me** (10) — profil, préférences, password, sessions, 2FA setup/verify/disable
- **04-Projects** (22 répartis en 4 sous-dossiers)
  - Racine (8) — CRUD + duplicate + scene GET/PUT
  - Models (7) — upload multipart + presigned + CRUD transforms
  - Annotations (5) — CRUD
  - Sharing (4) — CRUD + accès public
- **05-Renders** (7) — création (prompt + sketch), liste, history, détail, update title, delete
- **06-Billing** (6) — plans publics, subscription, checkout, cancel, invoices, payment methods

## Endpoints qui requièrent une config tierce

Sans clés tierces, certains endpoints retournent une erreur explicite
plutôt que de planter :

| Endpoint | Requiert | Sans config |
|---|---|---|
| `POST /renders/` | `GEMINI_API_KEY` | HTTP 503 + `code: gemini_unavailable` |
| `POST /me/subscription/checkout` | `STRIPE_TEST_SECRET_KEY` + `setup_stripe_products` | HTTP 503 + `code: stripe_unavailable` |
| `POST /auth/oauth/google/exchange` | `GOOGLE_OAUTH_CLIENT_ID` | HTTP 503 |
| `POST /auth/oauth/github/exchange` | `GITHUB_OAUTH_*` | HTTP 503 |

Voir [`../SETUP_KEYS.md`](../SETUP_KEYS.md) pour activer chaque
intégration.

## Tests automatiques

Chaque requête contient un bloc `tests` qui vérifie le code HTTP et le
shape de la réponse. Lance toute la collection (Run → Run All) pour un
smoke test complet.

## OpenAPI spec (`openapi.yml`)

Le fichier [`openapi.yml`](./openapi.yml) contient le schéma OpenAPI 3
complet généré par `drf-spectacular`. Bruno desktop peut l'importer pour
te générer automatiquement des requêtes ou pour la complétion auto.

### Régénérer après modification d'un endpoint

```bash
# Backend doit tourner
curl -sS http://localhost:8000/api/schema/ -o bruno/openapi.yml
```

Ou via la commande Django :

```bash
docker compose exec api python manage.py spectacular --file /app/openapi.yml
docker compose cp api:/app/openapi.yml ./bruno/openapi.yml
```

### Workflow recommandé

- **Source de vérité** = le code Django (decorators `@extend_schema`,
  serializers, urls). Le `openapi.yml` est régénéré à partir de ça.
- **Bruno requests `.bru`** = curated à la main (chainage tokens,
  fixtures réalistes, scripts post-response). Ne **pas** auto-générer
  depuis l'OpenAPI, ça casserait toute la logique.
- L'OpenAPI sert pour : Swagger UI, ReDoc, génération de clients
  (TypeScript / Python), import dans Postman/Insomnia, et référence
  manuelle quand tu écris une nouvelle requête Bruno.

## Notes spécifiques

### Upload de modèle 3D

Deux modes selon la taille du fichier :

- **Multipart classique** (< ~10 MB) — `04-Projects > Models > Upload Model (multipart)`.
  Tu dois pointer vers un vrai fichier `.glb` / `.obj` / `.fbx` / `.stl` en
  remplaçant `@file(/chemin/vers/model.glb)` dans le body.
- **Presigned URL** (recommandé) — `Get Presigned URL` puis PUT manuel
  vers l'URL retournée (Bruno ne peut pas chaîner un PUT vers une URL
  externe automatiquement), puis `Confirm Presigned Upload`.

### Flow 2FA

Le `POST /auth/login` peut retourner `{require_2fa: true, challenge_token, expires_in}`
au lieu des tokens. Le script post-response détecte ce cas et stocke
`challengeToken`. Tu utilises ensuite `02-Auth > 2FA Verify Login` avec
le code généré par ton app TOTP.

### Polling de render

Bruno ne supporte pas le polling automatique natif. Exécute manuellement
`Get Render` plusieurs fois jusqu'à `status: done` ou `failed`.
