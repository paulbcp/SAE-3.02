import math
import time

from Conduite import (S0, B_CONF, B_MAX, MARGE_CONTACT, acceleration_idm, distance_freinage,
                      obstacle_devant)
from Geometrie import DISPOSITION_CROIX, DISPOSITION_GIRATOIRE, LONGUEUR_VEHICULE, compatibles, trajectoire

NORMAL = "normal"
PRIORITAIRE = "prioritaire"

ROUGE = "rouge"
ORANGE = "orange"
VERT = "vert"
PANNEAU_STOP = "stop"   # pas de feu à cette entrée mais un panneau STOP : arrêt obligatoire
DUREE_VERT = 5          # secondes
DUREE_ORANGE = 1.5
DUREE_TOUT_ROUGE = 1.5

VITESSE_MAX_DEFAUT = 4.0     # vitesse de croisière souhaitée (unités/s) quand elle n'est pas précisée
VITESSE_ARRETE = 0.1         # u/s : en dessous, un véhicule est considéré comme arrêté
DISTANCE_ARRET_STOP = 0.6    # au STOP, le pare-chocs doit être à moins de 0,6 u de la ligne...
DUREE_ARRET_STOP = 1.0       # ... pendant au moins 1 s pour que l'arrêt compte
MARGE_DECISION = 1.5         # un véhicule « décide » d'entrer quand il est à cette distance de son freinage


def passage_permis(etat, autorise):
    return autorise and etat in (VERT, PANNEAU_STOP)


class Vehicule:

    def __init__(self, id, entree, sortie, x=0, y=0, vitesse=0, type=NORMAL, vitesse_max=None,
                 disposition=DISPOSITION_CROIX):
        self.__id = id
        self.__entree = entree
        self.__sortie = sortie
        self.__disposition = disposition
        self.__trajectoire = trajectoire(entree, sortie, disposition)
        self.__x = x
        self.__y = y
        self.__vitesse = vitesse
        self.__type = type
        self.__vitesse_max = vitesse_max if vitesse_max else max(VITESSE_MAX_DEFAUT, vitesse)

    @classmethod
    def depuis_json(cls, d, disposition=None):
        try:
            vitesse_max = d.get("vitesse_max")
            v = cls(str(d["id"]), int(d["entree"]), int(d["sortie"]), float(d["x"]),
                    float(d.get("y", 0)), float(d["vitesse"]), d.get("type", NORMAL),
                    None if vitesse_max is None else float(vitesse_max),
                    disposition or d.get("disposition", DISPOSITION_CROIX))
        except (KeyError, TypeError, ValueError, AttributeError) as erreur:
            raise ValueError(f"message de véhicule invalide : {erreur!r}") from erreur
        if v.type not in (NORMAL, PRIORITAIRE):
            raise ValueError(f"type de véhicule inconnu : {v.type!r}")
        if not (math.isfinite(v.x) and math.isfinite(v.vitesse) and 0 <= v.vitesse <= 50
                and math.isfinite(v.vitesse_max) and v.vitesse_max > 0):
            raise ValueError("position ou vitesse hors limites")
        return v

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
        self.__trajectoire = trajectoire(value, self.__sortie, self.__disposition)
        self.__entree = value

    @property
    def sortie(self):
        return self.__sortie

    @sortie.setter
    def sortie(self, value):
        self.__trajectoire = trajectoire(self.__entree, value, self.__disposition)
        self.__sortie = value

    @property
    def disposition(self):
        return self.__disposition

    @disposition.setter
    def disposition(self, value):
        self.__trajectoire = trajectoire(self.__entree, self.__sortie, value)
        self.__disposition = value

    @property
    def trajectoire(self):
        return self.__trajectoire

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
    def vitesse_max(self):
        return self.__vitesse_max

    @vitesse_max.setter
    def vitesse_max(self, value):
        self.__vitesse_max = value

    @property
    def type(self):
        return self.__type

    @type.setter
    def type(self, value):
        self.__type = value

    def est_prioritaire(self):
        return self.__type == PRIORITAIRE

    # ------------------------------------------------------------------ position / zone
    def engage(self):
        return self.__x + LONGUEUR_VEHICULE / 2 > self.__trajectoire.x_ligne

    def libere(self):
        return self.__x - LONGUEUR_VEHICULE / 2 > self.__trajectoire.x_fin_carrefour

    def dans_carrefour(self):
        return self.engage() and not self.libere()

    def termine(self):
        return self.__x - LONGUEUR_VEHICULE / 2 >= self.__trajectoire.longueur

    def zone(self):
        if self.libere():
            return "sortie"
        return "carrefour" if self.engage() else "approche"

    def distance_ligne(self):
        return self.__trajectoire.x_ligne - LONGUEUR_VEHICULE / 2 - self.__x

    def peut_s_arreter(self):
        return distance_freinage(self.__vitesse, B_MAX) <= self.distance_ligne()

    def passage_inevitable(self):
        if self.engage():
            return False
        return (distance_freinage(self.__vitesse, B_MAX) + 0.15 * self.__vitesse
                > self.distance_ligne())

    def distance_de_decision(self):
        return distance_freinage(self.__vitesse, B_CONF) + MARGE_DECISION

    # ------------------------------------------------------------------ conduite
    def doit_s_arreter(self, etat_feu, autorise):
        if self.engage():
            return False
        if passage_permis(etat_feu, autorise):
            return False
        return self.peut_s_arreter()

    def deplacer(self, dt, consigne=None):
        if dt <= 0:
            return
        consigne = consigne or {}
        traj = self.__trajectoire
        etat_feu = VERT
        for feu in consigne.get("feux", []):
            if feu["id_entree"] == self.__entree:
                etat_feu = feu["etat"]
        obstacle = consigne.get("obstacle")

        ecart, vitesse_devant, limite = None, 0.0, None
        if obstacle:
            ecart, vitesse_devant = obstacle["distance"], obstacle["vitesse"]
            limite = max(0.0, ecart - MARGE_CONTACT)

        if self.doit_s_arreter(etat_feu, consigne.get("autorise", True)):
            # La ligne d'arrêt agit comme un obstacle immobile situé là où le centre doit s'arrêter.
            ecart_ligne = traj.x_arret - self.__x + S0
            if ecart is None or ecart_ligne < ecart:
                ecart, vitesse_devant = ecart_ligne, 0.0
            reste = max(0.0, traj.x_arret + 0.05 - self.__x)
            limite = reste if limite is None else min(limite, reste)

        # Dans les virages (et juste avant), la vitesse souhaitée est limitée.
        vitesse_voulue = min(self.__vitesse_max, traj.vitesse_limite(self.__x))
        acceleration = acceleration_idm(self.__vitesse, vitesse_voulue, ecart, vitesse_devant)
        nouvelle = max(0.0, self.__vitesse + acceleration * dt)
        deplacement = 0.5 * (self.__vitesse + nouvelle) * dt
        # Garde-fou : quoi qu'il arrive, on n'avance jamais au-delà de l'obstacle ou de la ligne.
        if limite is not None and deplacement > limite:
            deplacement = limite
            nouvelle = min(nouvelle, deplacement / dt)
        self.__x += deplacement
        self.__vitesse = nouvelle

    def vers_json(self):
        return {
            "id": self.__id,
            "x": self.__x,
            "y": self.__y,
            "vitesse": self.__vitesse,
            "vitesse_max": self.__vitesse_max,
            "type": self.__type,
            "entree": self.__entree,
            "sortie": self.__sortie,
            "disposition": self.__disposition,
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

    DISPOSITION = DISPOSITION_CROIX      # forme du carrefour (voir Geometrie.py)
    AUTORISE_PAR_DEFAUT = True           # un véhicule que le carrefour n'a pas refusé peut passer

    def __init__(self, carrefour_id, nb_entrees=4, horloge=time.monotonic):
        self.__carrefour_id = carrefour_id
        self.__feux = [Feu(i) for i in range(nb_entrees)]
        self.__horloge = horloge            # injectable pour tester sans attendre
        self.__admis = set()                # véhicules autorisés à entrer
        self.__refuses = set()              # véhicules qui doivent attendre à la ligne
        self.__engages = set()              # véhicules engagés ou qui ne peuvent plus s'arrêter

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

    def maintenant(self):
        return self.__horloge()

    def initialiser(self):
        for feu in self.feux:
            feu.changer_etat(ROUGE)
        self.__admis = set()
        self.__refuses = set()
        self.__engages = set()

    def feu(self, id_entree):
        return self.feux[id_entree]

    def evaluer(self, vehicules):
        self.mettre_a_jour_feux(vehicules)
        self.mettre_a_jour_passages(vehicules)

    def mettre_a_jour_feux(self, vehicules):
        pass

    def trouver_prioritaire(self, vehicules):
        for v in vehicules:
            if v.est_prioritaire() and not v.libere():
                return v
        return None

    def donner_priorite(self, prioritaire):
        for feu in self.feux:
            feu.changer_etat(VERT if feu.id_entree == prioritaire.entree else ROUGE)

    def demande_a_passer(self, tete):
        return self.feu(tete.entree).etat == VERT and tete.distance_ligne() <= tete.distance_de_decision()

    def ordre_de_passage(self, tete, rang):
        return rang[tete.id]

    def mettre_a_jour_passages(self, vehicules):
        rang = {v.id: i for i, v in enumerate(vehicules)}
        occupants = []      # mouvements déjà engagés, ou qui ne peuvent plus s'arrêter
        tetes = {}          # entrée -> véhicule en tête de file, pas encore engagé
        engages = set()
        for v in vehicules:
            if v.engage() or v.passage_inevitable():
                engages.add(v.id)
                if not v.libere():
                    occupants.append((v.entree, v.sortie))
            elif v.entree not in tetes or v.x > tetes[v.entree].x:
                tetes[v.entree] = v
        files_prioritaires = {v.entree for v in vehicules if v.est_prioritaire() and not v.engage()}

        candidats = [t for t in tetes.values() if self.demande_a_passer(t)]
        candidats.sort(key=lambda t: (t.entree not in files_prioritaires,
                                      t.id not in self.__admis,
                                      self.ordre_de_passage(t, rang)))
        reserves = list(occupants)
        en_attente = []     # un candidat refusé bloque ceux qui le suivent et le croisent (pas de doublement)
        admis, refuses = set(), set()
        for t in candidats:
            mouvement = (t.entree, t.sortie)
            if all(compatibles(mouvement, autre, self.DISPOSITION) for autre in reserves + en_attente):
                admis.add(t.id)
                reserves.append(mouvement)
            else:
                refuses.add(t.id)
                en_attente.append(mouvement)
        self.__admis, self.__refuses, self.__engages = admis, refuses, engages

    def autorise(self, vehicule):
        if self.AUTORISE_PAR_DEFAUT:
            return vehicule.id not in self.__refuses
        return vehicule.id in self.__admis or vehicule.id in self.__engages

    def consigne(self, vehicule, vehicules):
        obstacle = obstacle_devant(vehicule, vehicules)
        return {
            "feux": [{"id_entree": f.id_entree, "etat": f.etat} for f in self.feux],
            "autorise": self.autorise(vehicule),
            "obstacle": None if obstacle is None else {"distance": obstacle[0], "vitesse": obstacle[1]},
            "disposition": self.DISPOSITION,
        }


class ControleurStop(ControleurBase):

    AUTORISE_PAR_DEFAUT = False          # au STOP, on ne passe qu'avec l'accord du carrefour

    def __init__(self, carrefour_id, nb_entrees=4, horloge=time.monotonic):
        super().__init__(carrefour_id, nb_entrees, horloge)
        self.__debut_arret = {}          # id -> instant où le véhicule s'est arrêté à la ligne
        self.__arret_fait = set()        # véhicules qui ont marqué l'arrêt
        self.__prioritaire = None        # véhicule d'urgence présent, s'il y en a un

    def initialiser(self):
        super().initialiser()
        self.__debut_arret, self.__arret_fait, self.__prioritaire = {}, set(), None

    def mettre_a_jour_feux(self, vehicules):
        for feu in self.feux:
            feu.changer_etat(PANNEAU_STOP)
        self.__prioritaire = self.trouver_prioritaire(vehicules)
        maintenant = self.maintenant()
        presents = set()
        for v in vehicules:
            presents.add(v.id)
            if v.engage() or v.id in self.__arret_fait:
                continue
            if v.vitesse < VITESSE_ARRETE and v.distance_ligne() < DISTANCE_ARRET_STOP:
                debut = self.__debut_arret.setdefault(v.id, maintenant)
                if maintenant - debut >= DUREE_ARRET_STOP:
                    self.__arret_fait.add(v.id)
            else:
                self.__debut_arret.pop(v.id, None)       # l'arrêt doit être continu
        self.__debut_arret = {i: t for i, t in self.__debut_arret.items() if i in presents}
        self.__arret_fait &= presents

    def demande_a_passer(self, tete):
        if tete.est_prioritaire():
            return True                  # le véhicule d'urgence ne marque pas l'arrêt
        if self.__prioritaire is not None and tete.entree != self.__prioritaire.entree:
            return False                 # les autres bras laissent passer le véhicule d'urgence
        return tete.id in self.__arret_fait

    def ordre_de_passage(self, tete, rang):
        return (self.__debut_arret.get(tete.id, math.inf), rang[tete.id])


class ControleurFeux(ControleurBase):
    def __init__(self, carrefour_id, nb_entrees=4, horloge=time.monotonic):
        super().__init__(carrefour_id, nb_entrees, horloge)
        self.__phase = 0
        self.__debut_phase = self.maintenant()

    @property
    def phase(self):
        return self.__phase

    @phase.setter
    def phase(self, value):
        self.__phase = value

    def mettre_a_jour_feux(self, vehicules):
        prioritaire = self.trouver_prioritaire(vehicules)
        if prioritaire is not None:
            self.donner_priorite(prioritaire)
            return

        ecoule = self.maintenant() - self.__debut_phase
        if ecoule >= DUREE_VERT + DUREE_ORANGE + DUREE_TOUT_ROUGE:
            self.phase = 1 - self.phase          # on passe à l'autre axe
            self.__debut_phase = self.maintenant()
            ecoule = 0

        if ecoule < DUREE_VERT:
            couleur = VERT
        elif ecoule < DUREE_VERT + DUREE_ORANGE:
            couleur = ORANGE
        else:
            couleur = ROUGE
        entrees_actives = {0, 2} if self.phase == 0 else {1, 3}
        for feu in self.feux:
            feu.changer_etat(couleur if feu.id_entree in entrees_actives else ROUGE)


class ControleurGiratoireFeux(ControleurBase):

    DISPOSITION = DISPOSITION_GIRATOIRE

    def mettre_a_jour_feux(self, vehicules):
        prioritaire = self.trouver_prioritaire(vehicules)
        if prioritaire is not None:
            self.donner_priorite(prioritaire)
        else:
            for feu in self.feux:
                feu.changer_etat(VERT)


# --- les trois simulations : type de carrefour -> (nom affiché, contrôleur) ------------------
# Partagé par l'interface (boutons), le serveur en console et le lanceur.
STOP = "stop"
FEUX = "feux"
GIRATOIRE = "giratoire"

TYPES_CARREFOUR = {
    STOP: "Carrefour à stop",
    FEUX: "Carrefour à feux",
    GIRATOIRE: "Carrefour à giratoire",
}

CONTROLEURS = {
    STOP: ControleurStop,
    FEUX: ControleurFeux,
    GIRATOIRE: ControleurGiratoireFeux,
}


def type_carrefour(controleur):
    for type_c, classe in CONTROLEURS.items():
        if type(controleur) is classe:
            return type_c
    return type(controleur).__name__


def compter_conflits(vehicules):
    dedans = [v for v in vehicules if v.dans_carrefour()]
    return sum(1 for i in range(len(dedans)) for j in range(i + 1, len(dedans))
               if not compatibles((dedans[i].entree, dedans[i].sortie),
                                  (dedans[j].entree, dedans[j].sortie), dedans[i].disposition))


if __name__ == "__main__":
    controleur = ControleurGiratoireFeux("carrefour_1")
    controleur.initialiser()

    v1 = Vehicule("v1", entree=1, sortie=3, type=NORMAL)
    v2 = Vehicule("v2", entree=2, sortie=0, type=PRIORITAIRE)

    controleur.evaluer([v1, v2])
    for feu in controleur.feux:
        print(feu.id_entree, feu.etat)
