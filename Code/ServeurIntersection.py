import argparse
import os
import select
import socket
import threading
import time

from Domaine import CONTROLEURS, GIRATOIRE, NORMAL, TYPES_CARREFOUR, Vehicule, type_carrefour
from Protocole import LecteurLignes, encoder

PERIODE_EVALUATION = 0.05     # s : réévaluation des feux même sans message
PERIODE_RAPPEL = 1 / 30       # s : au plus 30 mises à jour de l'affichage par seconde
PERIODE_MESURE = 1.0          # s : une mesure statistique par seconde (base de données)
ATTENTE_SELECT = 0.02         # s : délai maximal d'attente d'un message
ESSAIS_PORTS = 10             # si le port demandé est pris, on essaie les 9 suivants


class JournalVide:

    def debut_simulation(self, type_carrefour, maintenant):
        pass

    def fin_simulation(self, maintenant):
        pass

    def vehicule(self, cle, vehicule, maintenant):
        pass

    def depart(self, cle, maintenant):
        pass

    def feux(self, feux, prioritaire, maintenant):
        pass

    def prioritaire_refuse(self, cle, vehicule, maintenant):
        pass

    def mesure(self, vehicules, maintenant):
        return {}

    def fermer(self):
        pass


class ServeurIntersection:
    def __init__(self, controleur, rappel=None, journal=None, hote="127.0.0.1", port=5000):
        self.__controleur = controleur
        self.__rappel = rappel                  # appelé avec (véhicules, feux, stats) pour l'affichage
        self.__journal = journal or JournalVide()
        self.__hote = hote
        self.__port = port
        self.__socket_serveur = None
        self.__clients = []
        self.__lecteurs = {}                    # connexion -> LecteurLignes (découpage des messages)
        self.__vehicules = {}                   # connexion -> Vehicule, dans l'ordre d'arrivée
        self.__identifiants = {}                # connexion -> identifiant unique du véhicule
        self.__renommages = 0
        self.__connexion_prioritaire = None     # connexion du seul véhicule prioritaire accepté
        self.__refus_signales = set()
        self.__actif = False
        self.__generation = 0                   # numéro de la simulation en cours (+1 à chaque réinitialisation)
        self.__derniere_mesure = {}
        self.__verrou = threading.RLock()       # protège les demandes venant des autres threads
        self.__demandes = []                    # réinitialisations demandées par un autre thread
        self.__fil_boucle = None                # thread qui exécute boucle()

    # ------------------------------------------------------------------ propriétés
    @property
    def controleur(self):
        return self.__controleur

    @controleur.setter
    def controleur(self, nouveau):
        self.reinitialiser(nouveau)

    @property
    def port(self):
        return self.__port

    @property
    def generation(self):
        return self.__generation

    @property
    def actif(self):
        return self.__actif

    # ------------------------------------------------------------------ démarrage / arrêt
    def demarrer(self):
        if self.__actif:
            return self.__port
        erreur = None
        for port in range(self.__port, self.__port + ESSAIS_PORTS):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if os.name != "nt":
                    # Linux/macOS : permet de relancer tout de suite après une fermeture.
                    # (Sous Windows, SO_REUSEADDR laisserait deux serveurs écouter le MÊME port.)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.__hote, port))
                s.listen(16)
            except OSError as e:
                s.close()
                erreur = e
                continue
            self.__socket_serveur = s
            self.__port = port
            self.__actif = True
            self.__journal.debut_simulation(type_carrefour(self.__controleur), time.monotonic())
            return port
        raise OSError(f"aucun port libre entre {self.__port} et {self.__port + ESSAIS_PORTS - 1} "
                      f"({erreur})")

    def arreter(self):
        self.__actif = False
        with self.__verrou:
            if self.__fil_boucle is None:       # pas de boucle en cours : on ferme nous-mêmes
                self.__fermer()

    def accepter(self):
        try:
            conn, _ = self.__socket_serveur.accept()
        except OSError:
            return
        conn.settimeout(0.5)       # un véhicule qui ne lit plus ses réponses ne bloque pas le carrefour
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # petits messages : pas d'attente
        self.__clients.append(conn)
        self.__lecteurs[conn] = LecteurLignes()

    def boucle(self):
        with self.__verrou:
            self.__fil_boucle = threading.current_thread()
        prochaine_evaluation = prochain_rappel = prochaine_mesure = time.monotonic()
        try:
            while self.__actif:
                self.__traiter_demandes()
                try:
                    lisibles, _, _ = select.select([self.__socket_serveur] + self.__clients, [], [],
                                                   ATTENTE_SELECT)
                except (OSError, ValueError):
                    # une connexion invalide dans la liste : on la retire et on recommence
                    for client in [c for c in self.__clients if c.fileno() < 0]:
                        self.deconnecter(client)
                    continue
                for s in lisibles:
                    if s is self.__socket_serveur:
                        self.accepter()
                    elif s in self.__lecteurs:
                        self.lire(s)
                maintenant = time.monotonic()
                if maintenant >= prochaine_evaluation:
                    self.evaluer()
                    prochaine_evaluation = maintenant + PERIODE_EVALUATION
                if maintenant >= prochaine_mesure:
                    self.mesurer(maintenant)
                    prochaine_mesure = maintenant + PERIODE_MESURE
                if maintenant >= prochain_rappel:
                    self.prevenir()
                    prochain_rappel = maintenant + PERIODE_RAPPEL
        finally:
            with self.__verrou:
                self.__traiter_demandes()
                self.__fermer()
                self.__fil_boucle = None

    # ------------------------------------------------------------------ réinitialisation
    def reinitialiser(self, controleur, delai=2.0):
        fait = threading.Event()
        with self.__verrou:
            boucle = self.__fil_boucle
            if boucle is None or boucle is threading.current_thread():
                self.__appliquer_reinitialisation(controleur)    # pas de boucle concurrente
                return
            self.__demandes.append((controleur, fait))
        if not fait.wait(delai):
            raise TimeoutError("le serveur n'a pas répondu à la demande de réinitialisation")

    def __traiter_demandes(self):
        with self.__verrou:
            demandes, self.__demandes = self.__demandes, []
        for controleur, fait in demandes:
            self.__appliquer_reinitialisation(controleur)
            fait.set()

    def __appliquer_reinitialisation(self, controleur):
        maintenant = time.monotonic()
        self.__journal.fin_simulation(maintenant)
        for client in list(self.__clients):
            self.__fermer_connexion(client)
        self.__clients = []
        self.__lecteurs = {}
        self.__vehicules = {}
        self.__identifiants = {}
        self.__connexion_prioritaire = None
        self.__refus_signales = set()
        # on garde l'état de la base affiché, mais pas le taux d'accident de l'ancien type de carrefour
        self.__derniere_mesure = {k: v for k, v in self.__derniere_mesure.items() if k == "bdd"}
        self.__controleur = controleur
        self.__controleur.initialiser()
        self.__generation += 1
        if self.__actif:
            self.__journal.debut_simulation(type_carrefour(controleur), maintenant)
        self.evaluer()
        self.prevenir()

    # ------------------------------------------------------------------ messages des véhicules
    def lire(self, client):
        try:
            donnees = client.recv(4096)
        except OSError:
            donnees = b""
        if not donnees:
            self.deconnecter(client)
            return
        try:
            messages = self.__lecteurs[client].alimenter(donnees)
        except ValueError:                  # ligne démesurée : ce client ne parle pas notre protocole
            self.deconnecter(client)
            return
        maintenant = time.monotonic()
        for message in messages:
            try:
                # la forme du carrefour est celle du contrôleur, quoi qu'annonce le véhicule
                vehicule = Vehicule.depuis_json(message, self.__controleur.DISPOSITION)
            except ValueError as erreur:
                print("message de véhicule ignoré :", erreur)
                continue
            vehicule.id = self.__identifiant(client, vehicule.id)
            refuse = self.__verifier_prioritaire(client, vehicule)
            self.__vehicules[client] = vehicule
            self.__journal.vehicule(id(client), vehicule, maintenant)
            if refuse:
                self.__journal.prioritaire_refuse(id(client), vehicule, maintenant)
        if messages and client in self.__vehicules:
            # Une seule réponse par lot : un véhicule envoie un message puis attend sa réponse.
            vehicules = list(self.__vehicules.values())
            self.__controleur.evaluer(vehicules)
            self.envoyer_consigne(client, self.__vehicules[client], vehicules)

    def __identifiant(self, client, demande):
        """Identifiant unique du véhicule de cette connexion. Deux clients lancés séparément
        peuvent choisir le même (« v0 ») : le second est renommé, sinon le carrefour les
        confondrait (feux, autorisations de passage, priorité)."""
        identifiant = self.__identifiants.get(client)
        if identifiant is None:
            identifiant = str(demande)
            if identifiant in self.__identifiants.values():
                self.__renommages += 1
                identifiant = f"{identifiant}#{self.__renommages}"
            self.__identifiants[client] = identifiant
        return identifiant

    def __verifier_prioritaire(self, client, vehicule):
        if not vehicule.est_prioritaire():
            return False
        if self.__connexion_prioritaire is None:
            self.__connexion_prioritaire = client
            return False
        if self.__connexion_prioritaire is client:
            return False
        vehicule.type = NORMAL
        if client in self.__refus_signales:
            return False
        self.__refus_signales.add(client)
        print(f"véhicule {vehicule.id} : un véhicule prioritaire a déjà circulé dans cette "
              "simulation, il est traité comme un véhicule normal")
        return True

    def envoyer_consigne(self, client, vehicule, vehicules):
        consigne = self.__controleur.consigne(vehicule, vehicules)
        consigne["type"] = vehicule.type          # le type retenu par le carrefour
        try:
            client.sendall(encoder(consigne))
        except OSError:
            self.deconnecter(client)

    def deconnecter(self, client):
        self.__fermer_connexion(client)
        if client in self.__clients:
            self.__clients.remove(client)
        self.__lecteurs.pop(client, None)
        self.__identifiants.pop(client, None)
        if self.__vehicules.pop(client, None) is not None:
            self.__journal.depart(id(client), time.monotonic())

    @staticmethod
    def __fermer_connexion(client):
        try:
            client.close()
        except OSError:
            pass

    def __fermer(self):
        for client in list(self.__clients):
            self.__fermer_connexion(client)
        self.__clients = []
        self.__lecteurs = {}
        self.__vehicules = {}
        self.__identifiants = {}
        if self.__socket_serveur is not None:
            self.__fermer_connexion(self.__socket_serveur)
            self.__socket_serveur = None
            self.__journal.fin_simulation(time.monotonic())
            self.__journal.fermer()

    # ------------------------------------------------------------------ évaluation / affichage
    def evaluer(self):
        """Réévalue les feux et les autorisations de passage, et journalise ce qui a changé."""
        vehicules = list(self.__vehicules.values())
        self.__controleur.evaluer(vehicules)
        self.__journal.feux(self.__controleur.feux, self.__controleur.trouver_prioritaire(vehicules),
                            time.monotonic())

    def mesurer(self, maintenant):
        try:
            self.__derniere_mesure = self.__journal.mesure(list(self.__vehicules.values()), maintenant)
        except Exception as erreur:         # la base ne doit jamais arrêter la simulation
            print("statistiques :", erreur)
            self.__derniere_mesure = {}

    def prevenir(self):
        if self.__rappel:
            stats = dict(self.__derniere_mesure, generation=self.__generation)
            self.__rappel(list(self.__vehicules.values()), self.__controleur.feux, stats)


def main():
    parser = argparse.ArgumentParser(description="Carrefour connecté sans interface graphique (console).")
    parser.add_argument("--carrefour", choices=list(CONTROLEURS), default=GIRATOIRE)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--trafic", action="store_true",
                        help="faire aussi circuler des véhicules (sinon : lancer ClientVehicule.py à part)")
    parser.add_argument("--duree", type=float, default=None, help="durée en secondes (sinon jusqu'à Ctrl+C)")
    parser.add_argument("--sans-bdd", action="store_true", help="ne pas utiliser MariaDB")
    args = parser.parse_args()

    dernier_affichage = [0.0]

    def afficher(vehicules, feux, stats):
        if time.monotonic() - dernier_affichage[0] >= 1.0:
            dernier_affichage[0] = time.monotonic()
            nb = len(vehicules)
            vitesse = sum(v.vitesse for v in vehicules) / nb if nb else 0.0
            prio = sum(1 for v in vehicules if v.est_prioritaire())
            print(f"feux {[f.etat for f in feux]}  véhicules {nb} (prioritaire : {prio})  "
                  f"vitesse moyenne {vitesse:.1f}")

    journal = None
    if not args.sans_bdd:
        from Journal import ouvrir_journal
        journal = ouvrir_journal()
    serveur = ServeurIntersection(CONTROLEURS[args.carrefour]("carrefour_1"), afficher, journal, port=args.port)
    port = serveur.demarrer()
    fil = threading.Thread(target=serveur.boucle, name="serveur", daemon=True)
    fil.start()
    print(f"{TYPES_CARREFOUR[args.carrefour]} à l'écoute sur 127.0.0.1:{port} (Ctrl+C pour arrêter)")
    generateur = None
    if args.trafic:
        from ClientVehicule import GenerateurTrafic
        generateur = GenerateurTrafic(port=port)
        generateur.demarrer()
    try:
        if args.duree:
            time.sleep(args.duree)
        else:
            threading.Event().wait()            # attend indéfiniment, jusqu'à Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        if generateur is not None:
            generateur.arreter()
        serveur.arreter()
        fil.join(2.0)


if __name__ == "__main__":
    main()
