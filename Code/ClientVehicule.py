import argparse
import math
import random
import socket
import threading
import time

from Conduite import B_CONF, S0
from Domaine import Vehicule, NORMAL, PRIORITAIRE
from Geometrie import DISPOSITIONS, LONGUEUR_VEHICULE
from Protocole import LecteurLignes, encoder

PAS_CLIENT = 0.05

MAX_VEHICULES = 14
INTERVALLE_APPARITION = (1.5, 3.5)    # secondes entre deux apparitions
ESPACE_APPARITION = 5.0               # le bras doit être libre sur cette distance pour qu'un véhicule y apparaisse
VITESSE_VOULUE = (2.5, 5.0)           # vitesse de croisière tirée au hasard (unités/s)
DELAI_PRIORITAIRE = 10.0


def vehicule_aleatoire(numero, prioritaire=False, rng=random, entree=None):
    if entree is None:
        entree = rng.randint(0, 3)
    sortie = rng.choice([i for i in range(4) if i != entree])
    if prioritaire:
        type_v, vitesse_max = PRIORITAIRE, VITESSE_VOULUE[1]
    else:
        type_v, vitesse_max = NORMAL, rng.uniform(*VITESSE_VOULUE)
    return Vehicule("v" + str(numero), entree, sortie, 0, 0, 0.6 * vitesse_max, type_v, vitesse_max)


def circuler(v, hote="127.0.0.1", port=5000, arret=None):
    arret = arret or threading.Event()
    lecteur = LecteurLignes()
    try:
        with socket.create_connection((hote, port), timeout=2.0) as s:
            s.settimeout(2.0)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # petits messages : pas d'attente
            dernier = time.monotonic()
            prochain = dernier
            while not arret.is_set() and not v.termine():
                s.sendall(encoder(v.vers_json()))
                reponse = None
                while reponse is None:
                    octets = s.recv(4096)
                    if not octets:
                        return  # le carrefour a fermé la connexion
                    messages = lecteur.alimenter(octets)
                    if messages:
                        reponse = messages[-1]
                if reponse.get("type") in (NORMAL, PRIORITAIRE):
                    v.type = reponse["type"]  # le carrefour peut refuser un 2e prioritaire
                if reponse.get("disposition") in DISPOSITIONS and reponse["disposition"] != v.disposition:
                    v.disposition = reponse["disposition"]  # croix ou giratoire : c'est le carrefour qui le dit
                maintenant = time.monotonic()
                dt = min(max(maintenant - dernier, 0.005), 0.2)
                dernier = maintenant
                v.deplacer(dt, reponse)
                prochain += PAS_CLIENT
                attente = prochain - time.monotonic()
                if attente > 0:
                    arret.wait(attente)
                else:
                    prochain = time.monotonic()  # en retard : on ne cherche pas à rattraper
    except (OSError, ValueError) as erreur:
        if not arret.is_set():
            print(f"véhicule {v.id} : connexion perdue ({erreur})")

class GenerateurTrafic:
    def __init__(self, hote="127.0.0.1", port=5000, rng=None, max_vehicules=MAX_VEHICULES):
        self.__hote = hote
        self.__port = port
        self.__rng = rng or random.Random()
        self.__max = max_vehicules
        self.__compteur = 0
        self.__prochaine_apparition = None
        self.__heure_prioritaire = None
        self.__prioritaire_cree = False
        self.__arret = threading.Event()
        self.__vivants = {}             # id -> (véhicule, thread)
        self.__fil = None

    # ------------------------------------------------------------------ décision
    def creer_vehicule(self, vivants, maintenant):
        if self.__prochaine_apparition is None:
            self.__prochaine_apparition = maintenant + self.__rng.uniform(0.5, 1.5)
            self.__heure_prioritaire = maintenant + DELAI_PRIORITAIRE

        if maintenant < self.__prochaine_apparition or len(vivants) >= self.__max:
            return None

        entrees = [0, 1, 2, 3]
        self.__rng.shuffle(entrees)
        for entree in entrees:
            file = [v for v in vivants if v.entree == entree]
            dernier = min(file, key=lambda v: v.x, default=None)    # le plus proche du point d'apparition
            if dernier is not None and dernier.x < ESPACE_APPARITION:
                continue                                            # bras occupé : on essaie un autre
            prioritaire = not self.__prioritaire_cree and maintenant >= self.__heure_prioritaire
            v = vehicule_aleatoire(self.__compteur, prioritaire, self.__rng, entree)
            if dernier is not None:                                 # ne jamais arriver plus vite que le véhicule devant
                ecart = dernier.x - LONGUEUR_VEHICULE
                v.vitesse = min(v.vitesse, dernier.vitesse + math.sqrt(2 * B_CONF * max(0.0, ecart - S0)))
            self.__compteur += 1
            if prioritaire:
                self.__prioritaire_cree = True                      # le seul de la simulation
            self.__prochaine_apparition = maintenant + self.__rng.uniform(*INTERVALLE_APPARITION)
            return v
        return None

    def reinitialiser(self):
        self.__compteur = 0
        self.__prochaine_apparition = None
        self.__heure_prioritaire = None
        self.__prioritaire_cree = False

    # ------------------------------------------------------------------ exécution
    def demarrer(self):
        self.arreter()
        self.reinitialiser()
        self.__arret = threading.Event()
        self.__vivants = {}
        self.__fil = threading.Thread(target=self.__boucle, args=(self.__arret, self.__vivants),
                                      name="generateur-trafic", daemon=True)
        self.__fil.start()
    def __boucle(self, arret, vivants):
        while not arret.is_set():
            for identifiant in [i for i, (_, fil) in vivants.items() if not fil.is_alive()]:
                del vivants[identifiant]
            v = self.creer_vehicule([v for v, _ in list(vivants.values())], time.monotonic())
            if v is not None:
                fil = threading.Thread(target=circuler, args=(v, self.__hote, self.__port, arret),
                                       name="vehicule-" + v.id, daemon=True)
                vivants[v.id] = (v, fil)
                fil.start()
            arret.wait(0.1)

    def arreter(self):
        self.__arret.set()
        fin = time.monotonic() + 2.0
        if self.__fil is not None and self.__fil is not threading.current_thread():
            self.__fil.join(2.0)           # d'abord le générateur : il ne crée plus de véhicule
        for _, fil in list(self.__vivants.values()):
            fil.join(max(0.0, fin - time.monotonic()))
        self.__vivants = {}
        self.__fil = None


def main():
    parser = argparse.ArgumentParser(description="Fait circuler des véhicules vers un carrefour déjà démarré.")
    parser.add_argument("--hote", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--duree", type=float, default=None, help="durée en secondes (sinon jusqu'à Ctrl+C)")
    args = parser.parse_args()
    generateur = GenerateurTrafic(args.hote, args.port)
    generateur.demarrer()
    print(f"Véhicules lancés vers {args.hote}:{args.port} (Ctrl+C pour arrêter)")
    try:
        if args.duree:
            time.sleep(args.duree)
        else:
            threading.Event().wait()            # attend indéfiniment, jusqu'à Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        generateur.arreter()


if __name__ == "__main__":
    main()
