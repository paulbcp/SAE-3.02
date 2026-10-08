import sys
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QBrush, QPen
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QPushButton,
    QLabel,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QApplication,
)
from Domaine import (
    ControleurFeux,
    ControleurGiratoireFeux,
    ControleurStop,
    PRIORITAIRE,
)
from Simulationthread import SimulationThread

# ------------------------------------------------------------------------------

STOP = "stop"
FEUX = "feux"
GIRATOIRE = "giratoire"

TYPE_CARREFOUR = {
    STOP: "Carrefour à stop",
    FEUX: "Carrefour à feux",
    GIRATOIRE: "Carrefour à giratoire",
}

CONTROLEUR = {
    STOP: ControleurStop,
    FEUX: ControleurFeux,
    GIRATOIRE: ControleurGiratoireFeux,
}

COULEUR_FEU = {"rouge": "#FA0000", "orange": "#FA7500", "vert": "#32FA00"}


class FenetrePrincipale(QMainWindow):
    LARGEUR = 560      # taille de la scène
    HAUTEUR = 480
    ROUTE = 100        # largeur des routes

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulation de carrefour connecté")
        self.setFixedSize(QSize(800, 600))

        # --- données affichées ---
        self.vehicules_affiches = []
        self.carrefour = GIRATOIRE
        self.controleur = CONTROLEUR[self.carrefour]("carrefour_1")
        self.etats_feux = [{"id_entree": f.id_entree, "etat": f.etat}
                           for f in self.controleur.feux]

        # --- scène au centre ---
        self.scene = QGraphicsScene(0, 0, self.LARGEUR, self.HAUTEUR)
        self.view = QGraphicsView(self.scene)

        # --- boutons du haut (type de carrefour) ---
        self.boutons = {}
        barre = QHBoxLayout()
        for type_c, texte in TYPE_CARREFOUR.items():
            bouton = QPushButton(texte)
            bouton.setCheckable(True)
            bouton.clicked.connect(lambda checked, t=type_c: self.changer_carrefour(t))
            self.boutons[type_c] = bouton
            barre.addWidget(bouton)
        self.boutons[self.carrefour].setChecked(True)

        # --- statistiques à droite ---
        self.lbl_nb = QLabel("0")
        self.lbl_vitesse = QLabel("0.0")
        self.lbl_prio = QLabel("0")
        self.lbl_accident = QLabel("-")
        stats = QFormLayout()
        stats.addRow("Véhicules :", self.lbl_nb)
        stats.addRow("Vitesse moyenne :", self.lbl_vitesse)
        stats.addRow("Prioritaires :", self.lbl_prio)
        stats.addRow("Taux d'accident :", self.lbl_accident)
        panneau = QWidget()
        panneau.setLayout(stats)
        panneau.setFixedWidth(200)

        # --- assemblage ---
        milieu = QHBoxLayout()
        milieu.addWidget(self.view)
        milieu.addWidget(panneau)
        principal = QVBoxLayout()
        principal.addLayout(barre)
        principal.addLayout(milieu)
        centre = QWidget()
        centre.setLayout(principal)
        self.setCentralWidget(centre)

        self.redessiner()

        # --- thread du serveur ---
        self.simulation = SimulationThread(self.controleur)
        self.simulation.maj.connect(self.on_maj)
        self.simulation.start()

    # ---------------------------------------------------------------- slots
    def on_maj(self, vehicules, feux):
        """Appelé à chaque signal du thread (dans le thread principal)."""
        self.vehicules_affiches = vehicules
        self.etats_feux = feux
        self.mettre_a_jour_stats()
        self.redessiner()

    def changer_carrefour(self, type_c):
        self.carrefour = type_c
        self.controleur = CONTROLEUR[type_c]("carrefour_1")
        self.simulation.serveur.controleur = self.controleur
        for t, bouton in self.boutons.items():
            bouton.setChecked(t == type_c)

    def closeEvent(self, event):
        self.simulation.serveur.arreter()
        self.simulation.wait(1000)
        super().closeEvent(event)

    # ---------------------------------------------------------------- stats
    def mettre_a_jour_stats(self):
        nb = len(self.vehicules_affiches)
        if nb:
            vitesse = sum(v["vitesse"] for v in self.vehicules_affiches) / nb
        else:
            vitesse = 0
        prio = sum(1 for v in self.vehicules_affiches if v["type"] == PRIORITAIRE)
        self.lbl_nb.setText(str(nb))
        self.lbl_vitesse.setText(f"{vitesse:.1f}")
        self.lbl_prio.setText(str(prio))

    # -------------------------------------------------------------- dessin
    def position_feu(self, entree):
        cx, cy, r = self.LARGEUR / 2, self.HAUTEUR / 2, self.ROUTE / 2 + 14
        return {0: (cx - r, cy - r), 1: (cx + r, cy - r),
                2: (cx + r, cy + r), 3: (cx - r, cy + r)}[entree]

    def position_vehicule(self, entree, x):
        """x va de 0 (bord de la scène) à 10 (devant le carrefour)."""
        t = min(max(x / 10, 0), 1)
        cx, cy, decalage = self.LARGEUR / 2, self.HAUTEUR / 2, self.ROUTE / 4
        dist_v = cy - self.ROUTE / 2
        dist_h = cx - self.ROUTE / 2
        return {0: (cx - decalage, t * dist_v),
                1: (self.LARGEUR - t * dist_h, cy - decalage),
                2: (cx + decalage, self.HAUTEUR - t * dist_v),
                3: (t * dist_h, cy + decalage)}[entree]

    def redessiner(self):
        self.scene.clear()
        cx, cy, r = self.LARGEUR / 2, self.HAUTEUR / 2, self.ROUTE
        sans_contour = QPen(Qt.PenStyle.NoPen)
        route = QBrush(QColor("#555555"))
        self.scene.addRect(0, cy - r / 2, self.LARGEUR, r, sans_contour, route)
        self.scene.addRect(cx - r / 2, 0, r, self.HAUTEUR, sans_contour, route)

        for feu in self.etats_feux:
            if feu["id_entree"] in range(4):
                x, y = self.position_feu(feu["id_entree"])
                self.scene.addEllipse(x - 10, y - 10, 20, 20, QPen(Qt.GlobalColor.black),
                                      QBrush(QColor(COULEUR_FEU[feu["etat"]])))

        for v in self.vehicules_affiches:
            if v["entree"] in range(4):
                x, y = self.position_vehicule(v["entree"], v["x"])
                couleur = Qt.GlobalColor.red if v["type"] == PRIORITAIRE else Qt.GlobalColor.black
                self.scene.addRect(x - 9, y - 9, 18, 18, QPen(Qt.GlobalColor.white),
                                   QBrush(couleur))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = FenetrePrincipale()
    fenetre.show()
    sys.exit(app.exec())