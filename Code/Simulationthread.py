from PyQt6.QtCore import QThread, pyqtSignal
from ServeurIntersection import ServeurIntersection
from base_stats import BaseStats


class SimulationThread(QThread):
    maj = pyqtSignal(list, list, dict)   # véhicules, feux, stats

    def __init__(self, controleur):
        super().__init__()
        try:
            stats = BaseStats()
        except Exception as erreur:
            print("MariaDB indisponible, statistiques désactivées :", erreur)
            stats = None
        self.serveur = ServeurIntersection(controleur, self.envoyer, stats)

    def envoyer(self, vehicules, feux, stats):
        self.maj.emit([v.vers_json() for v in vehicules],
                      [{"id_entree": f.id_entree, "etat": f.etat} for f in feux],
                      stats)

    def run(self):
        self.serveur.demarrer()
        self.serveur.boucle()