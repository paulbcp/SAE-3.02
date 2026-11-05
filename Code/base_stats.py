import pymysql

ZONE_DEBUT = 10    # ligne d'arrêt
ZONE_FIN = 16      # sortie du carrefour


class BaseStats:
    def __init__(self, hote="127.0.0.1", utilisateur="sae",
                 mot_de_passe="un_mot_de_passe", base="carrefour"):
        self.__connexion = pymysql.connect(host=hote, user=utilisateur, password=mot_de_passe,
                                           database=base, autocommit=True)
        with self.__connexion.cursor() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS statistiques (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            instant DATETIME DEFAULT CURRENT_TIMESTAMP,
                            type_carrefour VARCHAR(40),
                            nb_vehicules INT,
                            vitesse_moyenne FLOAT,
                            nb_prioritaires INT,
                            nb_conflits INT)""")

    @staticmethod
    def compter_conflits(vehicules):
        """Un conflit = deux véhicules dans le carrefour en même temps,
        venant d'entrées perpendiculaires."""
        dedans = [v for v in vehicules if ZONE_DEBUT < v.x < ZONE_FIN]
        conflits = 0
        for i in range(len(dedans)):
            for j in range(i + 1, len(dedans)):
                if (dedans[i].entree - dedans[j].entree) % 2 == 1:
                    conflits += 1
        return conflits

    def enregistrer_tick(self, vehicules, type_carrefour):
        nb = len(vehicules)
        vitesse = sum(v.vitesse for v in vehicules) / nb if nb else 0
        prioritaires = sum(1 for v in vehicules if v.est_prioritaire())
        conflits = self.compter_conflits(vehicules)
        with self.__connexion.cursor() as c:
            c.execute("INSERT INTO statistiques (type_carrefour, nb_vehicules, vitesse_moyenne, "
                      "nb_prioritaires, nb_conflits) VALUES (%s, %s, %s, %s, %s)",
                      (type_carrefour, nb, vitesse, prioritaires, conflits))
            # taux d'accident = % de mesures avec au moins un conflit, pour ce type de carrefour
            c.execute("SELECT COALESCE(100 * AVG(nb_conflits > 0), 0) FROM statistiques "
                      "WHERE type_carrefour = %s AND nb_vehicules > 0", (type_carrefour,))
            taux = float(c.fetchone()[0])
        return {"nb_vehicules": nb, "vitesse_moyenne": vitesse,
                "nb_prioritaires": prioritaires, "nb_conflits": conflits,
                "taux_accident": taux}