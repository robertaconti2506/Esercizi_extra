## Descrizione
L'obiettivo è automatizzare la configurazione del servizio SSH, applicando impostazioni differenti in base all'ambiente e gestendo utenti, autenticazione, accessi e logging.

## Struttura
```text
prod-dev-test
├── inventory.ini
├── playbook.yml
└── roles
    └── ssh_configuration
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

## Prerequisiti
Prima di iniziare assicurarsi di avere installato:
- Vagrant 
- VirtualBox
- Ansible

È inoltre necessaria una chiave SSH moderna `ed25519` sul Mac.

Verificare che la chiave pubblica esista:
```bash
ls -l ~/.ssh/id_ed25519.pub
```

Se non esiste, crearla con:
```bash
ssh-keygen -t ed25519
```

## Avviare le VM
Dalla directory contenente il `Vagrantfile`:
```bash
vagrant up
```

Il `Vagrantfile` crea tre macchine virtuali:

| VM           | IP privato     |
| ------------ | -------------- |
| `proxy-dev`  | `192.168.56.4` |
| `proxy-test` | `192.168.56.5` |
| `proxy-prod` | `192.168.56.6` |

Verificare lo stato delle macchine:
```bash
vagrant status
```
Tutte e tre le VM devono avere stato:
```text
running
```

## Configurazione Ansible
L'inventory Ansible utilizza gli IP privati delle tre VM.

Per la connessione iniziale vengono utilizzate le chiavi SSH generate da Vagrant. Ogni macchina dispone di una propria chiave privata:
```text
.vagrant/machines/proxy-dev/virtualbox/private_key
.vagrant/machines/proxy-test/virtualbox/private_key
.vagrant/machines/proxy-prod/virtualbox/private_key
```

I percorsi indicati nell'`inventory.ini` devono corrispondere alla posizione della directory `.vagrant` sul sistema locale.

## Verificare la connessione Ansible
Prima di eseguire il playbook, verificare che Ansible riesca a raggiungere tutte le VM:
```bash
ansible all -i inventory.ini -m ping
```

Il risultato atteso è `SUCCESS` per:
```text
proxy-dev
proxy-test
proxy-prod
```

## Installazione della chiave SSH del Mac
Il playbook utilizza la chiave pubblica presente sul Mac:
```text
~/.ssh/id_ed25519.pub
```

Durante la configurazione iniziale, la chiave viene aggiunta all'utente `vagrant` tramite il task:
```text
Add Mac public key to vagrant authorized_keys
```

In questo modo la chiave SSH del Mac può essere utilizzata per le connessioni SSH successive.

## Eseguire il playbook
Una volta verificata la connessione con Ansible, eseguire:
```bash
ansible-playbook -i inventory.ini playbook.yml
```

Il playbook applica il ruolo `ssh_configuration` a tutte le macchine appartenenti al gruppo `all`.


