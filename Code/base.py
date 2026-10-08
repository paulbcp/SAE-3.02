import pymysql


class BaseStats:
    def __init__(self, hote="localhost", utilisateur="sae", mot_de_passe="un_mot_de_passe", base="carrefour"):
        self.__connexion = pymysql.connect(host=hote, user=utilisateur,
                                           password=mot_de_passe, database=base)
        with self.__connexion.cursor() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS statistiques (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            instant DATETIME DEFAULT CURRENT_TIMESTAMP,
                            nb_vehicules INT,
                            vitesse_moyenne FLOAT,
                            nb_prioritaires INT)""")
        self.__connexion.commit()

    def enregistrer_tick(self, vehicules):
        nb = len(vehicules)
        vitesse = sum(v.vitesse for v in vehicules) / nb if nb else 0
        prioritaires = sum(1 for v in vehicules if v.est_prioritaire())
        with self.__connexion.cursor() as c:
            c.execute("INSERT INTO statistiques (nb_vehicules, vitesse_moyenne, nb_prioritaires) "
                      "VALUES (%s, %s, %s)", (nb, vitesse, prioritaires))
        self.__connexion.commit()

    def derniere_stat(self):
        with self.__connexion.cursor() as c:
            c.execute("SELECT nb_vehicules, vitesse_moyenne, nb_prioritaires "
                      "FROM statistiques ORDER BY id DESC LIMIT 1")
            return c.fetchone()