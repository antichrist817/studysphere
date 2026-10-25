import os
import random
import string
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
)
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-before-production"
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///studysphere.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Some hosting providers use postgres:// URLs.
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        app.config["SQLALCHEMY_DATABASE_URI"].replace(
            "postgres://", "postgresql://", 1
        )
    )

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins=[])


# =========================================================
# IN-MEMORY ROOM AND CONNECTION TRACKING
# =========================================================

rooms = {}

# Socket ID -> logged-in user ID
connected_users = {}

# Socket ID -> room code
connected_room_sids = {}

# Socket IDs currently connected to the main public chat
main_chat_members = {}

MAIN_CHAT_ROOM = "studysphere_main_chat"


# =========================================================
# DATABASE MODELS
# =========================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    rank = db.Column(db.String(50), default="User")
    display_name = db.Column(db.String(80), default="")
    bio = db.Column(db.Text, default="")
    profile_picture = db.Column(db.String(500), default="")
    online = db.Column(db.Boolean, default=False)

    sent_private_messages = db.relationship(
        "PrivateMessage",
        backref="sender",
        lazy=True,
        foreign_keys="PrivateMessage.sender_id",
    )


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_one_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    user_two_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    user_one = db.relationship(
        "User", foreign_keys=[user_one_id]
    )
    user_two = db.relationship(
        "User", foreign_keys=[user_two_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "user_one_id",
            "user_two_id",
            name="unique_conversation_pair",
        ),
    )


class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversation.id"), nullable=False
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    read = db.Column(db.Boolean, default=False)

    conversation = db.relationship(
        "Conversation",
        backref=db.backref("messages", lazy=True),
    )


class PublicMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    message = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )

    sender = db.relationship(
        "User",
        backref=db.backref("public_messages", lazy=True),
    )


# Create any missing database tables without deleting existing data.
with app.app_context():
    db.create_all()


# =========================================================
# GENERAL HELPERS
# =========================================================

def get_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        return None

    return db.session.get(User, user_id)


def generate_unique_code(length=6):
    characters = string.ascii_uppercase + string.digits

    while True:
        code = "".join(
            random.choice(characters) for _ in range(length)
        )

        if code not in rooms:
            return code


def get_public_message_data(message):
    user = message.sender

    if user is None:
        name = "Unknown user"
        username = "unknown"
        rank = "User"
        profile_picture = ""
    else:
        name = user.display_name or user.username
        username = user.username
        rank = user.rank or "User"
        profile_picture = user.profile_picture or ""

    return {
        "id": message.id,
        "name": name,
        "username": username,
        "rank": rank,
        "profile_picture": profile_picture,
        "message": message.message,
        "created_at": message.created_at.strftime("%H:%M"),
    }


def get_online_members():
    user_ids = set(main_chat_members.values())
    members = []

    for user_id in user_ids:
        user = db.session.get(User, user_id)

        if user is None:
            continue

        members.append({
            "id": user.id,
            "username": user.username,
            "name": user.display_name or user.username,
            "rank": user.rank or "User",
            "profile_picture": user.profile_picture or "",
        })

    members.sort(key=lambda member: member["name"].lower())
    return members


def emit_online_members():
    socketio.emit(
        "main_chat_members",
        get_online_members(),
        to=MAIN_CHAT_ROOM,
    )


def user_is_in_main_chat(sid, user_id):
    return main_chat_members.get(sid) == user_id


def user_is_in_conversation(conversation, user_id):
    return user_id in (
        conversation.user_one_id,
        conversation.user_two_id,
    )


def get_or_create_conversation(user_one_id, user_two_id):
    first_id, second_id = sorted([user_one_id, user_two_id])

    conversation = Conversation.query.filter_by(
        user_one_id=first_id,
        user_two_id=second_id,
    ).first()

    if conversation is None:
        conversation = Conversation(
            user_one_id=first_id,
            user_two_id=second_id,
        )
        db.session.add(conversation)
        db.session.commit()

    return conversation


# =========================================================
# HOME AND CHAT ROOMS
# =========================================================

@app.route("/", methods=["GET", "POST"])
def home():
    user = get_logged_in_user()

    if request.method == "POST":
        if user is None:
            return redirect(url_for("login"))

        action = request.form.get("action", "").lower()
        code = request.form.get("code", "").strip().upper()

        # Accept the common form button names as well.
        if not action:
            if request.form.get("create_room") is not None:
                action = "create"
            elif request.form.get("join_room") is not None:
                action = "join"

        if action == "create":
            code = generate_unique_code()

            rooms[code] = {
                "members": 0,
                "messages": [],
            }

            session["room"] = code
            session["name"] = user.display_name or user.username

            return redirect(url_for("room"))

        if action == "join":
            if not code:
                return render_template(
                    "home.html",
                    user=user,
                    name=user.display_name or user.username,
                    error="Please enter a room code.",
                )

            if code not in rooms:
                return render_template(
                    "home.html",
                    user=user,
                    name=user.display_name or user.username,
                    error="That room doesn't exist or has expired.",
                )

            session["room"] = code
            session["name"] = user.display_name or user.username

            return redirect(url_for("room"))

        return render_template(
            "home.html",
            user=user,
            name=user.display_name or user.username,
            error="Please choose an action.",
        )

    return render_template(
        "home.html",
        user=user,
        name=(user.display_name or user.username) if user else "",
    )


@app.route("/main-chat")
def main_chat():
    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    recent_messages = (
        PublicMessage.query
        .order_by(PublicMessage.created_at.desc())
        .limit(100)
        .all()
    )
    recent_messages.reverse()

    messages = [
        get_public_message_data(message)
        for message in recent_messages
    ]

    return render_template(
        "main_chat.html",
        user=user,
        messages=messages,
    )


@app.route("/room")
def room():
    code = session.get("room")
    name = session.get("name")

    if not code or not name or code not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", code=code, name=name)


# =========================================================
# ACCOUNT REGISTRATION AND LOGIN
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if get_logged_in_user() is not None:
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            password,
        )

        if not username or not password:
            error = "Please enter a username and password."

        elif len(username) > 80:
            error = "Your username must be 80 characters or fewer."

        elif len(password) < 6:
            error = "Your password must be at least 6 characters."

        elif password != confirm_password:
            error = "Your passwords don't match."

        elif User.query.filter_by(username=username).first():
            error = "That username is already taken."

        else:
            user = User(
                username=username,
                password=generate_password_hash(password),
                display_name=username,
                rank="User",
                online=False,
            )

            db.session.add(user)
            db.session.commit()

            session.clear()
            session["user_id"] = user.id
            session["name"] = user.display_name or user.username

            return redirect(url_for("home"))

    return render_template("auth.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_logged_in_user() is not None:
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.id
            session["name"] = user.display_name or user.username

            return redirect(url_for("home"))

        error = "Incorrect username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    user = get_logged_in_user()

    if user is not None:
        # The disconnect handler will update online status when the
        # user's remaining active sockets disconnect.
        user_id = user.id
        session.clear()

        if not any(
            connected_user_id == user_id
            for connected_user_id in connected_users.values()
        ):
            user.online = False
            db.session.commit()
    else:
        session.clear()

    return redirect(url_for("home"))


# =========================================================
# PROFILES
# =========================================================

@app.route("/profile")
def profile():
    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=user,
        profile_user=user,
    )


@app.route("/user/<username>")
def view_user(username):
    current_user = get_logged_in_user()
    profile_user = User.query.filter_by(username=username).first_or_404()

    return render_template(
        "profile.html",
        user=current_user,
        profile_user=profile_user,
    )


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    error = None

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        profile_picture = request.form.get(
            "profile_picture",
            "",
        ).strip()

        if len(display_name) > 80:
            error = "Your display name must be 80 characters or fewer."
        elif len(bio) > 2000:
            error = "Your bio must be 2000 characters or fewer."
        elif len(profile_picture) > 500:
            error = "Your profile picture URL is too long."
        else:
            user.display_name = display_name or user.username
            user.bio = bio
            user.profile_picture = profile_picture

            db.session.commit()

            session["name"] = user.display_name

            return redirect(url_for("profile"))

    return render_template(
        "edit_profile.html",
        user=user,
        error=error,
    )


# =========================================================
# USER SEARCH
# =========================================================

@app.route("/search", methods=["GET", "POST"])
def search():
    current_user = get_logged_in_user()

    if current_user is None:
        return redirect(url_for("login"))

    query = request.values.get("q", "").strip()
    users = []

    if query:
        users = (
            User.query
            .filter(
                User.username.ilike(f"%{query}%")
            )
            .order_by(User.username.asc())
            .limit(50)
            .all()
        )

    return render_template(
        "search.html",
        user=current_user,
        users=users,
        query=query,
    )


# =========================================================
# PRIVATE MESSAGES
# =========================================================

@app.route("/messages")
def inbox():
    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    conversations = (
        Conversation.query
        .filter(
            db.or_(
                Conversation.user_one_id == user.id,
                Conversation.user_two_id == user.id,
            )
        )
        .order_by(Conversation.id.desc())
        .all()
    )

    conversation_data = []

    for conversation in conversations:
        other_user = (
            conversation.user_two
            if conversation.user_one_id == user.id
            else conversation.user_one
        )

        last_message = (
            PrivateMessage.query
            .filter_by(conversation_id=conversation.id)
            .order_by(PrivateMessage.created_at.desc())
            .first()
        )

        unread_count = (
            PrivateMessage.query
            .filter_by(
                conversation_id=conversation.id,
                read=False,
            )
            .filter(PrivateMessage.sender_id != user.id)
            .count()
        )

        conversation_data.append({
            "conversation": conversation,
            "other_user": other_user,
            "last_message": last_message,
            "unread_count": unread_count,
        })

    return render_template(
        "inbox.html",
        user=user,
        conversations=conversation_data,
    )


@app.route("/dm/<username>", methods=["GET", "POST"])
def private_message(username):
    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    other_user = User.query.filter_by(username=username).first_or_404()

    if other_user.id == user.id:
        flash("You can't start a conversation with yourself.")
        return redirect(url_for("inbox"))

    conversation = get_or_create_conversation(user.id, other_user.id)

    if request.method == "POST":
        message_text = request.form.get("message", "").strip()

        if message_text:
            if len(message_text) > 2000:
                flash("Your message is too long.")
            else:
                message = PrivateMessage(
                    conversation_id=conversation.id,
                    sender_id=user.id,
                    message=message_text,
                )
                db.session.add(message)
                db.session.commit()

        return redirect(
            url_for("private_message", username=other_user.username)
        )

    messages = (
        PrivateMessage.query
        .filter_by(conversation_id=conversation.id)
        .order_by(PrivateMessage.created_at.asc())
        .all()
    )

    unread_messages = (
        PrivateMessage.query
        .filter_by(
            conversation_id=conversation.id,
            read=False,
        )
        .filter(PrivateMessage.sender_id == other_user.id)
        .all()
    )

    for message in unread_messages:
        message.read = True

    db.session.commit()

    return render_template(
        "private_message.html",
        user=user,
        other_user=other_user,
        conversation=conversation,
        messages=messages,
    )


@socketio.on("join_private_conversation")
def join_private_conversation(data):
    user = get_logged_in_user()

    if user is None or not isinstance(data, dict):
        return

    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return

    conversation = db.session.get(Conversation, conversation_id)

    if conversation is None:
        return

    if not user_is_in_conversation(conversation, user.id):
        return

    join_room(f"dm_{conversation.id}")


@socketio.on("private_message")
def handle_private_message(data):
    user = get_logged_in_user()

    if user is None or not isinstance(data, dict):
        return

    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return

    message_text = str(data.get("message", "")).strip()

    if not message_text or len(message_text) > 2000:
        return

    conversation = db.session.get(Conversation, conversation_id)

    if conversation is None:
        return

    if not user_is_in_conversation(conversation, user.id):
        return

    message = PrivateMessage(
        conversation_id=conversation.id,
        sender_id=user.id,
        message=message_text,
    )

    db.session.add(message)
    db.session.commit()

    payload = {
        "id": message.id,
        "conversation_id": conversation.id,
        "sender_id": user.id,
        "sender": user.display_name or user.username,
        "username": user.username,
        "message": message.message,
        "created_at": message.created_at.strftime("%H:%M"),
    }

    emit(
        "private_message",
        payload,
        to=f"dm_{conversation.id}",
    )


# =========================================================
# MAIN PUBLIC CHAT — LIVE MESSAGES AND ONLINE MEMBERS
# =========================================================

@socketio.on("join_main_chat")
def handle_join_main_chat():
    user = get_logged_in_user()

    if user is None:
        return

    sid = request.sid

    # Join once per socket so repeated events don't duplicate membership.
    if sid not in main_chat_members:
        main_chat_members[sid] = user.id
        join_room(MAIN_CHAT_ROOM)

        user.online = True
        db.session.commit()

        emit_online_members()

    recent_messages = (
        PublicMessage.query
        .order_by(PublicMessage.created_at.desc())
        .limit(100)
        .all()
    )
    recent_messages.reverse()

    emit(
        "main_chat_history",
        [get_public_message_data(message) for message in recent_messages],
    )


@socketio.on("main_chat_message")
def handle_main_chat_message(data):
    user = get_logged_in_user()

    if user is None or not isinstance(data, dict):
        return

    # Only allow a socket that has joined the main chat to post there.
    if not user_is_in_main_chat(request.sid, user.id):
        return

    message_text = str(data.get("message", "")).strip()

    if not message_text or len(message_text) > 2000:
        return

    message = PublicMessage(
        sender_id=user.id,
        message=message_text,
    )

    db.session.add(message)
    db.session.commit()

    socketio.emit(
        "main_chat_message",
        get_public_message_data(message),
        to=MAIN_CHAT_ROOM,
    )


# =========================================================
# EXISTING PRIVATE ROOM CHAT
# =========================================================

@socketio.on("message")
def handle_room_message(data):
    user = get_logged_in_user()

    if user is None or not isinstance(data, dict):
        return

    code = session.get("room")

    if not code or code not in rooms:
        return

    if connected_room_sids.get(request.sid) != code:
        return

    message_text = str(data.get("data", "")).strip()

    if not message_text:
        return

    if len(message_text) > 2000:
        return

    payload = {
        "name": user.display_name or user.username,
        "message": message_text,
    }

    rooms[code]["messages"].append(payload)

    socketio.emit(
        "message",
        payload,
        to=code,
    )


# =========================================================
# SOCKET CONNECTION MANAGEMENT
# =========================================================

@socketio.on("connect")
def handle_connect(auth=None):
    user = get_logged_in_user()

    if user is not None:
        connected_users[request.sid] = user.id
        user.online = True
        db.session.commit()

    code = session.get("room")

    if code and code in rooms:
        join_room(code)
        connected_room_sids[request.sid] = code
        rooms[code]["members"] = rooms[code].get("members", 0) + 1

        emit(
            "message",
            {
                "name": "StudySphere",
                "message": f"{session.get('name', 'Someone')} joined the room.",
            },
            to=code,
        )


@socketio.on("disconnect")
def handle_disconnect(reason=None):
    sid = request.sid

    # Remove this socket from the main chat's online-member list.
    if sid in main_chat_members:
        main_chat_members.pop(sid, None)
        emit_online_members()

    # Remove this socket from its private room.
    code = connected_room_sids.pop(sid, None)

    if code and code in rooms:
        leave_room(code)

        rooms[code]["members"] = max(
            0,
            rooms[code].get("members", 0) - 1,
        )

        emit(
            "message",
            {
                "name": "StudySphere",
                "message": f"{session.get('name', 'Someone')} left the room.",
            },
            to=code,
        )

        if rooms[code]["members"] <= 0:
            rooms.pop(code, None)

    # Only mark a user offline if none of their other sockets remain.
    user_id = connected_users.pop(sid, None)

    if user_id is not None:
        still_connected = any(
            other_user_id == user_id
            for other_user_id in connected_users.values()
        )

        if not still_connected:
            user = db.session.get(User, user_id)

            if user is not None:
                user.online = False
                db.session.commit()


# =========================================================
# START THE APP
# =========================================================

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
