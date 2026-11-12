import math

# --- dimensions de la scène en pixels (la fenêtre les réutilise) --------------------------
LARGEUR = 560
HAUTEUR = 480
ROUTE = 100                      # largeur des routes
PX_PAR_UNITE = ROUTE / 6

# --- dimensions en unités -----------------------------------------------------------------
DEMI_ROUTE = 3.0                 # demi-largeur d'une route
DECALAGE_VOIE = 1.5              # axe de la route -> centre d'une voie
LONGUEUR_VEHICULE = 34 / PX_PAR_UNITE
LARGEUR_VEHICULE = 18 / PX_PAR_UNITE
DECALAGE_LIGNE = 4 / PX_PAR_UNITE     # la ligne d'arrêt est 4 px avant le carrefour (comme dessinée)
ESPACE_LIGNE = 3 / PX_PAR_UNITE       # un véhicule arrêté laisse 3 px avant la ligne

# --- giratoire (en unités) ------------------------------------------------------------------
RAYON_ILOT = 2.4                 # îlot central
RAYON_ANNEAU = 4.3               # trajectoire des véhicules sur l'anneau (milieu de la chaussée)
RAYON_EXTERIEUR = 6.2            # bord extérieur de l'anneau
RAYON_RACCORD = 3.0              # rayon des virages d'entrée et de sortie de l'anneau
LIGNE_GIRATOIRE = 6.4            # distance du centre à la ligne d'arrêt (des feux) d'une entrée

# --- vitesse dans les virages ---------------------------------------------------------------
ACCELERATION_LATERALE = 2.5      # u/s² : vitesse max dans un virage = racine(a × rayon)
DECELERATION_VIRAGE = 1.5        # u/s² : freinage d'anticipation avant un virage

PAS_TABLE = 0.05                 # pas des tables précalculées (poses, vitesses limites)
SEUIL_CONFLIT = 2.4              # deux centres plus proches => les voitures peuvent se toucher
EXTENSION_TABLE = 15.0           # la table dépasse la fin du trajet (balayage des obstacles)

DISPOSITION_CROIX = "croix"
DISPOSITION_GIRATOIRE = "giratoire"
# distance du centre du carrefour à la ligne d'arrêt d'une entrée (pour le dessin)
DISTANCE_LIGNE = {DISPOSITION_CROIX: DEMI_ROUTE + DECALAGE_LIGNE,
                  DISPOSITION_GIRATOIRE: LIGNE_GIRATOIRE}


def _bord(bras):
    return (HAUTEUR if bras in (0, 2) else LARGEUR) / 2 / PX_PAR_UNITE


def _tourner(x, y, quarts):
    for _ in range(quarts % 4):
        x, y = -y, x
    return x, y


class _TrajectoireBase:

    disposition = None

    def __init__(self, entree, sortie):
        if entree == sortie or entree not in range(4) or sortie not in range(4):
            raise ValueError(f"trajectoire impossible : entrée {entree}, sortie {sortie}")
        self.entree = entree
        self.sortie = sortie
        # 1 = tourne à gauche, 2 = tout droit, 3 = tourne à droite
        self.virage = (sortie - entree) % 4
        self._construire()       # définit l_approche, l_carrefour, l_sortie et x_ligne
        self.longueur = self.l_approche + self.l_carrefour + self.l_sortie
        # Repères le long du trajet (abscisse du CENTRE du véhicule)
        self.x_arret = self.x_ligne - LONGUEUR_VEHICULE / 2 - ESPACE_LIGNE   # centre d'un véhicule à l'arrêt
        self.x_fin_carrefour = self.l_approche + self.l_carrefour

        n = int((self.longueur + EXTENSION_TABLE) / PAS_TABLE) + 2
        self._table = [self._pose_exacte(i * PAS_TABLE) for i in range(n)]
        self._limites = self._tabuler_limites(n)

    # ------------------------------------------------------------------ à définir
    def _construire(self):
        raise NotImplementedError

    def _pose_exacte(self, s):
        raise NotImplementedError

    def _courbure(self, s):
        raise NotImplementedError

    # ------------------------------------------------------------------ commun
    def _tabuler_limites(self, n):
        limites = []
        for i in range(n):
            k = self._courbure(i * PAS_TABLE)
            limites.append(math.sqrt(ACCELERATION_LATERALE / k) if k > 0 else math.inf)
        for i in range(n - 2, -1, -1):
            limites[i] = min(limites[i], math.sqrt(limites[i + 1] ** 2 + 2 * DECELERATION_VIRAGE * PAS_TABLE))
        return limites

    def vitesse_limite(self, s):
        return self._limites[min(max(int(s / PAS_TABLE), 0), len(self._limites) - 1)]

    def pose(self, s):
        if s <= 0:
            return self._table[0]
        position = s / PAS_TABLE
        i = int(position)
        if i >= len(self._table) - 1:
            return self._table[-1]
        f = position - i
        a, b = self._table[i], self._table[i + 1]
        hx = a[2] + f * (b[2] - a[2])
        hy = a[3] + f * (b[3] - a[3])
        norme = math.hypot(hx, hy) or 1.0
        return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), hx / norme, hy / norme)

    def pose_ecran(self, s):
        x, y, hx, hy = self.pose(s)
        return (LARGEUR / 2 + x * PX_PAR_UNITE,
                HAUTEUR / 2 + y * PX_PAR_UNITE,
                math.degrees(math.atan2(hy, hx)))

    def points_carrefour(self, pas=0.25):
        debut = self.l_approche - 1.0
        fin = self.x_fin_carrefour + 4.0
        n = int((fin - debut) / pas) + 1
        return [self.pose(debut + i * pas)[:2] for i in range(n)]

    def _vers_absolu(self, x, y, hx, hy):
        x, y = _tourner(x, y, self.entree)
        hx, hy = _tourner(hx, hy, self.entree)
        return (x, y, hx, hy)


class Trajectoire(_TrajectoireBase):

    disposition = DISPOSITION_CROIX

    def _construire(self):
        r, d = DEMI_ROUTE, DECALAGE_VOIE
        self.l_approche = _bord(self.entree) - r          # bord de la scène -> début du carrefour
        self.l_carrefour = {2: 2 * r,
                            3: (r - d) * math.pi / 2,
                            1: (r + d) * math.pi / 2}[self.virage]
        self.l_sortie = _bord(self.sortie) - r            # fin du carrefour -> bord de la scène
        self.x_ligne = self.l_approche - DECALAGE_LIGNE   # le pare-chocs avant touche la ligne

    def _courbure(self, s):
        t = s - self.l_approche
        if t < 0 or t > self.l_carrefour or self.virage == 2:
            return 0.0
        return 1 / (DEMI_ROUTE - DECALAGE_VOIE) if self.virage == 3 else 1 / (DEMI_ROUTE + DECALAGE_VOIE)

    def _pose_exacte(self, s):
        r, d = DEMI_ROUTE, DECALAGE_VOIE
        s = max(s, 0.0)
        if s <= self.l_approche:                                  # approche
            x, y, hx, hy = -d, -(self.l_approche + r) + s, 0.0, 1.0
        else:
            t = s - self.l_approche
            if t <= self.l_carrefour:                             # dans le carrefour
                if self.virage == 2:
                    x, y, hx, hy = -d, -r + t, 0.0, 1.0
                elif self.virage == 3:                            # droite : quart de cercle autour du coin
                    rayon = r - d
                    phi = t / rayon
                    x, y = -r + rayon * math.cos(phi), -r + rayon * math.sin(phi)
                    hx, hy = -math.sin(phi), math.cos(phi)
                else:                                             # gauche : grand quart de cercle
                    rayon = r + d
                    phi = math.pi - t / rayon
                    x, y = r + rayon * math.cos(phi), -r + rayon * math.sin(phi)
                    hx, hy = math.sin(phi), -math.cos(phi)
            else:                                                 # voie de sortie
                t -= self.l_carrefour
                if self.virage == 2:
                    x, y, hx, hy = -d, r + t, 0.0, 1.0
                elif self.virage == 3:
                    x, y, hx, hy = -r - t, -d, -1.0, 0.0
                else:
                    x, y, hx, hy = r + t, d, 1.0, 0.0
        return self._vers_absolu(x, y, hx, hy)


class TrajectoireGiratoire(_TrajectoireBase):

    disposition = DISPOSITION_GIRATOIRE

    def _construire(self):
        d, R, r = DECALAGE_VOIE, RAYON_ANNEAU, RAYON_RACCORD
        # Le centre du virage d'entrée est à r de la voie et à R + r du centre de l'anneau.
        self._b = math.sqrt((R + r) ** 2 - (d + r) ** 2)    # le virage commence à cette distance du centre
        self._alpha = math.atan2(self._b, d + r)            # angle des virages d'entrée et de sortie
        # Angles (repère écran) où l'on rejoint l'anneau en venant du haut, et où on le quitte
        # pour repartir par le haut ; pour une autre sortie, on tourne ce point d'un quart de tour par bras.
        self._theta_entree = math.atan2(-self._b, -(d + r))
        theta_sortie = math.atan2(-self._b, d + r)
        self._delta = (self._theta_entree - theta_sortie - self.virage * math.pi / 2) % (2 * math.pi)
        self._l_raccord = r * self._alpha
        self._l_anneau = R * self._delta
        self.l_approche = _bord(self.entree) - self._b
        self.l_carrefour = 2 * self._l_raccord + self._l_anneau
        self.l_sortie = _bord(self.sortie) - self._b
        self.x_ligne = _bord(self.entree) - LIGNE_GIRATOIRE

    def _courbure(self, s):
        t = s - self.l_approche
        if t < 0 or t > self.l_carrefour:
            return 0.0
        if self._l_raccord <= t <= self._l_raccord + self._l_anneau:
            return 1 / RAYON_ANNEAU
        return 1 / RAYON_RACCORD

    def _pose_exacte(self, s):
        d, R, r, b = DECALAGE_VOIE, RAYON_ANNEAU, RAYON_RACCORD, self._b
        s = max(s, 0.0)
        if s <= self.l_approche:                                  # approche
            return self._vers_absolu(-d, -(self.l_approche + b) + s, 0.0, 1.0)
        t = s - self.l_approche
        if t <= self._l_raccord:                                  # virage d'entrée (à droite)
            phi = t / r
            return self._vers_absolu(-(d + r) + r * math.cos(phi), -b + r * math.sin(phi),
                                     -math.sin(phi), math.cos(phi))
        t -= self._l_raccord
        if t <= self._l_anneau:                                   # anneau (sens inverse des aiguilles)
            theta = self._theta_entree - t / R
            return self._vers_absolu(R * math.cos(theta), R * math.sin(theta),
                                     math.sin(theta), -math.cos(theta))
        t -= self._l_anneau
        if t <= self._l_raccord:                                  # virage de sortie (à droite)
            psi = math.pi - self._alpha + t / r
            x, y, hx, hy = (d + r) + r * math.cos(psi), -b + r * math.sin(psi), -math.sin(psi), math.cos(psi)
        else:                                                     # voie de sortie
            x, y, hx, hy = d, -b - (t - self._l_raccord), 0.0, -1.0
        x, y = _tourner(x, y, self.virage)                        # vers le bras de sortie
        hx, hy = _tourner(hx, hy, self.virage)
        return self._vers_absolu(x, y, hx, hy)


# --- les 2 × 12 trajectoires possibles -------------------------------------------------------
TRAJECTOIRES = {(e, s): Trajectoire(e, s) for e in range(4) for s in range(4) if e != s}
TRAJECTOIRES_GIRATOIRE = {(e, s): TrajectoireGiratoire(e, s) for e in range(4) for s in range(4) if e != s}
_PAR_DISPOSITION = {DISPOSITION_CROIX: TRAJECTOIRES, DISPOSITION_GIRATOIRE: TRAJECTOIRES_GIRATOIRE}
DISPOSITIONS = tuple(_PAR_DISPOSITION)


def trajectoire(entree, sortie, disposition=DISPOSITION_CROIX):
    try:
        return _PAR_DISPOSITION[disposition][(entree, sortie)]
    except (KeyError, TypeError):
        raise ValueError(f"trajectoire impossible : entrée {entree!r}, sortie {sortie!r}, "
                         f"disposition {disposition!r}") from None


def _se_rapprochent(a, b):
    points_b = b.points_carrefour()
    seuil2 = SEUIL_CONFLIT ** 2
    return any((xa - xb) ** 2 + (ya - yb) ** 2 < seuil2
               for xa, ya in a.points_carrefour() for xb, yb in points_b)


def _construire_compatibilites(trajectoires):
    table = {}
    mouvements = sorted(trajectoires)
    for i, ma in enumerate(mouvements):
        table[(ma, ma)] = True
        for mb in mouvements[i + 1:]:
            ok = ma[0] == mb[0] or not _se_rapprochent(trajectoires[ma], trajectoires[mb])
            table[(ma, mb)] = table[(mb, ma)] = ok
    return table


_COMPATIBLES = {disposition: _construire_compatibilites(trajectoires)
                for disposition, trajectoires in _PAR_DISPOSITION.items()}


def compatibles(mouvement_a, mouvement_b, disposition=DISPOSITION_CROIX):
    return _COMPATIBLES[disposition][(mouvement_a, mouvement_b)]
