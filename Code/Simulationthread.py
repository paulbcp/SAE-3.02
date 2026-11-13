from PyQt6.QtCore import QThread, pyqtSignal
from ServeurIntersection import ServeurIntersection


def ouvrir_journal():
    try:
        from Journal import ouvrir_journal as ouvrir
    except ImportError as erreur:
        print("MariaDB désactivée :", erreur)
        return None
    return ouvrir()


class SimulationThread(QThread):
    maj = pyqtSignal(list, list, dict)   # véhicules, feux, stats

    def __init__(self, controleur, port=5000, avec_bdd=True):
        super().__init__()
        journal = ouvrir_journal() if avec_bdd else None
        self.serveur = ServeurIntersection(controleur, self.envoyer, journal, port=port)

    def envoyer(self, vehicules, feux, stats):
        self.maj.emit([v.vers_json() for v in vehicules],
                      [{"id_entree": f.id_entree, "etat": f.etat} for f in feux],
                      stats)

    def run(self):
        self.serveur.demarrer()      # sans effet s'il a déjà été démarré par l'interface
        self.serveur.boucle()