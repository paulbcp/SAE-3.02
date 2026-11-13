-- Schéma de la base « carrefour » (MariaDB 10.5 ou plus récent).
--
-- Rejouable sans risque : rien n'est supprimé, ce qui existe déjà est conservé. L'application
-- l'exécute automatiquement au premier lancement si les tables manquent. À la main :
--
--     mariadb -u sae -p carrefour < sql/02_schema.sql
--
-- Relations :
--   simulation 1 ── n vehicule 1 ── 0..1 vehicule_prioritaire
--   simulation 1 ── n evenement n ── 0..1 vehicule
--   simulation 1 ── n statistiques

-- Une simulation = un lancement d'un type de carrefour, jusqu'au changement de bouton ou à la
-- fermeture de l'application.
CREATE TABLE IF NOT EXISTS simulation (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    type_carrefour  ENUM('stop', 'feux', 'giratoire') NOT NULL,
    debut           DATETIME(3) NOT NULL,
    fin             DATETIME(3) NULL,               -- NULL : en cours (ou application arrêtée brutalement)
    INDEX idx_simulation_debut (debut)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Une fiche par véhicule ayant circulé dans une simulation.
CREATE TABLE IF NOT EXISTS vehicule (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    simulation_id     INT UNSIGNED NOT NULL,
    code              VARCHAR(32) NOT NULL,         -- identifiant dans la simulation (v0, v1...)
    type              ENUM('normal', 'prioritaire') NOT NULL,
    entree            TINYINT UNSIGNED NOT NULL,    -- bras d'arrivée : 0 haut, 1 droite, 2 bas, 3 gauche
    sortie            TINYINT UNSIGNED NOT NULL,    -- bras de sortie
    mouvement         ENUM('gauche', 'tout_droit', 'droite') NOT NULL,
    vitesse_max       FLOAT NOT NULL,               -- vitesse souhaitée (unités/s)
    apparition        DATETIME(3) NOT NULL,
    entree_carrefour  DATETIME(3) NULL,             -- franchissement de la ligne d'arrêt
    sortie_carrefour  DATETIME(3) NULL,             -- l'arrière du véhicule a quitté le carrefour
    disparition       DATETIME(3) NULL,
    trajet_complet    BOOLEAN NOT NULL DEFAULT FALSE,   -- FALSE : interrompu (changement de simulation...)
    temps_attente_s   FLOAT NOT NULL DEFAULT 0,     -- temps passé à l'arrêt
    vitesse_moyenne   FLOAT NULL,
    UNIQUE KEY uq_vehicule_code (simulation_id, code),
    CONSTRAINT fk_vehicule_simulation FOREIGN KEY (simulation_id)
        REFERENCES simulation (id) ON DELETE CASCADE,
    CONSTRAINT ck_vehicule_bras CHECK (entree <= 3 AND sortie <= 3 AND entree <> sortie)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Le véhicule d'urgence (un seul par simulation) : ce qui lui est propre.
CREATE TABLE IF NOT EXISTS vehicule_prioritaire (
    vehicule_id       INT UNSIGNED NOT NULL PRIMARY KEY,
    debut_priorite    DATETIME(3) NULL,             -- il prend la main sur les feux
    fin_priorite      DATETIME(3) NULL,             -- il a quitté le carrefour : les feux reprennent leur cycle
    duree_priorite_s  FLOAT NULL,
    CONSTRAINT fk_prioritaire_vehicule FOREIGN KEY (vehicule_id)
        REFERENCES vehicule (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Les événements datés de la simulation.
CREATE TABLE IF NOT EXISTS evenement (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    simulation_id  INT UNSIGNED NOT NULL,
    instant        DATETIME(3) NOT NULL,
    type           ENUM('debut_simulation', 'fin_simulation', 'changement_feu',
                        'entree_carrefour', 'sortie_carrefour', 'debut_priorite', 'fin_priorite',
                        'prioritaire_refuse', 'conflit') NOT NULL,
    vehicule_id    INT UNSIGNED NULL,               -- véhicule concerné, s'il y en a un
    bras           TINYINT UNSIGNED NULL,           -- changement de feu : bras concerné
    valeur         VARCHAR(20) NULL,                -- changement de feu : nouvelle couleur ; conflit : nombre
    INDEX idx_evenement_simulation (simulation_id, instant),
    CONSTRAINT fk_evenement_simulation FOREIGN KEY (simulation_id)
        REFERENCES simulation (id) ON DELETE CASCADE,
    CONSTRAINT fk_evenement_vehicule FOREIGN KEY (vehicule_id)
        REFERENCES vehicule (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Une mesure par seconde (table qui existait déjà dans le projet).
CREATE TABLE IF NOT EXISTS statistiques (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    instant          DATETIME DEFAULT CURRENT_TIMESTAMP,
    type_carrefour   VARCHAR(40),
    nb_vehicules     INT,
    vitesse_moyenne  FLOAT,
    nb_prioritaires  INT,
    nb_conflits      INT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Migration des anciennes versions de « statistiques » : on ajoute ce qui manque, les lignes
-- déjà enregistrées sont conservées (leur simulation_id reste vide).
ALTER TABLE statistiques ADD COLUMN IF NOT EXISTS type_carrefour VARCHAR(40) AFTER instant;
ALTER TABLE statistiques ADD COLUMN IF NOT EXISTS nb_conflits INT;
ALTER TABLE statistiques ADD COLUMN IF NOT EXISTS simulation_id INT UNSIGNED NULL;
ALTER TABLE statistiques ADD INDEX IF NOT EXISTS idx_statistiques_simulation (simulation_id);
ALTER TABLE statistiques ADD INDEX IF NOT EXISTS idx_statistiques_type (type_carrefour, nb_vehicules);
ALTER TABLE statistiques ADD CONSTRAINT fk_statistiques_simulation
    FOREIGN KEY IF NOT EXISTS (simulation_id) REFERENCES simulation (id) ON DELETE CASCADE;

-- --- vues pour consulter les données -------------------------------------------------------

-- Résumé de chaque simulation.
CREATE OR REPLACE VIEW v_resume_simulation AS
SELECT s.id,
       s.type_carrefour,
       s.debut,
       s.fin,
       ROUND(TIMESTAMPDIFF(MICROSECOND, s.debut, s.fin) / 1000000, 1) AS duree_s,
       COUNT(v.id)                                                    AS nb_vehicules,
       COALESCE(SUM(v.trajet_complet), 0)                             AS nb_trajets_complets,
       COALESCE(SUM(v.type = 'prioritaire'), 0)                       AS nb_prioritaires,
       ROUND(AVG(v.temps_attente_s), 1)                               AS attente_moyenne_s,
       ROUND(AVG(v.vitesse_moyenne), 2)                               AS vitesse_moyenne
FROM simulation s
LEFT JOIN vehicule v ON v.simulation_id = s.id
GROUP BY s.id, s.type_carrefour, s.debut, s.fin;

-- Tous les véhicules prioritaires, avec leur simulation.
CREATE OR REPLACE VIEW v_vehicules_prioritaires AS
SELECT v.simulation_id,
       s.type_carrefour,
       v.code,
       v.entree,
       v.sortie,
       v.mouvement,
       v.apparition,
       v.entree_carrefour,
       v.sortie_carrefour,
       p.debut_priorite,
       p.fin_priorite,
       p.duree_priorite_s,
       v.temps_attente_s
FROM vehicule_prioritaire p
JOIN vehicule v ON v.id = p.vehicule_id
JOIN simulation s ON s.id = v.simulation_id;

-- Journal lisible : les événements avec le code du véhicule.
CREATE OR REPLACE VIEW v_journal AS
SELECT e.id,
       e.simulation_id,
       e.instant,
       e.type,
       v.code AS vehicule,
       e.bras,
       e.valeur
FROM evenement e
LEFT JOIN vehicule v ON v.id = e.vehicule_id;

-- --- version du schéma ---------------------------------------------------------------------
-- L'application compare ce numéro à VERSION_SCHEMA (Code/base_stats.py) et ré-exécute ce
-- script si le sien est plus récent. Après toute modification de ce fichier : augmenter les deux.
CREATE TABLE IF NOT EXISTS version_schema (
    id       TINYINT UNSIGNED NOT NULL DEFAULT 1 PRIMARY KEY,
    version  INT UNSIGNED NOT NULL,
    CONSTRAINT ck_version_ligne_unique CHECK (id = 1)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO version_schema (id, version) VALUES (1, 1)
    ON DUPLICATE KEY UPDATE version = VALUES(version);
