# Changelog

## v1.0.0 – 12 novembre 2026

Prima release di produzione di **Joursense su OpenShift**: tutte le attività dell'esercitazione
sono implementate e verificate sul cluster.

| | |
|---|---|
| Chart Helm `joursense-helm` | `1.0.0` |
| Immagine in prod | `joursense-helm/joursense:3b25c722434a21060e6d0c6ba1ca3f3ca73e4f27` (tag in `values-prod.yaml`) |
| Ambienti | `joursense-dev` (sync automatica), `joursense-prod` (sync manuale) |
| Istruzioni di deploy | [`DEPLOY.md`](DEPLOY.md) |

### Funzionalità

**CI con OpenShift Pipelines**
- Operatore OpenShift Pipelines installato da YAML (canale `pipelines-1.24`).
- Pipeline Tekton `fetch-source` → `test` → `build-push`; immagine taggata con lo SHA del commit.
- Test pytest su `/healthz`: se falliscono, la build non parte.
- ServiceAccount dedicato con permessi minimi, limitati al namespace `joursense-helm`.
- Avvio automatico da webhook GitHub (via smee.io), solo per i push su `main` che modificano
  `joursense/`; firma del webhook verificata.

**Deploy GitOps con Argo CD**
- Operatore OpenShift GitOps installato da YAML (canale `gitops-1.22`).
- Due ambienti dallo stesso chart: `values-dev.yaml` e `values-prod.yaml` contengono solo le
  differenze.
- Application `joursense-dev` con sync automatica, `joursense-prod` con sync manuale.
- Argo CD Image Updater: scrive in Git il tag della nuova immagine per dev e prod.
- Nessuna password nella repo: credenziali in Secret creati a parte.

**Affidabilità e osservabilità**
- Probe di liveness (`/healthz`) e readiness (`/readyz`, controlla anche il database).
- HPA sulla CPU (prod da 2 a 5 pod), verificato con load test.
- Backup notturno del database con `pg_dump` su PVC separato, conservazione 7 giorni in prod.
- Procedura di ripristino verificata su un Postgres vuoto.
- Alert `PodNonReady` (PrometheusRule) e dashboard `joursense` nella console.
- ResourceQuota e LimitRange per dev e prod.
- NetworkPolicy: `default-deny-all` e solo il traffico necessario.

### Modifiche rispetto alle versioni di sviluppo

- La pipeline non fa più il deploy con `helm upgrade`: il deploy è passato ad Argo CD.
- Quota di prod portata da 10 a **12 CPU / 12Gi**: la quota precedente non considerava i pod in
  Terminating durante il rolling update (dettagli in
  [`joursense-ops/quota/`](joursense-ops/quota/README.md)).
- Chart portato alla versione `1.0.0`.
- Aggiunte le istruzioni di deploy complete in [`DEPLOY.md`](DEPLOY.md).

### Problemi noti

- **Più PipelineRun per un solo push**: lo `smee-client` può accumulare connessioni verso smee.io
  e inoltrare lo stesso evento più volte. Le build in parallelo dello stesso commit falliscono al
  push sul registry (errore 500). Si risolve riavviando lo smee-client:
  `oc rollout restart deploy/smee-client -n joursense-helm`.
- **Token GitHub dell'Image Updater** in scadenza il 4 dicembre 2026: va rinnovato, altrimenti
  dev e prod non ricevono più i nuovi tag.
- Il PVC di backup resta `Pending` finché il CronJob non parte la prima volta (comportamento dello
  storage `lvms-vg1`).
