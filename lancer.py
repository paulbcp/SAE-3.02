import argparse
import os
import sys

DOSSIER_CODE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Code")
sys.path.insert(0, DOSSIER_CODE)


def main():
    from Domaine import CONTROLEURS, GIRATOIRE

    parser = argparse.ArgumentParser(description="Simulation de carrefour connecté.")
    parser.add_argument("carrefour", nargs="?", choices=list(CONTROLEURS), default=GIRATOIRE,
                        help="simulation à afficher au démarrage (giratoire par défaut)")
    parser.add_argument("--port", type=int, default=5000, help="port du serveur (5000 par défaut)")
    parser.add_argument("--sans-trafic", action="store_true",
                        help="ne pas générer de véhicules (les lancer avec Code/ClientVehicule.py)")
    parser.add_argument("--sans-bdd", action="store_true", help="ne pas utiliser MariaDB")
    parser.add_argument("--console", action="store_true", help="sans interface graphique")
    parser.add_argument("--duree", type=float, default=None, help="(console) durée en secondes")
    args = parser.parse_args()

    if args.console:
        import ServeurIntersection
        sys.argv = [sys.argv[0], "--carrefour", args.carrefour, "--port", str(args.port)]
        if not args.sans_trafic:
            sys.argv.append("--trafic")
        if args.sans_bdd:
            sys.argv.append("--sans-bdd")
        if args.duree:
            sys.argv += ["--duree", str(args.duree)]
        ServeurIntersection.main()
        return

    from PyQt6.QtWidgets import QApplication
    from Fenetre_principale import FenetrePrincipale

    app = QApplication(sys.argv)
    fenetre = FenetrePrincipale(args.carrefour, args.port, not args.sans_trafic, not args.sans_bdd)
    fenetre.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
