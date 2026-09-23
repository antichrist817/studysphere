from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import random
from string import ascii_uppercase

app = Flask(**name**)

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

```
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
```

with app.app_context():
db.create_all()

# =========================

# ROOM SYSTEM

# =========================

def generate_unique_code(length=4):

```
while True:

    code = "".join(
        random.choice(ascii_uppercase)
        for _ in range(length)
    )

    if code not in rooms:
        return code
```

# =========================

# HOME

# =========================

@app.route("/", methods=["GET", "POST"])
def home():

```
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
```

# =========================

# ACCOUNT CREATION

# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

```
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
```

# =========================

# LOGIN

# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

```
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
```

# =========================

# PROFILE

# =========================

@app.route("/profile")
def profile():

```
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
```

# =========================

# EDIT PROFILE

# =========================

@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():

```
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
```

# =========================

# LOGOUT

# =========================

@app.route("/logout")
def logout():

```
user_id = session.get("user_id")

if user_id:

    user = User.query.get(user_id)

    if user:

        user.online = False
        db.session.commit()

session.clear()

return redirect(url_for("home"))
```

# =========================

# CHAT ROOM

# =========================

@app.route("/room")
def room():

```
room = session.get("room")
name = session.get("name")

if (
    not room
    or not name
    or room not in rooms
):

    return redirect(url_for("home"))

return render_template(
    "room.html",
    code=room,
    messages=rooms[room]["messages"]
)
```

# =========================

# SEND MESSAGE

# =========================

@socketio.on("message")
def handle_message(data):

```
room = session.get("room")
name = session.get("name")

if (
    not room
    or not name
    or room not in rooms
):

    return

message = str(
    data.get("data", "")
).strip()

if not message:
    return

content = {
    "name": name,
    "message": message
}

send(
    content,
    to=room
)

rooms[room]["messages"].append(
    content
)
```

# =========================

# USER CONNECTS

# =========================

@socketio.on("connect")
def handle_connect():

```
room = session.get("room")
name = session.get("name")

if (
    not room
    or not name
    or room not in rooms
):

    return

join_room(room)

rooms[room]["members"] += 1

send(
    {
        "name": "StudySphere",
        "message": f"{name} joined the room."
    },
    to=room
)
```

# =========================

# USER DISCONNECTS

# =========================

@socketio.on("disconnect")
def handle_disconnect():

```
room = session.get("room")
name = session.get("name")

if not room:
    return

leave_room(room)

if room in rooms:

    rooms[room]["members"] -= 1

    if rooms[room]["members"] <= 0:

        del rooms[room]

        return

if name:

    send(
        {
            "name": "StudySphere",
            "message": f"{name} left the room."
        },
        to=room
    )
```

# =========================

# START SERVER

# =========================

if **name** == "**main**":

```
socketio.run(
    app,
    debug=True
)
```
