<h1 align="center">Monitoring </h1>

## Descrizione

In questo esercizio viene creata una piccola infrastruttura di monitoring utilizzando Vagrant e Ansible.

Vengono create tre virtual machine Rocky Linux:
- `elasticsearch-host`, dove viene eseguito Elasticsearch tramite Docker
- `monitoring-grafana`, dove viene eseguito Grafana tramite Docker
- `monitoring-prometheus`, dove viene eseguito Prometheus tramite Docker <br/> 
Su tutte e tre le macchine viene installato anche Node Exporter direttamente sulla VM, quindi senza utilizzare Docker. 
Node Exporter raccoglie ed espone le metriche delle macchine, Prometheus le raccoglie tramite scarping e Grafana le utilizza per creare le visualizzazioni.
L'obiettivo dell'esercizio è mettere insieme questi componenti e automatizzarne il deployment e la configurazione tramite Ansible.

## Struttura del progetto

```
Esercizio2
├── inventory.ini
├── playbook.yml
├── requirements.yml
└── roles
    ├── docker
    │   ├── defaults
    │   │   └── main.yml
    │   └── tasks
    │       └── main.yml
    │
    ├── monitoring
    │   ├── defaults
    │   │   └── main.yml
    │   ├── tasks
    │   │   ├── elasticsearch.yml
    │   │   ├── grafana.yml
    │   │   ├── main.yml
    │   │   ├── node_exporter.yml
    │   │   └── prometheus.yml
    │   └── templates
    │       ├── grafana-datasource.yml.j2
    │       ├── jvm.options.j2
    │       ├── node_exporter.service.j2
    │       └── prometheus.yml.j2
    │
    └── vagrant
        ├── Vagrantfile
        ├── tasks
        │   └── main.yml
        ├── vagrant.err
        └── vars
            └── main.yml
```


## Playbook

Il `playbook.yml` è composto da due play principali.

`Deploy Vagrant VMs` <br/>
Il primo play viene eseguito su `localhost` e utilizza il ruolo `vagrant`.
Prima dell'esecuzione viene verificato che la box Vagrant utilizzata sia:
```text
generic/rocky9
```

`Configure monitoring infrastructure` <br/>
Il secondo play viene eseguito sul gruppo:
```text
monitoring
```
e applica, nell'ordine, i ruoli:
```yaml
roles:
  - docker
  - monitoring
```

Prima dell'esecuzione viene inoltre verificata la presenza delle collection Ansible richieste.

Le collection utilizzate dal progetto sono definite in `requirements.yml`:
```yaml
collections:
  - name: community.vagrant
  - name: community.docker
  - name: community.grafana
  - name: community.general
  - name: ansible.posix
```

Prima di eseguire il progetto è quindi necessario installarle: 
```bash
ansible-galaxy collection install -r requirements.yml
```

## Avvio del progetto

Dalla directory principale del progetto è possibile avviare il deployment tramite:

```bash
ansible-playbook -i inventory.ini playbook.yml
```


## Flusso di deployment

```text
                    playbook.yml
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
          vagrant                monitoring
             │                       │
             ▼                       ▼
        3 Rocky VM              Docker role
                                     │
                                     ▼
                              Monitoring role
                                     │
             ┌───────────────────────┼──────────────────────┐
             │                       │                      │
             ▼                       ▼                      ▼
       Elasticsearch              Grafana              Prometheus
             │                       │                      │
             └───────────────┬───────┴──────────────────────┘
                             │
                             ▼
                       Node Exporter
                             │
                             ▼
                         Prometheus
                             │
                             ▼
                          Grafana
```

---

## Componenti del monitoring

L'infrastruttura utilizza quattro componenti principali: Elasticsearch, Prometheus, Grafana e Node Exporter. Ognuno ha un compito diverso e, messi insieme, permettono di raccogliere, conservare e visualizzare le informazioni provenienti dalle macchine.

### Elasticsearch

Elasticsearch è un motore di ricerca e analisi distribuito. In questo esercizio viene eseguito all'interno di un container Docker sulla macchina `elasticsearch-host`.
Il suo compito principale è quello di permettere di archiviare e ricercare grandi quantità di dati in modo veloce. Elasticsearch non viene utilizzato direttamente per raccogliere le metriche del monitoring realizzato in questo esercizio, ma viene comunque configurato, come richiesto, con un heap JVM di 1 GB.

### Prometheus

Prometheus è il componente che si occupa della raccolta delle metriche.
In questo esercizio, Prometheus viene eseguito all'interno di un container Docker sulla macchina `monitoring-prometheus`.
Prometheus interroga periodicamente i tre Node Exporter tramite i loro endpoint `/metrics` e salva le metriche raccolte. In questo modo può tenere sotto controllo le risorse e lo stato delle tre virtual machine.

### Node Exporter

Node Exporter è il componente che permette di esporre le metriche della macchina su cui è installato.
In questo esercizio viene installato direttamente sulle tre virtual machine e non tramite Docker.
Node Exporter raccoglie informazioni relative al sistema, come utilizzo della CPU, memoria, filesystem e altre metriche del sistema operativo, e le rende disponibili tramite un endpoint HTTP `/metrics`.
Prometheus utilizza proprio questo endpoint per effettuare lo scraping delle metriche.
Ogni macchina utilizza una porta differente per Node Exporter, così che Prometheus possa distinguere le tre sorgenti.

### Grafana

Grafana è il componente utilizzato per visualizzare le metriche raccolte da Prometheus.
Viene eseguito all'interno di un container Docker sulla macchina `monitoring-grafana`.
Grafana si collega a Prometheus tramite una datasource e permette di trasformare le metriche raccolte in grafici e dashboard.
In questo esercizio viene utilizzata la dashboard `Node Exporter Full`, che permette di visualizzare le principali metriche delle macchine monitorate.