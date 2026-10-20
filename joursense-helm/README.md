# joursense-helm

Chart Helm per installare **joursense** su OpenShift: l'applicazione web, il suo database PostgreSQL e la build dell'immagine a partire dal codice su Git.
Per l'architettura completa del progetto **joursense** visitare questa repo: https://github.com/robertaconti2506/Esercizi_extra/tree/main/joursense

## Cosa installa

| Risorsa | Nome (default) | A cosa serve |
|---|---|---|
| BuildConfig | `joursense` | Builda l'immagine dell'app dal repo Git usando il `Containerfile` |
| ImageStream | `joursense` | Contiene l'immagine prodotta dalla build (`joursense:latest`) |
| Deployment | `joursense` | L'applicazione, in ascolto sulla porta 8080 |
| Service | `joursense` | Espone l'app dentro il cluster |
| Route | `joursense` | Espone l'app all'esterno in HTTPS |
| StatefulSet | `postgres` | Il database PostgreSQL 16, con disco persistente |
| Service | `postgres` | Espone il database all'app |
| Secret | `postgres-credentials` | Nome del database, utente e password |
| NetworkPolicy | 6 policy | Bloccano tutto il traffico tranne quello necessario |

```
Browser ──HTTPS──▶ Route ──▶ Service joursense ──▶ Pod joursense ──▶ Service postgres ──▶ Pod postgres
                                                        ▲                                    │
                                     ImageStream ◀── BuildConfig (GitHub)                 PVC 1Gi
```

## Struttura del chart

```
joursense-helm/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── buildconfig.yaml
    ├── imagestream.yaml
    ├── deployment.yaml
    ├── service-app.yaml
    ├── route.yaml
    ├── statefulset.yaml
    ├── service-postgres.yaml
    ├── secret.yaml
    └── networkpolicy.yaml
```

## Installazione

La password del database **non è nel chart**: va passata a ogni installazione o aggiornamento.

```bash
oc project joursense-helm


helm install joursense joursense-helm -n joursense-helm --set postgres.password=LaTuaPassword
```


## Operazioni comuni

**Aggiornare dopo una modifica al chart o ai values**

```bash
helm upgrade joursense ./joursense-helm -n joursense-helm --set postgres.password=LaTuaPassword
```

Usa sempre **la stessa password** dell'installazione: Postgres crea l'utente solo al primo avvio, quindi cambiarla nel Secret rompe il collegamento tra app e database.
- Il chart non contiene password: è pensato per essere condiviso e versionato su Git.
- La password vive solo nel Secret dentro il progetto, leggibile da chi ha accesso al progetto.

**Ribuildare l'app dopo un push sul repo**

La build parte da sola solo alla prima installazione. Dopo, va lanciata a mano:

```bash
oc start-build joursense -n joursense-helm
```

Al termine della build il Deployment si aggiorna da solo.

**Tornare alla versione precedente**

```bash
helm rollback joursense <revisione> -n joursense-helm
```

**Disinstallare**

```bash
helm uninstall joursense -n joursense-helm
```

Il disco del database **non viene cancellato** (`persistentVolumeClaimRetentionPolicy: Retain`), così i dati sopravvivono a una reinstallazione. Per eliminarlo davvero:

```bash
oc delete pvc postgres-volume-postgres-0 -n joursense-helm
```

**Controllare il chart prima di installare**

```bash
helm lint ./joursense-helm --set postgres.password=test
helm template prova ./joursense-helm --set postgres.password=test
```

## Parametri (`values.yaml`)

Ogni valore si può sovrascrivere con `--set chiave=valore` o con un file passato con `-f`.

### Applicazione

| Chiave | Default | Descrizione |
|---|---|---|
| `app.name` | `joursense` | Nome di Deployment, Service, Route, BuildConfig, ImageStream e label `app` |
| `app.replicas` | `1` | Numero di pod dell'app |
| `app.port` | `8080` | Porta su cui ascolta l'app |
| `app.adminEmails` | *(3 indirizzi)* | Email degli amministratori, separate da virgola (variabile `ADMIN_EMAILS`) |
| `app.image.registry` | `image-registry.openshift-image-registry.svc:5000` | Registry interno di OpenShift |
| `app.image.tag` | `latest` | Tag dell'immagine prodotta dalla build |
| `app.image.pullPolicy` | `Always` | Politica di download dell'immagine |
| `app.resources.limits.cpu` | `500m` | CPU massima |
| `app.resources.limits.memory` | `512Mi` | Memoria massima |
| `app.resources.requests.cpu` | `100m` | CPU garantita |
| `app.resources.requests.memory` | `256Mi` | Memoria garantita |

### Build

| Chiave | Default | Descrizione |
|---|---|---|
| `build.gitUri` | `https://github.com/robertaconti2506/Esercizi_extra.git` | Repository del codice |
| `build.gitRef` | `""` | Branch o tag; vuoto = branch di default |
| `build.contextDir` | `/joursense` | Sottocartella del repo con il codice dell'app |
| `build.dockerfilePath` | `Containerfile` | File di build dentro `contextDir` |

### Database

| Chiave | Default | Descrizione |
|---|---|---|
| `postgres.name` | `postgres` | Nome di StatefulSet e Service; è anche il valore di `DB_HOST` |
| `postgres.label` | `database` | Label `app` dei pod del database |
| `postgres.port` | `5432` | Porta di PostgreSQL |
| `postgres.secretName` | `postgres-credentials` | Secret da cui app e database leggono le credenziali |
| `postgres.image` | `registry.redhat.io/rhel9/postgresql-16:latest` | Immagine PostgreSQL |
| `postgres.pullPolicy` | `Always` | Politica di download dell'immagine |
| `postgres.storage` | `1Gi` | Dimensione del disco. **Non modificabile dopo l'installazione** |
| `postgres.database` | `giornalino` | Nome del database creato al primo avvio |
| `postgres.user` | `giornalino` | Utente del database |
| `postgres.password` | `""` | **Obbligatoria**, da passare con `--set`. Non scriverla in questo file |
| `postgres.resources.*` | come l'app | Limiti e richieste di CPU e memoria |

### Route

| Chiave | Default | Descrizione |
|---|---|---|
| `route.host` | `""` | Hostname pubblico; vuoto = generato da OpenShift |
| `route.tls.termination` | `edge` | L'HTTPS termina sul router di OpenShift |
| `route.tls.insecureEdgeTerminationPolicy` | `Redirect` | Le richieste HTTP vengono rediritte su HTTPS |

## NetworkPolicy

Il progetto parte da "blocca tutto" e apre solo il traffico necessario:

| Policy | Permette |
|---|---|
| `default-deny-all` | niente: blocca tutto il traffico in entrata e in uscita |
| `allow-dns-egress` | a tutti i pod di usare il DNS del cluster |
| `allow-router-to-app` | al router di OpenShift di raggiungere l'app sulla porta 8080 |
| `allow-app-egress` | all'app di uscire solo verso il database (5432) |
| `allow-app-to-database` | al database di ricevere connessioni solo dall'app (5432) |
| `allow-build-egress` | ai pod di build di uscire ovunque (GitHub, immagini base) |