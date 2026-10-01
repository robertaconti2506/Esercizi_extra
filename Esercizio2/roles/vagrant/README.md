<h1 align="center">Vagrant Role </h1>


## Descrizione

Il role `vagrant` si occupa di creare e avviare le tre virtual machine richieste dall'esercizio tramite Vagrant e Ansible.
Le VM utilizzano come sistema operativo la box Rocky Linux 9:

```
generic/rocky9
```

Il provider utilizzato è VirtualBox.
Il role permette quindi di gestire la creazione delle macchine direttamente dal playbook Ansible, senza dover eseguire manualmente `vagrant up`.

## Variabili

La configurazione generale del role è definita in `vars/main.yml`.
In questo esercizio la configurazione delle VM, della box e del provider rappresenta una configurazione specifica dell'ambiente richiesto dall'esercizio stesso. Per questo motivo è stato preferito `vars/main.yml`.
La variabile principale del role è:
```
vagrant_vms:
```
Si tratta di una lista contenente la configurazione delle tre VM che devono essere create.
Per ogni macchina vengono definiti:
- nome della VM
- memoria
- numero di CPU
- interfaccia di rete
- indirizzo IP privato
In questo modo tutta la configurazione delle macchine è centralizzata in un'unica variabile e può essere passata direttamente al modulo `community.vagrant.vagrant`.

## Virtual machines

| VM | IP | CPU | RAM |
|---|---|---:|---:|
| `elasticsearch-host` | `192.168.45.13` | 2 | 1024 MB |
| `monitoring-grafana` | `192.168.45.14` | 2 | 1024 MB |
| `monitoring-prometheus` | `192.168.45.15` | 2 | 1024 MB |
