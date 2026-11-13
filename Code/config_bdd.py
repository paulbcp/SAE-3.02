
import os
from dataclasses import dataclass, field

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER_ENV = os.path.join(RACINE, ".env")
VARIABLES = ("BDD_ACTIVE", "BDD_HOTE", "BDD_PORT", "BDD_UTILISATEUR", "BDD_MOT_DE_PASSE",
             "BDD_NOM", "BDD_DELAI_CONNEXION")
NON = ("non", "no", "false", "faux", "0", "off")


@dataclass(frozen=True)
class ConfigBDD:
    hote: str
    port: int
    utilisateur: str
    mot_de_passe: str = field(repr=False)        # jamais affiché
    base: str
    delai_connexion: float = 3.0

    def __str__(self):
        return f"{self.utilisateur}@{self.hote}:{self.port}/{self.base}"


def lire_fichier_env(fichier):
    valeurs = {}
    with open(fichier, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            nom, valeur = ligne.split("=", 1)
            valeur = valeur.strip()
            if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                valeur = valeur[1:-1]                 # "valeur" ou 'valeur' : on retire les guillemets
            valeurs[nom.strip()] = valeur
    return valeurs


def lire_valeurs(fichier=FICHIER_ENV):
    valeurs = {}
    if os.path.exists(fichier):
        valeurs.update(lire_fichier_env(fichier))
    valeurs.update({k: os.environ[k] for k in VARIABLES if k in os.environ})
    return valeurs


def charger_config(fichier=FICHIER_ENV, bavard=True):
    def desactiver(raison):
        if bavard:
            print("MariaDB désactivée :", raison)
        return None

    valeurs = lire_valeurs(fichier)
    if not valeurs:
        return desactiver("pas de fichier .env (copier .env.example en .env pour l'activer)")
    if valeurs.get("BDD_ACTIVE", "oui").strip().lower() in NON:
        return desactiver("BDD_ACTIVE=non dans .env")
    manquantes = [nom for nom in ("BDD_UTILISATEUR", "BDD_NOM") if not valeurs.get(nom)]
    if manquantes:
        return desactiver(f"{', '.join(manquantes)} absent(s) du fichier .env")
    try:
        port = int(valeurs.get("BDD_PORT", 3306))
        delai = float(valeurs.get("BDD_DELAI_CONNEXION", 3))
    except ValueError:
        return desactiver("BDD_PORT et BDD_DELAI_CONNEXION doivent être des nombres")
    return ConfigBDD(hote=valeurs.get("BDD_HOTE", "127.0.0.1"), port=port,
                     utilisateur=valeurs["BDD_UTILISATEUR"],
                     mot_de_passe=valeurs.get("BDD_MOT_DE_PASSE", ""),
                     base=valeurs["BDD_NOM"], delai_connexion=delai)