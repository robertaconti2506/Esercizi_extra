# Ambienti dev e prod di joursense

Due ambienti, `joursense-dev` e `joursense-prod`, installati **dallo stesso chart**
(`joursense-helm/`) con un file di values per ambiente. Il deploy lo fa **Argo CD**: questo
README descrive come sono definiti gli ambienti, [`../argocd/README.md`](../argocd/README.md)
come vengono installati e aggiornati.

## Come è organizzato

```
joursense-helm/
├── templates/          # unico set di template, uguale per tutti gli ambienti
├── values.yaml         # valori di base
├── values-dev.yaml     # solo le differenze per dev
└── values-prod.yaml    # solo le differenze per prod
```

Helm parte da `values.yaml` e sovrascrive **solo le chiavi scritte nel file d'ambiente**. Tutto
il resto (probe, Postgres, Route, NetworkPolicy…) è comune. Non esistono copie del chart: le due
Application di Argo CD puntano alla stessa cartella e cambiano solo il file di values e il
namespace.

| Application | Chart | Values | Namespace | Sync |
|---|---|---|---|---|
| `joursense-dev` | `joursense-helm` | `values-dev.yaml` | `joursense-dev` | automatica |
| `joursense-prod` | `joursense-helm` | `values-prod.yaml` | `joursense-prod` | manuale |

```bash
oc get applications -n openshift-gitops \
  -o custom-columns=NAME:.metadata.name,PATH:.spec.source.path,VALUES:.spec.source.helm.valueFiles,NAMESPACE:.spec.destination.namespace
```

Entrambe mostrano `PATH joursense-helm`: stesso chart, values diversi.

## Differenze tra gli ambienti

| | `values.yaml` (base) | **dev** | **prod** |
|---|---|---|---|
| Repliche app | HPA 1–5 | **1 fissa** (HPA spento) | HPA **2**–5 |
| Risorse app (requests / limits) | 100m, 256Mi / 500m, 512Mi | **50m, 128Mi / 250m, 256Mi** | **200m, 512Mi / 1, 1Gi** |
| Risorse Postgres (requests / limits) | 100m, 256Mi / 500m, 512Mi | come base | **200m, 512Mi / 1, 1Gi** |
| Backup (CronJob + PVC) | attivo, 2Gi, 4 giorni | **assente** | attivo, **4Gi, 7 giorni** |
| Alert (PrometheusRule) | attivo | **assente** | attivo |
| Immagine dell'app | namespace del rilascio | da `joursense-helm` | da `joursense-helm` |
| Tag dell'immagine | `latest` | scritto dall'**Image Updater** | promosso a mano |
| Secret del database | creato dal chart | **creato a parte** | **creato a parte** |

Motivazioni:

- **Dev**: una replica e risorse ridotte bastano per sviluppare e non consumano il cluster.
  Niente backup (i dati di sviluppo non vanno conservati) e niente alert (in sviluppo i pod
  si riavviano spesso, l'alert sarebbe solo rumore). Riceve ogni nuova immagine in automatico.
- **Prod**: più risorse, almeno 2 pod (se uno cade l'altro serve il traffico), backup con più
  spazio e più giorni di conservazione, alert attivo. Una nuova versione arriva solo quando
  qualcuno la promuove.

I file, per intero:

**`values-dev.yaml`**

```yaml
app:
  image:
    namespace: joursense-helm   # l'immagine viene costruita solo li'
    tag: <SHA>                  # aggiornato dall'Image Updater
  autoscaling:
    enabled: false              # una replica fissa (app.replicas: 1 di values.yaml)
  resources:
    limits:   { cpu: 250m, memory: 256Mi }
    requests: { cpu: 50m,  memory: 128Mi }
backup:
  enabled: false
monitoring:
  enabled: false
postgres:
  createSecret: false
```

**`values-prod.yaml`**

```yaml
app:
  image:
    namespace: joursense-helm
  resources:
    limits:   { cpu: "1",  memory: 1Gi }
    requests: { cpu: 200m, memory: 512Mi }
  autoscaling:
    minReplicas: 2
postgres:
  createSecret: false
  resources:
    limits:   { cpu: "1",  memory: 1Gi }
    requests: { cpu: 200m, memory: 512Mi }
backup:
  pvc:
    storage: 4Gi
  cronjob:
    retentionDays: 7
```

Il backup in prod non ha `enabled: true`: è già il valore di `values.yaml`, quindi non è una
differenza.

### Namespace dell'immagine

L'immagine dell'app viene costruita solo nel namespace `joursense-helm` (pipeline Tekton). Nel
Deployment:

```yaml
image: {{ .Values.app.image.registry }}/{{ .Values.app.image.namespace | default .Release.Namespace }}/{{ .Values.app.name }}:{{ .Values.app.image.tag }}
```

- in `values.yaml` `app.image.namespace` è vuoto: il chart cerca l'immagine nel namespace in cui
  viene installato;
- `values-dev.yaml` e `values-prod.yaml` impostano `joursense-helm`: i due ambienti usano
  l'immagine costruita lì.

### Secret del database

Argo CD legge solo ciò che è nella repo, e la password non deve esserci. Per questo in dev e
prod `postgres.createSecret: false`: il chart **non** crea il Secret `postgres-credentials` e
usa quello creato a mano nel namespace (vedi [Prerequisiti](#prerequisiti)). Con
`createSecret: false` il chart non richiede nessuna password.

## Prerequisiti

Una volta sola, prima di creare le Application.

### 1. Namespace

```bash
oc new-project joursense-dev
oc new-project joursense-prod
```

### 2. Permesso di scaricare l'immagine da `joursense-helm`

Di default un namespace non può leggere le immagini di un altro. Da un admin di
`joursense-helm`:

```bash
oc policy add-role-to-group system:image-puller system:serviceaccounts:joursense-dev  -n joursense-helm
oc policy add-role-to-group system:image-puller system:serviceaccounts:joursense-prod -n joursense-helm
```

`system:image-puller` permette solo di scaricare le immagini, non di modificarle.

### 3. Secret di ogni ambiente

```bash
for NS in joursense-dev joursense-prod; do
  oc create secret generic postgres-credentials -n $NS \
    --from-literal=POSTGRESQL_DATABASE=giornalino \
    --from-literal=POSTGRESQL_USER=giornalino \
    --from-literal=POSTGRESQL_PASSWORD='<password diversa per ambiente>'
  oc create secret generic joursense-admin -n $NS \
    --from-literal=ADMIN_EMAILS='<email degli amministratori>'
done
```

PostgreSQL legge la password dal Secret **solo all'avvio**: se la si cambia, va riavviato
(`oc delete pod postgres-0 -n <namespace>`) e poi l'app
(`oc rollout restart deploy/joursense -n <namespace>`).

### 4. Argo CD e limiti di risorse

- label per Argo CD sui namespace, Application e permessi → [`../argocd/README.md`](../argocd/README.md)
- ResourceQuota e LimitRange → [`../quota/README.md`](../quota/README.md)

## Controllo dei template

`helm template` mostra cosa Argo CD applicherà, senza toccare il cluster. Con
`createSecret: false` non serve passare nessuna password.

```bash
helm template joursense ./joursense-helm -n joursense-dev  -f joursense-helm/values-dev.yaml  > /dev/null && echo "dev OK"
helm template joursense ./joursense-helm -n joursense-prod -f joursense-helm/values-prod.yaml > /dev/null && echo "prod OK"
```

Risorse generate per ambiente:

```bash
echo "===== DEV ====="
helm template joursense ./joursense-helm -n joursense-dev -f joursense-helm/values-dev.yaml | grep "^kind:" | sort | uniq -c

echo "===== PROD ====="
helm template joursense ./joursense-helm -n joursense-prod -f joursense-helm/values-prod.yaml | grep "^kind:" | sort | uniq -c
```

In dev non compaiono `CronJob`, `PersistentVolumeClaim` (di backup),
`HorizontalPodAutoscaler`, `PrometheusRule` e `Secret`; in prod compaiono tutti tranne
`Secret`.

## Verifica sul cluster

### Dev

```bash
oc get deploy,hpa,cronjob,pvc -n joursense-dev
oc describe deploy joursense -n joursense-dev | grep -A6 -E "Limits|Replicas"
```

Atteso: `READY 1/1`, `Replicas: 1 desired`, limits `250m` / `256Mi`, requests `50m` / `128Mi`.
HPA e CronJob non devono comparire, e tra i PVC c'è solo `postgres-volume-postgres-0`: in dev
il backup è disattivato.

### Prod

```bash
oc get deploy,hpa,cronjob,pvc,prometheusrule -n joursense-prod
oc describe deploy joursense -n joursense-prod | grep -A6 -E "Limits|Replicas"
```

Atteso: `READY 2/2`, HPA con `MINPODS 2`, limits `1` / `1Gi`, requests `200m` / `512Mi`,
CronJob `postgres-backup` (`0 2 * * *`), PVC `postgres-backup` da 4Gi, PrometheusRule
`joursense-alerts`.

Il PVC `postgres-backup` resta `Pending` finché il CronJob non parte la prima volta: lo
storage `lvms-vg1` crea il disco solo quando un pod lo usa. Per provare subito il backup:

```bash
oc create job --from=cronjob/postgres-backup backup-prova -n joursense-prod
oc get jobs -n joursense-prod -w                  # Complete 1/1
oc get pvc postgres-backup -n joursense-prod      # Bound
oc logs job/backup-prova -n joursense-prod        # ... Backup completato
```

### Nessuna password nei values

```bash
grep -n -i "password" joursense-helm/values*.yaml
```

Compare solo `password: ""` in `values.yaml`, usato soltanto quando il chart crea il Secret
(`createSecret: true`).
