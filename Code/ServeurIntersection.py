import socket
import json
import select
from Domaine import Vehicule


class ServeurIntersection:
    def __init__(self, controleur, rappel=None, stats=None, hote="127.0.0.1", port=5000):
        self.__controleur = controleur
        self.__rappel = rappel
        self.__stats = stats
        self.__hote = hote
        self.__port = port
        self.__socket_serveur = None
        self.__clients = []
        self.__vehicules = {}
        self.__actif = False

    @property
    def controleur(self):
        return self.__controleur

    @controleur.setter
    def controleur(self, nouveau):
        self.__controleur = nouveau

    def demarrer(self):
        self.__socket_serveur = socket.socket()
        self.__socket_serveur.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__socket_serveur.bind((self.__hote, self.__port))
        self.__socket_serveur.listen(5)
        self.__actif = True

    def accepter(self):
        conn, adresse = self.__socket_serveur.accept()
        self.__clients.append(conn)

    def boucle(self):
        while self.__actif:
            lisibles, _, _ = select.select([self.__socket_serveur] + self.__clients, [], [], 0.1)
            for s in lisibles:
                if s is self.__socket_serveur:
                    self.accepter()
                else:
                    self.lire(s)

    def arreter(self):
        self.__actif = False

    def lire(self, client):
        try:
            donnees = client.recv(1024)
        except OSError:
            donnees = b""
        if not donnees:
            self.__clients.remove(client)
            self.__vehicules.pop(client, None)
            client.close()
            self.__controleur.evaluer(list(self.__vehicules.values()))
            self.prevenir()
            return
        d = json.loads(donnees.decode())
        self.__vehicules[client] = Vehicule(d["id"], d["entree"], d["sortie"],
                                            d["x"], d["y"], d["vitesse"], d["type"])
        self.__controleur.evaluer(list(self.__vehicules.values()))
        self.envoyer_etat(client)
        self.prevenir()

    def envoyer_etat(self, client):
        etat = [{"id_entree": f.id_entree, "etat": f.etat} for f in self.__controleur.feux]
        client.send(json.dumps(etat).encode())

    def prevenir(self):
        vehicules = list(self.__vehicules.values())
        stats = {}
        if self.__stats:
            try:
                stats = self.__stats.enregistrer_tick(vehicules, type(self.__controleur).__name__)
            except Exception as erreur:
                print("statistiques :", erreur)
        if self.__rappel:
            self.__rappel(vehicules, self.__controleur.feux, stats)