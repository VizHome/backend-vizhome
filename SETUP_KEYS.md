# 🔑 Guide d'activation des clés API

Tous les services tiers (Gemini, Stripe, Google OAuth, GitHub OAuth, MinIO) sont **désactivés gracieusement** sans clés (les endpoints renvoient 503 ou un fallback). Voici la marche à suivre pour les activer.

---

## 1. 🤖 Gemini (génération IA des rendus)

### Obtenir une clé

1. Va sur **https://aistudio.google.com/apikey**
2. Connecte-toi avec un compte Google
3. Clique sur **"Create API key"** → choisis un projet Google Cloud existant ou créé-en un
4. Copie la clé (format `AIzaSy...`)

### Configurer

```bash
# backend-vizhome/.env
GEMINI_API_KEY=AIzaSy...
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image-preview  # ou autre modèle disponible
RENDERS_DEFAULT_PROVIDER=gemini
```

Puis redémarrer le backend pour recharger les env :

```bash
docker compose up -d --force-recreate api celery
```

### Tester

```bash
# Login pour récupérer un token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@vizhome.fr","password":"SecurePass1!"}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['access'])")

# Création d'un render
curl -X POST http://localhost:8000/api/v1/renders/ \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"source":"prompt","output_type":"2d","prompt":"A modern living room"}'
```

Si tu obtiens un `202 Accepted` avec `{id, status:"pending"}` → ✅ pipeline OK. Sinon `400` avec `"Provider IA indisponible"` = clé absente ou invalide.

### Quotas Gemini gratuits (au 2026-05)

- **Imagen 3** (text-to-image) : 50 images/jour gratuit
- **Gemini 2.5 Flash Image** : 1500 requêtes/jour gratuit

Si tu dépasses, le pipeline marquera les renders `failed` avec l'error message Gemini.

---

## 2. 💳 Stripe (abonnements + facturation)

### Obtenir les clés test

1. Va sur **https://dashboard.stripe.com/test/apikeys**
2. Crée un compte Stripe (test mode par défaut)
3. Copie les deux clés :
   - **Publishable key** (`pk_test_...`) — utilisable côté frontend
   - **Secret key** (`sk_test_...`) — backend uniquement, NE JAMAIS LEAK

### Configurer le backend

```bash
# backend-vizhome/.env
STRIPE_LIVE_MODE=False
STRIPE_TEST_SECRET_KEY=sk_test_...
STRIPE_TEST_PUBLISHABLE_KEY=pk_test_...
STRIPE_LIVE_SECRET_KEY=        # vide pour l'instant
STRIPE_LIVE_PUBLISHABLE_KEY=   # vide pour l'instant
STRIPE_WEBHOOK_SECRET=whsec_placeholder  # provisoire jusqu'à étape 4
```

Restart : `docker compose up -d --force-recreate api`

### Créer les Products + Prices côté Stripe

```bash
docker compose exec api python manage.py setup_stripe_products
```

Sortie attendue :
```
→ Plan « pro »
  Product   : VizHome Pro
  Lookup    : vizhome_pro_monthly
  Prix      : 19.00 € / mois
  + Product créé : prod_xxx
  + Price créée : price_xxx
→ Plan « enterprise »
  ...
✓ Setup Stripe terminé.
```

### Configurer le webhook (recevoir les events Stripe)

#### Option A — Stripe CLI (recommandé en dev)

```bash
# 1. Installer Stripe CLI : https://docs.stripe.com/stripe-cli
stripe login

# 2. Forward les events Stripe vers ton backend local
stripe listen --forward-to http://localhost:8000/webhooks/stripe/webhook/

# Affiche : Ready! Your webhook signing secret is whsec_xxx
```

Met à jour `.env` avec ce secret :
```bash
STRIPE_WEBHOOK_SECRET=whsec_xxx
```

Restart : `docker compose up -d --force-recreate api`

#### Option B — Webhook permanent (prod)

Dashboard Stripe → Developers → Webhooks → Add endpoint :
- URL : `https://api.vizhome.fr/webhooks/stripe/webhook/`
- Events à écouter :
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `checkout.session.completed`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

Copie le **Signing secret** dans `.env.prod`.

### Tester le checkout

Depuis le frontend :
1. UserNav → "Abonnement"
2. Clique "Passer au Pro"
3. Tu es redirigé vers Stripe Checkout
4. Saisis la carte test : `4242 4242 4242 4242` / `12/34` / `123`
5. Après paiement → retour sur `/account/billing?checkout=success`
6. Vérifie via `GET /api/v1/me/subscription` que `plan` est devenu `pro`

### Configurer le frontend

```bash
# frontend-vizhome/.env
# La publishable key sert si tu utilises Stripe Elements (pas le cas pour
# l'instant — on utilise Checkout Session redirect). Optionnel.
NUXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Passage en prod (live mode)

Quand tu actives ton compte Stripe :
```bash
STRIPE_LIVE_MODE=True
STRIPE_LIVE_SECRET_KEY=sk_live_...
STRIPE_LIVE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_xxx  # nouveau, différent du test
```

Refait `setup_stripe_products` (les products live sont séparés des test).

---

## 3. 🔐 Google OAuth (Sign-In)

### Créer le client OAuth

1. Va sur **https://console.cloud.google.com/apis/credentials**
2. Crée un projet (ou utilise un existant)
3. **APIs & Services > OAuth consent screen** :
   - User type : External
   - App name : `VizHome`
   - Scopes : `email`, `profile`, `openid`
4. **Credentials > Create credentials > OAuth client ID** :
   - Application type : **Web application**
   - Name : `VizHome Web`
   - Authorized JavaScript origins :
     - `http://localhost:3000` (dev)
     - `https://app.vizhome.fr` (prod)
   - Authorized redirect URIs : *(vide — on utilise le flow Sign-In id_token, pas le code flow)*

5. Copie le **Client ID** (`xxx.apps.googleusercontent.com`)

### Configurer

Le **même Client ID** côté backend (vérification id_token) ET frontend (initialisation Google Sign-In) :

```bash
# backend-vizhome/.env
GOOGLE_OAUTH_CLIENT_ID=xxx.apps.googleusercontent.com

# frontend-vizhome/.env
NUXT_PUBLIC_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

Restart les deux. Le bouton "Google" sur `/auth/login` devient cliquable.

### Tester

1. Frontend → `/auth/login` → "Google"
2. Popup Google → choisis un compte
3. Auto-redirect vers `/render` avec session ouverte

---

## 4. 🐙 GitHub OAuth

### Créer l'OAuth App

1. Va sur **https://github.com/settings/developers** (ou Organization > Settings > Developer settings > OAuth Apps)
2. **New OAuth App** :
   - Application name : `VizHome`
   - Homepage URL : `http://localhost:3000` (ou `https://app.vizhome.fr`)
   - Authorization callback URL : **`http://localhost:3000/auth/oauth/github/callback`** (ou prod equivalent)
3. Après création, **Generate a new client secret**

Tu obtiens :
- **Client ID** (`Iv1.xxxxxxxxxxxx`)
- **Client Secret** (`xxxxxxx...`) — **NE JAMAIS LEAK CÔTÉ FRONTEND**

### Configurer

```bash
# backend-vizhome/.env (secret + id pour l'échange code → token)
GITHUB_OAUTH_CLIENT_ID=Iv1.xxxxxxxxxxxx
GITHUB_OAUTH_CLIENT_SECRET=xxxxxxx...

# frontend-vizhome/.env (id seul pour construire l'URL d'autorisation)
NUXT_PUBLIC_GITHUB_CLIENT_ID=Iv1.xxxxxxxxxxxx
```

Restart les deux. Le bouton "GitHub" devient cliquable.

### Tester

1. Frontend → `/auth/login` → "GitHub"
2. Redirect vers github.com → autorise
3. Callback `/auth/oauth/github/callback?code=...` → backend échange → session ouverte

---

## 5. 📦 MinIO (storage S3-compatible)

### Dev — déjà fonctionnel

Déjà configuré dans `docker-compose.yml`. Vérifier :
- Console MinIO : http://localhost:9001 (login `vizhome` / `vizhome_minio_dev_password`)
- Bucket `vizhome-media` existe et est public en lecture

### Prod — adapter pour ton domaine

```bash
# backend-vizhome/.env.prod
USE_S3=True
MINIO_S3_ACCESS_KEY=xxx                  # GÉNÈRE un mot de passe FORT
MINIO_S3_SECRET_KEY=xxx                  # GÉNÈRE un mot de passe FORT
MINIO_S3_BUCKET_NAME=vizhome-media
MINIO_S3_REGION=us-east-1
MINIO_S3_ENDPOINT_URL=http://minio:9000  # interne docker
MINIO_S3_CUSTOM_DOMAIN=cdn.vizhome.fr    # domaine public via reverse proxy
MINIO_S3_URL_PROTOCOL=https:
```

Pour générer des passwords forts :
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Le reverse proxy (Traefik, déjà configuré dans `docker-compose.prod.yml`) routera `cdn.vizhome.fr` → MinIO via Let's Encrypt HTTPS.

### Alternative — vraie S3 (Cloudflare R2, Backblaze B2, AWS S3, OVH Object Storage)

Aucun changement de code. Juste les variables :
```bash
USE_S3=True
MINIO_S3_ACCESS_KEY=ton_access_key
MINIO_S3_SECRET_KEY=ton_secret_key
MINIO_S3_BUCKET_NAME=vizhome-media
MINIO_S3_REGION=auto                                   # R2 utilise "auto"
MINIO_S3_ENDPOINT_URL=https://xxx.r2.cloudflarestorage.com
MINIO_S3_CUSTOM_DOMAIN=cdn.vizhome.fr
MINIO_S3_URL_PROTOCOL=https:
```

Le bucket doit avoir une policy "public read" pour les renders/modèles 3D.

---

## 6. 📧 Email SMTP (prod uniquement)

En dev les emails (forgot password etc.) s'affichent dans les logs Docker via `console.EmailBackend`. En prod, configure un SMTP :

```bash
# backend-vizhome/.env.prod
EMAIL_HOST=smtp.sendgrid.net          # ou mailgun, postmark, AWS SES…
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxx...
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@vizhome.fr
```

---

## 7. 🚨 Sentry (monitoring d'erreurs, optionnel)

1. **https://sentry.io** → crée un projet Django
2. Copie le DSN (`https://xxx@xxx.ingest.sentry.io/xxx`)

```bash
# backend-vizhome/.env.prod
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

Restart → toutes les exceptions Django remontent dans Sentry. Aucune action sur le DSN vide.

---

## Récap : minimum pour avoir un truc qui fonctionne en dev

```bash
# backend-vizhome/.env
GEMINI_API_KEY=AIzaSy...                  # pour la génération IA
STRIPE_TEST_SECRET_KEY=sk_test_...        # pour le billing
STRIPE_WEBHOOK_SECRET=whsec_xxx           # via stripe listen
GOOGLE_OAUTH_CLIENT_ID=xxx                # pour le bouton Google (optionnel)
GITHUB_OAUTH_CLIENT_ID=xxx                # idem
GITHUB_OAUTH_CLIENT_SECRET=xxx

# frontend-vizhome/.env
NUXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NUXT_PUBLIC_GOOGLE_CLIENT_ID=xxx          # MÊME ID que côté backend
NUXT_PUBLIC_GITHUB_CLIENT_ID=xxx          # idem
```

Et :
```bash
cd backend-vizhome
docker compose up -d --force-recreate api
docker compose exec api python manage.py setup_stripe_products

# Dans un autre terminal
stripe listen --forward-to http://localhost:8000/webhooks/stripe/webhook/

# Frontend
cd ../frontend-vizhome
npm run dev
```

L'app est prête à tester end-to-end sur http://localhost:3000.
