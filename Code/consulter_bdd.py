import argparse
import datetime
import sys

from config_bdd import charger_config

BRAS = {0: "haut", 1: "droite", 2: "bas", 3: "gauche"}


def texte(valeur):
    if valeur is None:
        return "-"
    if isinstance(valeur, datetime.datetime):
        return valeur.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if isinstance(valeur, float):
        return f"{valeur:.2f}"
    return str(valeur)


def tableau(lignes, colonnes):
    colonnes = [c if isinstance(c, tuple) else (c, c) for c in colonnes]
    cellules = [[texte(ligne.get(cle)) for cle, _ in colonnes] for ligne in lignes]
    largeurs = [max([len(titre)] + [len(ligne[i]) for ligne in cellules])
                for i, (_, titre) in enumerate(colonnes)]
    resultat = ["  ".join(titre.ljust(l) for (_, titre), l in zip(colonnes, largeurs)),
                "  ".join("-" * l for l in largeurs)]
    resultat += ["  ".join(c.ljust(l) for c, l in zip(ligne, largeurs)) for ligne in cellules]
    return "\n".join(resultat) if lignes else "(aucune donnée)"


COLONNES_SIMULATION = [("id", "n°"), ("type_carrefour", "carrefour"), ("debut", "début"), ("fin", "fin"),
                       ("duree_s", "durée (s)"), ("nb_vehicules", "véhicules"),
                       ("nb_trajets_complets", "trajets complets"), ("nb_prioritaires", "prioritaires"),
                       ("attente_moyenne_s", "attente moy. (s)"), ("vitesse_moyenne", "vitesse moy.")]


def afficher_liste(base, nombre):
    print("Dernières simulations :\n")
    print(tableau(base.simulations(nombre), COLONNES_SIMULATION))
    print("\nDétail d'une simulation : python consulter_bdd.py <n°>")


def afficher_detail(base, simulation_id, tous_les_evenements):
    simulation = base.simulation(simulation_id)
    if simulation is None:
        print(f"Aucune simulation n°{simulation_id}.")
        return False
    print(f"Simulation n°{simulation_id}\n")
    print(tableau([simulation], COLONNES_SIMULATION))

    print("\nVéhicules :\n")
    vehicules = base.vehicules(simulation_id)
    for v in vehicules:
        v["trajet"] = f"{BRAS[v['entree']]} -> {BRAS[v['sortie']]}"
        v["complet"] = "oui" if v["trajet_complet"] else "non"
    print(tableau(vehicules, [("code", "code"), ("type", "type"), ("trajet", "trajet"),
                              ("mouvement", "mouvement"), ("apparition", "apparition"),
                              ("entree_carrefour", "entrée carrefour"), ("sortie_carrefour", "sortie carrefour"),
                              ("temps_attente_s", "attente (s)"), ("vitesse_moyenne", "vitesse moy."),
                              ("complet", "trajet complet")]))

    print("\nVéhicule prioritaire :\n")
    print(tableau(base.vehicules_prioritaires(simulation_id),
                  [("code", "code"), ("debut_priorite", "début de priorité"),
                   ("fin_priorite", "fin de priorité"), ("duree_priorite_s", "durée (s)"),
                   ("temps_attente_s", "attente (s)")]))

    print("\nStatistiques (une mesure par seconde) :\n")
    print(tableau([base.resume_statistiques(simulation_id)],
                  [("nb_mesures", "mesures"), ("vehicules_moyen", "véhicules (moy.)"),
                   ("vehicules_max", "véhicules (max)"), ("vitesse_moyenne", "vitesse moy."),
                   ("mesures_avec_conflit", "mesures avec conflit")]))

    print("\nÉvénements par type :\n")
    print(tableau(base.nombre_evenements(simulation_id), [("type", "type"), ("nombre", "nombre")]))

    limite = None if tous_les_evenements else 30
    titre = "Tous les événements" if tous_les_evenements else "30 derniers événements (--evenements pour tous)"
    print(f"\n{titre} :\n")
    evenements = base.evenements(simulation_id, limite)
    for e in evenements:
        e["bras"] = BRAS.get(e["bras"]) if e["bras"] is not None else None
    print(tableau(evenements, [("instant", "instant"), ("type", "événement"), ("vehicule", "véhicule"),
                               ("bras", "bras"), ("valeur", "valeur")]))
    return True


def main():
    parser = argparse.ArgumentParser(description="Consulter les simulations enregistrées dans MariaDB.")
    parser.add_argument("simulation", nargs="?", type=int, help="numéro de la simulation à détailler")
    parser.add_argument("--evenements", action="store_true", help="afficher tous les événements")
    parser.add_argument("--prioritaires", action="store_true", help="lister les véhicules prioritaires")
    parser.add_argument("--nombre", type=int, default=20, help="nombre de simulations listées")
    args = parser.parse_args()

    config = charger_config()
    if config is None:
        sys.exit(1)
    try:
        from base_stats import BaseStats
    except ImportError:
        print("Module mariadb manquant : pip install mariadb")
        sys.exit(1)
    try:
        base = BaseStats(config)
    except Exception as erreur:
        print(f"Connexion à MariaDB impossible ({config}) : {erreur}")
        sys.exit(1)
    with base:
        if args.prioritaires:
            print(tableau(base.vehicules_prioritaires(),
                          [("simulation_id", "simulation"), ("type_carrefour", "carrefour"), ("code", "code"),
                           ("mouvement", "mouvement"), ("apparition", "apparition"),
                           ("debut_priorite", "début de priorité"), ("fin_priorite", "fin de priorité"),
                           ("duree_priorite_s", "durée (s)")]))
        elif args.simulation is not None:
            if not afficher_detail(base, args.simulation, args.evenements):
                sys.exit(1)
        else:
            afficher_liste(base, args.nombre)


if __name__ == "__main__":
    main()