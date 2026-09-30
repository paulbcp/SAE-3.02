import Domaine
import socket
import json
import select
import threading

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
            