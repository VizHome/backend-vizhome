# Guide Utilisateur — VizHome

> VizHome est une plateforme SaaS de visualisation et de génération de rendus 3D assistée par IA. Ce guide explique comment utiliser toutes les fonctionnalités de l'application.

---

## Accéder à l'application

Ouvrir un navigateur et aller sur **https://vizhome.fr**

> Navigateurs supportés : Chrome 120+, Firefox 120+, Safari 17+, Edge 120+

---

## Créer un compte

### Inscription par email

1. Cliquer sur **"S'inscrire"** sur la page d'accueil
2. Renseigner :
   - Adresse email
   - Mot de passe (8 caractères minimum)
3. Cliquer sur **"Créer mon compte"**
4. Consulter votre boîte email et cliquer sur le lien de confirmation

### Connexion via Google ou GitHub

1. Sur la page de connexion, cliquer sur **"Continuer avec Google"** ou **"Continuer avec GitHub"**
2. Autoriser VizHome à accéder à votre profil
3. Vous êtes automatiquement connecté

---

## Se connecter

1. Aller sur https://vizhome.fr/login
2. Saisir votre email et mot de passe
3. Cliquer sur **"Se connecter"**

### Connexion avec authentification à deux facteurs (2FA)

Si vous avez activé la 2FA :

1. Saisir email + mot de passe
2. Ouvrir votre application d'authentification (Google Authenticator, Authy…)
3. Saisir le code à 6 chiffres affiché

### Mot de passe oublié

1. Cliquer sur **"Mot de passe oublié ?"** sur la page de connexion
2. Saisir votre adresse email
3. Consulter votre boîte email et suivre les instructions

---

## Tableau de bord

Après connexion, vous arrivez sur votre **tableau de bord** qui affiche :

- Vos projets récents
- Vos derniers rendus IA
- Votre consommation du mois (rendus utilisés / rendus disponibles selon votre plan)
- Raccourcis vers les fonctionnalités principales

---

## Projets 3D

### Créer un projet

1. Cliquer sur **"Nouveau projet"** depuis le tableau de bord
2. Renseigner :
   - **Nom du projet** (obligatoire)
   - **Description** (optionnel)
3. Cliquer sur **"Créer"**

### Naviguer dans un projet

Un projet contient une **scène 3D** interactive basée sur Three.js :

- **Orbite** : clic gauche + glisser
- **Zoom** : molette de la souris
- **Pan** : clic droit + glisser (ou molette + clic)

### Importer un modèle 3D

Formats supportés : **GLB, GLTF, OBJ, FBX, STL**

1. Dans votre projet, cliquer sur **"Importer un modèle"**
2. Sélectionner votre fichier 3D (taille maximum : 100 Mo)
3. Attendre la fin de l'import (le fichier est uploadé directement sur notre stockage sécurisé)
4. Le modèle apparaît dans votre scène

> Pour les fichiers > 100 Mo, contacter le support pour un accès multipart.

### Ajouter des annotations

Les annotations permettent d'ajouter des notes à des points précis de votre scène 3D :

1. Activer le mode **"Annotation"** dans la barre d'outils
2. Cliquer sur le point de la scène à annoter
3. Saisir votre note
4. Cliquer sur **"Enregistrer"**

Les annotations sont visibles par toutes les personnes ayant accès au projet.

### Partager un projet

1. Dans votre projet, cliquer sur **"Partager"**
2. Cliquer sur **"Créer un lien de partage"**
3. Copier le lien généré et le partager

> Le lien est public — toute personne possédant le lien peut consulter votre projet (en lecture seule).

Pour **révoquer** l'accès, supprimer le lien de partage depuis les paramètres du projet.

### Dupliquer un projet

1. Sur la liste des projets, cliquer sur les **"..."** d'un projet
2. Sélectionner **"Dupliquer"**
3. Un nouveau projet identique est créé avec le suffixe " (copie)"

### Supprimer un projet

1. Sur la liste des projets, cliquer sur les **"..."** du projet
2. Sélectionner **"Supprimer"**
3. Confirmer la suppression dans la boîte de dialogue

> **Attention** : la suppression est définitive. Tous les modèles 3D et annotations associés sont également supprimés.

---

## Génération IA (Rendus)

VizHome utilise **Gemini** (Google) pour générer des visuels 2D/3D à partir d'un texte ou d'une esquisse.

### Créer un rendu depuis un texte (prompt)

1. Aller dans la section **"Rendus"** ou cliquer sur **"Nouveau rendu"**
2. Choisir le mode **"Texte"**
3. Saisir votre description (en français ou anglais) :
   - Exemple : *"Salon moderne minimaliste avec canapé gris, lumière naturelle, vue depuis l'entrée"*
4. Choisir le format de sortie (2D / 3D)
5. Cliquer sur **"Générer"**

La génération prend **15 à 30 secondes**. Un indicateur de progression est affiché.

### Créer un rendu depuis une esquisse

1. Choisir le mode **"Esquisse"**
2. Uploader votre dessin ou screenshot (JPG, PNG)
3. Ajouter une description optionnelle pour guider l'IA
4. Cliquer sur **"Générer"**

### Statuts des rendus

| Statut | Signification |
|---|---|
| **En attente** | Le rendu est en file d'attente |
| **En cours** | L'IA génère votre image |
| **Terminé** | Le rendu est disponible |
| **Échoué** | Une erreur s'est produite (quota dépassé, service indisponible…) |

### Galerie de rendus

Tous vos rendus terminés sont accessibles dans la **Galerie** :

- Filtrer par date, format, statut
- Télécharger un rendu (bouton de téléchargement)
- Supprimer un rendu

### Quotas de rendus

Le nombre de rendus disponibles dépend de votre plan d'abonnement :

| Plan | Rendus / mois |
|---|---|
| Gratuit | 5 rendus |
| Pro | 100 rendus |
| Entreprise | Illimité |

Le compteur se remet à zéro le 1er de chaque mois.

---

## Forum Communautaire

Le forum permet d'échanger avec d'autres utilisateurs VizHome.

### Parcourir les catégories

1. Aller dans **"Forum"** depuis le menu principal
2. Choisir une catégorie (ex: Aide, Showcase, Tutoriels…)

### Créer un sujet

1. Dans une catégorie, cliquer sur **"Nouveau sujet"**
2. Renseigner :
   - **Titre** (obligatoire)
   - **Contenu** (éditeur riche avec mise en forme)
   - **Images** (glisser-déposer ou bouton d'upload)
3. Cliquer sur **"Publier"**

### Répondre à un sujet

1. Ouvrir un sujet
2. Cliquer sur **"Répondre"** en bas de page
3. Rédiger votre réponse
4. Cliquer sur **"Publier"**

### Modifier ou supprimer une réponse

> Vous pouvez modifier votre réponse dans les **15 minutes** suivant sa publication.

1. Cliquer sur le menu **"..."** de votre réponse
2. Sélectionner **"Modifier"** ou **"Supprimer"**

---

## Support

### Créer un ticket de support

1. Aller dans **"Support"** depuis le menu ou footer
2. Cliquer sur **"Nouveau ticket"**
3. Renseigner :
   - **Sujet** : description courte du problème
   - **Catégorie** : (Technique, Facturation, Autre)
   - **Priorité** : (Normale, Haute)
   - **Description détaillée** du problème
4. Cliquer sur **"Envoyer"**

### Suivre un ticket

1. Aller dans **"Support"** → **"Mes tickets"**
2. Cliquer sur un ticket pour voir les échanges et les réponses du support

### Statuts des tickets

| Statut | Signification |
|---|---|
| **Ouvert** | Ticket reçu, en attente de traitement |
| **En cours** | Un agent support traite votre demande |
| **Résolu** | Votre problème est résolu |
| **Fermé** | Ticket archivé |

---

## Mon Compte

### Accéder aux paramètres

Cliquer sur votre avatar (haut droite) → **"Paramètres"** ou **"Mon compte"**

### Modifier le profil

1. Section **"Profil"**
2. Modifier votre nom, photo de profil
3. Cliquer sur **"Enregistrer"**

### Changer de mot de passe

1. Section **"Sécurité"**
2. Saisir le mot de passe actuel
3. Saisir et confirmer le nouveau mot de passe
4. Cliquer sur **"Modifier"**

### Activer l'authentification à deux facteurs (2FA)

1. Section **"Sécurité"** → **"Authentification à deux facteurs"**
2. Cliquer sur **"Configurer la 2FA"**
3. Scanner le QR code avec votre application (Google Authenticator, Authy, 1Password…)
4. Saisir le code à 6 chiffres pour confirmer
5. **Sauvegarder les codes de secours** dans un endroit sûr

> En cas de perte d'accès à votre application 2FA, les codes de secours sont le seul moyen de récupérer votre compte.

### Gérer les sessions actives

1. Section **"Sécurité"** → **"Sessions actives"**
2. Voir la liste des appareils connectés (nom d'appareil, dernière activité)
3. Cliquer sur **"Déconnecter"** pour révoquer un appareil

### Préférences

Section **"Préférences"** :

| Option | Description |
|---|---|
| **Thème** | Clair / Sombre / Système |
| **Langue** | Français / Anglais |
| **Qualité des rendus** | Standard / Haute / Ultra |
| **Format de sortie par défaut** | 2D / 3D |

---

## Abonnement & Facturation

### Voir mon plan actuel

1. Section **"Facturation"** dans les paramètres
2. Affiche votre plan actuel, date de renouvellement, consommation

### Changer de plan

1. Section **"Facturation"** → **"Changer de plan"**
2. Comparer les plans disponibles
3. Cliquer sur **"Souscrire"** sur le plan souhaité
4. Vous êtes redirigé vers Stripe (paiement sécurisé)
5. Renseigner vos informations de paiement
6. Confirmer l'abonnement

### Consulter les factures

1. Section **"Facturation"** → **"Historique de facturation"**
2. Cliquer sur **"Télécharger"** pour obtenir une facture en PDF

### Annuler l'abonnement

1. Section **"Facturation"** → **"Gérer l'abonnement"**
2. Cliquer sur **"Annuler l'abonnement"**
3. L'abonnement reste actif jusqu'à la fin de la période en cours

---

## Confidentialité et RGPD

### Exporter mes données

1. Section **"Confidentialité"** dans les paramètres
2. Cliquer sur **"Exporter mes données"**
3. Un email vous est envoyé avec un lien de téléchargement dans les 24h

Les données exportées incluent : profil, projets, rendus, messages forum et support, historique de facturation.

### Supprimer mon compte

1. Section **"Confidentialité"** → **"Supprimer mon compte"**
2. Lire les informations sur les données supprimées
3. Confirmer avec votre mot de passe
4. La suppression est planifiée sous 30 jours (délai légal RGPD)

Pour annuler une suppression planifiée, se reconnecter et cliquer sur **"Annuler la suppression"** dans la bannière.

---

## Questions fréquentes

**Puis-je utiliser VizHome sans abonnement payant ?**
Oui. Le plan Gratuit inclut 5 rendus IA par mois et un accès complet aux projets 3D.

**Mes fichiers 3D sont-ils privés ?**
Oui. Vos modèles 3D et projets sont strictement privés, sauf si vous créez explicitement un lien de partage.

**Quel est le format de fichier 3D recommandé ?**
Le format **GLB** (version binaire de GLTF) est recommandé pour les meilleures performances. Il intègre textures et géométrie dans un seul fichier.

**Comment contacter l'équipe VizHome ?**
Via le formulaire de contact sur https://vizhome.fr/contact ou par email à support@vizhome.fr.

**Mon rendu a échoué, que faire ?**
Vérifier que votre quota mensuel n'est pas épuisé. Si le problème persiste, ouvrir un ticket de support en précisant le rendu concerné.
