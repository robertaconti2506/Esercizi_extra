<h1 align="center">Monitoring </h1>

Il ruolo `monitoring` configura tutta la parte di monitoring dell'infrastruttura. <br/>
Il ruolo viene eseguito sulle tre VM del gruppo `monitoring` e, in base al gruppo a cui appartiene ciascun host, configura:
- Elasticsearch su `elasticsearch-host`
- Grafana su `monitoring-grafana`
- Prometheus su `monitoring-prometheus`
- Node Exporter su tutte e tre le VM
Il flusso principale del monitoring è:
```
Node Exporter → Prometheus → Grafana
```
Elasticsearch è invece un servizio separato, richiesto dall'esercizio, e non fa parte del flusso Prometheus/Grafana.

Il file `tasks/main.yml` suddivide la configurazione in base al gruppo dell'host.
In questo modo Node Exporter viene installato su tutte le VM, mentre Elasticsearch, Grafana e Prometheus vengono configurati solamente sull'host previsto.

## Elasticsearch

Elasticsearch viene installato sulla VM `elasticsearch-host` e viene eseguito all'interno di un container Docker.
Rappresenta un servizio separato dalla parte di monitoring composta da Prometheus, Grafana e Node Exporter. Il suo compito è semplicemente quello di fornire il servizio Elasticsearch richiesto dall'esercizio.
Per l'esecuzione viene utilizzata l'immagine `docker.elastic.co/elasticsearch/elasticsearch:8.19.0` e il container espone la porta `9200`.
I dati di Elasticsearch vengono salvati in un volume Docker chiamato `elasticsearch-data`, in modo che non vengano persi nel caso in cui il container venga ricreato.

### Memoria JVM

L'esercizio richiede di impostare `1 GB` di heap, quindi vengono configurati sia il valore iniziale sia quello massimo a `1 GB`:
```
-Xms1g
-Xmx1g
```

Queste impostazioni vengono generate automaticamente dal template `jvm.options.j2` e montate all'interno del container nella directory prevista da Elasticsearch.
Elasticsearch viene configurato come nodo singolo. Per semplificare la configurazione dell'ambiente di esercizio, la security di Elasticsearch viene disabilitata tramite `xpack.security.enabled: "false"`.

Al termine della configurazione, Ansible controlla che il container Elasticsearch sia effettivamente in esecuzione.
È possibile verificare manualmente il servizio collegandosi alla VM `elasticsearch-host` e controllando lo stato del container:

```
docker ps
```

Per verificare che Elasticsearch risponda correttamente, si può anche effettuare una richiesta alla porta `9200`:

```
curl http://localhost:9200
```

Se il servizio è correttamente avviato, Elasticsearch restituisce una risposta contenente le informazioni relative al nodo.

## Prometheus

Prometheus viene installato sulla VM `monitoring-prometheus` ed eseguito all'interno di un container Docker.

Il suo compito è raccogliere e memorizzare le metriche esposte dai tre Node Exporter presenti sulle VM. Prometheus interroga periodicamente ogni Node Exporter e salva i dati raccolti, che potranno poi essere utilizzati da Grafana.

Per l'esecuzione viene utilizzata l'immagine `prom/prometheus:latest`. Il servizio è raggiungibile sulla porta `9090` e i dati vengono salvati nel volume Docker `prometheus-data`, così da mantenerli anche nel caso in cui il container venga ricreato.

### Raccolta delle metriche

Prometheus utilizza una configurazione statica per indicare i tre Node Exporter da interrogare:

```text
elasticsearch-host       → 192.168.45.13:9101
monitoring-grafana       → 192.168.45.14:9102
monitoring-prometheus    → 192.168.45.15:9103
```

La configurazione viene generata automaticamente dal template `prometheus.yml.j2`.

Le metriche vengono raccolte ogni `15 secondi`, secondo il valore impostato nella configurazione del ruolo.

### Verifica

Al termine della configurazione, Ansible controlla che il container Prometheus sia effettivamente in esecuzione.

Dal Mac è possibile verificare che Prometheus sia raggiungibile collegandosi all'indirizzo della VM:

```text
http://192.168.45.15:9090
```

Una volta aperta l'interfaccia web di Prometheus, è possibile verificare che i tre target dei Node Exporter risultino raggiungibili nella sezione dedicata agli endpoint di scraping.

## Grafana

Grafana viene installato sulla VM `monitoring-grafana` ed eseguito all'interno di un container Docker.

Il suo compito è visualizzare in modo grafico le metriche raccolte da Prometheus. Grafana non raccoglie direttamente le metriche dai Node Exporter: utilizza Prometheus come sorgente dei dati.

Per l'esecuzione viene utilizzata l'immagine `grafana/grafana:latest`. Il servizio è raggiungibile sulla porta `3000` e i dati di Grafana vengono salvati nel volume Docker `grafana-data`, così da mantenerli anche nel caso in cui il container venga ricreato.

### Collegamento a Prometheus

Il ruolo configura automaticamente Prometheus come datasource di Grafana utilizzando il seguente indirizzo:

```text
http://192.168.45.15:9090
```

In questo modo Grafana può recuperare da Prometheus le metriche raccolte dai tre Node Exporter.

Il datasource viene configurato tramite il template `grafana-datasource.yml.j2`, quindi non è necessario aggiungerlo manualmente dall'interfaccia di Grafana.

### Dashboard

Al termine dell'avvio, viene importata automaticamente la dashboard `Node Exporter Full`, con ID `1860`.

La dashboard permette di visualizzare le principali metriche delle VM, raccolte tramite Node Exporter e memorizzate da Prometheus.

### Verifica

Al termine della configurazione, Ansible aspetta che Grafana risponda correttamente alla sua API di health check.

Dal Mac è possibile verificare che Grafana sia raggiungibile aprendo nel browser:

```text
http://192.168.45.14:3000
```

Dopo aver effettuato l'accesso, è possibile verificare che il datasource Prometheus sia presente e che la dashboard `Node Exporter Full` sia disponibile.

## Node Exporter

Node Exporter viene installato direttamente sulle tre VM e non viene eseguito tramite Docker.

Il suo compito è raccogliere informazioni sulle risorse e sullo stato delle macchine, come utilizzo della CPU, memoria, disco e rete. Queste metriche vengono poi messe a disposizione di Prometheus.

Viene utilizzata la versione `1.12.1` per l'architettura `linux-amd64`. Il binario viene installato in:

```text
/usr/local/bin/node_exporter
```

### Porte

Ogni VM utilizza una porta diversa:

|VM|Porta|
|---|--:|
|`elasticsearch-host`|`9101`|
|`monitoring-grafana`|`9102`|
|`monitoring-prometheus`|`9103`|

Le porte vengono aperte tramite `firewalld`, permettendo a Prometheus di raggiungere i tre Node Exporter.

### Avvio del servizio

Node Exporter viene configurato come servizio `systemd --user` dell'utente `vagrant`.

Il servizio viene quindi eseguito senza utilizzare Docker e viene configurato per essere avviato automaticamente. Viene inoltre abilitato il `systemd linger` per l'utente `vagrant`, in modo che il servizio possa continuare a funzionare anche quando non è presente una sessione SSH attiva.

### Verifica

Al termine della configurazione, Ansible controlla che il servizio Node Exporter sia effettivamente attivo.

È inoltre possibile verificare manualmente dal Mac che il Node Exporter risponda correttamente interrogando l'endpoint `/metrics`.

```bash
curl http://192.168.45.13:9101/metrics  # elasticsearch-host
curl http://192.168.45.14:9102/metrics  # monitoring-grafana  
curl http://192.168.45.15:9103/metrics  # monitoring-prometheus
```

Se il servizio funziona correttamente, viene restituito un elenco di metriche.

## Flusso del monitoring

Il funzionamento della parte di monitoring può essere riassunto in questo modo:

```text
Node Exporter
     │
     │ metriche
     ▼
Prometheus
     │
     │ dati
     ▼
Grafana
```

Node Exporter raccoglie le metriche direttamente dalle tre VM e le espone sulle rispettive porte.

Prometheus interroga periodicamente i tre Node Exporter e raccoglie le metriche, che vengono poi memorizzate nel volume associato al container.

Grafana utilizza Prometheus come datasource e permette di visualizzare queste informazioni attraverso dashboard e grafici.

Elasticsearch rimane invece un servizio separato: viene eseguito sulla VM `elasticsearch-host` come richiesto dall'esercizio, ma non partecipa al flusso di raccolta e visualizzazione delle metriche.