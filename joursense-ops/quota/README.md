# Quote e limiti di default: ResourceQuota e LimitRange

Una **ResourceQuota** e un **LimitRange** in `joursense-dev` e `joursense-prod`,
con valori diversi per ambiente.

| File | Namespace | Contenuto |
|---|---|---|
| `joursense-ops/quota/quota-dev.yaml` | `joursense-dev` | ResourceQuota `joursense-quota` + LimitRange `joursense-limits` |
| `joursense-ops/quota/quota-prod.yaml` | `joursense-prod` | ResourceQuota `joursense-quota` + LimitRange `joursense-limits` |

## A cosa servono

- **ResourceQuota**: il tetto complessivo del namespace (CPU, memoria, numero di pod, dischi).
  Un pod che farebbe superare il tetto viene rifiutato.
- **LimitRange**: i valori per il singolo container. Assegna requests e limits di default ai
  container che non li dichiarano e fissa un minimo e un massimo.

Servono insieme: con una quota su `limits.cpu` e `limits.memory`, ogni pod **deve** dichiarare
quei valori, altrimenti viene rifiutato. Il LimitRange li compila in automatico per i pod che
non li hanno (per esempio un `oc run` di prova o un pod di debug).

La quota limita i **limits** (il massimo che i pod possono usare). È un tetto, non una
prenotazione: non toglie risorse ad altri namespace.

## Perché non sono nel chart Helm

Il ruolo `admin` del progetto non può creare ResourceQuota e LimitRange: chi è limitato da una
quota non deve poterla modificare. I file vanno quindi applicati da un **cluster-admin**:

```bash
oc apply -f joursense-ops/quota/quota-dev.yaml
oc apply -f joursense-ops/quota/quota-prod.yaml
```

Se fossero nel chart, ogni `helm upgrade` (manuale o della pipeline) fallirebbe con `Forbidden`.


## Valori

### ResourceQuota

| | dev | prod |
|---|---|---|
| `limits.cpu` | 2 | 10 |
| `limits.memory` | 2Gi | 10Gi |
| `pods` | 8 | 16 |
| `persistentvolumeclaims` | 2 | 5 |
| `requests.storage` | 5Gi | 10Gi |

### LimitRange (per container)

| | dev | prod |
|---|---|---|
| Default request (cpu / memoria) | 50m / 64Mi | 100m / 128Mi |
| Default limit (cpu / memoria) | 200m / 256Mi | 500m / 512Mi |
| Max (cpu / memoria) | 1 / 1Gi | 2 / 2Gi |
| Min (cpu / memoria) | 10m / 32Mi | 10m / 32Mi |

Il **max** è sopra il container più grande di ogni ambiente (Postgres: 500m in dev, 1 core in
prod); il **min** è sotto il più piccolo (il job di backup: 64Mi).

## Come sono stati calcolati

La quota deve contenere tutto ciò che può girare **contemporaneamente** nel caso peggiore,
compresi i pod in più del **rolling update**: durante un aggiornamento OpenShift crea i pod
nuovi prima di spegnere i vecchi (`maxSurge: 25%`, arrotondato per eccesso).

### Dev (limits)

| Cosa | Pod | CPU | Memoria |
|---|---|---|---|
| App (HPA spento, 1 replica) | 1 | 250m | 256Mi |
| Pod extra del rolling update | +1 | 250m | 256Mi |
| Postgres | 1 | 500m | 512Mi |
| Pod senza `resources` (default del LimitRange) | 1 | 200m | 256Mi |
| **Totale** | **4** | **1,2** | **1,25Gi** |

Quota: 2 / 2Gi / 8 pod. Storage: 1Gi (database).

### Prod (limits)

| Cosa | Pod | CPU | Memoria |
|---|---|---|---|
| App con HPA al massimo | 5 | 5 | 5Gi |
| Pod extra del rolling update (25% di 5 → 2) | +2 | 2 | 2Gi |
| Postgres | 1 | 1 | 1Gi |
| Job di backup | 1 | 200m | 256Mi |
| Pod di prova di ripristino | 1 | 500m | 512Mi |
| **Totale** | **10** | **8,7** | **~8,75Gi** |

Quota: 10 / 10Gi / 16 pod. Storage: 1Gi (database) + 4Gi (backup) = 5Gi su 10Gi.

I pod della pipeline Tekton girano nel namespace `joursense-helm`, non in dev e prod: non
pesano su queste quote.

## Verifica

### 1. Quota e LimitRange presenti

```bash
for NS in joursense-dev joursense-prod; do
  echo "===== $NS ====="
  oc describe quota -n $NS
  oc describe limitrange -n $NS
done
```

Nella quota, **Used** (uso attuale) deve restare sotto **Hard** (tetto).

### 2. Un pod senza `resources` riceve i default

```bash
oc run test-default --image=registry.access.redhat.com/ubi9/ubi-minimal -n joursense-dev --restart=Never -- sleep 300
oc get pod test-default -n joursense-dev -o jsonpath='{.spec.containers[0].resources}{"\n"}'
oc delete pod test-default -n joursense-dev
```

Risultato:

```
{"limits":{"cpu":"200m","memory":"256Mi"},"requests":{"cpu":"50m","memory":"64Mi"}}
```

### 3. L'app funziona con le quote attive

Le quote si applicano ai pod nuovi: un riavvio verifica che l'app riparta rispettandole.

```bash
oc rollout restart deploy/joursense -n joursense-dev
oc rollout restart deploy/joursense -n joursense-prod
oc rollout status deploy/joursense -n joursense-dev
oc rollout status deploy/joursense -n joursense-prod
oc get pods -n joursense-dev
oc get pods -n joursense-prod
```

Tutti i pod `Running` e `1/1` Ready.

### 4. Spazio per il caso peggiore in prod

HPA al massimo, backup e rolling update insieme:

```bash
# HPA a 5 pod (temporaneo)
oc patch hpa joursense -n joursense-prod -p '{"spec":{"minReplicas":5}}'
oc get pods -n joursense-prod -l app=joursense -w          # 5 pod Running

# backup e rolling update con l'app a 5 pod
oc create job --from=cronjob/postgres-backup backup-quota-test -n joursense-prod
oc rollout restart deploy/joursense -n joursense-prod
oc rollout status deploy/joursense -n joursense-prod

# controllo
oc get jobs -n joursense-prod                               # backup-quota-test Complete 1/1
oc describe quota -n joursense-prod                         # Used sotto Hard
oc get events -n joursense-prod | grep -i "quota" | grep -v backup-quota-test   # nessun output

# ripristino
oc patch hpa joursense -n joursense-prod -p '{"spec":{"minReplicas":2}}'
oc delete job backup-quota-test -n joursense-prod
```

Esito: 5 pod dell'app e Postgres, backup
completato, rolling update concluso, nessun evento di quota superata.

### 5. Un pod oltre i limiti viene rifiutato

Prove in `joursense-dev` (`limits.memory` 2Gi, `max` per container 1 core / 1Gi).

**Container oltre il massimo del LimitRange**: chiede 2 core, il massimo è 1.

```bash
cat <<EOF | oc apply -n joursense-dev -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-troppo-grande
spec:
  containers:
  - name: test
    image: registry.access.redhat.com/ubi9/ubi-minimal
    command: ["sleep", "300"]
    resources:
      limits:
        cpu: "2"
        memory: 256Mi
EOF
```

```
Error from server (Forbidden): ... maximum cpu usage per Container is 1, but limit is 2
```
---