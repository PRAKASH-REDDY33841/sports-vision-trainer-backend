import mysql.connector

def get_db():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="sports_vision_trainer"
    )
    return conn