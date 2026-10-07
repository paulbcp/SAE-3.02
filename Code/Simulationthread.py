from PyQt6.QtCore import QThread, pyqtSignal
from ServeurIntersection import ServeurIntersection


class SimulationThread(QThread):
    maj = pyqtSignal(list, list)   # véhicules, feux

    def __init__(self, controleur):
        super().__init__()
        self.serveur = ServeurIntersection(controleur, self.envoyer)

    def envoyer(self, vehicules, feux):
        self.maj.emit([v.vers_json() for v in vehicules],
                      [{"id_entree": f.id_entree, "etat": f.etat} for f in feux])

    def run(self):
        self.serveur.demarrer()
        self.serveur.boucle()