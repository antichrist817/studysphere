from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
from string import ascii_uppercase
import os

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
"SECRET_KEY",
"development-secret-change-before-deployment"
)

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

class Conversation(db.Model):

```
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

__table_args__ = (
    db.UniqueConstraint(
        "user_one_id",
        "user_two_id",
        name="unique_conversation_users"
    ),
)
```

class PrivateMessage(db.Model):

```
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

read = db.Column(
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

# MY PROFILE

# =========================

@app.route("/profile")
def profile():

```
user_id = session.get("user_id")

if not user_id:

    return redirect(url_for("login"))

user = db.session.get(
    User,
    user_id
)

if user is None:

    session.clear()

    return redirect(url_for("login"))

return render_template(
    "profile.html",
    user=user
)
```

# =========================

# OTHER USER PROFILE

# =========================

@app.route("/user/<username>")
def view_user(username):

```
user = User.query.filter_by(
    username=username
).first()

if user is None:

    return redirect(url_for("search"))

return render_template(
    "profile.html",
    user=user
)
```

# =========================

# USER SEARCH

# =========================

@app.route("/search")
def search():

```
query = request.args.get(
    "q",
    ""
).strip()

users = []

if query:

    users = User.query.filter(
        User.username.ilike(
            f"%{query}%"
        )
        |
        User.display_name.ilike(
            f"%{query}%"
        )
    ).all()

return render_template(
    "search.html",
    users=users,
    query=query
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

user = db.session.get(
    User,
    user_id
)

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

    return redirect(
        url_for("profile")
    )

return render_template(
    "edit_profile.html",
    user=user
)
```

# =========================

# MESSAGE INBOX

# =========================

@app.route("/messages")
def inbox():

```
user_id = session.get("user_id")

if not user_id:

    return redirect(url_for("login"))

current_user = db.session.get(
    User,
    user_id
)

if current_user is None:

    session.clear()

    return redirect(url_for("login"))

conversations = Conversation.query.filter(
    (
        Conversation.user_one_id == current_user.id
    )
    |
    (
        Conversation.user_two_id == current_user.id
    )
).all()

inbox_conversations = []

for conversation in conversations:

    if conversation.user_one_id == current_user.id:

        other_user_id = conversation.user_two_id

    else:

        other_user_id = conversation.user_one_id

    other_user = db.session.get(
        User,
        other_user_id
    )

    if other_user is None:

        continue

    last_message = PrivateMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(
        PrivateMessage.created_at.desc()
    ).first()

    unread_count = PrivateMessage.query.filter(
        PrivateMessage.conversation_id == conversation.id,
        PrivateMessage.sender_id != current_user.id,
        PrivateMessage.read == False
    ).count()

    inbox_conversations.append({
        "other_user": other_user,
        "last_message": last_message,
        "unread_count": unread_count
    })

inbox_conversations.sort(
    key=lambda conversation: (
        conversation["last_message"].created_at
        if conversation["last_message"]
        else datetime.min
    ),
    reverse=True
)

total_unread = sum(
    conversation["unread_count"]
    for conversation in inbox_conversations
)

return render_template(
    "inbox.html",
    current_user=current_user,
    conversations=inbox_conversations,
    total_unread=total_unread
)
```

# =========================

# PRIVATE MESSAGE PAGE

# =========================

@app.route("/dm/<username>", methods=["GET", "POST"])
def private_message(username):

```
user_id = session.get("user_id")

if not user_id:

    return redirect(url_for("login"))

current_user = db.session.get(
    User,
    user_id
)

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

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        conversation = Conversation.query.filter_by(
            user_one_id=user_one,
            user_two_id=user_two
        ).first()

if conversation is None:

    return "Unable to create conversation.", 500

if request.method == "POST":

    message_text = request.form.get(
        "message",
        ""
    ).strip()

    if message_text:

        private_message = PrivateMessage(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            message=message_text,
            read=False
        )

        db.session.add(
            private_message
        )

        db.session.commit()

    return redirect(
        url_for(
            "private_message",
            username=other_user.username
        )
    )

unread_messages = PrivateMessage.query.filter(
    PrivateMessage.conversation_id == conversation.id,
    PrivateMessage.sender_id != current_user.id,
    PrivateMessage.read == False
).all()

for message in unread_messages:

    message.read = True

if unread_messages:

    db.session.commit()

messages = PrivateMessage.query.filter_by(
    conversation_id=conversation.id
).order_by(
    PrivateMessage.created_at.asc()
).all()

return render_template(
    "dm.html",
    current_user=current_user,
    other_user=other_user,
    messages=messages
)
```

# =========================

# REAL-TIME PRIVATE MESSAGES

# =========================

@socketio.on("private_message")
def handle_private_message(data):

```
sender_id = session.get("user_id")

if not sender_id:

    return

sender = db.session.get(
    User,
    sender_id
)

if sender is None:

    return

try:

    receiver_id = int(
        data.get("receiver_id")
    )

except (
    TypeError,
    ValueError
):

    return

message_text = str(
    data.get("message", "")
).strip()

if not message_text:

    return

if len(message_text) > 2000:

    return

if receiver_id == sender.id:

    return

receiver = db.session.get(
    User,
    receiver_id
)

if receiver is None:

    return

user_one = min(
    sender.id,
    receiver.id
)

user_two = max(
    sender.id,
    receiver.id
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

    db.session.add(
        conversation
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        conversation = Conversation.query.filter_by(
            user_one_id=user_one,
            user_two_id=user_two
        ).first()

if conversation is None:

    return

private_message = PrivateMessage(
    conversation_id=conversation.id,
    sender_id=sender.id,
    message=message_text,
    read=False
)

db.session.add(
    private_message
)

db.session.commit()

timestamp = private_message.created_at.strftime(
    "%Y-%m-%d %H:%M"
)

socketio.emit(
    "private_message",
    {
        "sender_id": sender.id,
        "receiver_id": receiver.id,
        "sender_name": sender.display_name or sender.username,
        "message": private_message.message,
        "created_at": timestamp
    },
    room=f"dm_{conversation.id}"
)
```

# =========================

# PRIVATE MESSAGE ROOMS

# =========================

@socketio.on("join_private_conversation")
def join_private_conversation(data):

```
user_id = session.get("user_id")

if not user_id:

    return

try:

    other_user_id = int(
        data.get("other_user_id")
    )

except (
    TypeError,
    ValueError
):

    return

if user_id == other_user_id:

    return

user_one = min(
    user_id,
    other_user_id
)

user_two = max(
    user_id,
    other_user_id
)

conversation = Conversation.query.filter_by(
    user_one_id=user_one,
    user_two_id=user_two
).first()

if conversation is None:

    return

join_room(
    f"dm_{conversation.id}"
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

    user = db.session.get(
        User,
        user_id
    )

    if user:

        user.online = False

        db.session.commit()

session.clear()

return redirect(
    url_for("home")
)
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

    return redirect(
        url_for("home")
    )

return render_template(
    "room.html",
    code=room,
    messages=rooms[room]["messages"]
)
```

# =========================

# SEND ROOM MESSAGE

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
