import math

A_MAX = 1.5 # accéleration
B_CONF = 3.0 #freinage_normale
B_MAX = 6.0 #freinage urgence
T_INTER = 0.9        # temps entre les vehicules ideale
S0 = 0.6             # distance minimale souhaitée à l'arrêt
MARGE_CONTACT = 0.08  # distance qu'on ne franchit jamais, quoi qu'il arrive

# --- détection d'obstacles : une voiture est approchée par 2 disques ------------------------
RAYON_DISQUE = 0.58
DECALAGE_DISQUE = 0.45     # distance de chaque disque au centre de la voiture
PAS_BALAYAGE = 0.25        # pas de l'exploration du trajet devant le véhicule
HORIZON_MAX = 12.0
_SEUIL2 = (2 * RAYON_DISQUE) ** 2


def distance_freinage(vitesse, deceleration):
    return vitesse * vitesse / (2 * deceleration)


def acceleration_idm(vitesse, vitesse_voulue, ecart=None, vitesse_devant=0.0):
    libre = 1.0 - (vitesse / vitesse_voulue) ** 4
    if ecart is None:
        return A_MAX * libre
    voulu = S0 + max(0.0, vitesse * T_INTER
                     + vitesse * (vitesse - vitesse_devant) / (2 * math.sqrt(A_MAX * B_CONF)))
    acceleration = A_MAX * (libre - (voulu / max(ecart, 0.01)) ** 2)
    return max(-B_MAX, acceleration)


def obstacle_devant(vehicule, autres, horizon=None):
    traj = vehicule.trajectoire
    x = vehicule.x
    if horizon is None:
        horizon = min(HORIZON_MAX, 4.0 + 2.0 * vehicule.vitesse)
    x0, y0, hx0, hy0 = traj.pose(x)
    limite2 = (horizon + 3.0) ** 2

    proches = []
    for autre in autres:
        if autre is vehicule:
            continue
        xb, yb, hxb, hyb = autre.trajectoire.pose(autre.x)
        dx, dy = xb - x0, yb - y0
        if dx * dx + dy * dy > limite2:
            continue                       # trop loin pour gêner
        if dx * hx0 + dy * hy0 < -0.2:
            continue                       # derrière nous : jamais un obstacle
        proches.append((autre, hxb, hyb,
                        (xb - DECALAGE_DISQUE * hxb, yb - DECALAGE_DISQUE * hyb),
                        (xb + DECALAGE_DISQUE * hxb, yb + DECALAGE_DISQUE * hyb)))
    if not proches:
        return None
    
    def contact(d):
        """Si le véhicule, avancé de d, touche un autre véhicule : (vitesse de celui-ci), sinon None."""
        px, py, hx, hy = traj.pose(x + d)
        mes_disques = ((px - DECALAGE_DISQUE * hx, py - DECALAGE_DISQUE * hy),
                       (px + DECALAGE_DISQUE * hx, py + DECALAGE_DISQUE * hy))
        for autre, hxb, hyb, d1, d2 in proches:
            for ax, ay in mes_disques:
                for bx, by in (d1, d2):
                    if (ax - bx) ** 2 + (ay - by) ** 2 < _SEUIL2:
                        return max(0.0, autre.vitesse * (hx * hxb + hy * hyb))
        return None

    d = 0.0
    while d <= horizon:
        vitesse_obstacle = contact(d)
        if vitesse_obstacle is not None:
            if d > 0:                      # affine par dichotomie entre le dernier pas libre et celui-ci
                bas, haut = d - PAS_BALAYAGE, d
                for _ in range(6):
                    milieu = (bas + haut) / 2
                    if contact(milieu) is None:
                        bas = milieu
                    else:
                        haut = milieu
                d = haut
            return (d, vitesse_obstacle)
        d += PAS_BALAYAGE
    return None