import secrets
import csv
import io
import os
import sqlite3
import calendar as calendar_module

from datetime import datetime, timedelta, date
from functools import wraps
from flask import Response

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from translations import WORDS


# ============================================================
# CONFIGURATION
# ============================================================

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "agrisetu.db")

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-demo-change-this-before-deploying"
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def connect():

    db = sqlite3.connect(DB, timeout=20)

    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys=ON")

    db.execute("PRAGMA busy_timeout=20000")

    return db


def current_time():

    return datetime.now().isoformat(timespec="seconds")


def parse_time(value):

    if not value:
        return None

    try:
        return datetime.fromisoformat(value)

    except (ValueError, TypeError):
        return None


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    db = connect()

    try:

        db.executescript("""
        CREATE TABLE IF NOT EXISTS farmers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            village TEXT NOT NULL DEFAULT '',
            password TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS machines(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            rate REAL NOT NULL CHECK(rate > 0),
            status TEXT NOT NULL DEFAULT 'Available'
                CHECK(status IN ('Available','Under Service')),
            quantity INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL REFERENCES farmers(id),
            machine_id INTEGER NOT NULL REFERENCES machines(id),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            booked_hours INTEGER NOT NULL,
            actual_hours REAL,
            bill REAL,
            status TEXT NOT NULL DEFAULT 'Confirmed',
            created_at TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            actual_return_time TEXT
        );

        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL REFERENCES bookings(id),
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL REFERENCES farmers(id),
            message_en TEXT NOT NULL,
            message_kn TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        # Support databases created using the older version.

        machine_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(machines)"
            ).fetchall()
        }

        if "quantity" not in machine_columns:

            db.execute("""
                ALTER TABLE machines
                ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1
            """)

        booking_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(bookings)"
            ).fetchall()
        }

        if "quantity" not in booking_columns:

            db.execute("""
                ALTER TABLE bookings
                ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1
            """)

        if "actual_return_time" not in booking_columns:

            db.execute("""
                ALTER TABLE bookings
                ADD COLUMN actual_return_time TEXT
            """)

        count = db.execute(
            "SELECT COUNT(*) FROM machines"
        ).fetchone()[0]

        if count == 0:

            machines = [
                (
                    "Tractor",
                    "Field work",
                    "Cooperative Centre",
                    600,
                    2
                ),
                (
                    "Rotavator",
                    "Soil preparation",
                    "Cooperative Centre",
                    500,
                    2
                ),
                (
                    "Power Tiller",
                    "Field work",
                    "Cooperative Centre",
                    400,
                    2
                ),
                (
                    "Sprayer",
                    "Crop care",
                    "Cooperative Centre",
                    250,
                    3
                ),
                (
                    "Harvester",
                    "Harvesting",
                    "Cooperative Centre",
                    1500,
                    1
                )
            ]

            db.executemany("""
                INSERT INTO machines
                (name, category, location, rate, quantity)
                VALUES (?, ?, ?, ?, ?)
            """, machines)

        db.commit()

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


# ============================================================
# KANNADA / ENGLISH TRANSLATION
# ============================================================

def tr(key):

    lang = session.get("lang", "en")

    return WORDS.get(
        lang,
        WORDS["en"]
    ).get(
        key,
        WORDS["en"].get(key, key)
    )


app.jinja_env.globals["t"] = tr


@app.context_processor
def context():

    return {
        "lang": session.get("lang", "en"),
        "role": session.get("role"),
        "today": date.today().isoformat()
    }


# ============================================================
# AUTHENTICATION
# ============================================================

def auth(role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            if session.get("role") != role:

                flash(tr("please_login"), "error")

                return redirect(url_for("login"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# NOTIFICATIONS AND AUDIT
# ============================================================

def notify(db, farmer_id, english, kannada):

    db.execute("""
        INSERT INTO notifications
        (farmer_id, message_en, message_kn, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        farmer_id,
        english,
        kannada,
        current_time()
    ))


def audit(db, message):

    db.execute("""
        INSERT INTO audit(action, created_at)
        VALUES (?, ?)
    """, (
        message,
        current_time()
    ))


# ============================================================
# EQUIPMENT AVAILABILITY
# ============================================================

def available_stock(db, machine_id, start, end):

    machine = db.execute("""
        SELECT quantity, status
        FROM machines
        WHERE id = ?
    """, (machine_id,)).fetchone()

    if machine is None:
        return 0

    if machine["status"] != "Available":
        return 0

    total = int(machine["quantity"] or 0)

    bookings = db.execute("""
        SELECT start_time, end_time, quantity
        FROM bookings
        WHERE machine_id = ?
          AND status IN ('Confirmed', 'Completed')
          AND start_time < ?
          AND end_time > ?
    """, (
        machine_id,
        end.isoformat(timespec="minutes"),
        start.isoformat(timespec="minutes")
    )).fetchall()

    # Calculate maximum equipment occupied at any one time.

    events = []

    for booking in bookings:

        booking_start = max(
            parse_time(booking["start_time"]),
            start
        )

        booking_end = min(
            parse_time(booking["end_time"]),
            end
        )

        qty = int(booking["quantity"] or 1)

        events.append((booking_start, qty))
        events.append((booking_end, -qty))

    # At identical times, process ending bookings first.

    events.sort(key=lambda item: (item[0], item[1]))

    occupied = 0
    maximum_occupied = 0

    for event_time, change in events:

        occupied += change

        maximum_occupied = max(
            maximum_occupied,
            occupied
        )

    return max(0, total - maximum_occupied)


def valid_slot(db, machine_id, start, end, quantity=1):

    if start is None or end is None:

        return False, "Enter valid start and end dates."

    if end <= start:

        return False, "End time must be after start time."

    if start < datetime.now():

        return False, "Please select a future booking time."

    hours = (end - start).total_seconds() / 3600

    # Bookings use whole hours, from 1 to 10.

    if hours < 1 or hours > 10 or not hours.is_integer():

        return (
            False,
            "Booking duration must be 1 to 10 whole hours."
        )

    if quantity < 1:

        return False, "Quantity must be at least 1."

    machine = db.execute("""
        SELECT *
        FROM machines
        WHERE id = ?
    """, (machine_id,)).fetchone()

    if machine is None:

        return False, "Equipment not found."

    if machine["status"] != "Available":

        return False, "Equipment is Under Service."

    remaining = available_stock(
        db,
        machine_id,
        start,
        end
    )

    if quantity > remaining:

        return (
            False,
            f"Not Available! Only {remaining} unit(s) "
            "available during the selected time."
        )

    return (
        True,
        f"Available! {remaining} unit(s) available."
    )


# ============================================================
# CREATE BOOKING
# ============================================================

def create_booking(
    db,
    farmer_id,
    machine_id,
    start,
    end,
    quantity=1,
    source="Farmer"
):

    ok, message = valid_slot(
        db,
        machine_id,
        start,
        end,
        quantity
    )

    if not ok:
        return False, message

    hours = int(
        (end - start).total_seconds() / 3600
    )

    cursor = db.execute("""
        INSERT INTO bookings
        (
            farmer_id,
            machine_id,
            start_time,
            end_time,
            booked_hours,
            quantity,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'Confirmed', ?)
    """, (
        farmer_id,
        machine_id,
        start.isoformat(timespec="minutes"),
        end.isoformat(timespec="minutes"),
        hours,
        quantity,
        current_time()
    ))

    booking_id = cursor.lastrowid

    notify(
        db,
        farmer_id,
        f"Booking #{booking_id} confirmed.",
        f"ಬುಕಿಂಗ್ #{booking_id} ದೃಢೀಕರಿಸಲಾಗಿದೆ."
    )

    audit(
        db,
        f"{source} created booking #{booking_id}"
    )

    return (
        True,
        f"Booking #{booking_id} confirmed successfully!"
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# CHANGE LANGUAGE
# ============================================================

@app.route("/language/<code>")
def language(code):

    if code in WORDS:
        session["lang"] = code

    target = request.referrer or url_for("home")

    if target.startswith(request.host_url):

        return redirect(target)

    return redirect(url_for("home"))


# ============================================================
# FARMER REGISTRATION
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        village = request.form.get("village", "").strip()
        password = request.form.get("password", "")

        if (
            not name
            or len(phone) != 10
            or not phone.isdigit()
            or not password
            or not village
        ):

            flash(tr("invalid_registration"), "error")

            return redirect(url_for("register"))

        try:

            with connect() as db:

                cursor = db.execute("""
                    INSERT INTO farmers
                    (name, phone, village, password, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name,
                    phone,
                    village,
                    generate_password_hash(password),
                    current_time()
                ))

                farmer_id = cursor.lastrowid

                code = f"FE{farmer_id:04d}"

                ivr_pin = f"{secrets.randbelow(10000):04d}"

                db.execute("""
                    UPDATE farmers
                    SET ivr_pin = ?
                    WHERE id = ?
                """, (
                    generate_password_hash(ivr_pin),
                    farmer_id
                ))

                db.execute("""
                    UPDATE farmers
                    SET code = ?
                    WHERE id = ?
                """, (code, farmer_id))

                notify(
                    db,
                    farmer_id,
                    f"Welcome to AgriSetu! Your Farmer ID is {code}.",
                    f"ಅಗ್ರಿಸೇತುಗೆ ಸ್ವಾಗತ! ನಿಮ್ಮ ರೈತ ID {code}."
                )

                audit(
                    db,
                    f"Farmer {code} registered"
                )

            flash(
                f"Registration successful! "
                f"Farmer ID: {code} | "
                f"Your IVR PIN: {ivr_pin}. "
                f"Please save this PIN now.",
                "success"
            )

            return redirect(
                url_for("login", role="farmer")
            )

        except sqlite3.IntegrityError:

            flash(tr("phone_exists"), "error")

    return render_template("register.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    chosen = request.values.get(
        "role",
        "farmer"
    ).lower()

    if chosen not in ("farmer", "manager", "officer"):
        chosen = "farmer"

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        if (
            chosen == "manager"
            and username == "owner"
            and password == "owner123"
        ):

            session.clear()

            session["role"] = "manager"

            return redirect(url_for("manager"))

        if (
            chosen == "officer"
            and username == "admin"
            and password == "admin123"
        ):

            session.clear()

            session["role"] = "officer"

            return redirect(url_for("officer"))

        if chosen == "farmer":

            with connect() as db:

                farmer_record = db.execute("""
                    SELECT *
                    FROM farmers
                    WHERE code = ? OR phone = ?
                """, (
                    username.upper(),
                    username
                )).fetchone()

            if (
                farmer_record
                and farmer_record["active"]
                and check_password_hash(
                    farmer_record["password"],
                    password
                )
            ):

                session.clear()

                session["role"] = "farmer"

                session["farmer_id"] = farmer_record["id"]

                return redirect(url_for("farmer"))

        flash(tr("invalid_login"), "error")

    return render_template(
        "login.html",
        chosen=chosen
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ============================================================
# FARMER DASHBOARD
# ============================================================

@app.route("/farmer")
@auth("farmer")
def farmer():

    with connect() as db:

        farmer_record = db.execute("""
            SELECT *
            FROM farmers
            WHERE id = ?
        """, (
            session["farmer_id"],
        )).fetchone()

        if not farmer_record or not farmer_record["active"]:

            session.clear()

            flash(tr("inactive"), "error")

            return redirect(url_for("login"))

        machines = db.execute("""
            SELECT *
            FROM machines
            ORDER BY id
        """).fetchall()

        bookings = db.execute("""
            SELECT
                b.*,
                m.name AS machine_name,
                m.rate,
                (
                    SELECT COALESCE(SUM(amount), 0)
                    FROM payments
                    WHERE booking_id = b.id
                ) AS paid
            FROM bookings b
            JOIN machines m ON m.id = b.machine_id
            WHERE b.farmer_id = ?
            ORDER BY b.id DESC
        """, (
            farmer_record["id"],
        )).fetchall()

        notes = db.execute("""
            SELECT *
            FROM notifications
            WHERE farmer_id = ?
            ORDER BY id DESC
            LIMIT 30
        """, (
            farmer_record["id"],
        )).fetchall()

    return render_template(
        "farmer.html",
        farmer=farmer_record,
        machines=machines,
        bookings=bookings,
        notes=notes
    )


# ============================================================
# BOOKED SLOTS
# ============================================================

@app.route("/slots/<int:machine_id>")
@auth("farmer")
def slots(machine_id):

    with connect() as db:

        rows = db.execute("""
            SELECT
                start_time,
                end_time,
                quantity
            FROM bookings
            WHERE machine_id = ?
              AND status IN ('Confirmed', 'Completed')
              AND end_time >= ?
            ORDER BY start_time
        """, (
            machine_id,
            datetime.now().isoformat(timespec="minutes")
        )).fetchall()

    return jsonify([
        dict(row)
        for row in rows
    ])


# ============================================================
# CHECK AVAILABILITY
# ============================================================

@app.route("/availability", methods=["POST"])
@auth("farmer")
def availability():

    data = request.get_json(silent=True) or {}

    try:

        machine_id = int(
            data.get("machine_id", 0)
        )

        start = parse_time(
            data.get("start_time", "")
        )

        end = parse_time(
            data.get("end_time", "")
        )

        quantity = int(
            data.get("quantity", 1)
        )

        with connect() as db:

            ok, message = valid_slot(
                db,
                machine_id,
                start,
                end,
                quantity
            )

        return jsonify({
            "available": ok,
            "message": message
        })

    except (ValueError, TypeError):

        return jsonify({
            "available": False,
            "message": "Enter valid booking details."
        })


# ============================================================
# BOOKING CALENDAR
# ============================================================

@app.route("/calendar")
@auth("farmer")
def calendar():

    with connect() as db:

        machines = db.execute("""
            SELECT id, name, quantity
            FROM machines
            WHERE status = 'Available'
            ORDER BY name
        """).fetchall()

    return render_template(
        "calendar.html",
        machines=machines
    )


@app.route("/calendar-events/<int:machine_id>")
@auth("farmer")
def calendar_events(machine_id):

    with connect() as db:

        bookings = db.execute("""
            SELECT
                b.id,
                b.start_time,
                b.end_time,
                b.quantity,
                m.quantity AS total_stock
            FROM bookings b
            JOIN machines m ON m.id = b.machine_id
            WHERE b.machine_id = ?
              AND b.status IN ('Confirmed', 'Completed')
            ORDER BY b.start_time
        """, (machine_id,)).fetchall()

    events = []

    for booking in bookings:

        fully_reserved = (
            booking["quantity"] >= booking["total_stock"]
        )

        events.append({
            "id": booking["id"],
            "title": (
                f"Booked: {booking['quantity']} unit(s)"
            ),
            "start": booking["start_time"],
            "end": booking["end_time"],
            "color": (
                "#dc3545"
                if fully_reserved
                else "#f0ad4e"
            )
        })

    return jsonify(events)


# ============================================================
# CONFIRM FARMER BOOKING
# ============================================================

@app.route("/book", methods=["POST"])
@auth("farmer")
def book():

    try:

        machine_id = int(
            request.form.get("machine_id", 0)
        )

        start = parse_time(
            request.form.get("start_time", "")
        )

        end = parse_time(
            request.form.get("end_time", "")
        )

        quantity = int(
            request.form.get("quantity", 1)
        )

        db = connect()

        try:

            # Lock before checking remaining equipment.
            # Prevents two simultaneous bookings from
            # reserving the same remaining stock.

            db.execute("BEGIN IMMEDIATE")

            ok, message = create_booking(
                db,
                session["farmer_id"],
                machine_id,
                start,
                end,
                quantity
            )

            if ok:
                db.commit()

            else:
                db.rollback()

        finally:

            db.close()

        flash(
            message,
            "success" if ok else "error"
        )

    except (ValueError, TypeError, sqlite3.Error):

        flash(
            "Enter valid booking details.",
            "error"
        )

    return redirect(
        url_for("farmer") + "#booking"
    )


# ============================================================
# CANCEL BOOKING
# ============================================================

@app.route("/cancel/<int:bid>", methods=["POST"])
@auth("farmer")
def cancel(bid):

    with connect() as db:

        booking = db.execute("""
            SELECT *
            FROM bookings
            WHERE id = ?
              AND farmer_id = ?
        """, (
            bid,
            session["farmer_id"]
        )).fetchone()

        if (
            booking
            and booking["status"] == "Confirmed"
            and parse_time(booking["start_time"]) > datetime.now()
        ):

            db.execute("""
                UPDATE bookings
                SET status = 'Cancelled'
                WHERE id = ?
            """, (bid,))

            notify(
                db,
                booking["farmer_id"],
                f"Booking #{bid} cancelled.",
                f"ಬುಕಿಂಗ್ #{bid} ರದ್ದಾಗಿದೆ."
            )

            audit(
                db,
                f"Farmer cancelled booking #{bid}"
            )

            flash(tr("cancelled"), "success")

        else:

            flash(tr("cannot_cancel"), "error")

    return redirect(
        url_for("farmer") + "#mybookings"
    )


# ============================================================
# MANAGER DASHBOARD
# ============================================================

@app.route("/manager")
@auth("manager")
def manager():

    with connect() as db:

        machines = db.execute("""
            SELECT *
            FROM machines
            ORDER BY id DESC
        """).fetchall()

        farmers = db.execute("""
            SELECT *
            FROM farmers
            ORDER BY id DESC
        """).fetchall()

        bookings = db.execute("""
            SELECT
                b.*,
                f.name AS farmer_name,
                f.code,
                f.phone,
                m.name AS machine_name,
                m.rate,
                (
                    SELECT COALESCE(SUM(amount), 0)
                    FROM payments
                    WHERE booking_id = b.id
                ) AS paid
            FROM bookings b
            JOIN farmers f ON f.id = b.farmer_id
            JOIN machines m ON m.id = b.machine_id
            ORDER BY b.id DESC
        """).fetchall()

        payments = db.execute("""
            SELECT
                p.*,
                f.name AS farmer_name,
                m.name AS machine_name
            FROM payments p
            JOIN bookings b ON b.id = p.booking_id
            JOIN farmers f ON f.id = b.farmer_id
            JOIN machines m ON m.id = b.machine_id
            ORDER BY p.id DESC
        """).fetchall()

    return render_template(
        "manager.html",
        machines=machines,
        farmers=farmers,
        bookings=bookings,
        payments=payments
    )


# ============================================================
# ADD EQUIPMENT
# ============================================================

@app.route("/machine/add", methods=["POST"])
@auth("manager")
def machine_add():

    try:

        name = request.form.get(
            "name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        location = request.form.get(
            "location", ""
        ).strip()

        rate = float(
            request.form.get("rate", 0)
        )

        quantity = int(
            request.form.get("quantity", 1)
        )

        if not name or not 0 < rate <= 1000000:
            raise ValueError()

        if quantity < 1:
            raise ValueError()

        with connect() as db:

            db.execute("""
                INSERT INTO machines
                (name, category, location, rate, quantity)
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                category,
                location,
                rate,
                quantity
            ))

            audit(
                db,
                f"Added machine {name}, quantity {quantity}"
            )

        flash(tr("machine_added"), "success")

    except (ValueError, TypeError, sqlite3.Error):

        flash(tr("invalid_machine"), "error")

    return redirect(
        url_for("manager") + "#equipment"
    )


# ============================================================
# MACHINE STATUS
# ============================================================

@app.route("/machine/<int:mid>/status", methods=["POST"])
@auth("manager")
def machine_status(mid):

    status = request.form.get("status")

    if status not in ("Available", "Under Service"):

        flash(tr("invalid_status"), "error")

    else:

        with connect() as db:

            db.execute("""
                UPDATE machines
                SET status = ?
                WHERE id = ?
            """, (status, mid))

            audit(
                db,
                f"Machine #{mid}: {status}"
            )

        flash(tr("saved"), "success")

    return redirect(
        url_for("manager") + "#equipment"
    )


# ============================================================
# MANAGER PHONE BOOKING
# ============================================================

@app.route("/phone-book", methods=["POST"])
@auth("manager")
def phone_book():

    try:

        code = request.form.get(
            "farmer_code", ""
        ).strip().upper()

        machine_id = int(
            request.form.get("machine_id", 0)
        )

        start = parse_time(
            request.form.get("start_time", "")
        )

        hours = float(
            request.form.get("hours", 0)
        )

        if start is None or hours <= 0:
            raise ValueError()

        end = start + timedelta(hours=hours)

        db = connect()

        try:

            db.execute("BEGIN IMMEDIATE")

            farmer_record = db.execute("""
                SELECT *
                FROM farmers
                WHERE code = ? OR phone = ?
            """, (
                code,
                code
            )).fetchone()

            if (
                not farmer_record
                or not farmer_record["active"]
            ):

                ok = False
                message = "Active farmer not found."

            else:

                ok, message = create_booking(
                    db,
                    farmer_record["id"],
                    machine_id,
                    start,
                    end,
                    1,
                    "Manager phone booking"
                )

            if ok:
                db.commit()

            else:
                db.rollback()

        finally:

            db.close()

        flash(
            message,
            "success" if ok else "error"
        )

    except (ValueError, TypeError, sqlite3.Error):

        flash(tr("invalid_booking"), "error")

    return redirect(
        url_for("manager") + "#phone"
    )


# ============================================================
# COMPLETE BOOKING AND GENERATE BILL
# ============================================================

@app.route("/complete/<int:bid>", methods=["POST"])
@auth("manager")
def complete(bid):

    try:

        hours = float(
            request.form.get("actual_hours", 0)
        )

        if not 0 < hours <= 10000:
            raise ValueError()

        with connect() as db:

            booking = db.execute("""
                SELECT b.*, m.rate
                FROM bookings b
                JOIN machines m ON m.id = b.machine_id
                WHERE b.id = ?
            """, (bid,)).fetchone()

            if (
                not booking
                or booking["status"] != "Confirmed"
            ):

                flash(tr("cannot_complete"), "error")

            else:

                bill = round(
                    hours * booking["rate"] * booking["quantity"],
                    2
                )

                db.execute("""
                    UPDATE bookings
                    SET actual_hours = ?,
                        bill = ?,
                        status = 'Completed',
                        actual_return_time = ?
                    WHERE id = ?
                """, (
                    hours,
                    bill,
                    current_time(),
                    bid
                ))

                notify(
                    db,
                    booking["farmer_id"],
                    f"Booking #{bid} completed. Bill ₹{bill:.2f}.",
                    f"ಬುಕಿಂಗ್ #{bid} ಪೂರ್ಣಗೊಂಡಿದೆ. ಬಿಲ್ ₹{bill:.2f}."
                )

                audit(
                    db,
                    f"Booking #{bid} completed: ₹{bill:.2f}"
                )

                flash(tr("bill_generated"), "success")

    except (ValueError, TypeError):

        flash(tr("invalid_hours"), "error")

    return redirect(
        url_for("manager") + "#bookings"
    )


# ============================================================
# RECORD PAYMENT
# ============================================================

@app.route("/pay/<int:bid>", methods=["POST"])
@auth("manager")
def pay(bid):

    try:

        amount = round(
            float(request.form.get("amount", 0)),
            2
        )

        method = request.form.get(
            "method",
            "Cash"
        ).strip()

        if (
            amount <= 0
            or method not in (
                "Cash",
                "UPI",
                "Bank Transfer"
            )
        ):

            raise ValueError()

        db = connect()

        try:

            db.execute("BEGIN IMMEDIATE")

            booking = db.execute("""
                SELECT
                    b.*,
                    (
                        SELECT COALESCE(SUM(amount), 0)
                        FROM payments
                        WHERE booking_id = b.id
                    ) AS paid
                FROM bookings b
                WHERE b.id = ?
            """, (bid,)).fetchone()

            if not booking or booking["status"] != "Completed":

                db.rollback()

                flash(tr("invalid_payment"), "error")

            else:

                pending = round(
                    booking["bill"] - booking["paid"],
                    2
                )

                if amount > pending:

                    db.rollback()

                    flash(
                        "Payment cannot exceed pending amount.",
                        "error"
                    )

                else:

                    db.execute("""
                        INSERT INTO payments
                        (booking_id, amount, method, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (
                        bid,
                        amount,
                        method,
                        current_time()
                    ))

                    notify(
                        db,
                        booking["farmer_id"],
                        f"Payment ₹{amount:.2f} received for booking #{bid}.",
                        f"ಬುಕಿಂಗ್ #{bid} ಗೆ ₹{amount:.2f} ಪಾವತಿ ಸ್ವೀಕರಿಸಲಾಗಿದೆ."
                    )

                    audit(
                        db,
                        f"Payment ₹{amount:.2f} on booking #{bid}"
                    )

                    db.commit()

                    flash(tr("payment_saved"), "success")

        finally:

            db.close()

    except (ValueError, TypeError, sqlite3.Error):

        flash(tr("invalid_payment"), "error")

    return redirect(
        url_for("manager") + "#payments"
    )


# ============================================================
# MONTHLY REPORT
# ============================================================

@app.route("/report")
@auth("manager")
def report():

    month = request.args.get(
        "month",
        date.today().strftime("%Y-%m")
    )

    try:

        datetime.strptime(month, "%Y-%m")

    except ValueError:

        month = date.today().strftime("%Y-%m")

    with connect() as db:

        usage = db.execute("""
            SELECT
                m.name,

                COALESCE(
                    SUM(
                        CASE
                            WHEN substr(b.start_time, 1, 7) = ?
                            AND b.status = 'Completed'
                            THEN b.actual_hours * b.quantity
                            ELSE 0
                        END
                    ), 0
                ) AS hours,

                COALESCE(
                    SUM(
                        CASE
                            WHEN substr(b.start_time, 1, 7) = ?
                            AND b.status = 'Completed'
                            THEN b.bill
                            ELSE 0
                        END
                    ), 0
                ) AS billed

            FROM machines m

            LEFT JOIN bookings b
                ON b.machine_id = m.id

            GROUP BY m.id

            ORDER BY m.name
        """, (
            month,
            month
        )).fetchall()

        revenue = db.execute("""
            SELECT COALESCE(SUM(amount), 0) AS collected
            FROM payments
            WHERE substr(created_at, 1, 7) = ?
        """, (month,)).fetchone()

        dues = db.execute("""
            SELECT
                b.id,
                f.name,
                f.code,
                f.phone,
                m.name AS machine_name,
                b.bill,

                (
                    SELECT COALESCE(SUM(amount), 0)
                    FROM payments
                    WHERE booking_id = b.id
                ) AS paid

            FROM bookings b

            JOIN farmers f
                ON f.id = b.farmer_id

            JOIN machines m
                ON m.id = b.machine_id

            WHERE b.status = 'Completed'
              AND substr(b.start_time, 1, 7) = ?

              AND b.bill > (
                  SELECT COALESCE(SUM(amount), 0)
                  FROM payments
                  WHERE booking_id = b.id
              )

            ORDER BY b.id DESC
        """, (month,)).fetchall()

    return render_template(
        "report.html",
        month=month,
        usage=usage,
        revenue=revenue,
        dues=dues
    )


# ============================================================
# OFFICER DASHBOARD
# ============================================================

@app.route("/officer")
@auth("officer")
def officer():

    with connect() as db:

        farmers = db.execute("""
            SELECT *
            FROM farmers
            ORDER BY id DESC
        """).fetchall()

        logs = db.execute("""
            SELECT *
            FROM audit
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()

    return render_template(
        "officer.html",
        farmers=farmers,
        logs=logs
    )


# ============================================================
# ACTIVATE / DEACTIVATE FARMER
# ============================================================

@app.route("/farmer/<int:fid>/status", methods=["POST"])
@auth("officer")
def farmer_status(fid):

    active = request.form.get("active")

    if active not in ("0", "1"):

        flash(tr("invalid_status"), "error")

    else:

        with connect() as db:

            db.execute("""
                UPDATE farmers
                SET active = ?
                WHERE id = ?
            """, (
                int(active),
                fid
            ))

            audit(
                db,
                f"Officer set farmer #{fid} active={active}"
            )

            notify(
                db,
                fid,
                "Your account status was updated.",
                "ನಿಮ್ಮ ಖಾತೆಯ ಸ್ಥಿತಿಯನ್ನು ನವೀಕರಿಸಲಾಗಿದೆ."
            )

        flash(tr("saved"), "success")

    return redirect(url_for("officer"))

@app.route("/ivr")
def ivr():

    with connect() as db:

        rows = db.execute("""
            SELECT id, name, rate, status, quantity
            FROM machines
            ORDER BY id
            LIMIT 9
        """).fetchall()

    machines = [dict(row) for row in rows]

    return render_template(
        "ivr.html",
        machines=machines
    )
# ==========================================
        # IVR DATABASE
        # ==========================================

  # ==========================================   
# AGRISETU SIMULATED IVR BACKEND
# ============================================================

IVR_MAX_AGE = timedelta(hours=2)


def ivr_error(message, status=400):

    return jsonify({
        "error": message
    }), status


def ivr_data():

    return request.get_json(silent=True) or {}


def ivr_call(db, data, authenticated=False):

    token = data.get("token", "")

    if not isinstance(token, str) or not token:

        return None

    call = db.execute("""
        SELECT *
        FROM ivr_calls
        WHERE token = ?
          AND ended_at IS NULL
    """, (token,)).fetchone()

    if not call:

        return None

    started = parse_time(call["started_at"])

    if (
        started is None
        or datetime.now() - started > IVR_MAX_AGE
    ):

        return None

    if authenticated:

        if call["farmer_id"] is None:
            return None

        farmer = db.execute("""
            SELECT active
            FROM farmers
            WHERE id = ?
        """, (call["farmer_id"],)).fetchone()

        if not farmer or not farmer["active"]:
            return None

    return call


def ivr_log(db, call_id, action):

    db.execute("""
        UPDATE ivr_calls
        SET selections = selections || ?
        WHERE id = ?
    """, (
        action + "\n",
        call_id
    ))


def ivr_booking_details(data):
    machine_id = int(data.get("machine_id", 0))

    date_text = str(data.get("date", "")).strip()
    time_text = str(data.get("time", "")).strip()

    hours = int(data.get("hours", 0))
    quantity = int(data.get("quantity", 1))

    # Accept dates such as 20261030 or 2026-10-30.
    date_text = date_text.replace("-", "")

    start = datetime.strptime(
        date_text + time_text.replace(":", ""),
        "%Y%m%d%H%M"
    )

    if not 1 <= hours <= 10:
        raise ValueError("Hours must be from 1 to 10.")

    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    end = start + timedelta(hours=hours)

    return machine_id, start, end, hours, quantity
# ============================================================
# START IVR CALL
# ============================================================

@app.route("/api/ivr/start", methods=["POST"])
def ivr_start():

    try:
        token = secrets.token_urlsafe(32)

        with connect() as db:

            cursor = db.execute("""
                INSERT INTO ivr_calls
                (token, started_at, result)
                VALUES (?, ?, 'Started')
            """, (
                token,
                current_time()
            ))

            call_id = cursor.lastrowid

        return jsonify({
            "token": token,
            "call_id": call_id
        })

    except Exception as e:

        app.logger.exception("IVR START ERROR")

        return jsonify({
            "error": str(e)
        }), 500

# ============================================================
# SELECT LANGUAGE
# ============================================================

@app.route("/api/ivr/language", methods=["POST"])
def ivr_language():

    data = ivr_data()

    language = data.get("language")

    if language not in ("en", "kn"):

        return ivr_error("Invalid language.")

    with connect() as db:

        call = ivr_call(db, data)

        if not call:

            return ivr_error("Call expired. Start again.", 401)

        db.execute("""
            UPDATE ivr_calls
            SET language = ?
            WHERE id = ?
        """, (
            language,
            call["id"]
        ))

        ivr_log(
            db,
            call["id"],
            f"Language selected: {language}"
        )

    return jsonify({
        "ok": True,
        "language": language
    })


# ============================================================
# FARMER ID + IVR PIN VERIFICATION
# ============================================================

@app.route("/api/ivr/auth", methods=["POST"])
def ivr_auth():

    data = ivr_data()

    farmer_number = str(
        data.get("farmer_number", "")
    ).strip()

    pin = str(data.get("pin", ""))

    if (
        not farmer_number.isdigit()
        or len(farmer_number) > 8
        or not pin.isdigit()
        or len(pin) != 4
    ):

        return ivr_error("Invalid Farmer ID or PIN.", 401)

    farmer_code = "FE" + farmer_number.zfill(4)

    with connect() as db:

        call = ivr_call(db, data)

        if not call:

            return ivr_error("Call expired. Start again.", 401)

        # Limit incorrect PIN attempts for this call.

        failures = db.execute("""
            SELECT selections
            FROM ivr_calls
            WHERE id = ?
        """, (call["id"],)).fetchone()

        attempts = failures["selections"].count(
            "Authentication failed"
        )

        if attempts >= 3:

            return ivr_error(
                "Too many incorrect attempts. End the call.",
                429
            )

        farmer = db.execute("""
            SELECT *
            FROM farmers
            WHERE code = ?
              AND active = 1
        """, (farmer_code,)).fetchone()

        if (
            not farmer
            or not farmer["ivr_pin"]
            or not check_password_hash(
                farmer["ivr_pin"],
                pin
            )
        ):

            ivr_log(
                db,
                call["id"],
                "Authentication failed"
            )

            return ivr_error(
                "Incorrect Farmer ID or IVR PIN.",
                401
            )

        db.execute("""
            UPDATE ivr_calls
            SET farmer_id = ?,
                result = 'Authenticated'
            WHERE id = ?
        """, (
            farmer["id"],
            call["id"]
        ))

        ivr_log(
            db,
            call["id"],
            "Farmer authenticated"
        )

    return jsonify({
        "ok": True,
        "code": farmer["code"],
        "name": farmer["name"]
    })


# ============================================================
# IVR EQUIPMENT LIST
# ============================================================

@app.route("/api/ivr/machines", methods=["POST"])
def ivr_machines():

    data = ivr_data()

    with connect() as db:

        call = ivr_call(
            db,
            data,
            authenticated=True
        )

        if not call:

            return ivr_error(
                "Please verify your Farmer ID and PIN.",
                401
            )

        rows = db.execute("""
            SELECT id, name, rate, status, quantity
            FROM machines
            ORDER BY id
            LIMIT 9
        """).fetchall()

        ivr_log(
            db,
            call["id"],
            "Viewed equipment list"
        )

    return jsonify({
        "machines": [
            dict(row)
            for row in rows
        ]
    })


# ============================================================
# IVR LIVE AVAILABILITY CHECK
# ============================================================

@app.route("/api/ivr/check", methods=["POST"])
def ivr_check():

    data = ivr_data()

    try:

        machine_id, start, end, hours, quantity = (
            ivr_booking_details(data)
        )

    except (ValueError, TypeError, OverflowError):

        return ivr_error("Invalid booking details.")

    with connect() as db:

        call = ivr_call(
            db,
            data,
            authenticated=True
        )

        if not call:

            return ivr_error("Call expired.", 401)

        ok, message = valid_slot(
            db,
            machine_id,
            start,
            end,
            quantity
        )

        if not ok:

            ivr_log(
                db,
                call["id"],
                f"Availability rejected for machine #{machine_id}"
            )

            return jsonify({
                "available": False,
                "error": message
            })

        machine = db.execute("""
            SELECT *
            FROM machines
            WHERE id = ?
        """, (machine_id,)).fetchone()

        bill = round(
            machine["rate"] * hours * quantity,
            2
        )

        ivr_log(
            db,
            call["id"],
            f"Availability checked: machine #{machine_id}"
        )

    return jsonify({
        "available": True,
        "machine": machine["name"],
        "start": start.isoformat(timespec="minutes"),
        "end": end.isoformat(timespec="minutes"),
        "quantity": quantity,
        "bill": bill
    })


# ============================================================
# CONFIRM REAL BOOKING THROUGH IVR
# ============================================================

@app.route("/api/ivr/book", methods=["POST"])
def ivr_book():

    data = ivr_data()

    try:

        machine_id, start, end, hours, quantity = (
            ivr_booking_details(data)
        )

    except (ValueError, TypeError, OverflowError):

        return ivr_error("Invalid booking details.")

    db = connect()

    try:

        # Prevent simultaneous bookings from taking
        # the same remaining equipment.

        db.execute("BEGIN IMMEDIATE")

        call = ivr_call(
            db,
            data,
            authenticated=True
        )

        if not call:

            db.rollback()

            return ivr_error("Call expired.", 401)

        # Prevent repeated confirmation in one call.

        if call["booking_id"] is not None:

            db.rollback()

            return ivr_error(
                "A booking has already been confirmed in this call."
            )

        ok, message = create_booking(
            db,
            call["farmer_id"],
            machine_id,
            start,
            end,
            quantity,
            source="IVR"
        )

        if not ok:

            db.rollback()

            return ivr_error(message)

        booking_id = db.execute("""
            SELECT last_insert_rowid()
        """).fetchone()[0]

        machine = db.execute("""
            SELECT rate
            FROM machines
            WHERE id = ?
        """, (machine_id,)).fetchone()

        estimated_bill = round(
            machine["rate"] * hours * quantity,
            2
        )

        db.execute("""
            UPDATE ivr_calls
            SET machine_id = ?,
                booking_id = ?,
                result = 'Booking Confirmed'
            WHERE id = ?
        """, (
            machine_id,
            booking_id,
            call["id"]
        ))

        ivr_log(
            db,
            call["id"],
            f"Confirmed booking #{booking_id}"
        )

        db.commit()

        return jsonify({
            "ok": True,
            "booking_id": booking_id,
            "bill": estimated_bill,
            "status": "Confirmed"
        })

    except sqlite3.Error:

        db.rollback()

        return ivr_error(
            "Database error. Please try again.",
            500
        )

    finally:

        db.close()


# ============================================================
# FARMER BOOKING STATUS THROUGH IVR
# ============================================================

@app.route("/api/ivr/status", methods=["POST"])
def ivr_status():

    data = ivr_data()

    with connect() as db:

        call = ivr_call(
            db,
            data,
            authenticated=True
        )

        if not call:

            return ivr_error("Call expired.", 401)

        rows = db.execute("""
            SELECT
                b.id,
                m.name AS machine_name,
                b.start_time,
                b.status,
                b.bill,
                b.booked_hours,
                b.quantity,
                m.rate
            FROM bookings b
            JOIN machines m ON m.id = b.machine_id
            WHERE b.farmer_id = ?
            ORDER BY b.id DESC
            LIMIT 10
        """, (
            call["farmer_id"],
        )).fetchall()

        bookings = []

        for row in rows:

            item = dict(row)

            if item["bill"] is None:

                item["bill"] = round(
                    item["booked_hours"]
                    * item["quantity"]
                    * item["rate"],
                    2
                )

            bookings.append(item)

        ivr_log(
            db,
            call["id"],
            "Checked booking status"
        )

    return jsonify({
        "bookings": bookings
    })


# ============================================================
# CANCEL BOOKING THROUGH IVR
# ============================================================

@app.route("/api/ivr/cancel", methods=["POST"])
def ivr_cancel():

    data = ivr_data()

    try:

        booking_id = int(
            data.get("booking_id", 0)
        )

        if booking_id < 1:
            raise ValueError()

    except (ValueError, TypeError):

        return ivr_error("Invalid booking number.")

    db = connect()

    try:

        db.execute("BEGIN IMMEDIATE")

        call = ivr_call(
            db,
            data,
            authenticated=True
        )

        if not call:

            db.rollback()

            return ivr_error("Call expired.", 401)

        booking = db.execute("""
            SELECT *
            FROM bookings
            WHERE id = ?
              AND farmer_id = ?
        """, (
            booking_id,
            call["farmer_id"]
        )).fetchone()

        if (
            not booking
            or booking["status"] != "Confirmed"
            or parse_time(booking["start_time"]) <= datetime.now()
        ):

            db.rollback()

            return ivr_error(
                "This booking cannot be cancelled."
            )

        db.execute("""
            UPDATE bookings
            SET status = 'Cancelled'
            WHERE id = ?
        """, (booking_id,))

        notify(
            db,
            call["farmer_id"],
            f"Booking #{booking_id} cancelled through IVR.",
            f"ಬುಕಿಂಗ್ #{booking_id} ರದ್ದಾಗಿದೆ."
        )

        audit(
            db,
            f"IVR cancelled booking #{booking_id}"
        )

        ivr_log(
            db,
            call["id"],
            f"Cancelled booking #{booking_id}"
        )

        db.execute("""
            UPDATE ivr_calls
            SET result = 'Booking Cancelled'
            WHERE id = ?
        """, (call["id"],))

        db.commit()

        return jsonify({
            "ok": True,
            "booking_id": booking_id
        })

    finally:

        db.close()


# ============================================================
# END IVR CALL
# ============================================================

@app.route("/api/ivr/end", methods=["POST"])
def ivr_end():

    data = ivr_data()

    with connect() as db:

        call = ivr_call(db, data)

        if call:

            db.execute("""
                UPDATE ivr_calls
                SET ended_at = ?,
                    result = CASE
                        WHEN result IN (
                            'Booking Confirmed',
                            'Booking Cancelled'
                        )
                        THEN result
                        ELSE 'Call Ended'
                    END
                WHERE id = ?
            """, (
                current_time(),
                call["id"]
            ))

    return jsonify({
        "ok": True
    })


# ============================================================
# OWNER: IVR CALL RECORDS
# ============================================================

@app.route("/manager/ivr")
@auth("manager")
def manager_ivr():

    with connect() as db:

        calls = db.execute("""
            SELECT
                c.*,
                f.code,
                f.name AS farmer_name,
                m.name AS machine_name
            FROM ivr_calls c
            LEFT JOIN farmers f
                ON f.id = c.farmer_id
            LEFT JOIN machines m
                ON m.id = c.machine_id
            ORDER BY c.id DESC
        """).fetchall()

    return render_template(
        "ivr_records.html",
        calls=calls
    )


# ============================================================
# OWNER: EXPORT IVR CALL HISTORY
# ============================================================

@app.route("/manager/ivr/export")
@auth("manager")
def manager_ivr_export():

    with connect() as db:

        calls = db.execute("""
            SELECT
                c.id,
                f.code AS farmer_code,
                f.name AS farmer_name,
                c.language,
                c.started_at,
                c.ended_at,
                c.selections,
                m.name AS machine_name,
                c.booking_id,
                c.result
            FROM ivr_calls c
            LEFT JOIN farmers f
                ON f.id = c.farmer_id
            LEFT JOIN machines m
                ON m.id = c.machine_id
            ORDER BY c.id DESC
        """).fetchall()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Call ID",
        "Farmer ID",
        "Farmer Name",
        "Language",
        "Started At",
        "Ended At",
        "Selections",
        "Machine",
        "Booking ID",
        "Result"
    ])

    for call in calls:

        writer.writerow(list(call))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=agrisetu_ivr_calls.csv"
        }
    )


# ============================================================
# EXISTING FARMERS: GENERATE FIRST IVR PIN
# ============================================================

@app.route("/farmer/ivr-pin", methods=["POST"])
@auth("farmer")
def farmer_ivr_pin():

    farmer_id = session["farmer_id"]

    with connect() as db:

        farmer = db.execute("""
            SELECT ivr_pin
            FROM farmers
            WHERE id = ?
              AND active = 1
        """, (farmer_id,)).fetchone()

        if not farmer:

            flash("Farmer account unavailable.", "error")

        elif farmer["ivr_pin"]:

            flash(
                "An IVR PIN already exists. Contact the officer "
                "if you need a PIN reset.",
                "error"
            )

        else:

            pin = f"{secrets.randbelow(10000):04d}"

            db.execute("""
                UPDATE farmers
                SET ivr_pin = ?
                WHERE id = ?
            """, (
                generate_password_hash(pin),
                farmer_id
            ))

            flash(
                f"Your IVR PIN is {pin}. Save it now. "
                "It will not be displayed again.",
                "success"
            )

    return redirect(url_for("farmer"))
    # Create IVR call history table
# ============================================================
# IVR DATABASE INITIALIZATION AND MIGRATION
# ============================================================

def init_ivr_db():
    db = connect()

    try:
        # Add the IVR PIN column to existing databases.
        farmer_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(farmers)"
            ).fetchall()
        }

        if "ivr_pin" not in farmer_columns:
            db.execute("""
                ALTER TABLE farmers
                ADD COLUMN ivr_pin TEXT
            """)

        # Create the IVR call history table.
        db.execute("""
            CREATE TABLE IF NOT EXISTS ivr_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                farmer_id INTEGER REFERENCES farmers(id),
                language TEXT NOT NULL DEFAULT 'en',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                selections TEXT NOT NULL DEFAULT '',
                machine_id INTEGER REFERENCES machines(id),
                booking_id INTEGER REFERENCES bookings(id),
                result TEXT NOT NULL DEFAULT 'Started'
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ivr_farmer
            ON ivr_calls(farmer_id)
        """)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ============================================================
# START AGRISETU
# ============================================================

init_db()
init_ivr_db()


if __name__ == "__main__":
    print("=" * 55)
    print("AGRISETU")
    print("Farm Equipment Booking & Billing System")
    print("=" * 55)
    print("Website: http://127.0.0.1:5000")
    print("Owner: owner / owner123")
    print("Officer: admin / admin123")
    print("=" * 55)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )