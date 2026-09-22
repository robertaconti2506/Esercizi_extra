## Descrizione
Il ruolo `ssh_configuration` automatizza la configurazione e la messa in sicurezza del servizio SSH sulle macchine Ubuntu 22.04.
In base all'ambiente (`dev`, `test` o `prod`), il ruolo configura gli utenti autorizzati, le modalità di autenticazione, i limiti di accesso e le impostazioni specifiche del server SSH.
Sulla macchina di produzione vengono inoltre configurati la porta SSH `2222` e un sistema di logging dedicato tramite `rsyslog`.

## Obiettivi

Il ruolo configura:
- autenticazione SSH tramite chiavi pubbliche
- disabilitazione dell'autenticazione tramite password
- disabilitazione delle password vuote
- limite massimo di 2 tentativi di autenticazione
- utenti autorizzati in base all'ambiente
- gruppo autorizzato sulla macchina di produzione
- porta SSH `2222` sulla macchina di produzione
- `LogLevel VERBOSE` sulla macchina di produzione
- logging SSH dedicato sulla macchina di produzione

## Struttura del ruolo
```text
ssh_configuration
├── handlers
│   └── main.yml
├── tasks
│   ├── main.yml
│   ├── rsyslog.yml
│   ├── sshd.yml
│   └── users.yml
├── templates
│   ├── prod_ssh_rsyslog.conf.j2
│   └── sshd_config.j2
└── vars
    └── main.yml
```

`tasks/main.yml` è il punto di ingresso delle attività del ruolo e include:
- `users.yml`
- `sshd.yml`
- `rsyslog.yml`

 `tasks/users.yml` gestisce la creazione degli utenti e dei gruppi necessari:
- `sviluppatore` nell'ambiente development
- `tester` nell'ambiente test
- `administrators` nell'ambiente production
- `admin` nell'ambiente production

`tasks/sshd.yml` installa il template della configurazione SSH nella directory:
```text
/etc/ssh/sshd_config.d/
```

Il file principale `/etc/ssh/sshd_config` non viene modificato.
Prima dell'installazione, la configurazione viene validata tramite `sshd -t`.

 `tasks/rsyslog.yml`  configura il logging dedicato di SSH sulla macchina production.
Il task viene eseguito solamente quando l'host appartiene al gruppo `prod`.

 `templates/sshd_config.j2`
Template Jinja2 utilizzato per generare la configurazione di `sshd`.

La configurazione cambia in base al gruppo Ansible dell'host:

|Ambiente|Accesso SSH|
|---|---|
|Development|`sviluppatore` e `root`|
|Test|`tester` e `root`|
|Production|gruppo `administrators`|

Sulla macchina production vengono inoltre configurati:
- porta `2222`
- `PermitRootLogin no`
- `LogLevel VERBOSE`
- facility `LOCAL5`

 `templates/prod_ssh_rsyslog.conf.j2`
Definisce la regola `rsyslog` per indirizzare i messaggi provenienti dalla facility `local5` nel file:

```text
/var/log/prod_ssh.log
```

Il flusso dei log è quindi:

```text
sshd
  ↓
LOCAL5
  ↓
rsyslog
  ↓
/var/log/prod_ssh.log
```

 `handlers/main.yml` contiene gli handler utilizzati per riavviare i servizi quando una configurazione viene modificata:
- `Restart SSH`
- `Restart rsyslog`

`vars/main.yml` contiene le variabili utilizzate dal ruolo:

```yaml
ssh_max_auth_tries: 2

ssh_dev_user: sviluppatore

ssh_test_user: tester

ssh_prod_user: admin

ssh_prod_group: administrators

ssh_prod_port: 2222
```

## Configurazione per ambiente

Development:
```text
AllowUsers sviluppatore root
PermitRootLogin yes
```

Test:
```text
AllowUsers tester root
PermitRootLogin yes
```

Production:
```text
AllowGroups administrators
PermitRootLogin no
Port 2222
LogLevel VERBOSE
SyslogFacility LOCAL5
```

Sicurezza comune
Tutte le macchine utilizzano:

```text
PasswordAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
MaxAuthTries 2
```

In questo modo l'accesso SSH tramite password viene disabilitato e vengono accettate solamente autenticazioni tramite chiave pubblica.

Il ruolo viene richiamato dal `playbook.yml` principale:
```yaml
roles:
  - ssh_configuration
```

Le configurazioni vengono applicate in base ai gruppi presenti nell'`inventory.ini`.

## File generati

Il ruolo crea la configurazione SSH tramite un drop-in:

```text
/etc/ssh/sshd_config.d/99-ssh-configuration.conf
```

Sulla macchina production crea inoltre:

```text
/etc/rsyslog.d/30-prod-ssh.conf
```

e configura il file di log:

```text
/var/log/prod_ssh.log
```

### Perché utilizzare un file drop-in

La configurazione SSH viene inserita nella directory:

```text
/etc/ssh/sshd_config.d/
```

invece di modificare direttamente il file principale:

```text
/etc/ssh/sshd_config
```

Questa soluzione permette di mantenere separata la configurazione personalizzata da quella predefinita del sistema.

Il ruolo crea il file:

```text
/etc/ssh/sshd_config.d/99-ssh-configuration.conf
```

I file presenti nella directory `sshd_config.d` vengono letti da `sshd` come configurazioni aggiuntive.

L'utilizzo di un drop-in offre quindi alcuni vantaggi:
- non modifica il file principale di configurazione
- mantiene separate le configurazioni personalizzate
- rende più semplice la gestione tramite Ansible
- permette di aggiornare o rimuovere la configurazione del ruolo senza modificare la configurazione originale del sistema
- riduce il rischio di sovrascrivere configurazioni preesistenti

Il prefisso `99-` viene utilizzato per fare in modo che il file venga letto dopo gli altri eventuali file di configurazione presenti nella directory.

