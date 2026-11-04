# Operatori

Operatori installati tramite OLM con Subscription in YAML, non dalla console web. <br>
I comandi vanno lanciati dalla directory `joursense-ops`

## OpenShift GitOps (Argo CD)

File: `operators/openshift-gitops-subscription.yaml`

Contiene tre oggetti:

| Oggetto       | Nome                        | Namespace                   |
|---------------|-----------------------------|-----------------------------|
| Namespace     | `openshift-gitops-operator` | -                           |
| OperatorGroup | `openshift-gitops-operator` | `openshift-gitops-operator` |
| Subscription  | `openshift-gitops-operator` | `openshift-gitops-operator` |

- **Canale:** `gitops-1.22` (fisso, come Pipelines su `pipelines-1.24`)
- **Catalogo:** `redhat-operators` in `openshift-marketplace`
- **Namespace:** dedicato, `openshift-gitops-operator`; è il default
  da GitOps 1.10 (prima era `openshift-operators`)
- **OperatorGroup:** `spec` vuoto, perché GitOps supporta solo la
  modalità di installazione AllNamespaces

Una volta installato, l'operatore crea automaticamente un'istanza di
default di Argo CD nel namespace `openshift-gitops`.

### Installazione

Richiede l'utenza cluster-admin (l'installazione di un operatore è a
livello di cluster):

```bash
oc apply -f operators/openshift-gitops-subscription.yaml
```

### Verifica

Operatore (il CSV deve essere `Succeeded`):

```bash
oc get csv -n openshift-gitops-operator | grep gitops
```

Istanza di Argo CD (la phase deve essere `Available`):

```bash
oc get argocd openshift-gitops -n openshift-gitops -o jsonpath='{.status.phase}{"\n"}'
```

Pod di Argo CD (devono essere tutti `Running`):

```bash
oc get pods -n openshift-gitops
```

### Console di Argo CD

- **Admin:**
  ```bash
  oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='https://{.spec.host}{"\n"}'
  ```
- **Qualsiasi utente:** console web di OpenShift → menu delle
  applicazioni (icona a griglia, in alto a destra) → **Cluster Argo CD**

Login con **LOG IN VIA OPENSHIFT**. Per default solo i membri
