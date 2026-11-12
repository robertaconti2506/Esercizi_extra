# Deploy di joursense gestito da Argo CD (GitOps)

Questo documento descrive come il deploy di joursense negli ambienti dev e prod è gestito da Argo CD (Red Hat OpenShift GitOps).

Riferimento: issue **#14 – Deploy gestito da Argo CD**.

---

## Obiettivo

Prima di questa issue il deploy avveniva con `helm upgrade`, lanciato a mano oppure dall'ultimo passo della pipeline Tekton. <br>
Questo approccio ha alcuni limiti:

- lo stato del cluster dipende da chi ha lanciato il comando e con quali parametri;
- se qualcuno modifica una risorsa a mano, nessuno se ne accorge;
- non c'è un punto unico che descriva come dovrebbe essere ogni ambiente.

Con GitOps, il repository Git diventa l'unica fonte di verità: il chart e i file di values descrivono lo stato desiderato, e Argo CD si occupa di renderlo reale sul cluster, confrontando continuamente Git con ciò che gira davvero.

Requisiti dell'issue:

- Argo CD gestisce il deploy;
- sincronizzazione automatica per dev;
- sincronizzazione manuale per prod;
- il deploy non avviene più con `helm upgrade`, né a mano né dalla pipeline;
- le password restano in Secret creati a parte, non nel repository.

---

## Il flusso completo

```
 sviluppatore
     │  push di codice su main (cartella joursense/)
     ▼
 GitHub ──webhook (smee)──► EventListener Tekton
                               │  filtro: parte solo se cambia joursense/
                               ▼
                         Pipeline Tekton
                         clone → test → build
                               │  push immagine con tag = SHA del commit
                               ▼
              registry interno: joursense-helm/joursense:<sha>
                               │
                               ▼
                     Argo CD Image Updater
                     (controlla il registry ogni 2 minuti)
                               │  commit su GitHub: app.image.tag = <sha>
                               ▼
                 GitHub: joursense-helm/values-dev.yaml
                               │
                               ▼
                           Argo CD
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
   joursense-dev                           joursense-prod
   sync AUTOMATICA                         sync MANUALE
   (prune + selfHeal)                      (resta OutOfSync finché
                                            non si preme Sync)
```

Divisione dei compiti:

| Componente | Ruolo |
|---|---|
| **Tekton** (CI) | Testa il codice e costruisce l'immagine. Non fa più deploy. |
| **Image Updater** | Si accorge della nuova immagine e scrive il nuovo tag in Git, solo per dev. |
| **Argo CD** (CD) | Applica al cluster ciò che è descritto in Git. |
| **Persona** | Decide quando portare una versione in prod. |


## Le Application di Argo CD

Un'Application dice ad Argo CD: da quale repository e cartella prendere il chart, con quale file di values, e in quale namespace applicarlo.

Entrambe le Application usano **lo stesso chart** (`joursense-helm`); cambiano solo il file di values e il namespace di destinazione. Così una correzione ai template vale per entrambi gli ambienti, e le differenze tra dev e prod stanno solo nei rispettivi values.


### Perché automatica in dev e manuale in prod

- **Dev** è l'ambiente in cui si prova: si vuole vedere subito ogni modifica, e un errore ha conseguenze limitate.
- **Prod** è l'ambiente usato davvero: una modifica deve passare prima da dev e poi essere portata in prod con una decisione consapevole, scegliendo anche *quando* farlo. Senza `syncPolicy`, Argo CD rileva la differenza (stato **OutOfSync**) ma non la applica finché qualcuno non preme **Sync**.

---

## Modifiche al chart Helm

### Secret del database opzionale (`createSecret`)

In precedenza il chart creava sempre il Secret `postgres-credentials`, con la password passata al momento del `helm upgrade` (`--set postgres.password=...`).

Con Argo CD questo non è più possibile: Argo CD legge solo ciò che è nel repository, e la password non deve stare nel repository. È stato quindi aggiunto un interruttore:

**`values.yaml`** (default, comportamento invariato):

```yaml
postgres:
  secretName: postgres-credentials
  createSecret: true
```

**`templates/secret.yaml`**, racchiuso in una condizione:

```yaml
{{- if .Values.postgres.createSecret }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ .Values.postgres.secretName }}
type: Opaque
stringData:
  POSTGRESQL_DATABASE: {{ .Values.postgres.database | quote }}
  POSTGRESQL_USER: {{ .Values.postgres.user | quote }}
  POSTGRESQL_PASSWORD: {{ required "Devi passare postgres.password" .Values.postgres.password | quote }}
{{- end }}
```

**`values-dev.yaml`** e **`values-prod.yaml`**:

```yaml
postgres:
  createSecret: false   # Secret postgres-credentials creato a parte, non dal chart
```

Effetti:

- in dev e prod il chart non crea il Secret e usa quello già presente nel namespace (stesso nome, `postgres-credentials`);
- tutti i template che leggono `.Values.postgres.secretName` (Deployment, StatefulSet di Postgres, CronJob di backup) continuano a funzionare senza modifiche;
- il chart resta compatibile con il vecchio metodo: con `createSecret: true` (default) si comporta come prima;
- con `createSecret: false` il controllo `required` sulla password non viene valutato, quindi il rendering non richiede nessuna password.

### Values per ambiente

I file `values-dev.yaml` e `values-prod.yaml` (introdotti con l'issue #13) contengono solo le differenze rispetto a `values.yaml`. Helm, e quindi Argo CD, carica prima `values.yaml` e poi applica sopra il file dell'ambiente.

A questi file è stato aggiunto `postgres.createSecret: false`. Inoltre, in `values-dev.yaml`, il campo `app.image.tag` viene ora scritto automaticamente dall'Image Updater.

### Annotation `resolve-names` disattivata

In `templates/deployment.yaml` l'annotation
`alpha.image.policy.openshift.io/resolve-names: '*'` 
è stata commentata. Questa annotation chiede a OpenShift di risolvere i riferimenti alle immagini tramite gli ImageStream del namespace, e quindi di modificare il campo `image` del Deployment dopo che è stato applicato.

Con GitOps il campo `image` deve essere deciso solo da ciò che è scritto in Git: se OpenShift lo riscrive, l'immagine in esecuzione non corrisponde più a quella dichiarata e Argo CD rileva una differenza permanente. Il chart usa sempre il percorso completo del registry (`image-registry.openshift-image-registry.svc:5000/<namespace>/joursense:<tag>`), quindi la risoluzione tramite ImageStream non serve.

---

## Credenziali del database

Il Secret `postgres-credentials` esiste in ciascun namespace e non è nel repository. Contiene tre chiavi, con gli stessi nomi usati dal template del chart:

| Chiave | Contenuto |
|---|---|
| `POSTGRESQL_DATABASE` | nome del database (`giornalino`) |
| `POSTGRESQL_USER` | utente (`giornalino`) |
| `POSTGRESQL_PASSWORD` | password, diversa per ogni ambiente |



Per verificare che le chiavi siano presenti senza mostrarne il contenuto:

```bash
oc describe secret postgres-credentials -n <namespace>
```

---

## Modifiche alla pipeline Tekton

### Pipeline senza deploy (`pipeline.yaml`)

La pipeline passa da quattro a tre task e sono stati tolti anche i parametri `release-name` e `chart-path`, usati solo dal task di deploy.

Motivazione: se la pipeline continuasse a fare `helm upgrade`, ci sarebbero due strumenti a modificare le stesse risorse (Helm e Argo CD), con risultati imprevedibili. Ora la pipeline si occupa solo di CI (verificare il codice e produrre l'immagine), mentre il CD è interamente di Argo CD.

La pipeline continua a:

- partire a ogni push rilevante su `main`, tramite webhook ed EventListener;
- fermarsi se il test su `/healthz` fallisce, così un'immagine difettosa non viene nemmeno costruita;
- pubblicare l'immagine nel registry interno con tag = SHA del commit, che identifica in modo univoco il codice contenuto.

### Filtro sull'EventListener (`eventlistener.yaml`)

Il filtro CEL dell'EventListener è stato esteso:

```yaml
- ref:
    name: cel
  params:
    - name: filter
      value: >-
        body.ref == 'refs/heads/main' &&
        body.commits.exists(c,
          c.added.exists(f, f.startsWith('joursense/')) ||
          c.modified.exists(f, f.startsWith('joursense/')) ||
          c.removed.exists(f, f.startsWith('joursense/')))
```

La pipeline parte solo se il push su `main` modifica almeno un file nella cartella `joursense/`**, cioè il codice dell'applicazione, il `Containerfile` o i test.

Motivazioni:

- l'immagine contiene solo il contenuto di `joursense/` (`CONTEXT: ./joursense`): se lì non cambia nulla, ricostruirla è inutile;
- l'Image Updater fa commit su `values-dev.yaml`. Senza il filtro, una volta che le Application seguiranno `main`, ogni suo commit farebbe ripartire la pipeline, che produrrebbe una nuova immagine, che genererebbe un nuovo commit, in un ciclo continuo;
- il filtro controlla tutti i commit del push (`body.commits.exists`), non solo l'ultimo: un push con più commit viene considerato correttamente anche se il codice è stato modificato in uno dei commit intermedi.

---

## Argo CD Image Updater

### Perché

Togliendo il deploy dalla pipeline, viene meno il collegamento tra "nuova immagine costruita" e "nuova immagine in esecuzione": prima era il `helm upgrade --set image.tag=<sha>` a farlo. Argo CD guarda Git, non il registry, quindi un'immagine nuova nel registry non cambia nulla finché qualcuno non scrive il nuovo tag nel repository.

L'Argo CD Image Updater svolge esattamente questo compito, in modo automatico:

1. ogni 2 minuti legge l'elenco dei tag di `joursense-helm/joursense` nel registry interno;
2. sceglie il tag costruito più di recente;
3. lo confronta con quello usato da `joursense-dev`;
4. se è diverso, fa un commit su GitHub che scrive il nuovo tag in `values-dev.yaml`;
5. Argo CD vede il commit e aggiorna dev.

È stato scelto il write-back su Git (invece della modifica diretta dell'Application sul cluster) perché così:

- il repository resta l'unica fonte di verità, e il tag in uso in dev si legge in `values-dev.yaml`;
- ogni aggiornamento è tracciato nella cronologia di Git, con autore `argocd-image-updater`;
- tornare a una versione precedente è un normale `git revert`.

L'Image Updater segue solo dev: in prod la nuova versione si porta a mano, coerentemente con la sync manuale.

`repository` e `branch` non sono specificati: in loro assenza l'Image Updater usa quelli dell'Application.

> Formattazione: per aggiornare il tag, l'Image Updater riscrive `values-dev.yaml` con il proprio stile (un solo spazio prima dei commenti, senza righe vuote tra i blocchi). Contenuto e commenti restano invariati.

### Lavorare sul branch con l'Image Updater attivo

L'Image Updater fa commit direttamente su GitHub, sullo stesso branch seguito dalle Application. Prima di lavorare su quel branch conviene quindi aggiornare la copia locale:

```bash
git pull --no-rebase
```

Per non doverlo specificare ogni volta:

```bash
git config pull.rebase false
```

---

## Setup

Le operazioni elencate qui sotto richiedono i privilegi da cluster-admin, perché riguardano risorse a livello di cluster o il namespace di Argo CD.

### Installazione di OpenShift GitOps

L'operator Red Hat OpenShift GitOps (versione 1.22.3) è stato installato con l'issue #12; crea l'istanza di Argo CD nel namespace `openshift-gitops`.

### Attivazione dell'Image Updater

L'Image Updater è incluso nell'operator e si attiva dal Custom Resource `ArgoCD`:

```bash
oc patch argocd openshift-gitops -n openshift-gitops --type merge \
  -p '{"spec":{"imageUpdater":{"enabled":true}}}'
```

Verifica:

```bash
oc get pods -n openshift-gitops | grep image-updater
```

### Label sui namespace

```bash
oc label namespace joursense-dev  argocd.argoproj.io/managed-by=openshift-gitops
oc label namespace joursense-prod argocd.argoproj.io/managed-by=openshift-gitops
```

Quando l'operator vede questa label, crea automaticamente i RoleBinding che permettono ad Argo CD di gestire le risorse solo in quei namespace. Argo CD non ottiene così permessi sull'intero cluster.

### Accesso al registry interno

L'Image Updater deve leggere l'elenco dei tag dell'immagine. Per questo è stato creato un ServiceAccount dedicato, con il solo permesso di lettura delle immagini di `joursense-helm`:

```bash
oc create serviceaccount image-updater-registry -n openshift-gitops

oc policy add-role-to-user system:image-puller \
  system:serviceaccount:openshift-gitops:image-updater-registry \
  -n joursense-helm
```

Il token del ServiceAccount viene generato dal cluster a partire da `joursense-ops/argocd/image-updater-registry-token.yaml`, che non contiene segreti:

```bash
oc apply -f joursense-ops/argocd/image-updater-registry-token.yaml
```

Il token viene poi copiato in un pull secret nel formato standard dei registry.

Il registry interno è dichiarato nella configurazione dell'Image Updater (ConfigMap `argocd-image-updater-config`, creata dall'operator).


### Token GitHub per il write-back

Per i commit dell'Image Updater è stato creato un fine-grained personal access token con:

- accesso al solo repository `Esercizi_extra`;
- permesso Contents: Read and write (più Metadata: Read-only, obbligatorio);
- scadenza: 4 dicembre 2026.

Il token è salvato in un Secret nel namespace di Argo CD, con le chiavi `username` e `password`.

> **Attenzione:** alla scadenza del token l'Image Updater non potrà più fare commit. Va generato un nuovo token e aggiornato il Secret.

### Regole dell'Image Updater

```bash
oc apply -f joursense-ops/argocd/imageupdater-dev.yaml
```

## Permessi per l'utenza normale

L'obiettivo è che tutto il lavoro quotidiano (creare o modificare Application, sincronizzare, creare Secret, guardare pod e log) si svolga senza cluster-admin. Argo CD ha due sistemi di permessi indipendenti, ed entrambi vanno configurati.

### Gruppo OpenShift

I permessi sono assegnati a un gruppo, non ai singoli utenti: per dare accesso a una nuova persona basta aggiungerla al gruppo.

```bash
oc adm groups new joursense-team nicolas.cage alessandro.segato
```

### Permessi OpenShift sulle Application

Consentono di creare e modificare le Application con `oc apply`, solo nel namespace `openshift-gitops` e solo per le risorse di tipo Application:

```bash
oc create role joursense-argocd-apps \
  -n openshift-gitops \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=applications.argoproj.io

oc create rolebinding joursense-argocd-apps \
  -n openshift-gitops \
  --role=joursense-argocd-apps \
  --group=joursense-team
```

### Permessi dentro Argo CD (RBAC)

La console e la CLI di Argo CD usano un proprio sistema di permessi, configurato nel CR `ArgoCD`. Di default solo i cluster-admin vi hanno accesso. Sono state aggiunte due righe, mantenendo quelle esistenti:

```bash
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

| Riga | Significato |
|---|---|
| `g, system:cluster-admins, role:admin` | I cluster-admin restano amministratori di Argo CD (riga preesistente). |
| `g, cluster-admins, role:admin` | Idem (riga preesistente). |
| `p, role:joursense, applications, *, default/*, allow` | Il ruolo `joursense` può eseguire tutte le azioni sulle Application del progetto `default`. |
| `g, joursense-team, role:joursense` | Il gruppo OpenShift `joursense-team` riceve il ruolo `joursense`. |

### Accesso ai namespace

```bash
oc adm policy add-role-to-group edit joursense-team -n joursense-dev
oc adm policy add-role-to-group edit joursense-team -n joursense-prod
```

È stato scelto il ruolo `edit` invece di `admin`: permette di creare Secret e di consultare pod, log ed eventi, ma non di modificare i permessi del progetto.

---

## Passaggio da Helm ad Argo CD

Gli ambienti `joursense-dev` e `joursense-prod` erano già stati installati con Helm. Il passaggio è avvenuto senza reinstallare e senza perdere dati:

1. **Verifica preliminare**: è stato controllato che l'immagine prodotta dal chart con i nuovi values coincidesse con quella in esecuzione, così la presa in carico non avrebbe cambiato l'applicazione.
2. **Creazione dell'Application di prod**: senza sync automatica, Argo CD si è limitato a confrontare cluster e Git (stato OutOfSync / Healthy).
3. **Creazione dell'Application di dev**: Argo CD ha preso in carico le risorse esistenti (stessi nomi, stesso PVC del database, stesso Secret) ed è passato a Synced / Healthy.
4. **Sync manuale di prod** dalla console di Argo CD.
5. **Rimozione della "memoria" di Helm**: Helm tiene traccia di ogni installazione in Secret di tipo `helm.sh/release.v1`. Sono stati cancellati **solo** questi Secret:

   ```bash
   oc get secret -n joursense-dev  -l owner=helm,name=joursense   # verifica di cosa verrà cancellato
   oc delete secret -n joursense-dev  -l owner=helm,name=joursense
   oc delete secret -n joursense-prod -l owner=helm,name=joursense
   ```

   Da quel momento `helm list` nei due namespace è vuoto: Helm non considera più quelle risorse come proprie, e ne è responsabile solo Argo CD.

> **Importante:** non va usato `helm uninstall` su dev e prod. Cancellerebbe tutte le risorse dell'applicazione, compresi il database e il Secret delle credenziali.

---

## Operazioni

### Stato delle Application

```bash
oc get applications -n openshift-gitops
```

Oppure dalla console di Argo CD:

```bash
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}{"\n"}'
```

Il login si fa con **"Log in via OpenShift"**.

| Stato | Significato |
|---|---|
| **Synced** | Il cluster corrisponde a Git. |
| **OutOfSync** | Il cluster è diverso da Git: in dev si sistema da solo, in prod serve un Sync manuale. |
| **Healthy** | Le risorse funzionano. |
| **Progressing** | Un rollout è in corso (stato temporaneo). |
| **Degraded** | Qualche risorsa non funziona (ad esempio un pod che non parte). |

### Nuova versione del codice in dev

Nessuna operazione manuale: un push su `main` che modifica `joursense/` avvia la pipeline; l'Image Updater rileva la nuova immagine e aggiorna `values-dev.yaml`; Argo CD aggiorna dev.

Per verificare l'immagine in uso:

```bash
oc get deploy joursense -n joursense-dev \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

### Promozione in prod

1. Leggere il tag in uso in dev da `values-dev.yaml` (`app.image.tag`).
2. Scrivere lo stesso tag in `values-prod.yaml`:
   ```yaml
   app:
     image:
       tag: <sha>
   ```
3. Commit e push.
4. Prod risulta **OutOfSync**: controllare le differenze con **App Diff** in console, poi **SYNC → SYNCHRONIZE**.

### Modifica di configurazione (values o template)

Commit e push della modifica. Dev la applica da solo entro circa 3 minuti (oppure subito con **REFRESH** in console); prod resta OutOfSync fino al Sync manuale.

### Tornare a una versione precedente

Con GitOps si torna indietro **in Git**, non sul cluster: si annulla il commit con `git revert <commit>` e si fa push. Argo CD riallinea il cluster.

### Controllare l'Image Updater

```bash
# stato sintetico
oc get imageupdater joursense-dev -n openshift-gitops -o yaml | sed -n '/^status:/,$p'

# ultimi eventi del controller, in forma leggibile
oc logs -n openshift-gitops deploy/openshift-gitops-argocd-image-updater-controller --since=10m \
  | grep -i -E "push|updated|error" \
  | sed -E 's/^time="[^T]*T([^Z]*)Z" level=([a-z]+) msg="(.*)" (application|controller)=.*/\1  \2  \3/' \
  | tail -8
```

Per le risorse Tekton usare il nome completo:

```bash
oc get pipelines.tekton.dev -n joursense-helm
```

---

## Verifica degli acceptance criteria

| Criterio | Verifica |
|---|---|
| Esistono due Application, dev e prod, definite in YAML nel repo | `joursense-ops/argocd/application-dev.yaml` e `application-prod.yaml`; `oc get applications -n openshift-gitops` |
| Entrambe puntano allo stesso chart, con `values-dev.yaml` e `values-prod.yaml` | Stesso `path: joursense-helm`, `valueFiles` diversi |
| In console entrambe risultano Synced e Healthy | Console di Argo CD / `oc get applications` |
| Dev ha la sync automatica: una modifica nel repo arriva in `joursense-dev` senza intervento | Modificato `periodSeconds` della liveness probe in `values.yaml`: dev è passato da OutOfSync a Synced da solo e il Deployment ha ricevuto il nuovo valore |
| Prod ha la sync manuale: dopo una modifica risulta OutOfSync finché non si sincronizza a mano | Con la stessa modifica prod è rimasto OutOfSync e con il valore precedente; dopo il Sync dalla console ha ricevuto il nuovo valore |
| Il deploy non avviene più con `helm upgrade` a mano, né dalla pipeline | Pipeline con i soli task `fetch-source test build-push`; nessuna release Helm in dev e prod (`helm list` vuoto) |
| Le password restano in Secret creati a parte, non nel repo | `createSecret: false` nei values; Secret `postgres-credentials` presente nei namespace e assente dal repository |

Verifica dei task della pipeline sul cluster:

```bash
oc get pipelines.tekton.dev joursense-pipeline -n joursense-helm \
  -o jsonpath='{.spec.tasks[*].name}{"\n"}'
```


