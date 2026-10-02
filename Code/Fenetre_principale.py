import sys
from PyQt6.QtCore import QRect, Qt, QElapsedTimer, QSize
from PyQt6.QtGui import QColor, QBrush, QPen, QFont
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QDialog,
    QTabWidget,
    QScrollArea,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QLabel,
    QGraphicsScene,
    QGraphicsView,
    QSlider,
    QLCDNumber,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QListView,
    QListWidget,
    QTableView,
    QTableWidget,
    QToolBar,
    QApplication,
)
from Domaine import (
    Vehicule,
    ControleurFeux,
    ControleurGiratoireFeux,
    ControleurStop,
    ControleurBase,
    PRIORITAIRE
)
#------------------------------------------------------------------------------

STOP="stop"
FEUX="feux"
GIRATOIRE="giratoire"

TYPE_CARREFOUR={
    STOP: "Carrefour à stop",
    FEUX: "Carrefour à feux",
    GIRATOIRE: "Carrefour à Giratoire",
}

CONTROLEUR={
    STOP: ControleurStop,
    FEUX: ControleurFeux,
    GIRATOIRE: ControleurGiratoireFeux,
}

CONTROLEUR_FEU = {"rouge":"FA0000","orange":"FA7500","vert":"32FA00"}

class Fenetre_pricipale(QMainWindow):
    LARGEUR = 800
    LONGEUR = 600

    def __init__(self):
        super().__init__()
        self.setWindowTitle("simulation de carrefour connecté")
        self.setFixedSize(QSize(800,600))
        self.setCentralWidget(self.view)
        self.carrefour = GIRATOIRE
        self.controleur = CONTROLEUR[self.carrefour]
        self.scene = QGraphicsScene(0,0, self.LARGEUR, self.LONGEUR)
        self.view = QGraphicsView(self.scene)
