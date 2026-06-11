# Audit IDOR — backend-vizhome

Cet audit recense tous les endpoints DRF qui prennent un identifiant
d'objet (`<int:pk>`, `<int:model_id>`, etc.) dans l'URL, et vérifie que
chaque vue garantit que l'objet ciblé appartient bien à l'utilisateur
authentifié — autrement dit qu'un user A ne peut pas lire, modifier ou
supprimer un objet appartenant à un user B en devinant son ID.

## Méthodologie

1. Grep exhaustif des URL contenant `<int:` dans `src/apps/*/urls.py`.
2. Pour chaque endpoint :
   * lecture de la view associée ;
   * vérification de la présence d'un filtre `user=request.user` (ou
     équivalent) dans `get_queryset()` OU d'une `permission_classes`
     custom qui filtre par ownership au niveau de l'objet ;
   * note du verdict (OK / DOUTEUX / VULNÉRABLE).
3. Pour les vues `APIView` qui implémentent leur propre `get()` /
   `post()` / `delete()`, vérification que le `get_object_or_404` (ou
   équivalent) inclut bien `user=request.user`.
4. Audit statique uniquement — pas de test dynamique en runtime.
   Les tests d'intégration (`apps.projects.tests`, etc.) valident
   complémentairement le comportement attendu sur quelques routes.

## Tableau récapitulatif

Vérité au moment de l'audit (référence : branche `features/multi-lang`).

### `apps/accounts`

| Endpoint | View | Ownership ? | Permission | Verdict |
|---|---|---|---|---|
| DELETE `/me/sessions/<int:pk>` | `SessionDetailView` | `UserSession.objects.get(pk=pk, user=request.user, …)` | `IsAuthenticated` | OK |

### `apps/projects`

Toutes les vues passent par le helper `get_owned_project()` qui filtre
`Project, pk=pk, user=user`, ou par un `get_queryset()` user-scoped, ou
par la permission custom `IsProjectOwner.has_object_permission()`.

| Endpoint | View | Ownership ? | Permission | Verdict |
|---|---|---|---|---|
| GET/PATCH/PUT/DELETE `/projects/<pk>` | `ProjectDetailView` | `get_queryset` filtre `user=self.request.user` | `IsAuthenticated + IsProjectOwner` | OK |
| POST `/projects/<pk>/duplicate` | `ProjectDuplicateView.post` | `get_owned_project(request.user, pk)` | `IsAuthenticated` | OK |
| POST `/projects/<pk>/thumbnail` | `ProjectThumbnailView.post` | `get_owned_project(request.user, pk)` | `IsAuthenticated` | OK |
| GET/PUT `/projects/<pk>/scene` | `SceneView` | `get_owned_project()` dans `get_object` | `IsAuthenticated + IsProjectOwner` | OK |
| GET/POST `/projects/<pk>/models` | `ImportedModelListCreateView` | `get_owned_project()` dans GET et POST | `IsAuthenticated` | OK |
| POST `/projects/<pk>/models/upload-url` | `PresignedUploadView` | `get_owned_project()` | `IsAuthenticated` | OK |
| POST `/projects/<pk>/models/confirm` | `PresignedUploadConfirmView` | `get_owned_project()` | `IsAuthenticated` | OK |
| GET/PATCH/DELETE `/projects/<pk>/models/<model_id>` | `ImportedModelDetailView` | `get_queryset` filtre `project__user=self.request.user` ET `project_id=kwargs[pk]` | `IsAuthenticated + IsProjectOwner` | OK |
| GET/POST `/projects/<pk>/annotations` | `AnnotationListCreateView` | `get_queryset` filtre `project__user=user`. `perform_create` appelle `get_owned_project(...)`. | `IsAuthenticated` | OK |
| GET/PATCH/DELETE `/projects/<pk>/annotations/<annotation_id>` | `AnnotationDetailView` | `get_queryset` filtre `project__user=user, project_id=pk` | `IsAuthenticated` | OK |
| GET/POST `/projects/<pk>/share` | `ShareLinkListCreateView` | `get_queryset` filtre `project__user=user`. `perform_create` appelle `get_owned_project()`. | `IsAuthenticated` | OK |
| DELETE `/projects/<pk>/share/<share_id>` | `ShareLinkDetailView` | `get_queryset` filtre `project__user=user, project_id=pk` | `IsAuthenticated` | OK |
| GET `/shared/<token>` | `SharedProjectView` | Endpoint public **intentionnellement** — accès via token cryptographique non guessable (`secrets.token_urlsafe(32)`) | `AllowAny` | OK (par design) |

### `apps/renders`

| Endpoint | View | Ownership ? | Permission | Verdict |
|---|---|---|---|---|
| GET/PATCH/DELETE `/renders/<pk>` | `RenderDetailView` | `get_queryset` filtre `user=self.request.user` | `IsAuthenticated` | OK |
| GET `/renders/<pk>/events` (SSE) | `RenderSSEView.get` | `Render.objects.get(pk=pk, user=user)` (auth Bearer manuelle car View pure, pas DRF) | manuel | OK (commentaire ligne 90-92 du fichier) |
| GET `/renders/history` | `RenderHistoryView` | `get_queryset` filtre `user=self.request.user` | `IsAuthenticated` | OK |

### `apps/forum`

Modèle particulier : la **lecture** des topics/replies est publique
(forum communautaire), donc l'IDOR ne s'applique pas au GET. Pour les
mutations (PATCH/DELETE), la permission `IsAuthorWithinTimeWindowOrStaff`
vérifie au niveau objet que `obj.author_id == request.user.id` (ou que
l'utilisateur est staff).

| Endpoint | View | Ownership ? | Permission | Verdict |
|---|---|---|---|---|
| GET `/forum/categories` / `/forum/categories/<slug>` | `CategoryListView` / `CategoryDetailView` | Lecture publique, pas de notion d'ownership | `AllowAny` | OK (par design) |
| GET `/forum/topics` (liste) | `TopicListCreateView.get` | Public | `AllowAny` | OK (par design) |
| POST `/forum/topics` | `TopicListCreateView.post` | Auteur = `request.user` dans `serializer.save(author=request.user)` | `IsAuthenticated + IsNotForumBanned` | OK |
| GET `/forum/topics/<pk>` | `TopicDetailView.retrieve` | Public | `AllowAny` | OK (par design) |
| PATCH/DELETE `/forum/topics/<pk>` | `TopicDetailView` | `has_object_permission` vérifie `obj.author_id == request.user.id` OU staff | `IsAuthorWithinTimeWindowOrStaff` | OK |
| GET `/forum/topics/<topic_id>/replies` | `ReplyListCreateView.get` | Public | `AllowAny` | OK (par design) |
| POST `/forum/topics/<topic_id>/replies` | `ReplyListCreateView.post` | Auteur = `request.user`, topic resolved via `get_object_or_404(Topic, pk=topic_id)` | `IsAuthenticated + IsNotForumBanned` | OK |
| PATCH/DELETE `/forum/replies/<pk>` | `ReplyDetailView` | `has_object_permission` vérifie `obj.author_id == request.user.id` OU staff | `IsAuthorWithinTimeWindowOrStaff` | OK |
| POST `/forum/topics/<pk>/toggle-pin` | `TopicTogglePinView` | Staff only (check explicite `request.user.is_staff`) | `IsAuthenticated` + check inline | OK |
| POST `/forum/topics/<pk>/toggle-lock` | `TopicToggleLockView` | Staff only (check explicite) | `IsAuthenticated` + check inline | OK |
| POST `/forum/replies/<pk>/toggle-solution` | `ReplyToggleSolutionView` | Auteur du topic OU staff (check inline `reply.topic.author_id == request.user.id`) | `IsAuthenticated` + check inline | OK |
| POST `/forum/upload-image` | `ForumImageUploadView` | Pas d'ID dans l'URL — uploadé pour `request.user` | `IsAuthenticated` | OK |

### `apps/support`

| Endpoint | View | Ownership ? | Permission | Verdict |
|---|---|---|---|---|
| GET `/support/tickets` (liste) | `TicketListCreateView.get` | `get_queryset` filtre `user=self.request.user` | `IsAuthenticated` | OK |
| POST `/support/tickets` | `TicketListCreateView.post` | `serializer.save()` (le serializer fixe `user=request.user` via le context) | `IsAuthenticated` | OK |
| GET `/support/tickets/<pk>` | `TicketDetailView.get` | `get_queryset` : si user staff, qs complet ; sinon `.filter(user=self.request.user)` | `IsAuthenticated` | OK |
| PATCH `/support/tickets/<pk>` | `TicketDetailView.patch` | Staff only (permission `IsAdminUser`) | `IsAuthenticated + IsAdminUser` | OK |
| POST `/support/tickets/<pk>/messages` | `TicketMessageCreateView.post` | Si staff : `get_object_or_404(SupportTicket, pk=pk)`. Sinon : `get_object_or_404(SupportTicket, pk=pk, user=request.user)` | `IsAuthenticated` | OK |

### `apps/billing`

Les endpoints billing ne prennent **pas** d'ID dans l'URL. Les
ressources Stripe (subscription, invoices, payment methods) sont
filtrées en interne sur `customer = Customer.objects.filter(
subscriber=request.user).first()`. Pas de surface IDOR.

| Endpoint | View | Ownership ? | Verdict |
|---|---|---|---|
| GET `/me/subscription` | `SubscriptionView` | `Customer.objects.filter(subscriber=user)` | OK |
| POST `/me/subscription/checkout` | `CheckoutView` | `_get_or_create_customer(request.user)` | OK |
| POST `/me/subscription/cancel` | `CancelSubscriptionView` | `Customer.objects.filter(subscriber=request.user)` | OK |
| GET `/me/invoices` | `InvoiceListView` | `customer.invoices` (filtré sur customer du user) | OK |
| GET `/me/payment-methods` | `PaymentMethodListView` | `PaymentMethod.objects.filter(customer=customer)` | OK |

### `apps/admin_panel`

Toutes les vues exigent `IsAuthenticated + IsAdminUser`. L'IDOR au sens
"un user accède aux données d'un autre" n'est pas le risque ici ; le
risque équivalent serait qu'un non-staff atteigne ces endpoints, ce qui
est bloqué par la permission DRF appliquée systématiquement.

| Endpoint | View | Verdict |
|---|---|---|
| `/admin/*` (toutes routes) | `Admin*View` | OK (gardé par `IsAdminUser`) |

### `apps/gdpr` (livré dans cet audit)

| Endpoint | View | Ownership ? | Verdict |
|---|---|---|---|
| POST `/me/export-data` | `ExportDataView` | Action sur `request.user` uniquement, pas de pk URL | OK |
| GET `/me/export-data/status` | `ExportDataStatusView` | `ExportRequest.objects.filter(user=request.user)` | OK |
| POST `/me/delete-account` | `RequestDeleteAccountView` | Action sur `request.user` uniquement | OK |
| POST `/me/delete-account/cancel` | `CancelDeleteAccountView` | `DeletionRequest.objects.get(user=request.user)` | OK |

## Findings critiques

**Nombre de findings critiques : 0.**

Toutes les vues prenant un `<int:pk>` filtrent correctement par
`request.user` (directement ou via une permission custom). Aucun bug
IDOR n'a été détecté.

Quelques points méritent d'être soulignés comme "à surveiller en cas
d'évolution" sans pour autant constituer un bug actuel :

* `TopicDetailView.get_queryset()` (forum) retourne tous les topics —
  c'est volontaire car la lecture est publique. Mais si on ajoute
  demain un mode "private topics" ou "draft", il faudra ré-auditer
  cette vue car la permission `IsAuthorWithinTimeWindowOrStaff` ne
  filtre qu'au niveau objet (donc lecture toujours OK pour tout le
  monde tant qu'on ne change pas la branche GET).
* `ReplyToggleSolutionView` autorise l'auteur du topic à marquer
  n'importe quelle réponse de son topic comme solution. C'est le
  comportement souhaité ; à ne pas confondre avec un IDOR.
* `SharedProjectView` est intentionnellement public. La sécurité
  repose sur l'entropie du token (`secrets.token_urlsafe(32)` =
  256 bits) — toute évolution qui exposerait le token via un log,
  une URL Sentry, etc. doit être traitée comme un incident.

## Recommandations transversales

Pour tout nouveau endpoint qui prend un ID en URL :

1. **`get_queryset()` doit retourner un filter user-scoped** — sauf
   endpoint publique explicitement marqué (`AllowAny` + commentaire).
   Pattern de référence :

   ```python
   class FooDetailView(generics.RetrieveUpdateDestroyAPIView):
       permission_classes = [IsAuthenticated]

       def get_queryset(self):
           return Foo.objects.filter(user=self.request.user)
   ```

2. **Ne jamais faire `Model.objects.get(pk=kwargs['pk'])` sans
   filter `user=`**. Si on doit utiliser `get_object_or_404`, ajouter
   `user=request.user` comme paramètre obligatoire.

3. **Pour les nested resources** (`/parent/<pk>/child/<child_id>`),
   filtrer sur le parent ET sur l'ID enfant :

   ```python
   def get_queryset(self):
       return Child.objects.filter(
           parent__user=self.request.user,
           parent_id=self.kwargs['pk'],
       )
   ```

4. **Tests IDOR systématiques** : pour chaque DetailView, prévoir un
   test qui crée un objet pour un user A, s'authentifie comme user B,
   tape `GET /resource/<id_de_A>` et attend `404`. Exemple existant :
   `apps/projects/tests/test_projects.py::TestProjectCRUD::test_cannot_access_other_user_project`.

5. **`SerializerSave(user=request.user)` côté création** : c'est le
   serializer / la view qui doit imposer l'auteur, jamais le payload
   client. Vérifier qu'aucun serializer ne laisse passer `user_id` en
   write.

6. **Permissions custom** : préférer un `get_queryset` user-scoped
   plutôt qu'une permission `has_object_permission` seule. Le filtre
   queryset garantit un 404 (= "n'existe pas pour vous") plutôt qu'un
   403 (= "existe, mais tu n'y as pas droit"), ce qui limite les
   fuites d'information.
