import socket
import json
import random
import time
from Domaine import Vehicule, NORMAL, PRIORITAIRE


def vehicule_aleatoire(numero):
    entree = random.randint(0, 3)
    sortie = random.choice([i for i in range(4) if i != entree])
    if random.random() < 0.2:
        type_v = PRIORITAIRE
    else:
        type_v = NORMAL
    return Vehicule("v" + str(numero), entree, sortie, 0, 0, random.randint(1, 5), type_v)


def circuler(v):
    s = socket.socket()
    s.connect(("127.0.0.1", 5000))
    while v.x < 10:
        s.send(json.dumps(v.vers_json()).encode())
        feux = json.loads(s.recv(1024).decode())
        etats = [f["etat"] for f in feux]
        print(v.id, v.type, "entrée", v.entree, "x =", v.x, etats)
        v.deplacer(0.5)
        time.sleep(0.5)
    s.close()
