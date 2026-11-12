# Operatori

Operatori installati tramite OLM con Subscription in YAML, non dalla console web. <br>
I comandi vanno lanciati dalla directory `joursense-ops`

## OpenShift Pipelines (Tekton)

File: `operators/openshift-pipelines-subscription.yaml`

Contiene un solo oggetto:

| Oggetto      | Nome                           | Namespace             |
|--------------|--------------------------------|-----------------------|
| Subscription | `openshift-pipelines-operator` | `openshift-operators` |

- **Channel:** `pipelines-1.24` (fisso)
- **Package:** `openshift-pipelines-operator-rh` (diverso dal nome
  della Subscription)
- **CatalogSource:** `redhat-operators` in `openshift-marketplace`
- **Namespace:** `openshift-operators`, già presente nel cluster con il
  suo OperatorGroup globale (`global-operators`): per questo non servono
  né Namespace né OperatorGroup

Una volta installato, l'operatore crea automaticamente il `TektonConfig`
`config` e i componenti di Tekton nel namespace `openshift-pipelines`.

### Installazione

Richiede l'utenza cluster-admin (l'installazione di un operatore è a
livello di cluster):

```bash
oc apply -f operators/openshift-pipelines-subscription.yaml
```

### Verifica

Operatore (il CSV deve essere `Succeeded`):

```bash
oc get csv -n openshift-operators | grep pipelines
```

TektonConfig (la condizione `Ready` deve essere `True`):

```bash
oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
```

Pod di Tekton (devono essere tutti `Running`):

```bash
oc get pods -n openshift-pipelines
```

## OpenShift GitOps (Argo CD)

File: `operators/openshift-gitops-subscription.yaml`

Contiene tre oggetti:

| Oggetto       | Nome                        | Namespace                   |
|---------------|-----------------------------|-----------------------------|
| Namespace     | `openshift-gitops-operator` | -                           |
| OperatorGroup | `openshift-gitops-operator` | `openshift-gitops-operator` |
| Subscription  | `openshift-gitops-operator` | `openshift-gitops-operator` |

- **Channel:** `gitops-1.22` (fisso, come per Pipelines)
- **CatalogSource:** `redhat-operators` in `openshift-marketplace`
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

Login con **LOG IN VIA OPENSHIFT**. Per default solo i membri del gruppo
`cluster-admins` hanno il ruolo `role:admin`; gli altri utenti possono
accedere, ma senza permessi su applicazioni e progetti.

## Note

- `installPlanApproval: Automatic`: il channel è fisso, ma gli
  aggiornamenti minori (z-stream) all'interno del channel vengono
  installati in automatico
- I comandi di verifica su CSV e namespace degli operatori possono
  richiedere anch'essi l'utenza cluster-admin