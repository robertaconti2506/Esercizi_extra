# Ripristino del database joursense da backup

Procedura per ripristinare un backup del CronJob `postgres-backup` su un **database vuoto**
e verificare che i dati coincidano con la produzione.


## Come vengono fatti i backup

| | |
|---|---|
| CronJob | `postgres-backup` (installato dal chart Helm) |
| Comando | `pg_dump --format=custom` (equivale a `-Fc`)
| Destinazione | PVC `postgres-backup` (2Gi, storage `lvms-vg1`), montato su `/backup` |
| Nome dei file | `giornalino-AAAAMMGG-HHMMSS.dump` |

## Principio

Il ripristino si fa su un Postgres **temporaneo e separato** (`postgres-restore-test`),
mai su quello di produzione (`postgres-0`):

- si parte da un database senza tabelle, quindi l'unica fonte dei dati è il file di backup;
- la produzione non corre rischi.

---

## Procedura

### 1. Creare il Postgres vuoto, con il PVC dei backup montato

`joursense-ops/restore/postgres-restore-test.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres-restore-test
  labels:
    app: postgres-restore-test
spec:
  containers:
  - name: postgres
    image: registry.redhat.io/rhel9/postgresql-16:latest
    envFrom:
    - secretRef:
        name: postgres-credentials
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi
    volumeMounts:
    - name: data
      mountPath: /var/lib/pgsql/data
    - name: backup
      mountPath: /backup
      readOnly: true            # il ripristino non deve MAI modificare i backup
  volumes:
  - name: data
    emptyDir: {}                # dati temporanei: spariscono con il pod
  - name: backup
    persistentVolumeClaim:
      claimName: postgres-backup
```

| Scelta | Motivo |
|---|---|
| Pod semplice, non StatefulSet | serve solo per la durata della prova |
| Stessa immagine di produzione (`rhel9/postgresql-16`) | ripristino nella stessa versione di Postgres |
| Dati su `emptyDir` | spariscono con il pod, nessun residuo |
| PVC dei backup in `readOnly` | un errore nei comandi non può danneggiare i backup |
| Label `app: postgres-restore-test` | il Service `postgres` cerca `app: database`: l'app non si collega mai a questo pod |

```bash
oc apply -f joursense-ops/restore/postgres-restore-test.yaml
```


Verifica che il database sia vuoto:

```bash
oc exec postgres-restore-test -- psql -U giornalino -d giornalino -c "\dt"
```

Risultato atteso: `Did not find any relations.`

### 2. Scegliere il backup

```bash
oc exec postgres-restore-test -- ls -lh /backup
```

Per ripristinare un momento preciso si sceglie il file in base al nome.

### 3. Ripristinare

Ultimo backup disponibile:

```bash
oc exec postgres-restore-test -- bash -c '
  ULTIMO=$(ls -t /backup/*.dump | head -1)
  echo "Ripristino da: $ULTIMO"
  pg_restore -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" --no-owner --exit-on-error "$ULTIMO"
  echo "Exit code: $?"
'
```

Per un file specifico, sostituire `$ULTIMO` con il percorso, ad esempio
`/backup/giornalino-20261030-111604.dump`.

| Opzione | Significato |
|---|---|
| `ls -t ... \| head -1` | prende il file più recente; il nome viene stampato e resta nell'output |
| `-d "$POSTGRESQL_DATABASE"` | ripristina nel database vuoto `giornalino` |
| `--no-owner` | crea gli oggetti a nome dell'utente che ripristina, senza reimpostare il proprietario originale |
| `--exit-on-error` | si ferma al primo errore: evita un ripristino a metà che passa inosservato |

Risultato atteso: `Exit code: 0`.

```bash
oc exec postgres-restore-test -- psql -U giornalino -d giornalino -c "\dt"
```

Risultato atteso: 5 tabelle (`alembic_version`, `articoli`, `sessioni`, `tentativi_login`, `utenti`).

### 4. Verificare

Stessa query sui due database:

```bash
# produzione
oc exec postgres-0 -- psql -U giornalino -d giornalino -c "SELECT (SELECT count(*) FROM utenti) AS utenti, (SELECT count(*) FROM articoli) AS articoli, (SELECT count(*) FROM sessioni) AS sessioni, (SELECT version_num FROM alembic_version) AS versione"

# ripristinato
oc exec postgres-restore-test -- psql -U giornalino -d giornalino -c "SELECT (SELECT count(*) FROM utenti) AS utenti, (SELECT count(*) FROM articoli) AS articoli, (SELECT count(*) FROM sessioni) AS sessioni, (SELECT version_num FROM alembic_version) AS versione"
```

Le due righe devono coincidere.

- `alembic_version` contiene il numero dell'ultima migrazione applicata (Alembic). Deve essere
  uguale: se mancasse, all'avvio l'app proverebbe a ricreare tabelle già esistenti e non partirebbe.
- Il backup è una fotografia del momento in cui è stato fatto. Se nel frattempo l'app è stata
  usata, la produzione può avere **sessioni** in più o **letture** più alte: sono differenze
  attese, non errori.


### 5. Pulizia

```bash
oc delete pod postgres-restore-test
```

Il PVC `postgres-backup` non viene toccato: il pod lo montava in sola lettura.

---