"""Journal de la simulation dans MariaDB (facultatif).

Le serveur signale ce qu'il observe (un véhicule envoie sa position, un véhicule se déconnecte,
les feux viennent d'être évalués...). Le journal en déduit ce qu'il faut enregistrer :
  - la simulation (début, fin) ;
  - la fiche de chaque véhicule (apparition, entrée et sortie du carrefour, attente, vitesse) ;
  - la fiche du véhicule prioritaire (début et fin de sa priorité sur les feux) ;
  - les événements : changements de feux, passages dans le carrefour, priorité, conflits ;
  - une mesure statistique par seconde.

Les écritures passent par une file d'attente et sont faites par un thread à part : une base
lente ou absente ne ralentit jamais la simulation. Si MariaDB est injoignable ou tombe en cours
de route, les écritures sont abandonnées (un message s'affiche une fois) et le journal retente de
se connecter régulièrement.
"""
import datetime
import importlib.util
import queue
import threading
import time

from Domaine import compter_conflits
from Geometrie import LONGUEUR_VEHICULE

PAUSE_RECONNEXION = 10.0     # secondes entre deux tentatives de connexion
TAILLE_FILE = 20000          # au-delà, on abandonne des écritures plutôt que de ralentir la simulation


class SuiviVehicule:
    """Ce que le journal retient d'un véhicule pendant qu'il circule."""

    def __init__(self, numero, code, vehicule, maintenant):
        self.numero = numero                  # numéro local ; la base attribue son propre id
        self.code = code
        self.vehicule_id = vehicule.id
        self.trajectoire = vehicule.trajectoire
        self.apparition = maintenant
        self.dernier_instant = maintenant
        self.premier_x = vehicule.x
        self.dernier_x = vehicule.x
        self.entree_carrefour = None
        self.sortie_carrefour = None
        self.attente = 0.0


def _ouvrir_mariadb(config):
    from base_stats import BaseStats          # mariadb n'est importé que si la base est utilisée
    return BaseStats(config)


class JournalSimulation:
    def __init__(self, config, ouvrir_base=_ouvrir_mariadb):
        self.__config = config
        self.__ouvrir_base = ouvrir_base
        self.__file = queue.Queue(maxsize=TAILLE_FILE)
        self.__decalage = time.time() - time.monotonic()      # pour dater en heure réelle
        self.__etat = "connexion..."
        self.__taux = None
        # --- suivi : utilisé uniquement par le thread du serveur ---
        self.__simulation = None
        self.__type = None
        self.__nb_simulations = 0
        self.__nb_vehicules = 0
        self.__suivis = {}               # clé de connexion -> SuiviVehicule
        self.__codes = set()             # codes déjà utilisés dans la simulation
        self.__feux = None               # derniers états des feux
        self.__priorite = None           # (clé, numéro, début) du prioritaire qui commande les feux
        self.__fil = threading.Thread(target=self.__ecrire, name="journal-bdd", daemon=True)
        self.__fil.start()

    @property
    def etat(self):
        """'connexion...', 'connectée', 'indisponible' ou 'connexion perdue'."""
        return self.__etat

    def __date(self, maintenant):
        return None if maintenant is None else datetime.datetime.fromtimestamp(maintenant + self.__decalage)

    def __envoyer(self, *operation):
        try:
            self.__file.put_nowait(operation)
        except queue.Full:
            pass                         # la base ne suit pas : on perd cette écriture

    def __evenement(self, maintenant, type_evenement, numero=None, bras=None, valeur=None):
        self.__envoyer("evenement", self.__simulation, self.__date(maintenant), type_evenement,
                       numero, bras, valeur)

    # ------------------------------------------------------------------ signalements du serveur
    def debut_simulation(self, type_carrefour, maintenant):
        if self.__simulation is not None:
            self.fin_simulation(maintenant)
        self.__nb_simulations += 1
        self.__simulation = self.__nb_simulations
        self.__type = type_carrefour
        self.__suivis, self.__codes, self.__feux, self.__priorite = {}, set(), None, None
        self.__taux = None
        self.__envoyer("simulation", self.__simulation, type_carrefour, self.__date(maintenant))
        self.__evenement(maintenant, "debut_simulation")

    def fin_simulation(self, maintenant):
        if self.__simulation is None:
            return
        self.__terminer_priorite(maintenant)
        for cle in list(self.__suivis):
            self.depart(cle, maintenant, interrompu=True)
        self.__evenement(maintenant, "fin_simulation")
        self.__envoyer("fin_simulation", self.__simulation, self.__date(maintenant))
        self.__simulation = None

    def vehicule(self, cle, vehicule, maintenant):
        """Un véhicule vient d'envoyer sa position."""
        if self.__simulation is None:
            return
        suivi = self.__suivis.get(cle)
        if suivi is None:                                   # première apparition
            self.__nb_vehicules += 1
            code = vehicule.id if vehicule.id not in self.__codes else f"{vehicule.id}-{self.__nb_vehicules}"
            self.__codes.add(code)
            suivi = SuiviVehicule(self.__nb_vehicules, code, vehicule, maintenant)
            self.__suivis[cle] = suivi
            self.__envoyer("vehicule", suivi.numero, self.__simulation, code, vehicule.type,
                           vehicule.entree, vehicule.sortie, vehicule.vitesse_max, self.__date(maintenant))
        else:
            if vehicule.vitesse < 0.05:
                suivi.attente += maintenant - suivi.dernier_instant
            suivi.dernier_instant = maintenant
            suivi.dernier_x = vehicule.x
        zone = vehicule.zone()
        if zone != "approche" and suivi.entree_carrefour is None:
            suivi.entree_carrefour = maintenant
            self.__evenement(maintenant, "entree_carrefour", suivi.numero)
        if zone == "sortie" and suivi.sortie_carrefour is None:
            suivi.sortie_carrefour = maintenant
            self.__evenement(maintenant, "sortie_carrefour", suivi.numero)

    def depart(self, cle, maintenant, interrompu=False):
        """Un véhicule s'est déconnecté (fin de trajet, ou fin de la simulation si `interrompu`)."""
        suivi = self.__suivis.pop(cle, None)
        if suivi is None:
            return
        # Le dernier message d'un véhicule arrive juste avant qu'il ne quitte la scène.
        complet = (not interrompu and
                   suivi.dernier_x + 1.0 >= suivi.trajectoire.longueur + LONGUEUR_VEHICULE / 2)
        duree = suivi.dernier_instant - suivi.apparition
        vitesse = round((suivi.dernier_x - suivi.premier_x) / duree, 3) if duree > 0 else None
        self.__envoyer("fin_vehicule", suivi.numero, self.__date(suivi.entree_carrefour),
                       self.__date(suivi.sortie_carrefour), self.__date(maintenant), complet,
                       round(suivi.attente, 2), vitesse)

    def feux(self, feux, prioritaire, maintenant):
        """Les feux viennent d'être évalués ; `prioritaire` : véhicule qui les commande, ou None."""
        if self.__simulation is None:
            return
        etats = tuple(f.etat for f in feux)
        if etats != self.__feux:
            for bras, etat in enumerate(etats):
                if self.__feux is None or self.__feux[bras] != etat:
                    self.__evenement(maintenant, "changement_feu", bras=bras, valeur=etat)
            self.__feux = etats
        cle = None
        if prioritaire is not None:
            cle = next((c for c, s in self.__suivis.items() if s.vehicule_id == prioritaire.id), None)
        if cle != (self.__priorite[0] if self.__priorite else None):
            self.__terminer_priorite(maintenant)
            if cle is not None:
                numero = self.__suivis[cle].numero
                self.__priorite = (cle, numero, maintenant)
                self.__evenement(maintenant, "debut_priorite", numero)

    def __terminer_priorite(self, maintenant):
        if self.__priorite is None:
            return
        _, numero, debut = self.__priorite
        self.__evenement(maintenant, "fin_priorite", numero)
        self.__envoyer("fin_prioritaire", numero, self.__date(debut), self.__date(maintenant))
        self.__priorite = None

    def prioritaire_refuse(self, cle, vehicule, maintenant):
        suivi = self.__suivis.get(cle)
        if self.__simulation is not None and suivi is not None:
            self.__evenement(maintenant, "prioritaire_refuse", suivi.numero)

    def mesure(self, vehicules, maintenant):
        """Mesure statistique (une par seconde). Renvoie ce que l'interface affiche."""
        stats = {"bdd": self.__etat}
        if self.__taux is not None:
            stats["taux_accident"] = self.__taux
        if self.__simulation is None:
            return stats
        nb = len(vehicules)
        vitesse = sum(v.vitesse for v in vehicules) / nb if nb else 0.0
        prioritaires = sum(1 for v in vehicules if v.est_prioritaire())
        conflits = compter_conflits(vehicules)
        if conflits:
            self.__evenement(maintenant, "conflit", valeur=str(conflits))
        self.__envoyer("mesure", self.__simulation, self.__type, nb, round(vitesse, 3), prioritaires, conflits)
        return stats

    def fermer(self, delai=3.0):
        """Termine les écritures en attente (au plus `delai` secondes) puis ferme la connexion."""
        try:
            self.__file.put(None, timeout=delai)
        except queue.Full:
            pass
        self.__fil.join(delai)

    # ------------------------------------------------------------------ thread d'écriture
    def __changer_etat(self, etat, message):
        if etat != self.__etat:
            print(message)               # une seule fois par changement : pas de messages en rafale
        self.__etat = etat

    def __ecrire(self):
        base, prochain_essai = None, 0.0
        ids_simulations, ids_vehicules = {}, {}       # numéros locaux -> id en base
        while True:
            operation = self.__file.get()
            if operation is None:
                break
            if base is None:
                if time.monotonic() < prochain_essai:
                    continue                          # base indisponible : écriture abandonnée
                try:
                    base = self.__ouvrir_base(self.__config)
                except Exception as erreur:
                    self.__changer_etat("indisponible", f"MariaDB indisponible ({erreur}) : la simulation "
                                        f"continue sans enregistrer, nouvel essai dans {PAUSE_RECONNEXION:.0f} s")
                    prochain_essai = time.monotonic() + PAUSE_RECONNEXION
                    continue
                self.__changer_etat("connectée", f"MariaDB : enregistrement dans {self.__config}")
            try:
                self.__appliquer(base, operation, ids_simulations, ids_vehicules)
            except Exception as erreur:
                if base.est_connectee():
                    print("MariaDB : écriture ignorée :", erreur)
                else:
                    self.__changer_etat("connexion perdue", f"MariaDB : connexion perdue ({erreur}), "
                                        f"nouvel essai dans {PAUSE_RECONNEXION:.0f} s")
                    base.fermer()
                    base = None
                    prochain_essai = time.monotonic() + PAUSE_RECONNEXION
        if base is not None:
            base.fermer()

    def __appliquer(self, base, operation, ids_simulations, ids_vehicules):
        nature, *donnees = operation
        if nature == "simulation":
            numero, type_carrefour, debut = donnees
            ids_simulations[numero] = base.creer_simulation(type_carrefour, debut)
        elif nature == "fin_simulation":
            numero, fin = donnees
            if numero in ids_simulations:
                base.terminer_simulation(ids_simulations.pop(numero), fin)
        elif nature == "vehicule":
            numero, simulation, code, type_v, entree, sortie, vitesse_max, apparition = donnees
            if simulation in ids_simulations:
                ids_vehicules[numero] = base.creer_vehicule(ids_simulations[simulation], code, type_v,
                                                            entree, sortie, vitesse_max, apparition)
        elif nature == "fin_vehicule":
            numero, *resume = donnees
            if numero in ids_vehicules:
                base.terminer_vehicule(ids_vehicules[numero], *resume)
        elif nature == "fin_prioritaire":
            numero, debut, fin = donnees
            if numero in ids_vehicules:
                base.terminer_prioritaire(ids_vehicules[numero], debut, fin)
        elif nature == "evenement":
            simulation, instant, type_evenement, numero, bras, valeur = donnees
            if simulation in ids_simulations and (numero is None or numero in ids_vehicules):
                vehicule_id = None if numero is None else ids_vehicules[numero]
                base.ajouter_evenement(ids_simulations[simulation], instant, type_evenement,
                                       vehicule_id, bras, valeur)
        elif nature == "mesure":
            simulation, type_carrefour, nb, vitesse, prioritaires, conflits = donnees
            if simulation in ids_simulations:
                base.enregistrer_mesure(ids_simulations[simulation], type_carrefour, nb, vitesse,
                                        prioritaires, conflits)
                self.__taux = base.taux_accident(type_carrefour)


def ouvrir_journal():
    """Journal MariaDB si la base est configurée dans .env et le module mariadb installé, sinon None
    (la raison est affichée ; la simulation fonctionne aussi sans base)."""
    from config_bdd import charger_config
    config = charger_config()
    if config is None:
        return None
    if importlib.util.find_spec("mariadb") is None:
        print("MariaDB désactivée : module mariadb manquant (pip install mariadb)")
        return None
    return JournalSimulation(config)