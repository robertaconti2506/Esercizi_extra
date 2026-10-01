<h1 align="center">Docker Role </h1>

## Descrizione

Il role `docker` si occupa di installare e configurare Docker sulle virtual machine create dal role `vagrant`.
Viene eseguito sulle tre macchine del gruppo `monitoring` e prepara l'ambiente necessario per eseguire successivamente i container di Elasticsearch, Grafana e Prometheus.
Il role non si occupa di creare container: il suo compito è installare Docker, avviare il servizio e verificare che sia correttamente in esecuzione.
