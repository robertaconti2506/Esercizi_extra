# Monitoring di joursense: alert e dashboard

Una dashboard e un alert ("pod non ready da 2 minuti") usando
il monitoring di OpenShift e una PrometheusRule.

## Cosa c'è e dove sta

| Oggetto | File | Namespace | Chi lo installa |
|---|---|---|---|
| Alert `PodNonReady` (PrometheusRule `joursense-alerts`) | `joursense-helm/templates/prometheusrule.yaml` | `joursense-helm` | il chart Helm (`helm upgrade`, pipeline Tekton) |
| Attivazione del monitoring dei progetti utente | `joursense-ops/monitoring/cluster-monitoring-config.yaml` | `openshift-monitoring` | cluster-admin, una volta sola |
| Dashboard `joursense` | `joursense-ops/monitoring/dashboard-joursense.yaml` | `openshift-config-managed` | cluster-admin |
| Pod di test per l'alert | `joursense-ops/monitoring/pod-test-non-ready.yaml` | `joursense-helm` | a mano, solo durante il test |

**Perché alcune cose sono nel chart e altre in `joursense-ops`.** Nel chart va solo quello
che sta nel namespace dell'app e si installa con i permessi del progetto. La dashboard e la
configurazione del monitoring vivono in namespace di sistema: se fossero nel chart,
l'`helm upgrade` della pipeline (service account con ruolo `edit`) riceverebbe `Forbidden`
e fallirebbe tutto il deploy. Stesso criterio di `joursense-ops/operators/`.

## Prerequisiti (una volta sola)

### 1. Permessi sul namespace

Il ruolo `admin` del progetto **non** include il monitoring. Un cluster-admin deve assegnare:

```bash
oc adm policy add-role-to-user monitoring-rules-edit <utente> -n joursense-helm   # PrometheusRule
```

Verifica:

```bash
oc auth can-i create prometheusrules     # yes
```

### 2. User workload monitoring

OpenShift ha due Prometheus: quello della **piattaforma**, sempre acceso, che legge solo le
regole dei namespace `openshift-*`, e quello dei **progetti utente**, che va attivato. Senza
quest'ultimo la PrometheusRule viene creata ma **nessuno la valuta**: l'alert non compare
da nessuna parte, neanche per un cluster-admin.

Sul nostro cluster non era attivo (la ConfigMap `cluster-monitoring-config` non esisteva).

```bash
oc apply -f joursense-ops/monitoring/cluster-monitoring-config.yaml
oc -n openshift-user-workload-monitoring get pods     # prometheus-operator, prometheus-user-workload-*, thanos-ruler-user-workload-* Running
```

## Alert `PodNonReady`

Nei values del chart:

```yaml
monitoring:
  enabled: true
  podNotReadyFor: 2m
```

Espressione:

```promql
(kube_pod_status_ready{namespace="joursense-helm", condition="false"} == 1)
and on (namespace, pod)
(kube_pod_status_phase{namespace="joursense-helm", phase=~"Running|Pending"} == 1)
```

- **Prima parte**: i pod **non ready**. `kube_pod_status_ready` ha una riga per ogni
  condizione (`true`, `false`, `unknown`) e vale 1 su quella attuale.
- **Seconda parte**: i pod **ancora attivi** (`Running` o `Pending`). Serve a escludere
  i pod terminati (`Completed`) di pipeline Tekton e Job di backup, che risultano
  "non ready" ma hanno solo finito il loro lavoro.
- **`and on (namespace, pod)`**: tiene un pod solo se compare in **entrambe** le parti,
  confrontandolo per namespace e nome.
- **`for: 2m`**: la condizione deve durare 2 minuti di fila. Prima l'alert è **Pending**,
  poi diventa **Firing**. Se il pod torna ready prima, non scatta.

Le metriche arrivano da kube-state-metrics, già presente in OpenShift: non serve
modificare l'app né creare un ServiceMonitor.

Deploy:

```bash
helm upgrade joursense ./joursense-helm --reset-then-reuse-values
oc get prometheusrule        # joursense-alerts
```

### Test dell'alert

```bash
oc apply -f joursense-ops/monitoring/pod-test-non-ready.yaml
oc get pod test-non-ready        # READY 0/1, STATUS Running
```

Il pod ha una readiness probe che esegue `false`, quindi gira ma non diventa mai ready.
In **Observe → Metrics**:

```promql
ALERTS{alertname="PodNonReady"}
```
`pending` dopo circa 1 minuto, `firing` dopo altri 2 minuti, sul pod
`test-non-ready`. Poi:

```bash
oc delete pod test-non-ready     # dopo 1-2 minuti l'alert si risolve
```

### Dove vederlo nella console

- **Observe → Alerting**, con *Project: joursense-helm* → scheda **Alerts**.

## Dashboard `joursense`

Dashboard personalizzata nella console: **Observe → Dashboards → joursense**.

| Pannello | Query (namespace `joursense-helm`) | Collegato a |
|---|---|---|
| Pod app ready | `sum(kube_pod_status_ready{condition="true", pod=~"joursense-[a-z0-9]+-[a-z0-9]+"})` | probe |
| Pod non ready | stessa espressione dell'alert | alert |
| Repliche HPA | `kube_horizontalpodautoscaler_status_current_replicas` / `..._spec_max_replicas` | HPA |
| CPU per pod | `sum by (pod) (rate(container_cpu_usage_seconds_total[5m]))` | HPA, load test |
| Memoria per pod | `sum by (pod) (container_memory_working_set_bytes)` | |
| Restart dei container | `sum by (pod) (kube_pod_container_status_restarts_total)` | liveness probe |

Installazione (cluster-admin):

```bash
oc apply -f joursense-ops/monitoring/dashboard-joursense.yaml
```

Poi ricaricare la pagina della console: l'elenco delle dashboard si carica all'apertura.
