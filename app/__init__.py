from flask import Flask
from flask_socketio import SocketIO

def create_app():
    app = Flask(__name__)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    socketio = SocketIO(app)

    from app import routes
    return app, socketio

app, socketio = create_app()