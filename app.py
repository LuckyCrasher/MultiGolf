import os
import time
import uuid

from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app)

active_sessions = {}
session_expiry_seconds = 3600  # 1 hour

path_events = {}


def generate_unique_session_id():
    return str(uuid.uuid4())


@app.route('/create_session', methods=['GET'])
def create_session():
    session_id = generate_unique_session_id()
    return {'created_session': True, 'session_id': session_id}


@app.route('/join_session/<session_id>', methods=['GET'])
def join_session(session_id):
    if session_id not in active_sessions or is_session_expired(session_id):
        return {'session_exists': False,
                'Error': 'session not found or expired',
                'session_id': session_id}
    return {'session_exists': True,
            'session_id': session_id}


@socketio.on('connect_to_session')
def handle_connect_to_session(data):
    session_id = data['session_id']

    # Check if the session exists
    if session_id not in active_sessions or is_session_expired(session_id):
        return  # Handle invalid session or session expiry

    join_room(session_id)

    # Update last activity timestamp for the session
    active_sessions[session_id]['last_activity_timestamp'] = time.time()

    emit('connected_to_session', {'session_id': session_id})


def is_session_expired(session_id):
    last_activity_timestamp = active_sessions[session_id].get('last_activity_timestamp', 0)
    current_timestamp = time.time()
    return (current_timestamp - last_activity_timestamp) > session_expiry_seconds


@socketio.on('start_path_determination')
def handle_start_path_determination(data):
    session_id = data['session_id']

    if session_id not in active_sessions or is_session_expired(session_id):
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

    if session_id not in active_sessions or is_session_expired(session_id):
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

    session_id = data['session_id']

    # Check if the session exists
    if session_id not in active_sessions or is_session_expired(session_id):
        emit('path_new_touch_release',
             {'session_exists': False,
              'Error': 'session does not exist',
              'session_id': session_id})  # Handle invalid session or session expiry
        return

    session_id = data['session_id']
    path_events[session_id] += data


@socketio.on('path_new_touch')
def handle_path_touch(data):
    # path new touch release object:
    # {
    #    'session_id': <session_id>,
    #    'event_type': <new_touch/touch_release>,
    #    <additional event data like time and screen position>
    # }

    session_id = data['session_id']

    # Check if the session exists
    if session_id not in active_sessions or is_session_expired(session_id):
        emit('path_new_touch_release',
             {'session_exists': False,
              'Error': 'session does not exist',
              'session_id': session_id})  # Handle invalid session or session expiry
        return

    session_id = data['session_id']
    path_events[session_id] += data


@socketio.on('disconnect')
def handle_disconnect():
    # Handle disconnect logic
    print("disconnect event")
    pass


if __name__ == '__main__':
    socketio.run(app, debug=True)
