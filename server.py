
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory,
    abort,
)
import mysql.connector
import os
import uuid
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# --------------------------------------------------
# Flask secret key
# --------------------------------------------------
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY is missing. Add it to the .env file.")

UPLOAD_DIR = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "gif", "webp",
    "txt", "doc", "docx", "ppt", "pptx",
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


# --------------------------------------------------
# MySQL connection
# --------------------------------------------------

def get_db_connection():
    required = [
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
    ]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            "Missing database settings in .env: " + ", ".join(missing)
        )

    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=15,
        ssl_disabled=False,
        use_pure=True
    )



def ensure_messages_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INT NOT NULL AUTO_INCREMENT,
            sender_id INT NOT NULL,
            receiver_id INT NOT NULL,
            body TEXT NULL,
            file_name VARCHAR(255) NULL,
            stored_name VARCHAR(255) NULL,
            is_read TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_sender (sender_id),
            KEY idx_receiver (receiver_id)
        )
        """
    )


def load_partner(cursor, partner_id, user_id):
    if partner_id == user_id:
        return None

    cursor.execute(
        """
        SELECT
            u.id,
            COALESCE(NULLIF(p.name, ''), u.name) AS name,
            p.college,
            p.department,
            p.academic_year
        FROM users u
        LEFT JOIN user_profiles p ON p.user_id = u.id
        WHERE u.id = %s
        """,
        (partner_id,),
    )
    return cursor.fetchone()


def conversation_list(cursor, user_id):
    cursor.execute(
        """
        SELECT partner_id, MAX(id) AS last_id
        FROM (
            SELECT
                CASE
                    WHEN sender_id = %s THEN receiver_id
                    ELSE sender_id
                END AS partner_id,
                id
            FROM messages
            WHERE sender_id = %s OR receiver_id = %s
        ) AS threads
        GROUP BY partner_id
        ORDER BY last_id DESC
        """,
        (user_id, user_id, user_id),
    )
    threads = cursor.fetchall()
    if not threads:
        return []

    cursor.execute(
        """
        SELECT sender_id, COUNT(*) AS unread
        FROM messages
        WHERE receiver_id = %s AND is_read = 0
        GROUP BY sender_id
        """,
        (user_id,),
    )
    unread = {
        row["sender_id"]: row["unread"]
        for row in cursor.fetchall()
    }

    conversations = []
    for thread in threads:
        partner = load_partner(cursor, thread["partner_id"], user_id)
        if partner is None:
            continue

        cursor.execute(
            """
            SELECT body, file_name, created_at, sender_id
            FROM messages
            WHERE id = %s
            """,
            (thread["last_id"],),
        )
        last = cursor.fetchone()
        if last and last["body"]:
            preview = last["body"]
        elif last and last["file_name"]:
            preview = "Shared a file: " + last["file_name"]
        else:
            preview = ""

        partner["preview"] = preview
        partner["last_at"] = last["created_at"] if last else None
        partner["unread"] = unread.get(partner["id"], 0)
        conversations.append(partner)

    return conversations


def fetch_thread(cursor, user_id, partner_id, after_id=0):
    cursor.execute(
        """
        SELECT id, sender_id, receiver_id, body, file_name, stored_name, created_at
        FROM (
            SELECT id, sender_id, receiver_id, body, file_name, stored_name, created_at
            FROM messages
            WHERE (
                (sender_id = %s AND receiver_id = %s)
                OR (sender_id = %s AND receiver_id = %s)
            )
            AND id > %s
            ORDER BY id DESC
            LIMIT 200
        ) AS recent
        ORDER BY id ASC
        """,
        (user_id, partner_id, partner_id, user_id, after_id),
    )
    return cursor.fetchall()


def mark_thread_read(cursor, user_id, partner_id):
    cursor.execute(
        """
        UPDATE messages
        SET is_read = 1
        WHERE sender_id = %s AND receiver_id = %s AND is_read = 0
        """,
        (partner_id, user_id),
    )


def message_payload(message, user_id):
    created = message["created_at"]
    file_name = message["file_name"] or ""
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return {
        "id": message["id"],
        "sender_id": message["sender_id"],
        "mine": message["sender_id"] == user_id,
        "body": message["body"] or "",
        "file_name": file_name,
        "file_url": (
            url_for("chat_file", message_id=message["id"])
            if message["stored_name"]
            else ""
        ),
        "is_image": extension in IMAGE_EXTENSIONS,
        "created_at": created.strftime("%d %b, %I:%M %p") if created else "",
    }


def save_attachment(upload):
    if upload is None or not upload.filename:
        return None, None

    original = secure_filename(upload.filename)
    if "." not in original:
        return None, "invalid"

    extension = original.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return None, "invalid"

    stored_name = uuid.uuid4().hex + "_" + original
    upload.save(os.path.join(UPLOAD_DIR, stored_name))
    return (original, stored_name), None


# --------------------------------------------------
# Home
# --------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# Login
# --------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():

    # Already logged in
    if "user_id" in session:
        return redirect(url_for("profile"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "error")
            return redirect(url_for("login"))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            user = cursor.fetchone()

            if user is None:
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            if not check_password_hash(user["password_hash"], password):
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            # Save login information in session
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            # Redirect to profile after login
            return redirect(url_for("profile"))

        except mysql.connector.Error as error:
            print("MySQL error:", error)
            flash("Database connection error. Please try again.", "error")
            return redirect(url_for("login"))

        finally:
            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("login.html")


# --------------------------------------------------
# Register
# --------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if "user_id" in session:
        return redirect(url_for("profile"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        if len(name) > 100:
            flash("Name must be 100 characters or fewer.", "error")
            return redirect(url_for("register"))

        if len(email) > 255:
            flash("Email must be 255 characters or fewer.", "error")
            return redirect(url_for("register"))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            # Check existing email
            cursor.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )

            existing_user = cursor.fetchone()

            if existing_user:
                flash("An account with this email already exists.", "error")
                return redirect(url_for("register"))

            # Hash password
            password_hash = generate_password_hash(password)

            # Insert new user
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name, email, password_hash)
            )

            connection.commit()

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except mysql.connector.Error as error:
            print("MySQL error:", error)

            if connection:
                connection.rollback()

            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("register"))

        finally:
            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("Register.html")


# --------------------------------------------------
# Profile
# --------------------------------------------------


@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = None
    cursor = None

    def render_profile(profile_data):
        return render_template(
            "profile.html",
            user_name=session.get("user_name", ""),
            user_email=session.get("user_email", ""),
            profile_data=profile_data,
        )

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # SAVE OR UPDATE PROFILE
        if request.method == "POST":

            name = request.form.get("name", "").strip()
            college = request.form.get("college", "").strip()
            department = request.form.get("department", "").strip()
            academic_year = request.form.get("year", "").strip()
            bio = request.form.get("bio", "").strip()
            teach_skills = request.form.get("teachSkills", "").strip()
            learn_skills = request.form.get("learnSkills", "").strip()

            submitted = {
                "name": name,
                "college": college,
                "department": department,
                "academic_year": academic_year,
                "bio": bio,
                "teach_skills": teach_skills,
                "learn_skills": learn_skills,
            }

            if not all([
                name,
                college,
                department,
                academic_year,
                bio,
                teach_skills,
                learn_skills
            ]):
                flash("Please fill in all fields.", "error")
                return render_profile(submitted)

            if len(name) > 100:
                flash("Name must be 100 characters or fewer.", "error")
                return render_profile(submitted)

            if (
                len(college) > 255
                or len(department) > 150
                or len(academic_year) > 50
            ):
                flash("One of the profile fields is too long.", "error")
                return render_profile(submitted)

            sql = """
                    INSERT INTO user_profiles
                    (
                        user_id,
                        name,
                        college,
                        department,
                        academic_year,
                        bio,
                        teach_skills,
                        learn_skills
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        college = VALUES(college),
                        department = VALUES(department),
                        academic_year = VALUES(academic_year),
                        bio = VALUES(bio),
                        teach_skills = VALUES(teach_skills),
                        learn_skills = VALUES(learn_skills)
                """

            values = (
                user_id,
                name,
                college,
                department,
                academic_year,
                bio,
                teach_skills,
                learn_skills
            )

            cursor.execute(sql, values)

            cursor.execute(
                "UPDATE users SET name = %s WHERE id = %s",
                (name, user_id)
            )

            conn.commit()

            session["user_name"] = name

            flash("Profile saved successfully!", "success")

            return redirect(url_for("dashboard"))


        # LOAD EXISTING PROFILE
        cursor.execute(
            """
            SELECT
                name,
                college,
                department,
                academic_year,
                bio,
                teach_skills,
                learn_skills
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,)
        )

        profile_data = cursor.fetchone()

        return render_profile(profile_data)

    except Exception as e:

        if conn:
            conn.rollback()

        print("Profile Error:", e)

        if request.method == "POST":
            flash("Something went wrong while saving your profile.", "error")
            submitted = {
                "name": request.form.get("name", "").strip(),
                "college": request.form.get("college", "").strip(),
                "department": request.form.get("department", "").strip(),
                "academic_year": request.form.get("year", "").strip(),
                "bio": request.form.get("bio", "").strip(),
                "teach_skills": request.form.get("teachSkills", "").strip(),
                "learn_skills": request.form.get("learnSkills", "").strip(),
            }
        else:
            flash("Something went wrong while loading your profile.", "error")
            submitted = None

        return render_profile(submitted)

    finally:

        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()




# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session["user_id"]

        # Fetch saved profile information
        cursor.execute(
            """
            SELECT
                name,
                college,
                department,
                academic_year,
                bio,
                teach_skills,
                learn_skills
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,)
        )

        profile = cursor.fetchone()

        return render_template(
            "dashboard.html",
            user_name=session.get("user_name", "Student"),
            user_email=session.get("user_email", ""),
            profile=profile
        )

    except Exception as e:

        print("Dashboard Error:", e)

        flash("Unable to load dashboard.", "error")

        return redirect(url_for("login"))

    finally:

        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


# --------------------------------------------------
# Logout
# --------------------------------------------------
@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))
# --------------------------------------------------
# Matches
# --------------------------------------------------

@app.route("/matches")
def matches():

    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session["user_id"]

        # Get current user's learning interests
        cursor.execute(
            """
            SELECT learn_skills
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,)
        )

        my_profile = cursor.fetchone()

        if not my_profile:
            flash("Please complete your profile first.", "error")
            return redirect(url_for("profile"))

        # Convert learning skills into a normalized set
        my_skills = {
            skill.strip().casefold()
            for skill in (my_profile["learn_skills"] or "").split(",")
            if skill.strip()
        }

        if not my_skills:
            return render_template(
                "matches.html",
                matches=[],
                user_name=session.get("user_name", "Student")
            )

        # Fetch other students who have profiles
        cursor.execute(
            """
            SELECT
                user_id,
                name,
                college,
                department,
                academic_year,
                bio,
                teach_skills,
                learn_skills
            FROM user_profiles
            WHERE user_id != %s
            """,
            (user_id,)
        )

        students = cursor.fetchall()

        matched_students = []

        # Compare teaching skills with current user's learning skills
        for student in students:

            teach_list = [
                skill.strip()
                for skill in (student["teach_skills"] or "").split(",")
                if skill.strip()
            ]

            matching_skills = [
                skill for skill in teach_list
                if skill.casefold() in my_skills
            ]

            if matching_skills:

                student["matching_skills"] = matching_skills

                student["match_count"] = len(matching_skills)

                student["match_percentage"] = round(
                    len(matching_skills) / len(my_skills) * 100
                )

                matched_students.append(student)

        # Rank students by number of matching skills
        matched_students.sort(
            key=lambda student: student["match_count"],
            reverse=True
        )

        return render_template(
            "matches.html",
            matches=matched_students,
            user_name=session.get("user_name", "Student")
        )

    except Exception as e:

        print("Matching Error:", e)

        flash("Unable to find learning partners.", "error")

        return redirect(url_for("dashboard"))

    finally:

        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


# --------------------------------------------------
# Messages
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(_error):
    flash("That file is too large. The maximum size is 8 MB.", "error")
    return redirect(request.referrer or url_for("messages_inbox"))


@app.route("/messages")
def messages_inbox():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_messages_table(cursor)
        conversations = conversation_list(cursor, session["user_id"])

        return render_template(
            "chat.html",
            user_name=session.get("user_name", "Student"),
            partner=None,
            messages=[],
            conversations=conversations,
        )
    except Exception as error:
        print("Messages Error:", error)
        flash("Unable to open messages.", "error")
        return redirect(url_for("dashboard"))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/chat/<int:partner_id>", methods=["GET", "POST"])
def chat(partner_id):
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_messages_table(cursor)

        partner = load_partner(cursor, partner_id, user_id)
        if partner is None:
            flash("That student could not be found.", "error")
            return redirect(url_for("messages_inbox"))

        if request.method == "POST":
            body = request.form.get("body", "").strip()
            attachment, attachment_error = save_attachment(
                request.files.get("attachment")
            )

            if attachment_error == "invalid":
                flash(
                    "That file type is not allowed. Share a PDF, image, text, Word, or PowerPoint file.",
                    "error",
                )
                return redirect(url_for("chat", partner_id=partner_id))

            if not body and attachment is None:
                flash("Write a message or choose a file to share.", "error")
                return redirect(url_for("chat", partner_id=partner_id))

            if len(body) > 4000:
                flash("Message must be 4000 characters or fewer.", "error")
                return redirect(url_for("chat", partner_id=partner_id))

            file_name, stored_name = attachment if attachment else (None, None)

            try:
                cursor.execute(
                    """
                    INSERT INTO messages
                        (sender_id, receiver_id, body, file_name, stored_name)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, partner_id, body or None, file_name, stored_name),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                if stored_name:
                    saved_path = os.path.join(UPLOAD_DIR, stored_name)
                    if os.path.exists(saved_path):
                        os.remove(saved_path)
                raise

            return redirect(url_for("chat", partner_id=partner_id))

        mark_thread_read(cursor, user_id, partner_id)
        conn.commit()
        thread = fetch_thread(cursor, user_id, partner_id)
        conversations = conversation_list(cursor, user_id)

        return render_template(
            "chat.html",
            user_name=session.get("user_name", "Student"),
            partner=partner,
            messages=thread,
            conversations=conversations,
        )
    except Exception as error:
        print("Chat Error:", error)
        flash("Unable to open this conversation.", "error")
        return redirect(url_for("messages_inbox"))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/chat/<int:partner_id>/updates")
def chat_updates(partner_id):
    if "user_id" not in session:
        abort(401)

    user_id = session["user_id"]
    after_id = request.args.get("after", default=0, type=int)
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_messages_table(cursor)

        partner = load_partner(cursor, partner_id, user_id)
        if partner is None:
            abort(404)

        mark_thread_read(cursor, user_id, partner_id)
        conn.commit()
        thread = fetch_thread(cursor, user_id, partner_id, after_id=after_id)
        return jsonify([message_payload(item, user_id) for item in thread])
    except HTTPException:
        raise
    except Exception as error:
        print("Chat update error:", error)
        abort(500)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/chat/file/<int:message_id>")
def chat_file(message_id):
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT sender_id, receiver_id, file_name, stored_name
            FROM messages
            WHERE id = %s
            """,
            (message_id,),
        )
        message = cursor.fetchone()

        stored_name = message["stored_name"] if message else ""
        if (
            message is None
            or not stored_name
            or os.path.basename(stored_name) != stored_name
        ):
            abort(404)

        if user_id not in (message["sender_id"], message["receiver_id"]):
            abort(403)

        extension = ""
        if message["file_name"] and "." in message["file_name"]:
            extension = message["file_name"].rsplit(".", 1)[-1].lower()

        return send_from_directory(
            UPLOAD_DIR,
            stored_name,
            as_attachment=extension not in IMAGE_EXTENSIONS,
            download_name=message["file_name"] or "shared-file",
        )
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# --------------------------------------------------
# Run application
# --------------------------------------------------
if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1"
    )
