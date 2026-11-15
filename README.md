# SAE-3.02
# Installer la simulation de carrefour sur deux VM 


La simulation tourne sur une première VM et enregistre ses données dans MariaDB sur une seconde VM, à travers le réseau.

| VM | Rôle | Ce qu'on y installe |
| --- | --- | --- |
| VM base | serveur de base de données | MariaDB uniquement, pas le projet |
| VM appli | simulation (fenêtre PyQt6) | le projet, Python et ses dépendances |

**Prérequis**

- VirtualBox PC.
- Une connexion Internet pour l'installation 


## 1. Réseau des deux VM (VirtualBox)

Les deux VM sont en **accès par pont** 

1. Si une VM est un **clone** de l'autre, donne-lui une adresse MAC différente, sinon les deux auront la même IP : dans **Carte 1 → Avancé**, clique sur les flèches à côté de **Adresse MAC**.
3. Démarre les deux VM et tape dans chacune :
```
ip a 
```
4. note toi bien les adresses reçu et prend en compte que pour le reste du doc @ip de la BDD sera BASE_IP et pour l'application se sera APPLI_IP

## 2. VM base : MariaDB

Toutes les commandes de cette partie se tapent en root.(su -)

**Installer MariaDB**

```
su -
apt update
apt install mariadb-server
```

**Accepter les connexions venant du réseau.** Ouvre la configuration :

```
nano /etc/mysql/mariadb.conf.d/50-server.cnf
```

Cherche la ligne `bind-address` (Ctrl+W, tape `bind-address`, Entrée) et remplace `127.0.0.1` par `0.0.0.0`. Elle doit devenir `bind-address = 0.0.0.0`, sans `#` devant. Enregistre avec Ctrl+s et Ctrl+x, puis redémarre MariaDB et vérifie :

```
systemctl restart mariadb
ss -tlnp | grep 3306
```

La dernière commande doit afficher `0.0.0.0:3306`.

**Créer la base et l'utilisateur de l'application.** Ouvre la console MariaDB :

```
mariadb
```

Puis tape, en remplaçant `ton_mot_de_passe` ansi que `sae` :

```sql
CREATE DATABASE IF NOT EXISTS carrefour CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'sae'@'BASE_IP' IDENTIFIED BY 'ton_mot_de_passe';
GRANT ALL PRIVILEGES ON carrefour.* TO 'sae'@'BASE_IP';
FLUSH PRIVILEGES;
EXIT;
```

Tape `exit` pour quitter le root. La VM base est prête.

## 3. VM appli : le projet

**Installer les paquets système** (en root) :

```
su -
apt update
apt install unzip python3.11-venv python3-dev gcc libmariadb-dev mariadb-client libxcb-cursor0
exit
```

`libmariadb-dev`, `gcc` et `python3-dev` servent à installer le module Python `mariadb` ; `libxcb-cursor0` permet à la fenêtre PyQt6 de s'ouvrir.

**Récupérer le projet.** prend le zip du prof donné sur moddle ou par un autre moyen sur ta vm appli et tape ce code :

```
cd ~/Téléchargements
unzip SAE-3.02-main.zip -d ~/Documents
cd ~/Documents/SAE-3.02-main
ls -a
```
ou bien fait juste l'extraction dans l'explorateur de fichier linux 

`ls -a` doit afficher `lancer.py`, `requirements.txt`, `.env.example`, `Code` et `sql`.

**Créer l'environnement Python et installer les dépendances** (en utilisateur normal, pas en root) :

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirement.txt
```
si il y a eu un probleme quelconque avec le venv veuillez bien supprimer le venv déjà en cour de production avec la commande (en su -):
```
rm -rf /home/toto/Documents/SAE-3.02-main/.venv
```


`(.venv)` apparaît alors au début de la ligne.

**Vérifier que la VM base répond** (remplace `IP_BASE`, puis entre le mot de passe de `sae`) :

```
mariadb -h IP_BASE -u sae -p carrefour
```

Si l'invite `MariaDB [carrefour]>` apparaît, tape `exit`.

**Créer le fichier `.env`**, à côté de `lancer.py` :

```
cp .env.example .env
nano .env
```

Remplis-le ainsi (avec ton IP et ton mot de passe), puis Ctrl+O, Entrée, Ctrl+X :

```
BDD_ACTIVE=oui
BDD_HOTE=IP_BASE
BDD_PORT=3306
BDD_UTILISATEUR=sae
BDD_MOT_DE_PASSE=ton_mot_de_passe
BDD_NOM=carrefour
BDD_DELAI_CONNEXION=3
```

**Lancer la simulation :**

```
python lancer.py feux
```

Remplace `feux` par `stop` ou `giratoire` pour ouvrir une autre simulation ; les trois boutons du haut permettent aussi d'en changer. Le terminal affiche `MariaDB : enregistrement dans sae@IP_BASE:3306/carrefour`.

## 4. Vérifier et démontrer

**Pendant la simulation**, le panneau de droite affiche **Base de données : connectée**. Le véhicule d'urgence (rouge, gyrophare) arrive environ 10 s après le lancement de chaque simulation.

**Voir les données enregistrées sur la VM base**, depuis la VM appli (fenêtre fermée, venv actif) :

```
python Code/consulter_bdd.py
python Code/consulter_bdd.py 3
python Code/consulter_bdd.py --prioritaires
```

La première liste les simulations, la deuxième détaille la simulation n°3 (véhicules, événements, statistiques), la troisième liste les véhicules d'urgence.


**Les fois suivantes**, sur la VM appli, trois commandes suffisent (MariaDB redémarre tout seul avec la VM base) :

```
cd ~/Documents/SAE-3.02-main
source .venv/bin/activate
python lancer.py feux
```

## 5. Dépannage

| Message ou symptôme | Cause probable | Solution |
| --- | --- | --- |
| Les deux VM ont la même IP | VM clonée avec la même adresse MAC | régénérer la MAC d'une VM (partie 1, étape 2) |
| `Can't connect to server on 'IP_BASE'` | `bind-address` non modifié, MariaDB pas redémarré, ou mauvaise IP | refaire la partie 2 et vérifier `0.0.0.0:3306` |
| `Access denied for user 'sae'@...` | mot de passe différent de celui du `.env`, ou utilisateur créé pour un autre réseau | recréer l'utilisateur et corriger le `.env` |
| `ensurepip is not available` | paquet `python3.11-venv` manquant | l'installer en root, supprimer `.venv`, le recréer |
| erreur pendant `pip install` sur `mariadb` | il manque `libmariadb-dev`, `gcc` ou `python3-dev` | les installer en root et relancer `pip` |
| `Could not load the Qt platform plugin "xcb"` | `libxcb-cursor0` manquant, ou VM sans bureau | installer le paquet ; sans bureau, `python lancer.py feux --console` |
| `ModuleNotFoundError: No module named ...` | nom de fichier avec une majuscule (Linux les distingue) | renommer le fichier en minuscules, comme dans l'import |
| Panneau « Base de données : désactivée » | pas de fichier `.env` à côté de `lancer.py` | le créer (partie 3) |




