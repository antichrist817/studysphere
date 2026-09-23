```python
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
from string import ascii_uppercase

app = Flask(__name__)

app.config["SECRET_KEY"] = "CHANGE_THIS_SECRET_LATER"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studysphere.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

rooms = {}


# =========================
# DATABASE
# =========================

class User(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    rank = db.Column(
        db.String(30),
        default="User",
        nullable=False
    )

    display_name = db.Column(
        db.String(30),
        nullable=True
    )

    bio = db.Column(
        db.String(500),
        default="",
        nullable=False
    )

    profile_picture = db.Column(
        db.String(500),
        default="",
        nullable=False
    )

    online = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )


class Conversation(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_one_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    user_two_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )


class PrivateMessage(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversation.id"),
        nullable=False
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    message = db.Column(
        db.String(2000),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )


with app.app_context():
    db.create_all()


# =========================
# ROOM SYSTEM
# =========================

def generate_unique_code(length=4):

    while True:

        code = "".join(
            random.choice(ascii_uppercase)
            for _ in range(length)
        )

        if code not in rooms:
            return code


# =========================
# HOME
# =========================

@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        code = request.form.get(
            "code",
            ""
        ).strip().upper()

        join = request.form.get("join")
        create = request.form.get("create")

        if not name:

            return render_template(
                "home.html",
                error="Please enter a name.",
                name=name,
                code=code
            )

        if create:

            room = generate_unique_code()

            rooms[room] = {
                "members": 0,
                "messages": []
            }

        elif join:

            if not code:

                return render_template(
                    "home.html",
                    error="Please enter a room code.",
                    name=name,
                    code=code
                )

            if code not in rooms:

                return render_template(
                    "home.html",
                    error="Room does not exist.",
                    name=name,
                    code=code
                )

            room = code

        else:

            return render_template(
                "home.html",
                error="Please choose an option.",
                name=name,
                code=code
            )

        session["room"] = room
        session["name"] = name

        return redirect(url_for("room"))

    return render_template("home.html")


# =========================
# ACCOUNT CREATION
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            return render_template(
                "auth.html",
                error="Please fill in all fields."
            )

        if len(username) > 30:

            return render_template(
                "auth.html",
                error="Username must be 30 characters or less."
            )

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:

            return render_template(
                "auth.html",
                error="That username is already taken."
            )

        hashed_password = generate_password_hash(
            password
        )

        user = User(
            username=username,
            password=hashed_password,
            rank="User",
            display_name=username,
            bio="",
            profile_picture="",
            online=True
        )

        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        session["name"] = user.username

        return redirect(url_for("home"))

    return render_template("auth.html")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        user = User.query.filter_by(
            username=username
        ).first()

        if user is None:

            return render_template(
                "login.html",
                error="Invalid username or password."
            )

        if not check_password_hash(
            user.password,
            password
        ):

            return render_template(
                "login.html",
                error="Invalid username or password."
            )

        user.online = True
        db.session.commit()

        session["user_id"] = user.id
        session["name"] = user.username

        return redirect(url_for("home"))

    return render_template("login.html")


# =========================
# MY PROFILE
# =========================

@app.route("/profile")
def profile():

    user_id = session.get("user_id")

    if not user_id:

        return redirect(url_for("login"))

    user = User.query.get(user_id)

    if user is None:

        session.clear()

        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=user
    )


# =========================
# OTHER USER PROFILE
# =========================

@app.route("/user/<username>")
def view_user(username):

    user = User.query.filter_by(
        username=username
    ).first()

    if user is None:

        return redirect(url_for("search"))

    return render_template(
        "profile.html",
        user=user
    )


# =========================
# USER SEARCH
# =========================

@app.route("/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip()

    users = []

    if query:

        users = User.query.filter(
            User.username.ilike(f"%{query}%")
            | User.display_name.ilike(f"%{query}%")
        ).all()

    return render_template(
        "search.html",
        users=users,
        query=query
    )


# =========================
# EDIT PROFILE
# =========================

@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():

    user_id = session.get("user_id")

    if not user_id:

        return redirect(url_for("login"))

    user = User.query.get(user_id)

    if user is None:

        session.clear()

        return redirect(url_for("login"))

    if request.method == "POST":

        display_name = request.form.get(
            "display_name",
            ""
        ).strip()

        bio = request.form.get(
            "bio",
            ""
        ).strip()

        profile_picture = request.form.get(
            "profile_picture",
            ""
        ).strip()

        if len(display_name) > 30:

            return render_template(
                "edit_profile.html",
                user=user,
                error="Display name must be 30 characters or less."
            )

        if len(bio) > 500:

            return render_template(
                "edit_profile.html",
                user=user,
                error="Bio must be 500 characters or less."
            )

        if len(profile_picture) > 500:

            return render_template(
                "edit_profile.html",
                user=user,
                error="Profile picture URL is too long."
            )

        user.display_name = display_name
        user.bio = bio
        user.profile_picture = profile_picture

        db.session.commit()

        return redirect(url_for("profile"))

    return render_template(
        "edit_profile.html",
        user=user
    )


# =========================
# START PRIVATE MESSAGE
# =========================

@app.route("/dm/<username>", methods=["GET", "POST"])
def private_message(username):

    user_id = session.get("user_id")

    if not user_id:

        return redirect(url_for("login"))

    current_user = User.query.get(user_id)

    other_user = User.query.filter_by(
        username=username
    ).first()

    if current_user is None or other_user is None:

        return redirect(url_for("search"))

    if current_user.id == other_user.id:

        return redirect(url_for("profile"))

    user_one = min(
        current_user.id,
        other_user.id
    )

    user_two = max(
        current_user.id,
        other_user.id
    )

    conversation = Conversation.query.filter_by(
        user_one_id=user_one,
        user_two_id=user_two
    ).first()

    if conversation is None:

        conversation = Conversation(
            user_one_id=user_one,
            user_two_id=user_two
        )

        db.session.add(conversation)
        db.session.commit()

    if request.method == "POST":

        message_text = request.form.get(
            "message",
            ""
        ).strip()

        if message_text:

            private_message = PrivateMessage(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                message=message_text
            )

            db.session.add(private_message)
            db.session.commit()

        return redirect(
            url_for(
                "private_message",
                username=other_user.username
            )
        )

    messages = PrivateMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(
        PrivateMessage.created
```
