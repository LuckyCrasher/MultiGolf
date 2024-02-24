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

path_events = {}
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

    active_game_sessions[game_session_id] = {'game_started': False, 'device_count': 1}

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
    response = {'session_id': game_session_id, 'game_session_exists': True}
    emit('connected_to_game_session', response, broadcast=True, include_self=True)


@socketio.on('start_path_determination')
def handle_start_path_determination(data):
    session_id = data['session_id']

    if session_id not in active_game_sessions or is_game_session_expired(session_id):
        emit('start_path_determination',
             {'session_exists': False,
              'Error': 'session does not exist',
              'session_id': session_id})  # Handle invalid session or session expiry
        return

    data_out = {'session_id': session_id}
    emit('start_path_determination', data_out, broadcast=True, include_self=True)


@socketio.on('finish_path_determination')
def handle_finish_path_determination(data):
    session_id = data['session_id']

    if session_id not in active_game_sessions or is_game_session_expired(session_id):
        emit('finish_path_determination',
             {'session_exists': False,
              'Error': 'session does not exist',
              'session_id': session_id})  # Handle invalid session or session expiry
        return

    data_out = {
        'session_id': session_id,
        'path_events': path_events[session_id]
    }
    emit('finish_path_determination', data_out, broadcast=True, include_self=True)


@socketio.on('path_new_touch_release')
def handle_path_release_touch(data):
    # path new touch release object:
    # {
    #    'session_id': <session_id>,
    #    'event_type': <new_touch/touch_release>,
    #    <additional event data like time and screen position>
    # }

    game_session_id = data['game_session_id']

    # Check if the session exists
    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        emit('path_new_touch_release',
             {'session_exists': False,
              'Error': 'session does not exist',
              'session_id': game_session_id})  # Handle invalid session or session expiry
        return

    game_session_id = data['game_session_id']
    path_events[game_session_id] += data


@socketio.on('path_new_touch')
def handle_path_touch(data):
    # path new touch release object:
    # {
    #    'session_id': <session_id>,
    #    'event_type': <new_touch/touch_release>,
    #    <additional event data like time and screen position>
    # }

    game_session_id = data['game_session_id']

    # Check if the session exists
    if game_session_id not in active_game_sessions or is_game_session_expired(game_session_id):
        emit('path_new_touch_release',
             {'game_session_exists': False,
              'Error': 'game_session does not exist',
              'game_session_id': game_session_id})  # Handle invalid session or session expiry
        return

    game_session_id = data['game_session_id']
    path_events[game_session_id] += data


@socketio.on('disconnect')
def handle_disconnect():
    # Handle disconnect logic
    print("disconnect event")
    pass


if __name__ == '__main__':
    app.logger.info("Starting MultiGolf backend...")
    socketio.run(app, debug=debug, host=host, port=port)
