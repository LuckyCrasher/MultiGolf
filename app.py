import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*")

host = "0.0.0.0"
port = 5000

# active_game_session

active_game_sessions = {}
session_expiry_seconds = 3600  # 1 hour

debug = False


# Configure logging to a file
file_handler = RotatingFileHandler('app.log', maxBytes=10240, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
app.logger.addHandler(file_handler)

app.logger.setLevel(logging.INFO)  # Set the desired logging level (e.g., INFO, WARNING, ERROR)


def generate_unique_session_id():
    return str(uuid.uuid4())


def is_game_session_expired(game_session_id):
    return False
    #last_activity_timestamp = active_game_sessions[game_session_id].get('last_activity_timestamp', 0)
    #current_timestamp = time.time()
    #return (current_timestamp - last_activity_timestamp) > session_expiry_seconds


@app.route("/", methods=['GET'])
def index():
    app.logger.info("index request")
    return {"response": "Multi golf is alive and well..."}


@app.route('/create_game_session', methods=['GET'])
def create_game_session():
    timeout = 5
    count = 0
    game_session_id = generate_unique_session_id()
    while (game_session_id in active_game_sessions) and (count < timeout):
        game_session_id = generate_unique_session_id()
        count += 1

    active_game_sessions[game_session_id] = {'game_started': False, 'device_count': 1, 'updates': []}

    app.logger.info(f"Created new game session {game_session_id}")
    return {'created_game_session': True, 'game_session_id': game_session_id}


@app.route('/game_started/<game_session_id>', methods=['GET'])
def game_started(game_session_id):
    app.logger.info(f"Game started req: {game_session_id}")

    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        return {'session_exists': False,
                'Error': 'session not found or expired',
                'session_id': game_session_id}

    data_out = {
        'game_session_id': game_session_id,
        'session_exists': True,
        'game_started': active_game_sessions[game_session_id]['game_started'],
    }
    return data_out


@app.route('/join_game_session/<game_session_id>', methods=['GET'])
def join_session(game_session_id):
    app.logger.info(f"Join req: {game_session_id}")

    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        return {'session_exists': False,
                'Error': 'session not found or expired',
                'session_id': game_session_id}

    data_out = {
        'game_session_id': game_session_id,
        'session_exists': True,
        'game_started': active_game_sessions[game_session_id]['game_started'],
        'assigned_device_index': active_game_sessions[game_session_id]['device_count']
    }
    active_game_sessions[game_session_id]['device_count'] += 1

    return data_out


@app.route('/start_game/<game_session_id>', methods=['GET'])
def start_game(game_session_id):
    app.logger.info(f"Start game req: {game_session_id}")

    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        return {'session_exists': False,
                'Error': 'session not found or expired',
                'session_id': game_session_id}

    was_running = active_game_sessions[game_session_id]['game_started']
    if not was_running:
        active_game_sessions[game_session_id]['game_started'] = True

    data_out = {
        'game_session_id': game_session_id,
        'was_already_running': was_running,
        'game_started': active_game_sessions[game_session_id]['game_started']
    }
    return data_out


@socketio.on('login')
def handle_connect_to_session(data):
    game_session_id = data['game_session_id']

    app.logger.info(f"SOCKET: connect to game session {game_session_id}")

    # Check if the session exists
    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        return emit('connected_to_game_session', {'session_exists': False})  # Handle invalid session or session expiry

    join_room(game_session_id)

    # Update last activity timestamp for the session
    active_game_sessions[game_session_id]['last_activity_timestamp'] = time.time()
    updates = active_game_sessions[game_session_id]['updates']
    app.logger.info(f"Sending updates {updates}")
    response = {'session_id': game_session_id, 'game_session_exists': True, 'updates': updates}
    emit('connected_to_game_session', response, broadcast=True, include_self=True)


@socketio.on('update')
def handle_update(data):
    game_session_id = data['game_session_id']
    # Check if the session exists
    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        emit('path_new_touch_release',
             {'game_session_exists': False,
              'Error': 'game_session does not exist',
              'game_session_id': game_session_id})  # Handle invalid session or session expiry
        return

    game_session_id = data['game_session_id']
    active_game_sessions[game_session_id]['updates'] += data
    app.logger.info(f"New update {data}")
    emit('update', data, broadcast=True, include_self=True)


@socketio.on('disconnect')
def handle_disconnect():
    # Handle disconnect logic
    print("disconnect event")
    pass


if __name__ == '__main__':
    app.logger.info("Starting MultiGolf backend...")
    socketio.run(app, debug=debug, host=host, port=port)
