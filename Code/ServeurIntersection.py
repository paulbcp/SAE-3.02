import socket
import json
import select

class ServeurIntersection:
    def __init__(self, controleur, hote="127.0.0.1", port=5000):
        self.__controleur = controleur
        self.__hote = hote
        self.__port = port
        self.__socket_serveur = None
        self.__clients = []
        self.__vehicules = {}
        self.__actif = False
    def demarrer(self):
        self.__socket_serveur = socket.socket()
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
        donnees = client.recv(1024)
        if not donnees:
            self.__clients.remove(client)
            client.close()
            return
        print("reçu :", donnees.decode())

    def envoyer_etat(self):
        etat = [{"id_entree": f.id_entree, "etat": f.etat} for f in self.__controleur.feux]
        message = json.dumps(etat).encode()
        for client in self.__clients:
            client.send(message)