# Ambienti dev e prod di joursense

Due ambienti, `joursense-dev` e `joursense-prod`, installati **dallo stesso chart**
(`joursense-helm/`) con un file di values per ambiente.

## Come è organizzato

```
joursense-helm/
├── templates/          # unico set di template, uguale per tutti gli ambienti
├── values.yaml         # valori di base
├── values-dev.yaml     # solo le differenze per dev
└── values-prod.yaml    # solo le differenze per prod
```

Helm parte da `values.yaml` e, con `-f values-<ambiente>.yaml`, sovrascrive **solo le chiavi
scritte nel file d'ambiente**. Tutto il resto (probe, Postgres, Route, NetworkPolicy…) è
comune. Non esistono copie del chart: cambiano solo il namespace (`-n`) e il file di
values (`-f`).

```bash
helm list -A        # stesso chart joursense-helm-0.1.0 in joursense-dev e joursense-prod
```

## Differenze tra gli ambienti

| | `values.yaml` (base) | **dev** | **prod** |
|---|---|---|---|
| Repliche app | HPA 1–5 | **1 fissa** (HPA spento) | HPA **2**–5 |
| Risorse app (requests / limits) | 100m, 256Mi / 500m, 512Mi | **50m, 128Mi / 250m, 256Mi** | **200m, 512Mi / 1, 1Gi** |
| Risorse Postgres (requests / limits) | 100m, 256Mi / 500m, 512Mi | come base | **200m, 512Mi / 1, 1Gi** |
| Backup (CronJob + PVC) | attivo, 2Gi, 4 giorni | **assente** | attivo, **4Gi, 7 giorni** |
| Alert (PrometheusRule) | attivo | **assente** | attivo |
| Immagine dell'app | namespace del rilascio | da `joursense-helm` | da `joursense-helm` |

Motivazioni:

- **Dev**: una replica e risorse ridotte bastano per sviluppare e non consumano il cluster.
  Niente backup (i dati di sviluppo non vanno conservati) e niente alert (in sviluppo i pod
  si riavviano spesso, l'alert sarebbe solo rumore).
- **Prod**: più risorse, almeno 2 pod (se uno cade l'altro serve il traffico), backup con più
  spazio e più giorni di conservazione, alert attivo.

### Namespace dell'immagine

L'immagine dell'app viene costruita solo nel namespace `joursense-helm`. Nel Deployment:

```yaml
image: {{ .Values.app.image.registry }}/{{ .Values.app.image.namespace | default .Release.Namespace }}/{{ .Values.app.name }}:{{ .Values.app.image.tag }}
```

- in `values.yaml` `app.image.namespace` è vuoto, quindi il chart cerca l'immagine nel namespace
  in cui viene installato (comportamento di prima, invariato per `joursense-helm`);
- `values-dev.yaml` e `values-prod.yaml` impostano `app.image.namespace: joursense-helm`, quindi
  i due ambienti usano l'immagine costruita lì.

Per questo dev e prod vanno installati **sempre** con il proprio `-f`: senza, il chart
cercherebbe l'immagine in `joursense-dev` o `joursense-prod`, dove non esiste.

## Prerequisiti (una volta sola)

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

### 3. Permesso sulle PrometheusRule in prod

L'alert è attivo solo in prod. Il ruolo `admin` del progetto non include il monitoring:
da un cluster-admin:

```bash
oc adm policy add-role-to-user monitoring-rules-edit <utente> -n joursense-prod
```

In dev non serve (`monitoring.enabled: false`).

## Installazione e aggiornamento

La password del database **non è nei file di values**: si passa con `--set`. Usare una
password diversa per ogni ambiente.

```bash
# dev
helm upgrade --install joursense ./joursense-helm \
  -n joursense-dev \
  -f joursense-helm/values-dev.yaml \
  --set postgres.password='<password-dev>'

# prod
helm upgrade --install joursense ./joursense-helm \
  -n joursense-prod \
  -f joursense-helm/values-prod.yaml \
  --set postgres.password='<password-prod>'
```

- `upgrade --install` installa se il rilascio non esiste, altrimenti lo aggiorna.
- Il rilascio si chiama `joursense` in entrambi: Helm tiene i rilasci separati per namespace.
- Per gli aggiornamenti successivi si può usare `--reset-then-reuse-values` al posto di
  `--set postgres.password=...`: riprende la password dell'ultimo rilascio.

### Controllo dei template

```bash
helm template joursense ./joursense-helm -n joursense-dev  -f joursense-helm/values-dev.yaml  --set postgres.password=x > /dev/null && echo "dev OK"
helm template joursense ./joursense-helm -n joursense-prod -f joursense-helm/values-prod.yaml --set postgres.password=x > /dev/null && echo "prod OK"

# risorse generate per ambiente
echo "===== DEV ====="
helm template joursense ./joursense-helm -n joursense-dev -f joursense-helm/values-dev.yaml --set postgres.password=x | grep "^kind:" | sort | uniq -c

echo "===== PROD ====="
helm template joursense ./joursense-helm -n joursense-prod -f joursense-helm/values-prod.yaml --set postgres.password=x | grep "^kind:" | sort | uniq -c
```

In dev non devono comparire `CronJob`, `PersistentVolumeClaim` (di backup),
`HorizontalPodAutoscaler` e `PrometheusRule`; in prod sì.

## Verifica sul cluster

### Dev

```bash
oc get deploy,hpa,cronjob,pvc -n joursense-dev
oc describe deploy joursense -n joursense-dev | grep -A6 -E "Limits|Replicas"
```

Atteso: `READY 1/1`, `Replicas: 1 desired`, limits `250m` / `256Mi`, requests `50m` / `128Mi`;
nessun HPA, nessun CronJob, solo il PVC del database.

### Prod

```bash
oc get deploy,hpa,cronjob,pvc,prometheusrule -n joursense-prod
oc describe deploy joursense -n joursense-prod | grep -A6 -E "Limits|Replicas"
```

Atteso: `READY 2/2`, HPA con `MINPODS 2`, limits `1` / `1Gi`, requests `200m` / `512Mi`,
CronJob `postgres-backup` (`0 2 * * *`), PVC `postgres-backup` da 5Gi, PrometheusRule
`joursense-alerts`.

Il PVC `postgres-backup` resta `Pending` finché il CronJob non parte la prima volta: lo
storage `lvms-vg1` crea il disco solo quando un pod lo usa. Per provare subito il backup:

```bash
oc create job --from=cronjob/postgres-backup backup-prova -n joursense-prod
oc get jobs -n joursense-prod -w                  # Complete 1/1
oc get pvc postgres-backup -n joursense-prod      # Bound
oc logs job/backup-prova -n joursense-prod        # ... Backup completato
```
