
CREATE DATABASE IF NOT EXISTS carrefour
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- L'application se connecte en TCP à 127.0.0.1. Selon la configuration de MariaDB, cette
-- connexion est vue comme venant de 'localhost' ou de '127.0.0.1' : on crée donc les deux.
CREATE USER IF NOT EXISTS 'sae'@'localhost' IDENTIFIED BY 'un_mot_de_passe';
CREATE USER IF NOT EXISTS 'sae'@'127.0.0.1' IDENTIFIED BY 'un_mot_de_passe';

-- Droits limités à la base « carrefour » (création des tables et des vues comprise).
GRANT ALL PRIVILEGES ON carrefour.* TO 'sae'@'localhost';
GRANT ALL PRIVILEGES ON carrefour.* TO 'sae'@'127.0.0.1';
FLUSH PRIVILEGES;
