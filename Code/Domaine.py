NORMAL = "normal"
PRIORITAIRE = "prioritaire"

ROUGE = "rouge"
ORANGE = "orange"
VERT = "vert"


class Vehicule:
    def __init__(self, id, entree, sortie, x=0, y=0, vitesse=0, type=NORMAL):
        self.__id = id
        self.__entree = entree
        self.__sortie = sortie
        self.__x = x
        self.__y = y
        self.__vitesse = vitesse
        self.__type = type

    @property
    def id(self):
        return self.__id

    @id.setter
    def id(self, value):
        self.__id = value

    @property
    def entree(self):
        return self.__entree

    @entree.setter
    def entree(self, value):
        self.__entree = value

    @property
    def sortie(self):
        return self.__sortie

    @sortie.setter
    def sortie(self, value):
        self.__sortie = value

    @property
    def x(self):
        return self.__x

    @x.setter
    def x(self, value):
        self.__x = value

    @property
    def y(self):
        return self.__y

    @y.setter
    def y(self, value):
        self.__y = value

    @property
    def vitesse(self):
        return self.__vitesse

    @vitesse.setter
    def vitesse(self, value):
        self.__vitesse = value

    @property
    def type(self):
        return self.__type

    @type.setter
    def type(self, value):
        self.__type = value

    def est_prioritaire(self):
        return self.__type == PRIORITAIRE

    def deplacer(self, dt):
        self.__x += self.__vitesse * dt

    def vers_json(self):
        return {
            "id": self.__id,
            "x": self.__x,
            "y": self.__y,
            "vitesse": self.__vitesse,
            "type": self.__type,
            "entree": self.__entree,
            "sortie": self.__sortie,
        }


class Feu:
    def __init__(self, id_entree, etat=ROUGE):
        self.__id_entree = id_entree
        self.__etat = etat

    @property
    def id_entree(self):
        return self.__id_entree

    @id_entree.setter
    def id_entree(self, value):
        self.__id_entree = value

    @property
    def etat(self):
        return self.__etat

    @etat.setter
    def etat(self, value):
        self.__etat = value

    def changer_etat(self, etat):
        self.__etat = etat


class ControleurBase:
    def __init__(self, carrefour_id, nb_entrees=4):
        self.__carrefour_id = carrefour_id
        self.__feux = [Feu(i) for i in range(nb_entrees)]

    @property
    def carrefour_id(self):
        return self.__carrefour_id

    @carrefour_id.setter
    def carrefour_id(self, value):
        self.__carrefour_id = value

    @property
    def feux(self):
        return self.__feux

    @feux.setter
    def feux(self, value):
        self.__feux = value

    def initialiser(self):
        for feu in self.feux:
            feu.changer_etat(ROUGE)

    def feu(self, id_entree):
        return self.feux[id_entree]

    def evaluer(self, vehicules):
        pass
    def trouver_prioritaire(self, vehicules):
        for v in vehicules:
            if v.est_prioritaire():
                return v
        return None

    def donner_priorite(self, prioritaire):
        for feu in self.feux:
            feu.changer_etat(VERT if feu.id_entree == prioritaire.entree else ROUGE)

class ControleurStop(ControleurBase):
    def evaluer(self, vehicules):
        prioritaire = self.trouver_prioritaire(vehicules)
        if prioritaire is not None:
            self.donner_priorite(prioritaire)
            return
        for feu in self.feux:
            feu.changer_etat(ROUGE)
        if vehicules:
            premier = vehicules[0]
            self.feu(premier.entree).changer_etat(VERT)


class ControleurFeux(ControleurBase):
    def __init__(self, carrefour_id, nb_entrees=4):
        super().__init__(carrefour_id, nb_entrees)
        self.__phase = 0

    @property
    def phase(self):
        return self.__phase

    @phase.setter
    def phase(self, value):
        self.__phase = value

    def evaluer(self, vehicules):
        prioritaire = self.trouver_prioritaire(vehicules)
        if prioritaire is not None:
            self.donner_priorite(prioritaire)
            return
        self.phase = 1 - self.phase
        entrees_vertes = {0, 2} if self.phase == 0 else {1, 3}
        for feu in self.feux:
            feu.changer_etat(VERT if feu.id_entree in entrees_vertes else ROUGE)


class ControleurGiratoireFeux(ControleurBase):
    def evaluer(self, vehicules):
        prioritaire = None
        for i in vehicules:
            if i.est_prioritaire():
                prioritaire = i
                break

        if prioritaire is not None:
            for feu in self.feux:
                feu.changer_etat(VERT if feu.id_entree == prioritaire.entree else ROUGE)
        else:
            for feu in self.feux:
                feu.changer_etat(VERT)


if __name__ == "__main__":
    controleur = ControleurGiratoireFeux("carrefour_1")
    controleur.initialiser()

    v1 = Vehicule("v1", entree=1, sortie=3, type=NORMAL)
    v2 = Vehicule("v2", entree=2, sortie=0, type=PRIORITAIRE)

    controleur.evaluer([v1, v2])
    for feu in controleur.feux:
        print(feu.id_entree, feu.etat)