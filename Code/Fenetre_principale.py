import sys
import math
import time

from PyQt6.QtCore import Qt, QSize, QRectF, QPointF
from PyQt6.QtGui import QColor, QBrush, QFont, QPen, QPainter, QPainterPath, QPolygonF
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QPushButton,
    QButtonGroup,
    QLabel,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QApplication,
)
from ClientVehicule import GenerateurTrafic
    CONTROLEURS as CONTROLEUR,
    TYPES_CARREFOUR as TYPE_CARREFOUR,
    STOP,
    FEUX,
    GIRATOIRE,
    PANNEAU_STOP,
    PRIORITAIRE,
)
from Geometrie import (LARGEUR, HAUTEUR, ROUTE, PX_PAR_UNITE, DISPOSITION_GIRATOIRE, DISTANCE_LIGNE,
                       RAYON_EXTERIEUR, RAYON_ILOT, trajectoire)
from Simulationthread import SimulationThread

# ------------------------------------------------------------------------------

__all__ = ["FenetrePrincipale", "STOP", "FEUX", "GIRATOIRE", "TYPE_CARREFOUR", "CONTROLEUR"]

COULEUR_FEU = {"rouge": "#FA0000", "orange": "#FA7500", "vert": "#32FA00"}
COULEUR_ETEINT = {"rouge": "#4A1010", "orange": "#4A3010", "vert": "#104A10"}


class FenetrePrincipale(QMainWindow):
    LARGEUR = LARGEUR      # taille de la scène
    HAUTEUR = HAUTEUR
    ROUTE = ROUTE        # largeur des routes

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulation de carrefour connecté")
        self.setFixedSize(QSize(800, 600))

        # --- données affichées ---
        self.vehicules_affiches = []
        self.carrefour = carrefour
        self.controleur = CONTROLEUR[self.carrefour]("carrefour_1")
        self.etats_feux = [{"id_entree": f.id_entree, "etat": f.etat}
                           for f in self.controleur.feux]
        self.generation = 0
        self.element_dynamique = []
        self.element_fixes = []
        self.disposition_dessinee = None

        # --- scène au centre ---
        self.scene = QGraphicsScene(0, 0, self.LARGEUR, self.HAUTEUR)
        self.scene.setBackgroundBrush(QColor("#DDDECF"))
        self.view = QGraphicsView(self.scene)

        # --- boutons du haut (type de carrefour) ---
        self.boutons = {}
        self.groupe_boutons = QButtonGroup(self)
        self.groupe_boutons.setExclusive(True)
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
        stats.addRow("Serveur :", self.lbl_serveur)
        stats.addRow("Base de données :", self.lbl_bdd)
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

        self.dessiner_carrefour()
        self.redessiner()
        self.mettre_a_jour_titre()

        # --- thread du serveur ---
        self.simulation = SimulationThread(self.controleur, port, avec_bdd)
        self.simulation.maj.connect(self.on_maj)
        self.trafic = None
        try:
            port_reel = self.simulation.serveur.demarrer()
        except OSError as erreur:
            print("Le carrefour n'a pas pu démarrer :", erreur)
            self.lbl_serveur.setText("erreur (voir console)")
            return
        self.lbl_serveur.setText(f"port {port_reel}")
        self.simulation.start()
        if avec_trafic:
            self.trafic = GenerateurTrafic(port=port_reel)
            self.trafic.demarrer()
    # ---------------------------------------------------------------- slots
    def on_maj(self, vehicules, feux, stats):
        self.vehicules_affiches = vehicules
        self.etats_feux = feux
        self.mettre_a_jour_stats()
        if "taux_accident" in stats:
            self.lbl_accident.setText(f"{stats['taux_accident']:.1f} %")
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
        cx, cy = self.LARGEUR / 2, self.HAUTEUR / 2
        r = self.ROUTE / 2 + 14
        return {0: (cx - r, cy - r - 28),
                1: (cx + r + 28, cy - r),
                2: (cx + r, cy + r + 28),
                3: (cx - r - 28, cy + r)}[entree]

    def position_vehicule(self, entree, x):
        """x va de 0 (bord de la scène) à 10 (devant la ligne d'arrêt)."""
        t = min(max(x / 10, 0), 1)
        cx, cy, decalage = self.LARGEUR / 2, self.HAUTEUR / 2, self.ROUTE / 4
        dist_v = cy - self.ROUTE / 2 - 24
        dist_h = cx - self.ROUTE / 2 - 24
        return {0: (cx - decalage, t * dist_v),
                1: (self.LARGEUR - t * dist_h, cy - decalage),
                2: (cx + decalage, self.HAUTEUR - t * dist_v),
                3: (t * dist_h, cy + decalage)}[entree]

    def dessiner_route(self):
        cx, cy = self.LARGEUR / 2, self.HAUTEUR / 2
        r = self.ROUTE / 2       # demi-largeur des routes
        rc = 24                  # rayon des coins arrondis
        sans = QPen(Qt.PenStyle.NoPen)
        gris = QBrush(QColor("#B9B9B9"))
        noir = QPen(QColor("#222222"), 2)

        # les deux routes
        self.scene.addRect(0, cy - r, self.LARGEUR, 2 * r, sans, gris)
        self.scene.addRect(cx - r, 0, 2 * r, self.HAUTEUR, sans, gris)

        # coins arrondis : (centre x, centre y, sens x, sens y, angle de départ)
        coins = [(cx - r - rc, cy - r - rc, 1, 1, 0),
                 (cx + r + rc, cy - r - rc, -1, 1, 270),
                 (cx + r + rc, cy + r + rc, -1, -1, 180),
                 (cx - r - rc, cy + r + rc, 1, -1, 90)]
        for ccx, ccy, sx, sy, angle in coins:
            carre = QPainterPath()
            carre.addRect(QRectF(min(ccx, ccx + sx * rc), min(ccy, ccy + sy * rc), rc, rc))
            cercle = QPainterPath()
            zone = QRectF(ccx - rc, ccy - rc, 2 * rc, 2 * rc)
            cercle.addEllipse(zone)
            self.scene.addPath(carre.subtracted(cercle), sans, gris)
            arc = QPainterPath()
            arc.arcMoveTo(zone, angle)
            arc.arcTo(zone, angle, -90)
            self.scene.addPath(arc, noir)

        # bords des routes
        for x in (cx - r, cx + r):
            self.scene.addLine(x, 0, x, cy - r - rc, noir)
            self.scene.addLine(x, cy + r + rc, x, self.HAUTEUR, noir)
        for y in (cy - r, cy + r):
            self.scene.addLine(0, y, cx - r - rc, y, noir)
            self.scene.addLine(cx + r + rc, y, self.LARGEUR, y, noir)

        # ligne centrale en pointillés
        tirets = QPen(QColor("white"), 3)
        tirets.setStyle(Qt.PenStyle.DashLine)
        self.scene.addLine(cx, 0, cx, cy - r, tirets)
        self.scene.addLine(cx, cy + r, cx, self.HAUTEUR, tirets)
        self.scene.addLine(0, cy, cx - r, cy, tirets)
        self.scene.addLine(cx + r, cy, self.LARGEUR, cy, tirets)

        # lignes d'arrêt (une par entrée)
        arret = QPen(QColor("white"), 5)
        self.scene.addLine(cx - r, cy - r - 4, cx, cy - r - 4, arret)
        self.scene.addLine(cx + r + 4, cy - r, cx + r + 4, cy, arret)
        self.scene.addLine(cx, cy + r + 4, cx + r, cy + r + 4, arret)
        self.scene.addLine(cx - r - 4, cy, cx - r - 4, cy + r, arret)

    def dessiner_feu(self, entree, etat):
        x, y = self.position_feu(entree)
        vertical = entree in (0, 2)
        largeur, hauteur = (22, 62) if vertical else (62, 22)
        boitier = QPainterPath()
        boitier.addRoundedRect(QRectF(x - largeur / 2, y - hauteur / 2, largeur, hauteur), 6, 6)
        self.scene.addPath(boitier, QPen(Qt.GlobalColor.white, 1), QBrush(QColor("#111111")))
        for i, nom in enumerate(("rouge", "orange", "vert")):
            decalage = (i - 1) * 19
            px, py = (x, y + decalage) if vertical else (x + decalage, y)
            couleur = COULEUR_FEU[nom] if nom == etat else COULEUR_ETEINT[nom]
            self.scene.addEllipse(px - 7, py - 7, 14, 14, QPen(Qt.PenStyle.NoPen),
                                  QBrush(QColor(couleur)))

    def dessiner_voiture(self, x, y, entree, prioritaire):
        vertical = entree in (0, 2)
        largeur, hauteur = (18, 34) if vertical else (34, 18)
        corps = QPainterPath()
        corps.addRoundedRect(QRectF(x - largeur / 2, y - hauteur / 2, largeur, hauteur), 5, 5)
        couleur = QColor("#D01010") if prioritaire else QColor("#222222")
        self.scene.addPath(corps, QPen(Qt.GlobalColor.white, 1), QBrush(couleur))

        # pare-brise, côté avant de la voiture
        vitre = QBrush(QColor("#9FD3F0"))
        sans = QPen(Qt.PenStyle.NoPen)
        ax, ay = {0: (0, 1), 1: (-1, 0), 2: (0, -1), 3: (1, 0)}[entree]
        if vertical:
            self.scene.addRect(x - 6, y + ay * 8 - 3, 12, 6, sans, vitre)
        else:
            self.scene.addRect(x + ax * 8 - 3, y - 6, 6, 12, sans, vitre)

    def redessiner(self):
        self.scene.clear()
        self.dessiner_route()
        for feu in self.etats_feux:
            if feu["id_entree"] in range(4):
                self.dessiner_feu(feu["id_entree"], feu["etat"])
        for v in self.vehicules_affiches:
            if v["entree"] in range(4):
                x, y = self.position_vehicule(v["entree"], v["x"])
                self.dessiner_voiture(x, y, v["entree"], v["type"] == PRIORITAIRE)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = FenetrePrincipale()
    fenetre.show()
    sys.exit(app.exec())
