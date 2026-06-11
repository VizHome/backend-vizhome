# Changelog

## [0.2.0](https://github.com/VizHome/backend-vizhome/compare/v0.1.0...v0.2.0) (2026-06-11)


### ✨ Features

* **admin_panel:** add admin overview endpoint with metrics aggregation ([1b7dbbf](https://github.com/VizHome/backend-vizhome/commit/1b7dbbf8fd5be8b889e16954662473fe1ebed7bd))
* **admin_panel:** ajouter des endpoints pour l'audit, les abonnements, les factures et l'export CSV des utilisateurs et des renders ([f3fb009](https://github.com/VizHome/backend-vizhome/commit/f3fb009b82660e066460aedf262930cad6908801))
* **admin:** introduce admin audit log and daily snapshots ([452d512](https://github.com/VizHome/backend-vizhome/commit/452d5123350988570bb2ed0ec572d108a6e95c50))
* ajouter des benchmarks de performance pour le backend avec Locust et pytest-benchmark ([022e576](https://github.com/VizHome/backend-vizhome/commit/022e576c679af9d73ea6e833fbddb5a62f360a42))
* ajouter des workflows pour l'analyse de sécurité avec CodeQL, la révision des dépendances et OSSAR ([4701d2b](https://github.com/VizHome/backend-vizhome/commit/4701d2b51f88649b09c6e1992a0cfe6f2892fdf5))
* ajouter le calcul du propriétaire en minuscules pour les images Docker ([e9ac317](https://github.com/VizHome/backend-vizhome/commit/e9ac317e464551727b796e5d78c87afe2a820a06))
* Ajouter un fichier README.md avec des instructions de démarrage et des détails sur l'architecture ([a904509](https://github.com/VizHome/backend-vizhome/commit/a9045091ae1256ebe12c702fbb711c6099cfefd7))
* ajouter un système d'envoi d'emails transactionnels avec templates HTML et texte ([efc2cb9](https://github.com/VizHome/backend-vizhome/commit/efc2cb957a74148a1716e63db0878a7886aa74f4))
* **billing:** ajouter des patches de compatibilité pour stripe-python ≥ 12 et dj-stripe 2.10 ([0152860](https://github.com/VizHome/backend-vizhome/commit/0152860043ecbe62954ec31687fe12beafb4a751))
* **billing:** ajouter un patch de compatibilité pour stripe-python ≥ 12 et dj-stripe 2.10 ([36bd9ae](https://github.com/VizHome/backend-vizhome/commit/36bd9ae5c116d28b3e7f926d54b0c37e43efc0f3))
* **billing:** créer une commande pour configurer le webhook endpoint local avec Stripe CLI ([36bd9ae](https://github.com/VizHome/backend-vizhome/commit/36bd9ae5c116d28b3e7f926d54b0c37e43efc0f3))
* **billing:** mettre à jour dj-stripe à la version 2.10.3 pour compatibilité avec stripe-python ≥ 12 ([a55f0a8](https://github.com/VizHome/backend-vizhome/commit/a55f0a8b559368ac7a4d84ea9fc5748a2d6205af))
* **ci:** mettre à jour les secrets GitHub pour les workflows CI/CD ([69ac6ea](https://github.com/VizHome/backend-vizhome/commit/69ac6eabb930aa591f0e213b9b90ec9a68f1e090))
* **ci:** mettre à jour les workflows CI/CD pour améliorer la validation et le déploiement ([22ab719](https://github.com/VizHome/backend-vizhome/commit/22ab719cdd926763271fde7f07977c3be8fddc63))
* **contact:** add public contact form with email notifications and newsletter opt-in ([bb5c481](https://github.com/VizHome/backend-vizhome/commit/bb5c4819bab7d422ae8114f313b16e38fb3267df))
* **docs:** add comprehensive documentation for architecture, contributing, deployment, development, and project structure ([0573939](https://github.com/VizHome/backend-vizhome/commit/05739393e08b509d1830678bdd331873cce86b9c))
* Enhance security, add contact form, and improve deployment setup ([32278b7](https://github.com/VizHome/backend-vizhome/commit/32278b79d01848fbf2bb80fb2d974c83b9baa9c0))
* fix/all project ([661119d](https://github.com/VizHome/backend-vizhome/commit/661119dfd563c11af6c3ed290ccd226be61144ef))
* **forum:** add moderation actions for topics and replies ([452d512](https://github.com/VizHome/backend-vizhome/commit/452d5123350988570bb2ed0ec572d108a6e95c50))
* **forum:** implement forum functionality with categories, topics, and replies ([77c8b3e](https://github.com/VizHome/backend-vizhome/commit/77c8b3e97bb963aeec459fe17d9ec3df3931ae0c))
* **gdpr:** add GDPR endpoints for account deletion and data export ([0b8f443](https://github.com/VizHome/backend-vizhome/commit/0b8f443fb2fac01cf85ccc8006f70eaf6dade154))
* Implement project management features with annotations, models, and sharing capabilities ([356c32f](https://github.com/VizHome/backend-vizhome/commit/356c32f90cb938209381e1eb8e612ab8c790c1b1))
* Implement Render app with Gemini provider integration ([efa2563](https://github.com/VizHome/backend-vizhome/commit/efa25630f1da2ca49a463639bc913167a6dea901))
* mise à jour de la configuration pour le déploiement et la sécurité, ajout de middlewares Traefik, et amélioration de la documentation ([231222f](https://github.com/VizHome/backend-vizhome/commit/231222ff473a78cb99f28469529d6d372d3b1b41))
* Mise à jour des variables d'environnement pour l'intégration avec MinIO ([050d4d7](https://github.com/VizHome/backend-vizhome/commit/050d4d789e9bc5d3598d56d510dde4cffab042da))
* **notifications:** ajouter des notifications par email pour les tickets de support ([17b4b2e](https://github.com/VizHome/backend-vizhome/commit/17b4b2e7c633e3f22443598a375461736d93acc3))
* **oauth:** ajouter le support du flow d'autorisation par code pour Google OAuth ([529a3d4](https://github.com/VizHome/backend-vizhome/commit/529a3d40f3eaf3ab4240a2aa1c5883ef0eb39a56))
* **projects:** ajouter un endpoint pour télécharger une miniature de projet ([36bd9ae](https://github.com/VizHome/backend-vizhome/commit/36bd9ae5c116d28b3e7f926d54b0c37e43efc0f3))
* **readme:** ajouter des badges de statut de qualité et de couverture ([c125789](https://github.com/VizHome/backend-vizhome/commit/c1257894e3430d94132fc4a7ca0700b093f1bc02))
* renforcer la sécurité de l'API avec des throttles, des politiques CSP et des validations de fichiers ([0132423](https://github.com/VizHome/backend-vizhome/commit/0132423b7cf8c6231d82043af2e571132a25235b))
* **subscription:** améliorer l'accès aux champs de la subscription avec une méthode défensive ([07cd5f2](https://github.com/VizHome/backend-vizhome/commit/07cd5f21371bc168dedcc1421c96b3b82a4a12de))
* **support:** augmenter la limite de caractères pour les messages de support à 50 000 ([36bd9ae](https://github.com/VizHome/backend-vizhome/commit/36bd9ae5c116d28b3e7f926d54b0c37e43efc0f3))
* **support:** implement support ticket system with CRUD operations ([5838c95](https://github.com/VizHome/backend-vizhome/commit/5838c95c0f98f02401582db55af4a53df9a8116a))
* suppression de fichiers image inutilisés ([d904a17](https://github.com/VizHome/backend-vizhome/commit/d904a17b2cbd75f732fad8129c28a1f17054314f))


### 🐛 Bug fixes

* ajouter des valeurs par défaut pour les variables d'environnement PostgreSQL dans les fichiers docker-compose ([e229501](https://github.com/VizHome/backend-vizhome/commit/e22950108bf8f6518b4500b9f2bf65471cb24fb4))
* ajouter le service stripe-cli pour le forwarding automatique des webhooks et mettre à jour la documentation ([40a8ed5](https://github.com/VizHome/backend-vizhome/commit/40a8ed5566213271e0ca1784b416b110ebaede32))
* améliorer la gestion des erreurs et la configuration des services dans le code ([57194d7](https://github.com/VizHome/backend-vizhome/commit/57194d746f0a11963002f868223deb6b04ebdd5b))
* **core:** minor code style adjustments for consistency ([bb5c481](https://github.com/VizHome/backend-vizhome/commit/bb5c4819bab7d422ae8114f313b16e38fb3267df))
* corriger la version de l'action Trivy dans le workflow CI ([df73fa1](https://github.com/VizHome/backend-vizhome/commit/df73fa14ad421f46e1df3ee0e8c5ff589a2b94bf))
* mettre à jour l'accès aux données de facturation pour la compatibilité avec dj-stripe 2.10 ([ec1ee33](https://github.com/VizHome/backend-vizhome/commit/ec1ee3339b479ae03e8866b1339349e98993d7e3))
* mettre à jour la configuration du provider Gemini pour supporter Vertex AI et ajuster les instructions de transformation ([4e880e8](https://github.com/VizHome/backend-vizhome/commit/4e880e871fd3edf307b30d7386042c234debcd67))
* mettre à jour les dépendances OpenTelemetry vers les versions les plus récentes ([752c16b](https://github.com/VizHome/backend-vizhome/commit/752c16b0cb3aa371f37756753e1035884aad866c))


### ♻️ Refactoring

* améliorer la lisibilité et la cohérence du code dans plusieurs fichiers ([b7bb161](https://github.com/VizHome/backend-vizhome/commit/b7bb1611e1dde9f6768630643192023d1225fcbf))
* harmoniser le style de code et améliorer la lisibilité dans plusieurs fichiers ([9249faa](https://github.com/VizHome/backend-vizhome/commit/9249faa03221860798176a94c4bfd07066bd5d20))
* simplifier les appels à l'API dans locustfile.py ([0431905](https://github.com/VizHome/backend-vizhome/commit/0431905eb5a70c86f9320ad8cfb246d574a9eb7b))


### 📚 Documentation

* ajouter des directives de validation et des conventions pour les commits et les tests ([817230e](https://github.com/VizHome/backend-vizhome/commit/817230e8a0028534274bb548189fdec596ed9de7))
