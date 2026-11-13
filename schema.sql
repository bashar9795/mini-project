-- SkillSwap database, matching the tables already in use.
-- This file documents the schema. It does not need to be run again
-- on the existing database.

CREATE TABLE users (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY email (email)
);

CREATE TABLE user_profiles (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    name VARCHAR(150) NOT NULL,
    college VARCHAR(255) NOT NULL,
    department VARCHAR(150) NOT NULL,
    academic_year VARCHAR(50) NOT NULL,
    bio TEXT NULL,
    teach_skills TEXT NULL,
    learn_skills TEXT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY user_id (user_id),
    KEY idx_user_id (user_id)
);

-- Add this later, after a backup. It links every profile to a real account.
-- ALTER TABLE user_profiles
--     ADD CONSTRAINT fk_user_profiles_user
--     FOREIGN KEY (user_id) REFERENCES users (id);

-- Messages between two students. The app also creates this table on startup.
CREATE TABLE IF NOT EXISTS messages (
    id INT NOT NULL AUTO_INCREMENT,
    sender_id INT NOT NULL,
    receiver_id INT NOT NULL,
    body TEXT NULL,
    file_name VARCHAR(255) NULL,
    stored_name VARCHAR(255) NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_sender (sender_id),
    KEY idx_receiver (receiver_id)
);
