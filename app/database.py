import sqlite3
import os
from flask import g

# Use an absolute path for the database file
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'recipes.db')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = dict_factory  # Use dict_factory instead of sqlite3.Row
    return db

def init_db():
    if not os.path.exists(DATABASE):
        with sqlite3.connect(DATABASE) as db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    whiskey_type TEXT NOT NULL,
                    whiskey_volume REAL NOT NULL,
                    syrup_type TEXT NOT NULL,
                    syrup_volume REAL NOT NULL,
                    bitters_type TEXT NOT NULL,
                    bitters_volume INTEGER NOT NULL
                )
            ''')
    print(f"Database initialized at {DATABASE}")  # Add this line for debugging

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_recipe(recipe):
    db = get_db()
    cur = db.cursor()
    cur.execute('''
        INSERT INTO recipes (name, whiskey_type, whiskey_volume, syrup_type, syrup_volume, bitters_type, bitters_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (recipe['name'], recipe['whiskey_type'], recipe['whiskey_volume'],
          recipe['syrup_type'], recipe['syrup_volume'],
          recipe['bitters_type'], recipe['bitters_volume']))
    db.commit()
    return cur.lastrowid

def update_recipe(recipe_id, recipe_data):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE recipes
        SET name = ?, whiskey_type = ?, whiskey_volume = ?, 
            syrup_type = ?, syrup_volume = ?, 
            bitters_type = ?, bitters_volume = ?
        WHERE id = ?
    ''', (recipe_data['name'], recipe_data['whiskey_type'], recipe_data['whiskey_volume'],
          recipe_data['syrup_type'], recipe_data['syrup_volume'],
          recipe_data['bitters_type'], recipe_data['bitters_volume'],
          recipe_id))
    db.commit()

def delete_recipe(recipe_id):
    db = get_db()
    db.execute('DELETE FROM recipes WHERE id=?', (recipe_id,))
    db.commit()

def get_all_recipes():
    return query_db('SELECT * FROM recipes')

def get_recipe(recipe_id):
    return query_db('SELECT * FROM recipes WHERE id=?', (recipe_id,), one=True)

# Add this line at the end of the file to ensure DATABASE is exported
__all__ = ['DATABASE', 'get_db', 'init_db', 'query_db', 'insert_recipe', 'update_recipe', 'delete_recipe', 'get_all_recipes', 'get_recipe']
