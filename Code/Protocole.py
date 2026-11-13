import json

TAILLE_MAX = 65536      # une « ligne » plus longue n'est pas un message valide


def encoder(message):
    """dict -> octets prêts à être envoyés (une ligne)."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


class LecteurLignes:
    """Reconstitue les messages à partir des morceaux d'octets reçus sur une connexion."""

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
            ligne = bytes(self.__tampon[:fin])
            del self.__tampon[:fin + 1]
            if not ligne.strip():
                continue
            try:
                message = json.loads(ligne.decode("utf-8"))
            except ValueError:      # JSONDecodeError et UnicodeDecodeError en héritent
                self.invalides += 1
                continue
            if isinstance(message, dict):
                messages.append(message)
            else:
                self.invalides += 1
        if len(self.__tampon) > TAILLE_MAX:
            raise ValueError("message trop long")
        return messages
