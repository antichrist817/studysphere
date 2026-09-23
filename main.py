from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from string import ascii_uppercase

app = Flask(__name__)

app.config["SECRET_KEY"] = "CHANGE_THIS_SECRET_LATER"

socketio = SocketIO(app)

rooms = {}


def generate_unique_code(length=4):
    while True:
        code = "".join(
            random.choice(ascii_uppercase)
            for _ in range(length)
        )

        if code not in rooms:
            return code


@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()

        join = request.form.get("join")
        create = request.form.get("create")

        if not name:
            return render_template(
                "home.html",
                error="Please enter a name.",
                name=name,
                code=code
            )

        # CREATE ROOM

        if create:

            room = generate_unique_code()

            rooms[room] = {
                "members": 0,
                "messages": []
            }

        # JOIN ROOM

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


@app.route("/room")
def room():

    room = session.get("room")
    name = session.get("name")

    if not room or not name or room not in rooms:
        return redirect(url_for("home"))

    return render_template(
        "room.html",
        code=room,
        messages=rooms[room]["messages"]
    )


@socketio.on("message")
def handle_message(data):

    room = session.get("room")
    name = session.get("name")

    if not room or not name or room not in rooms:
        return

    message = str(data.get("data", "")).strip()

    if not message:
        return

    content = {
        "name": name,
        "message": message
    }

    send(content, to=room)

    rooms[room]["messages"].append(content)


@socketio.on("connect")
def handle_connect():

    room = session.get("room")
    name = session.get("name")

    if not room or not name or room not in rooms:
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


@socketio.on("disconnect")
def handle_disconnect():

    room = session.get("room")
    name = session.get("name")

    if not room:
        return

    leave_room(room)

    if room in rooms:

        rooms[room]["members"] -= 1

        if rooms[room]["members"] <= 0:
            del rooms[room]

    if name:
        send(
            {
                "name": "StudySphere",
                "message": f"{name} left the room."
            },
            to=room
        )


if __name__ == "__main__":
    socketio.run(
        app,
        debug=True
    )
