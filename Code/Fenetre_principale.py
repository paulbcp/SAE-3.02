import sys
import math
import time

from PyQt6.QtCore import Qt, QSize, QRectF, QPointF
from PyQt6.QtGui import QColor, QBrush, QFont, QPen, QPainterPath, QPolygonF
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
from Domaine import (
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

    def __init__(self, carrefour=GIRATOIRE, port=5000, avec_trafic=True, avec_bdd=True):
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
        self.elements_dynamiques = []
        self.elements_fixes = []
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
            self.groupe_boutons.addButton(bouton)
            self.boutons[type_c] = bouton
            barre.addWidget(bouton)
        self.boutons[self.carrefour].setChecked(True)

        # --- statistiques à droite ---
        self.lbl_nb = QLabel("0")
        self.lbl_vitesse = QLabel("0.0")
        self.lbl_prio = QLabel("0")
        self.lbl_accident = QLabel("-")
        self.lbl_serveur = QLabel("-")
        self.lbl_bdd = QLabel("-")
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
        if stats.get("generation", self.generation) != self.generation:
            return
        self.vehicules_affiches = vehicules
        self.etats_feux = feux
        self.mettre_a_jour_stats()
        if "taux_accident" in stats:
            self.lbl_accident.setText(f"{stats['taux_accident']:.1f} %")
        self.lbl_bdd.setText(stats.get("bdd", "désactivée"))
        self.redessiner()

    def changer_carrefour(self, type_c):
        for t, bouton in self.boutons.items():
            bouton.setChecked(t == type_c)
        if type_c == self.carrefour:
            return  # déjà affichée : rien à changer
        self.carrefour = type_c
        self.controleur = CONTROLEUR[type_c]("carrefour_1")
        self.dessiner_carrefour()  # croix ou giratoire
        if self.trafic is not None:
            self.trafic.arreter()
        if self.simulation.serveur.actif:
            try:
                self.simulation.serveur.reinitialiser(self.controleur)
            except TimeoutError as erreur:  # (PyQt6 ferme l'application si une exception sort d'un slot)
                print("changement de simulation :", erreur)
            self.generation = self.simulation.serveur.generation
        self.vehicules_affiches = []
        self.etats_feux = [{"id_entree": f.id_entree, "etat": f.etat}
                           for f in self.controleur.feux]
        self.mettre_a_jour_stats()
        self.lbl_accident.setText("-")
        self.redessiner()
        if self.trafic is not None:
            self.trafic.demarrer()


    def closeEvent(self, event):
        if self.trafic is not None:
            self.trafic.arreter()
        self.simulation.serveur.arreter()
        self.simulation.wait(4000)
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
        distance = DISTANCE_LIGNE[self.controleur.DISPOSITION] * PX_PAR_UNITE + 38
        dx, dy = -(self.ROUTE / 2 + 14), -distance
        for _ in range(entree):
            dx, dy = -dy, dx
        return (cx + dx, cy + dy)

    def fixe(self, element):
        self.elements_fixes.append(element)
        return element

    def dessiner_carrefour(self):
        disposition = self.controleur.DISPOSITION
        if disposition == self.disposition_dessinee:
            return
        for element in self.elements_fixes:
            self.scene.removeItem(element)
        self.elements_fixes = []
        if disposition == DISPOSITION_GIRATOIRE:
            self.dessiner_giratoire()
        else:
            self.dessiner_route()
        self.disposition_dessinee = disposition

    def dessiner_route(self):
        cx, cy = self.LARGEUR / 2, self.HAUTEUR / 2
        r = self.ROUTE / 2       # demi-largeur des routes
        rc = 24                  # rayon des coins arrondis
        sans = QPen(Qt.PenStyle.NoPen)
        gris = QBrush(QColor("#B9B9B9"))
        noir = QPen(QColor("#222222"), 2)

        # les deux routes
        self.fixe(self.scene.addRect(0, cy - r, self.LARGEUR, 2 * r, sans, gris))
        self.fixe(self.scene.addRect(cx - r, 0, 2 * r, self.HAUTEUR, sans, gris))

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
            self.fixe(self.scene.addPath(carre.subtracted(cercle), sans, gris))
            arc = QPainterPath()
            arc.arcMoveTo(zone, angle)
            arc.arcTo(zone, angle, -90)
            self.fixe(self.scene.addPath(arc, noir))

        # bords des routes
        for x in (cx - r, cx + r):
            self.fixe(self.scene.addLine(x, 0, x, cy - r - rc, noir))
            self.fixe(self.scene.addLine(x, cy + r + rc, x, self.HAUTEUR, noir))
        for y in (cy - r, cy + r):
            self.fixe(self.scene.addLine(0, y, cx - r - rc, y, noir))
            self.fixe(self.scene.addLine(cx + r + rc, y, self.LARGEUR, y, noir))

        # ligne centrale en pointillés
        tirets = QPen(QColor("white"), 3)
        tirets.setStyle(Qt.PenStyle.DashLine)
        self.fixe(self.scene.addLine(cx, 0, cx, cy - r, tirets))
        self.fixe(self.scene.addLine(cx, cy + r, cx, self.HAUTEUR, tirets))
        self.fixe(self.scene.addLine(0, cy, cx - r, cy, tirets))
        self.fixe(self.scene.addLine(cx + r, cy, self.LARGEUR, cy, tirets))

        self.dessiner_lignes_arret(DISTANCE_LIGNE[self.controleur.DISPOSITION] * PX_PAR_UNITE)

    def dessiner_giratoire(self):
        cx, cy = self.LARGEUR / 2, self.HAUTEUR / 2
        r = self.ROUTE / 2                              # demi-largeur des routes
        r_ext = RAYON_EXTERIEUR * PX_PAR_UNITE          # bord extérieur de l'anneau
        r_ilot = RAYON_ILOT * PX_PAR_UNITE
        sans = QPen(Qt.PenStyle.NoPen)
        gris = QBrush(QColor("#B9B9B9"))
        noir = QPen(QColor("#222222"), 2)

        # chaussée : les deux routes et l'anneau
        self.fixe(self.scene.addRect(0, cy - r, self.LARGEUR, 2 * r, sans, gris))
        self.fixe(self.scene.addRect(cx - r, 0, 2 * r, self.HAUTEUR, sans, gris))
        self.fixe(self.scene.addEllipse(cx - r_ext, cy - r_ext, 2 * r_ext, 2 * r_ext, sans, gris))

        # bords : chaque bord de route s'arrête sur l'anneau, et l'anneau est bordé entre les routes
        y_coin = math.sqrt(r_ext ** 2 - r ** 2)
        for x in (cx - r, cx + r):
            self.fixe(self.scene.addLine(x, 0, x, cy - y_coin, noir))
            self.fixe(self.scene.addLine(x, cy + y_coin, x, self.HAUTEUR, noir))
        for y in (cy - r, cy + r):
            self.fixe(self.scene.addLine(0, y, cx - y_coin, y, noir))
            self.fixe(self.scene.addLine(cx + y_coin, y, self.LARGEUR, y, noir))
        demi_route = math.degrees(math.asin(r / r_ext))      # demi-angle qu'occupe une route sur l'anneau
        zone = QRectF(cx - r_ext, cy - r_ext, 2 * r_ext, 2 * r_ext)
        for depart in (0, 90, 180, 270):
            arc = QPainterPath()
            arc.arcMoveTo(zone, depart + demi_route)
            arc.arcTo(zone, depart + demi_route, 90 - 2 * demi_route)
            self.fixe(self.scene.addPath(arc, noir))

        # îlot central
        self.fixe(self.scene.addEllipse(cx - r_ilot, cy - r_ilot, 2 * r_ilot, 2 * r_ilot,
                                        QPen(QColor("white"), 3), QBrush(QColor("#7DB356"))))

        # lignes centrales en pointillés, jusqu'à l'anneau
        tirets = QPen(QColor("white"), 3)
        tirets.setStyle(Qt.PenStyle.DashLine)
        self.fixe(self.scene.addLine(cx, 0, cx, cy - r_ext, tirets))
        self.fixe(self.scene.addLine(cx, cy + r_ext, cx, self.HAUTEUR, tirets))
        self.fixe(self.scene.addLine(0, cy, cx - r_ext, cy, tirets))
        self.fixe(self.scene.addLine(cx + r_ext, cy, self.LARGEUR, cy, tirets))

        self.dessiner_lignes_arret(DISTANCE_LIGNE[DISPOSITION_GIRATOIRE] * PX_PAR_UNITE)

    def dessiner_lignes_arret(self, distance):
        cx, cy = self.LARGEUR / 2, self.HAUTEUR / 2
        r = self.ROUTE / 2
        arret = QPen(QColor("white"), 5)
        for x1, y1, x2, y2 in ((-r, -distance, 0, -distance), (distance, -r, distance, 0),
                               (0, distance, r, distance), (-distance, 0, -distance, r)):
            self.fixe(self.scene.addLine(cx + x1, cy + y1, cx + x2, cy + y2, arret))

    def ajouter(self, element):
        """Enregistre un élément à effacer au prochain redessin (feux, voitures)."""
        self.elements_dynamiques.append(element)
        return element

    def dessiner_feu(self, entree, etat):
        x, y = self.position_feu(entree)
        vertical = entree in (0, 2)
        largeur, hauteur = (22, 62) if vertical else (62, 22)
        boitier = QPainterPath()
        boitier.addRoundedRect(QRectF(x - largeur / 2, y - hauteur / 2, largeur, hauteur), 6, 6)
        self.ajouter(self.scene.addPath(boitier, QPen(Qt.GlobalColor.white, 1), QBrush(QColor("#111111"))))
        for i, nom in enumerate(("rouge", "orange", "vert")):
            decalage = (i - 1) * 19
            px, py = (x, y + decalage) if vertical else (x + decalage, y)
            couleur = COULEUR_FEU[nom] if nom == etat else COULEUR_ETEINT[nom]
            self.ajouter(self.scene.addEllipse(px - 7, py - 7, 14, 14, QPen(Qt.PenStyle.NoPen),
                                               QBrush(QColor(couleur))))

    def dessiner_panneau_stop(self, entree):
        """Panneau STOP (octogone rouge) à droite de la voie d'entrée."""
        x, y = self.position_feu(entree)
        rayon = 15
        octogone = QPolygonF([QPointF(x + rayon * math.cos(math.radians(22.5 + 45 * i)),
                                      y + rayon * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)])
        self.ajouter(self.scene.addPolygon(octogone, QPen(QColor("white"), 2), QBrush(QColor("#D0021B"))))
        texte = self.scene.addSimpleText("STOP")
        police = QFont()
        police.setBold(True)
        police.setPixelSize(9)
        texte.setFont(police)
        texte.setBrush(QBrush(QColor("white")))
        cadre = texte.boundingRect()
        texte.setPos(x - cadre.width() / 2, y - cadre.height() / 2)
        self.ajouter(texte)

    def dessiner_voiture(self, x, y, angle, prioritaire):
        corps = QPainterPath()
        corps.addRoundedRect(QRectF(-17, -9, 34, 18), 5, 5)
        couleur = QColor("#D01010") if prioritaire else QColor("#222222")
        sans = QPen(Qt.PenStyle.NoPen)
        elements = [self.scene.addPath(corps, QPen(Qt.GlobalColor.white, 1), QBrush(couleur)),
                    # pare-brise, côté avant de la voiture
                    self.scene.addRect(5, -6, 6, 12, sans, QBrush(QColor("#9FD3F0")))]
        if prioritaire:
            bleu_a_gauche = int(time.monotonic() * 4) % 2 == 0
            gauche, droite = ("#1E5BFF", "#FFFFFF") if bleu_a_gauche else ("#FFFFFF", "#1E5BFF")
            elements.append(self.scene.addRect(-7, -7, 5, 7, sans, QBrush(QColor(gauche))))
            elements.append(self.scene.addRect(-7, 0, 5, 7, sans, QBrush(QColor(droite))))
        for element in elements:
            element.setPos(x, y)
            element.setRotation(angle)
            element.setZValue(2 if prioritaire else 1)     # le véhicule d'urgence passe au-dessus
            self.ajouter(element)

    def redessiner(self):
        for element in self.elements_dynamiques:
            self.scene.removeItem(element)
        self.elements_dynamiques = []
        for feu in self.etats_feux:
            if feu["id_entree"] not in range(4):
                continue
            if feu["etat"] == PANNEAU_STOP:                 # carrefour à stop : panneaux, pas de feux
                self.dessiner_panneau_stop(feu["id_entree"])
            else:
                self.dessiner_feu(feu["id_entree"], feu["etat"])
        for v in self.vehicules_affiches:
            try:
                x, y, angle = trajectoire(v["entree"], v["sortie"],
                                          v.get("disposition", self.controleur.DISPOSITION)).pose_ecran(v["x"])
            except ValueError:
                continue
            self.dessiner_voiture(x, y, angle, v["type"] == PRIORITAIRE)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = FenetrePrincipale()
    fenetre.show()
    sys.exit(app.exec())