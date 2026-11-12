# Probe di liveness e readiness

Probe `/healthz` (liveness) e `/readyz` (readiness) nel chart, e indirizzi
email degli amministratori tolti da `values.yaml`.

## Cosa c'è e dove sta

| Cosa | File |
|---|---|
| Endpoint `/healthz` e `/readyz` | `joursense/app/main.py` |
| Probe nel Deployment | `joursense-helm/templates/deployment.yaml` |
| Parametri delle probe | `joursense-helm/values.yaml` → `app.probes` |
| Email degli admin | Secret `joursense-admin` sul cluster (non nella repo) |

## Probe

### I due endpoint

| Endpoint | Probe | Cosa controlla | Risposta |
|---|---|---|---|
| `/healthz` | liveness | solo che il processo Python risponda | `200 {"status": "ok"}` |
| `/readyz` | readiness | che l'app raggiunga PostgreSQL (`SELECT 1`) | `200 {"status": "ready", ...}` oppure `503 {"status": "not ready", ...}` |

Entrambi non richiedono login: OpenShift li chiama senza cookie.

### Perché due probe diverse

- **Liveness** risponde alla domanda "il processo è bloccato?". Se fallisce, OpenShift
  **riavvia** il container. Per questo `/healthz` **non** controlla il database: se Postgres
  cadesse, riavviare l'app non servirebbe a niente e si finirebbe in un ciclo di riavvii.
- **Readiness** risponde alla domanda "posso mandargli traffico?". Se fallisce, OpenShift
  **toglie il pod dal Service** (niente richieste dalla Route) ma non lo riavvia. Quando
  `/readyz` torna a rispondere `200`, il pod rientra.

Effetti pratici:

- all'avvio un pod riceve traffico solo dopo essersi collegato al database (dopo
  `alembic upgrade head`);
- con più repliche (HPA) i pod nuovi entrano nel bilanciamento solo quando sono pronti: niente
  errori 502 durante lo scale-up e i rolling update;
- se Postgres non è raggiungibile, i pod risultano `0/1` ma restano in esecuzione e tornano
  `1/1` da soli quando il database torna.

### Parametri

In `values.yaml`, configurabili per ambiente:

```yaml
app:
  probes:
    liveness:
      path: /healthz
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readiness:
      path: /readyz
      initialDelaySeconds: 5
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
```

| | liveness | readiness |
|---|---|---|
| Primo controllo dopo l'avvio | 10 s | 5 s |
| Frequenza | ogni 10 s | ogni 5 s |
| Tempo massimo di risposta | 2 s | 2 s |
| Fallimenti consecutivi prima di agire | 3 → riavvio (circa 30 s) | 3 → fuori dal Service (circa 15 s) |

La readiness è più frequente: deve accorgersi presto quando un pod smette o ricomincia a poter
servire traffico.

### Verifica

```bash
oc describe deploy joursense -n joursense-helm | grep -E "Liveness|Readiness"
```

```
Liveness:   http-get http://:8080/healthz delay=10s timeout=2s period=10s #success=1 #failure=3
Readiness:  http-get http://:8080/readyz delay=5s timeout=2s period=5s #success=1 #failure=3
```

Gli endpoint dall'esterno:

```bash
HOST=$(oc get route joursense -n joursense-helm -o jsonpath='{.spec.host}')
curl -sk https://$HOST/healthz      # {"status":"ok"}
curl -sk https://$HOST/readyz       # {"status":"ready","postgres":"ok"}
```

### Prova della readiness senza database

In `joursense-dev`, dove non ci sono dati da proteggere: si spegne Postgres e si osserva l'app.

```bash
oc scale statefulset postgres -n joursense-dev --replicas=0
oc get pods -n joursense-dev -l app=joursense -w
```

Entro circa 15 secondi il pod passa a `0/1` (non ready), **senza riavvii**: la readiness
fallisce, la liveness no. Poi:

```bash
oc scale statefulset postgres -n joursense-dev --replicas=1
```

Quando Postgres è di nuovo pronto, il pod torna `1/1`.

## Email fuori dai values

### Prima

`values.yaml` conteneva gli indirizzi personali degli amministratori:

```yaml
app:
  adminEmails: "...@gmail.com,...@gmail.com"
```

La repo è pubblica: chiunque poteva leggerli.

### Dopo

Gli indirizzi sono in un Secret, creato a mano sul cluster e mai nella repo:

```bash
oc create secret generic joursense-admin -n <namespace> \
  --from-literal=ADMIN_EMAILS="admin1@example.com,admin2@example.com"
```

Il Deployment legge la variabile `ADMIN_EMAILS` dal Secret:

```yaml
        - name: ADMIN_EMAILS
          valueFrom:
            secretKeyRef:
              name: joursense-admin
              key: ADMIN_EMAILS
              optional: true
```

`optional: true`: se il Secret non esiste l'app parte lo stesso, senza amministratori.
Senza, il pod resterebbe bloccato in `CreateContainerConfigError`.

Il Secret va creato in **ogni** namespace in cui gira l'app (`joursense-helm`,
`joursense-dev`, `joursense-prod`) in cui servono amministratori.

### Verifica

```bash
oc get secret joursense-admin -n joursense-helm
```