import json

TAILLE_MAX = 65536      # une « ligne » plus longue n'est pas un message valide


def encoder(message):
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


class LecteurLignes:

    def __init__(self):
        self.__tampon = bytearray()
        self.invalides = 0          # nombre de lignes ignorées car illisibles

    def alimenter(self, octets):
        self.__tampon += octets
        messages = []
        while True:
            fin = self.__tampon.find(b"\n")
            if fin < 0:
                break