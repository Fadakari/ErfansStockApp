CREATE DATABASE my_database;
USE my_database;

CREATE TABLE user (
	id INT AUTO_INCREMENT PRIMARY KEY, 
	username VARCHAR(64) NOT NULL UNIQUE, 
	email VARCHAR(120) NOT NULL UNIQUE, 
	password_hash VARCHAR(256) NOT NULL
);

INSERT INTO user VALUES(1, 'erfan85', 'erfan85.parham94@gmail.com', 'scrypt:32768:8:1$yI50sHbfvgG4zCcd$601776924316f6b85b18c245deeb5d4860cb63dba2a18ac611629f3559d0e2278e6107df6a8db6024cfc08867635b8da19cbbf1e9a774f6c8fd34747fa7ce1ed');

CREATE TABLE category (
	id INT AUTO_INCREMENT PRIMARY KEY, 
	name VARCHAR(50) NOT NULL
);

INSERT INTO category VALUES(1, 'ابزار برقی');
INSERT INTO category VALUES(2, 'کرگیر');
INSERT INTO category VALUES(3, 'دریل ها');
INSERT INTO category VALUES(4, 'ابزار های شارژی');
INSERT INTO category VALUES(5, 'بتن کن ها');

CREATE TABLE product (
	id INT AUTO_INCREMENT PRIMARY KEY, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	price DECIMAL(10,2) NOT NULL, 
	category_id INT, 
	image_path VARCHAR(255), 
	created_at DATETIME, 
	updated_at DATETIME, 
	user_id INT NOT NULL, 
	FOREIGN KEY(category_id) REFERENCES category(id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES user(id) ON DELETE CASCADE
);

INSERT INTO product VALUES(1, 'محصول ۱', 'توضیحات محصول ۱', 2500.00, 1, 'product1.png', '2025-03-15 13:53:57', '2025-03-15 13:53:57', 1);
INSERT INTO product VALUES(2, 'T-3000', 'توضیحات محصول ۲', 3000.00, 2, 'product2.jpeg', '2025-03-15 14:48:47', '2025-03-15 14:48:47', 1);
