# Istruzioni di deploy – Joursense v1.1.0

Questa guida installa Joursense **da zero** su un cluster OpenShift: CI con Tekton, deploy
GitOps con Argo CD, ambienti `joursense-dev` e `joursense-prod`.
I passi vanno eseguiti **in ordine**: ogni blocco usa ciò che crea il precedente.

Le spiegazioni (perché una scelta, come funziona un componente) sono nei README delle cartelle,
indicati in ogni passo. Qui ci sono solo i comandi e le verifiche.

## Cosa si installa

| Componente | Versione |
|---|---|
| Chart Helm `joursense-helm` | `1.1.0` |
| OpenShift Pipelines (Tekton) | canale `pipelines-1.24` |
| OpenShift GitOps (Argo CD + Image Updater) | canale `gitops-1.22` |
| Immagine dell'app | tag = SHA del commit, costruita dalla pipeline |

## Prerequisiti

- Cluster OpenShift con accesso **cluster-admin** (per la parte A) e un'utenza normale del team
  (per la parte B).
- Storage class predefinita che crei i PVC (sul nostro cluster `lvms-vg1`).
- Sul proprio PC: `oc`, `helm` (solo per il controllo dei template), `git`.
- Accesso da **admin** alla repo GitHub (per webhook e token).
- Clone della repo, sul tag della release:
  ```bash
  git clone https://github.com/robertaconti2506/Esercizi_extra.git
  cd Esercizi_extra
  git checkout v1.1.0
  ```

**Tutti i comandi vanno lanciati dalla root della repo.**

Valori da preparare prima di iniziare (non sono nella repo):

| Valore | Dove si usa |
|---|---|
| Password del database, una diversa per dev e prod | Secret `postgres-credentials` |
| Email degli amministratori dell'app | Secret `joursense-admin` |
| Segreto condiviso del webhook (stringa casuale) | Secret `github-webhook-secret` e webhook GitHub |
| Token GitHub fine-grained (solo questa repo, Contents: Read and write) | Secret `git-creds-joursense` |
| URL di un canale smee.io (https://smee.io → *Start a new channel*) | `smee-client.yaml` e webhook GitHub |

---

## Parte A – Cluster-admin (una volta sola)

### A1. Operatori

→ [`joursense-ops/operators/`](joursense-ops/operators/README.md)

```bash
oc apply -f joursense-ops/operators/openshift-pipelines-subscription.yaml
oc apply -f joursense-ops/operators/openshift-gitops-subscription.yaml
```

Verifica (può servire qualche minuto):

```bash
oc get csv -n openshift-operators | grep pipelines                 # Succeeded
oc get csv -n openshift-gitops-operator | grep gitops              # Succeeded
oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
oc get argocd openshift-gitops -n openshift-gitops -o jsonpath='{.status.phase}{"\n"}'          # Available
```

### A2. Image Updater

```bash
oc patch argocd openshift-gitops -n openshift-gitops --type merge \
  -p '{"spec":{"imageUpdater":{"enabled":true}}}'

oc get pods -n openshift-gitops | grep image-updater               # Running
```

### A3. Monitoring dei progetti utente e dashboard

→ [`joursense-ops/monitoring/`](joursense-ops/monitoring/README.md)

```bash
oc apply -f joursense-ops/monitoring/cluster-monitoring-config.yaml
oc apply -f joursense-ops/monitoring/dashboard-joursense.yaml

oc get pods -n openshift-user-workload-monitoring                  # prometheus-*, thanos-ruler-* Running
```

### A4. Namespace

```bash
oc new-project joursense-helm
oc new-project joursense-dev
oc new-project joursense-prod

# Argo CD può gestire solo dev e prod
oc label namespace joursense-dev  argocd.argoproj.io/managed-by=openshift-gitops
oc label namespace joursense-prod argocd.argoproj.io/managed-by=openshift-gitops

# dev e prod possono scaricare l'immagine costruita in joursense-helm
oc policy add-role-to-group system:image-puller system:serviceaccounts:joursense-dev  -n joursense-helm
oc policy add-role-to-group system:image-puller system:serviceaccounts:joursense-prod -n joursense-helm
```

### A5. Permessi del team

→ [`joursense-ops/argocd/`](joursense-ops/argocd/README.md#permessi-per-lutenza-normale)

```bash
# gruppo del team (aggiungere gli utenti)
oc adm groups new joursense-team <utente1> <utente2>

# accesso ai namespace
oc adm policy add-role-to-group admin joursense-team -n joursense-helm
oc adm policy add-role-to-group edit  joursense-team -n joursense-dev
oc adm policy add-role-to-group edit  joursense-team -n joursense-prod
oc adm policy add-role-to-group monitoring-rules-edit joursense-team -n joursense-helm

# creare e modificare le Application di Argo CD
oc create role joursense-argocd-apps -n openshift-gitops \
  --verb=get,list,watch,create,update,patch,delete --resource=applications.argoproj.io
oc create rolebinding joursense-argocd-apps -n openshift-gitops \
  --role=joursense-argocd-apps --group=joursense-team

# permessi dentro Argo CD (console e Sync)
oc patch argocd openshift-gitops -n openshift-gitops --type merge -p '
spec:
  rbac:
    policy: |
      g, system:cluster-admins, role:admin
      g, cluster-admins, role:admin
      p, role:joursense, applications, *, default/*, allow
      g, joursense-team, role:joursense
'
```

### A6. ResourceQuota e LimitRange

→ [`joursense-ops/quota/`](joursense-ops/quota/README.md)

```bash
oc apply -f joursense-ops/quota/quota-dev.yaml
oc apply -f joursense-ops/quota/quota-prod.yaml

oc describe quota -n joursense-prod                                # Hard: limits.cpu 12, limits.memory 12Gi
```

### A7. ServiceAccount della pipeline e dell'EventListener

→ [`joursense-ops/tekton/`](joursense-ops/tekton/README.md#4-serviceaccount-dedicato-con-permessi-minimi)

```bash
oc apply -f joursense-ops/tekton/serviceaccount-pipeline.yaml
oc apply -f joursense-ops/tekton/eventlistener-sa.yaml

SA=system:serviceaccount:joursense-helm:pipeline-service-account
oc auth can-i update imagestreams/layers -n joursense-helm --as=$SA   # yes
oc auth can-i create deployments -n joursense-prod --as=$SA           # no
```

### A8. Credenziali dell'Image Updater

→ [`joursense-ops/argocd/`](joursense-ops/argocd/README.md#setup)

Lettura del registry interno:

```bash
oc create serviceaccount image-updater-registry -n openshift-gitops
oc policy add-role-to-user system:image-puller \
  system:serviceaccount:openshift-gitops:image-updater-registry -n joursense-helm
oc apply -f joursense-ops/argocd/image-updater-registry-token.yaml

TOKEN=$(oc get secret image-updater-registry-token -n openshift-gitops -o jsonpath='{.data.token}' | base64 -d)
oc create secret docker-registry image-updater-registry-pull -n openshift-gitops \
  --docker-server=image-registry.openshift-image-registry.svc:5000 \
  --docker-username=image-updater-registry \
  --docker-password="$TOKEN"
```

Il registry interno deve essere dichiarato nella ConfigMap `argocd-image-updater-config`
(creata dall'operatore):

```bash
oc get configmap argocd-image-updater-config -n openshift-gitops -o yaml
```

Commit su GitHub (token fine-grained preparato prima):

```bash
oc create secret generic git-creds-joursense -n openshift-gitops \
  --from-literal=username=<utente GitHub> \
  --from-literal=password='<token GitHub>'
```

> Il token ha una scadenza: quando scade, l'Image Updater non riesce più a fare commit e dev
> smette di aggiornarsi. Va rigenerato e il Secret va ricreato.

Regola dell'Image Updater, solo per dev (scrive sul branch `dev`; prod si aggiorna con il merge su `main`):

```bash
oc apply -f joursense-ops/argocd/imageupdater-dev.yaml
oc get imageupdater -n openshift-gitops                            # joursense-dev
```

---

## Parte B – Team (utenza normale)

### B1. Secret degli ambienti

```bash
for NS in joursense-dev joursense-prod; do
  oc create secret generic postgres-credentials -n $NS \
    --from-literal=POSTGRESQL_DATABASE=giornalino \
    --from-literal=POSTGRESQL_USER=giornalino \
    --from-literal=POSTGRESQL_PASSWORD='<password diversa per ambiente>'
  oc create secret generic joursense-admin -n $NS \
    --from-literal=ADMIN_EMAILS='<email degli amministratori>'
done

oc create secret generic github-webhook-secret -n joursense-helm \
  --from-literal=secretToken='<segreto del webhook>'
```

### B2. Pipeline e trigger

→ [`joursense-ops/tekton/`](joursense-ops/tekton/README.md)

Se si usa un canale smee.io nuovo, sostituire prima l'URL in
`joursense-ops/tekton/smee-client.yaml` (argomento `-u`).

```bash
oc apply -f joursense-ops/tekton/task-run-tests.yaml
oc apply -f joursense-ops/tekton/pipeline.yaml
oc apply -f joursense-ops/tekton/triggerbinding.yaml
oc apply -f joursense-ops/tekton/triggertemplate.yaml
oc apply -f joursense-ops/tekton/eventlistener.yaml
oc apply -f joursense-ops/tekton/smee-client.yaml
oc apply -f joursense-ops/tekton/networkpolicy-webhook.yaml
```

Verifica:

```bash
oc get eventlistener github-listener -n joursense-helm             # AVAILABLE True
oc get pods -n joursense-helm | grep -E "el-github-listener|smee-client"   # Running, un solo smee-client
```

### B3. Webhook su GitHub

Nella repo: *Settings → Webhooks → Add webhook*.

| Campo | Valore |
|---|---|
| Payload URL | URL del canale smee.io (lo stesso di `smee-client.yaml`) |
| Content type | `application/json` |
| Secret | lo stesso del Secret `github-webhook-secret` |
| Eventi | *Just the push event* |

### B4. Prima build dell'immagine

Avvio manuale della pipeline sul tag della release:

```bash
cat <<EOF | oc create -n joursense-helm -f -
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: joursense-pipeline-run-manuale-
spec:
  pipelineRef:
    name: joursense-pipeline
  taskRunTemplate:
    serviceAccountName: pipeline-service-account
  params:
    - name: git-url
      value: https://github.com/robertaconti2506/Esercizi_extra.git
    - name: git-revision
      value: v1.1.0
    - name: image
      value: image-registry.openshift-image-registry.svc:5000/joursense-helm/joursense
  workspaces:
    - name: source
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 1Gi
EOF

oc get pipelinerun -n joursense-helm -w                            # Succeeded
oc get istag -n joursense-helm | grep joursense                    # joursense:<SHA>
```

### B5. Controllo dei template (facoltativo)

```bash
helm template joursense ./joursense-helm -n joursense-dev  -f joursense-helm/values-dev.yaml  > /dev/null && echo "dev OK"
helm template joursense ./joursense-helm -n joursense-prod -f joursense-helm/values-prod.yaml > /dev/null && echo "prod OK"
```

### B6. Deploy con Argo CD

→ [`joursense-ops/argocd/`](joursense-ops/argocd/README.md)

Dev segue il branch `dev`, prod il branch `main`:

| | Branch | Tag in Git | Applicazione al cluster |
|---|---|---|---|
| dev | `dev` | Image Updater (automatico, commit su `dev`) | Argo CD, automatica |
| prod | `main` | scritto a mano in `values-prod.yaml`, arriva con la PR `dev` → `main` | Argo CD, solo dopo il **Sync** manuale |

**Dev**:

```bash
oc apply -f joursense-ops/argocd/application-dev.yaml
oc get applications -n openshift-gitops                            # joursense-dev Synced / Healthy
```

**Prod**:

```bash
oc apply -f joursense-ops/argocd/application-prod.yaml
oc get applications -n openshift-gitops                            # joursense-prod OutOfSync
```

1. Sul branch `dev`, dopo `git pull`, copiare in `values-prod.yaml` il tag che si trova in
   `values-dev.yaml`; commit e push.
2. Su GitHub aprire la PR `dev` → `main` e fare il merge.
3. Nella console di Argo CD (eventualmente dopo **REFRESH**) controllare le differenze con **App Diff**.
4. **SYNC → SYNCHRONIZE**.

Console di Argo CD: *console OpenShift → menu applicazioni → Cluster Argo CD*, login con
**LOG IN VIA OPENSHIFT**.

---

## Verifica finale

```bash
# Application
oc get applications -n openshift-gitops                            # entrambe Synced / Healthy

# Dev: 1 replica, niente HPA e backup
oc get deploy,hpa,cronjob,pvc -n joursense-dev

# Prod: HPA 2-5, backup notturno, alert
oc get deploy,hpa,cronjob,pvc,prometheusrule -n joursense-prod

# Immagine in uso
oc get deploy joursense -n joursense-dev  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
oc get deploy joursense -n joursense-prod -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# App raggiungibile
oc get route -n joursense-dev
oc get route -n joursense-prod
```

Primo backup di prova (il PVC di backup resta `Pending` finché un job non lo usa):

```bash
oc create job --from=cronjob/postgres-backup backup-prova -n joursense-prod
oc get jobs -n joursense-prod -w                                   # Complete 1/1
oc logs job/backup-prova -n joursense-prod                         # ... Backup completato
oc delete job backup-prova -n joursense-prod
```

Flusso CI/CD completo: un push su `dev` che modifica `joursense/` deve creare **una sola**
PipelineRun, poi il commit dell'Image Updater su `values-dev.yaml` (branch `dev`) e
l'aggiornamento automatico di dev; prod resta **Synced** sulla versione precedente. Dopo la PR
`dev` → `main` con il nuovo tag in `values-prod.yaml`, prod va in **OutOfSync** fino al Sync.

---

## Operazioni dopo il deploy

| Operazione | Come |
|---|---|
| Nuova versione in dev | push su `dev` in `joursense/`: automatico |
| Nuova versione in prod | sul branch `dev` si copia in `values-prod.yaml` il tag di `values-dev.yaml`, PR `dev` → `main`, merge; si controlla con **App Diff** e si applica con **Sync** |
| Modifica di configurazione | modifica di values o template sul branch `dev`, push; dev si aggiorna da solo, prod dopo la PR su `main` e il **Sync** |
| Rollback in prod | in `values-prod.yaml` si rimette il tag precedente (o `git revert <commit>`), PR `dev` → `main`, poi **Sync** |

Si lavora sempre sul branch `dev`: su `main` le modifiche arrivano solo con una PR.
L'Image Updater fa commit su `dev`: prima di lavorare in locale fare sempre `git pull`.