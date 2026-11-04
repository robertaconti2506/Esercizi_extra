# Backup del database (CronJob con pg_dump)

Un CronJob che esegue `pg_dump` del database e salva il file su un PVC separato da
quello di PostgreSQL. La procedura di ripristino è in [`../restore/README.md`](../restore/README.md).

## Cosa c'è e dove sta

Tutto è nel chart, attivato da `backup.enabled`:

| Oggetto | File | Ruolo |
|---|---|---|
| CronJob `postgres-backup` | `joursense-helm/templates/cronjob-backup.yaml` | esegue il backup a orario fisso |
| PVC `postgres-backup` | `joursense-helm/templates/pvc-backup.yaml` | disco dei backup, separato da quello del database |
| NetworkPolicy `allow-backup-egress`, `allow-backup-to-database` | `joursense-helm/templates/networkpolicy-backup.yaml` | aprono il traffico job di backup → Postgres |

## Configurazione

```yaml
backup:
  enabled: true
  pvc:
    name: postgres-backup
    storage: 2Gi
    storageClassName: ""          # vuoto = storage class di default del cluster
  cronjob:
    name: postgres-backup
    schedule: "0 2 * * *"         # ogni notte alle 02:00
    successfulJobsHistoryLimit: 3
    failedJobsHistoryLimit: 3
    mountPath: /backup
    retentionDays: 4
```

| Ambiente | Backup | Note |
|---|---|---|
| `joursense-helm` | attivo | valori di `values.yaml` |
| `joursense-dev` | **disattivato** | `backup.enabled: false` in `values-dev.yaml` |
| `joursense-prod` | attivo | PVC più grande e conservazione più lunga in `values-prod.yaml` |

Lo schedule è in **UTC** (il cluster non usa il fuso italiano): `0 2 * * *` sono le 03:00 in
inverno e le 04:00 in estate.

## Come funziona il job

Il container usa la stessa immagine di PostgreSQL del database
(`registry.redhat.io/rhel9/postgresql-16`), quindi `pg_dump` ha la stessa versione del server.

Le credenziali arrivano dal Secret `postgres-credentials` come variabili standard di
PostgreSQL (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`): `pg_dump` le legge da
solo, senza password sulla riga di comando.

Lo script:

```bash
set -euo pipefail
file="${BACKUP_DIR}/${PGDATABASE}-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --format=custom --file="${file}.tmp"
mv "${file}.tmp" "${file}"
test -s "${file}"
find "${BACKUP_DIR}" -name "${PGDATABASE}-*.dump" -mtime +"${BACKUP_RETENTION_DAYS}" -print -delete
```

| Passo | Perché |
|---|---|
| `set -euo pipefail` | al primo errore lo script si ferma e il Job risulta fallito |
| nome `giornalino-AAAAMMGG-HHMMSS.dump` | un file per esecuzione, ordinabile per data (orario UTC) |
| `--format=custom` | formato binario compresso, si ripristina con `pg_restore` (anche tabella per tabella) |
| scrittura su `.tmp` e poi `mv` | nella cartella non compare mai un backup scritto a metà: se `pg_dump` si interrompe resta solo il `.tmp` |
| `test -s` | se il file è vuoto il Job fallisce invece di risultare `Complete` |
| `find ... -mtime +N -delete` | cancella i backup più vecchi di `retentionDays` giorni, così il PVC non si riempie |

Impostazioni del CronJob:

| Campo | Valore | Effetto |
|---|---|---|
| `concurrencyPolicy` | `Forbid` | se un backup è ancora in corso, quello successivo non parte |
| `backoffLimit` | 2 | in caso di errore il Job riprova fino a 2 volte |
| `restartPolicy` | `Never` | ogni tentativo è un pod nuovo, con i suoi log |
| `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | 3 / 3 | restano gli ultimi 3 Job riusciti e falliti, per controllare i log |
| risorse | 50m / 64Mi richiesti, 200m / 256Mi limite | il job è leggero |

## Il PVC separato

- Il PVC `postgres-backup` è distinto da `postgres-volume-postgres-0` (i dati del database):
  se si perde o si corrompe il disco del database, i backup restano.
- Ha l'annotazione `helm.sh/resource-policy: keep`: con `helm uninstall` Helm **non** lo
  cancella, quindi i backup sopravvivono anche alla rimozione dell'app.
- Con lo storage `lvms-vg1` il PVC resta `Pending` finché il primo job non lo usa: il disco
  viene creato solo quando un pod lo monta (*WaitForFirstConsumer*).

## Rete

Nel namespace c'è `default-deny-all`. Le due NetworkPolicy del backup aprono solo il
necessario:

- `allow-backup-egress`: i pod con label `app: joursense-backup` possono uscire **solo** verso
  Postgres sulla 5432;
- `allow-backup-to-database`: Postgres accetta connessioni dai pod di backup sulla 5432.

## Verifica

```bash
oc get cronjob,pvc -n joursense-helm
```

Il CronJob `postgres-backup` con lo schedule `0 2 * * *` e `SUSPEND False`; il PVC
`postgres-backup` `Bound`.

Backup a mano, senza aspettare la notte:

```bash
oc create job --from=cronjob/postgres-backup backup-manuale -n joursense-helm
oc get jobs -n joursense-helm -w                     # Complete 1/1
oc logs job/backup-manuale -n joursense-helm         # ... Backup completato
```

Il CronJob segnala il job manuale con un evento `UnexpectedJob`: è normale, indica solo un job
che non ha creato lui.

Elenco dei backup sul PVC (montato in sola lettura da un pod temporaneo, come nella procedura
di ripristino):

```bash
oc apply -f joursense-ops/restore/postgres-restore-test.yaml
oc exec postgres-restore-test -- ls -lh /backup
oc delete pod postgres-restore-test
```

Un backup vale solo se si ripristina: la prova di ripristino su un database vuoto è documentata
in [`../restore/README.md`](../restore/README.md).