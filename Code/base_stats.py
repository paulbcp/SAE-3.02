"""Accès à la base MariaDB avec le connecteur officiel mariadb : c'est le SEUL module qui contient du SQL.

Écriture (appelée par le thread du journal, voir Journal.py) : simulations, véhicules, véhicule
prioritaire, événements, statistiques. Lecture (consulter_bdd.py) : résumés et détails.
Les tables sont décrites dans sql/02_schema.sql ; elles sont créées automatiquement si elles
manquent.
"""
import os

import mariadb

from config_bdd import RACINE

SCHEMA = os.path.join(RACINE, "sql", "02_schema.sql")
VERSION_SCHEMA = 1        # doit correspondre à la fin de sql/02_schema.sql
MOUVEMENTS = {1: "gauche", 2: "tout_droit", 3: "droite"}     # (sortie - entrée) % 4


def decouper_sql(texte):
    """Découpe un script SQL en instructions (une instruction se termine par « ; » en fin de
    ligne). Les commentaires « -- » sont retirés ; le script ne doit pas en contenir dans des
    chaînes de caractères."""
    instructions, courante = [], []
    for ligne in texte.splitlines():
        position = ligne.find("--")
        if position >= 0:
            ligne = ligne[:position]
        ligne = ligne.rstrip()
        if not ligne:
            continue
        courante.append(ligne)
        if ligne.endswith(";"):
            instructions.append("\n".join(courante)[:-1])
            courante = []
    if "".join(courante).strip():
        instructions.append("\n".join(courante))
    return instructions


class BaseStats:
    def __init__(self, config):
        """Se connecte (lève mariadb.Error si c'est impossible) et crée les tables au besoin."""
        self.__connexion = mariadb.connect(
            host=config.hote, port=config.port, user=config.utilisateur,
            password=config.mot_de_passe, database=config.base, autocommit=True,
            connect_timeout=max(1, int(config.delai_connexion)), read_timeout=10, write_timeout=10)
        self.verifier_schema()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fermer()

    def fermer(self):
        try:
            self.__connexion.close()
        except mariadb.Error:
            pass

    def est_connectee(self):
        try:
            self.__connexion.ping()
            return True
        except mariadb.Error:
            return False

    # ------------------------------------------------------------------ outils
    def __executer(self, requete, parametres=None):
        with self.__connexion.cursor() as c:
            c.execute(requete, parametres or ())
            return c.lastrowid

    def __lire(self, requete, parametres=None):
        with self.__connexion.cursor(dictionary=True) as c:
            c.execute(requete, parametres or ())
            return c.fetchall()

    def version_schema(self):
        """Version du schéma installé dans la base (0 : base vide ou ancienne version du projet)."""
        if not self.__lire("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() "
                           "AND table_name = 'version_schema'"):
            return 0
        lignes = self.__lire("SELECT version FROM version_schema WHERE id = 1")
        return lignes[0]["version"] if lignes else 0

    def verifier_schema(self):
        """Exécute sql/02_schema.sql si la base est vide, vient d'une ancienne version du projet
        (ancienne table « statistiques ») ou a un schéma plus ancien que ce code. Le script ne
        supprime rien : les données déjà enregistrées sont conservées."""
        if self.version_schema() < VERSION_SCHEMA:
            self.executer_script(SCHEMA)

    def executer_script(self, chemin):
        with open(chemin, encoding="utf-8") as fichier:
            for instruction in decouper_sql(fichier.read()):
                self.__executer(instruction)

    # ------------------------------------------------------------------ écriture
    def creer_simulation(self, type_carrefour, debut):
        return self.__executer("INSERT INTO simulation (type_carrefour, debut) VALUES (%s, %s)",
                               (type_carrefour, debut))

    def terminer_simulation(self, simulation_id, fin):
        self.__executer("UPDATE simulation SET fin = %s WHERE id = %s", (fin, simulation_id))

    def creer_vehicule(self, simulation_id, code, type_v, entree, sortie, vitesse_max, apparition):
        """Fiche du véhicule à son apparition ; le véhicule prioritaire a aussi sa fiche dédiée."""
        vehicule_id = self.__executer(
            "INSERT INTO vehicule (simulation_id, code, type, entree, sortie, mouvement, "
            "vitesse_max, apparition) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (simulation_id, code, type_v, entree, sortie, MOUVEMENTS[(sortie - entree) % 4],
             vitesse_max, apparition))
        if type_v == "prioritaire":
            self.__executer("INSERT INTO vehicule_prioritaire (vehicule_id) VALUES (%s)", (vehicule_id,))
        return vehicule_id

    def terminer_vehicule(self, vehicule_id, entree_carrefour, sortie_carrefour, disparition,
                          trajet_complet, temps_attente_s, vitesse_moyenne):
        self.__executer(
            "UPDATE vehicule SET entree_carrefour = %s, sortie_carrefour = %s, disparition = %s, "
            "trajet_complet = %s, temps_attente_s = %s, vitesse_moyenne = %s WHERE id = %s",
            (entree_carrefour, sortie_carrefour, disparition, trajet_complet, temps_attente_s,
             vitesse_moyenne, vehicule_id))

    def terminer_prioritaire(self, vehicule_id, debut, fin):
        self.__executer(
            "UPDATE vehicule_prioritaire SET debut_priorite = %s, fin_priorite = %s, "
            "duree_priorite_s = TIMESTAMPDIFF(MICROSECOND, %s, %s) / 1000000 WHERE vehicule_id = %s",
            (debut, fin, debut, fin, vehicule_id))

    def ajouter_evenement(self, simulation_id, instant, type_evenement, vehicule_id=None,
                          bras=None, valeur=None):
        self.__executer(
            "INSERT INTO evenement (simulation_id, instant, type, vehicule_id, bras, valeur) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (simulation_id, instant, type_evenement, vehicule_id, bras, valeur))

    def enregistrer_mesure(self, simulation_id, type_carrefour, nb_vehicules, vitesse_moyenne,
                           nb_prioritaires, nb_conflits):
        self.__executer(
            "INSERT INTO statistiques (simulation_id, type_carrefour, nb_vehicules, vitesse_moyenne, "
            "nb_prioritaires, nb_conflits) VALUES (%s, %s, %s, %s, %s, %s)",
            (simulation_id, type_carrefour, nb_vehicules, vitesse_moyenne, nb_prioritaires, nb_conflits))

    def taux_accident(self, type_carrefour):
        """% des mesures (avec au moins un véhicule) où un conflit a été constaté, pour ce type."""
        ligne = self.__lire(
            "SELECT COALESCE(100 * AVG(nb_conflits > 0), 0) AS taux FROM statistiques "
            "WHERE type_carrefour = %s AND nb_vehicules > 0", (type_carrefour,))
        return float(ligne[0]["taux"])

    # ------------------------------------------------------------------ lecture
    def simulations(self, limite=20):
        return self.__lire("SELECT * FROM v_resume_simulation ORDER BY id DESC LIMIT %s", (limite,))

    def simulation(self, simulation_id):
        lignes = self.__lire("SELECT * FROM v_resume_simulation WHERE id = %s", (simulation_id,))
        return lignes[0] if lignes else None

    def vehicules(self, simulation_id):
        return self.__lire(
            "SELECT v.code, v.type, v.entree, v.sortie, v.mouvement, v.apparition, "
            "v.entree_carrefour, v.sortie_carrefour, v.trajet_complet, v.temps_attente_s, "
            "v.vitesse_moyenne FROM vehicule v WHERE v.simulation_id = %s ORDER BY v.id",
            (simulation_id,))

    def vehicules_prioritaires(self, simulation_id=None):
        if simulation_id is None:
            return self.__lire("SELECT * FROM v_vehicules_prioritaires ORDER BY apparition DESC")
        return self.__lire("SELECT * FROM v_vehicules_prioritaires WHERE simulation_id = %s",
                           (simulation_id,))

    def evenements(self, simulation_id, limite=None):
        """Événements dans l'ordre chronologique (seulement les `limite` derniers si précisé)."""
        if limite is None:
            return self.__lire("SELECT * FROM v_journal WHERE simulation_id = %s ORDER BY instant, id",
                               (simulation_id,))
        return self.__lire(
            "SELECT * FROM (SELECT * FROM v_journal WHERE simulation_id = %s "
            "ORDER BY instant DESC, id DESC LIMIT %s) AS derniers ORDER BY instant, id",
            (simulation_id, int(limite)))

    def nombre_evenements(self, simulation_id):
        return self.__lire("SELECT type, COUNT(*) AS nombre FROM evenement WHERE simulation_id = %s "
                           "GROUP BY type ORDER BY type", (simulation_id,))

    def resume_statistiques(self, simulation_id):
        return self.__lire(
            "SELECT COUNT(*) AS nb_mesures, ROUND(AVG(nb_vehicules), 1) AS vehicules_moyen, "
            "MAX(nb_vehicules) AS vehicules_max, ROUND(AVG(vitesse_moyenne), 2) AS vitesse_moyenne, "
            "COALESCE(SUM(nb_conflits > 0), 0) AS mesures_avec_conflit "
            "FROM statistiques WHERE simulation_id = %s", (simulation_id,))[0]