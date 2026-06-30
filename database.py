import sqlite3

DB_NAME = "hostel.db"

def create_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ROOM
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Room (
            room_id       TEXT PRIMARY KEY NOT NULL,
            room_type     TEXT NOT NULL,
            fee_per_month REAL NOT NULL,
            capacity      INTEGER NOT NULL
        )
    """)

    # STAFF
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Staff (
            staff_id          INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            fullname          TEXT NOT NULL,
            email             TEXT UNIQUE NOT NULL,
            password          TEXT NOT NULL,
            role              TEXT NOT NULL CHECK(role IN ('admin', 'warden')),
            phone             TEXT NOT NULL,
            reset_token       TEXT DEFAULT NULL,
            reset_token_used  INTEGER DEFAULT 0
        )
    """)

    # APPLICATION
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Application (
            application_id  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            fullname        TEXT NOT NULL,
            email           TEXT UNIQUE NOT NULL CHECK(email LIKE 'p________@student.newinti.edu.my'),
            password        TEXT NOT NULL,
            gender          TEXT NOT NULL CHECK(gender IN ('F', 'M')),
            phone           TEXT NOT NULL,
            status          TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # STUDENT
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Student (
            student_id                TEXT PRIMARY KEY NOT NULL,
            fullname                  TEXT NOT NULL,
            email                     TEXT UNIQUE NOT NULL,
            password                  TEXT NOT NULL,
            gender                    TEXT NOT NULL,
            phone                     TEXT NOT NULL,
            last_read_announcement_at TEXT DEFAULT NULL,
            reset_token               TEXT DEFAULT NULL,
            reset_token_used          INTEGER DEFAULT 0,
            application_id            INTEGER NOT NULL,
            FOREIGN KEY (application_id) REFERENCES Application(application_id)
        )
    """)

    # ANNOUNCEMENT
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Announcement (
            announcement_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            title           TEXT NOT NULL,
            description     TEXT NOT NULL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            audience        TEXT NOT NULL DEFAULT 'all' CHECK(audience IN ('all', 'one')),
            staff_id        INTEGER NOT NULL,
            FOREIGN KEY (staff_id) REFERENCES Staff(staff_id)
        )
    """)

    # ANNOUNCEMENT RECIPIENT
    # Only populated when audience = 'one'
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Announcement_Recipient (
            announcement_id INTEGER NOT NULL,
            student_id      TEXT NOT NULL,
            is_read         INTEGER DEFAULT 0,
            PRIMARY KEY (announcement_id, student_id),
            FOREIGN KEY (announcement_id) REFERENCES Announcement(announcement_id),
            FOREIGN KEY (student_id)      REFERENCES Student(student_id)
        )
    """)

    # MAINTENANCE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Maintenance (
            request_id  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            description TEXT NOT NULL,
            category    TEXT NOT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            status      TEXT NOT NULL CHECK(status IN ('pending', 'in-progress', 'resolved')),
            room_id     TEXT NOT NULL,
            student_id  TEXT NOT NULL,
            FOREIGN KEY (room_id)    REFERENCES Room(room_id),
            FOREIGN KEY (student_id) REFERENCES Student(student_id)
        )
    """)

    # PAYMENT
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Payment (
            payment_id      INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            amount          REAL NOT NULL,
            payment_method  TEXT NOT NULL CHECK(payment_method IN ('cash', 'online_banking', 'e-wallet')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            student_id      TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Student(student_id)
        )
    """)

    # RENTAL BILL
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Rental_Bill (
            rental_id  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            amount     REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date   TEXT NOT NULL,
            student_id TEXT NOT NULL,
            payment_id INTEGER DEFAULT NULL,
            room_id    TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Student(student_id),
            FOREIGN KEY (payment_id) REFERENCES Payment(payment_id),
            FOREIGN KEY (room_id)    REFERENCES Room(room_id)
        )
    """)

    # FINE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Fine (
            fine_id    INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            reason     TEXT NOT NULL,
            amount     REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            student_id TEXT NOT NULL,
            staff_id   INTEGER NOT NULL,
            payment_id INTEGER DEFAULT NULL,
            FOREIGN KEY (student_id) REFERENCES Student(student_id),
            FOREIGN KEY (staff_id)   REFERENCES Staff(staff_id),
            FOREIGN KEY (payment_id) REFERENCES Payment(payment_id)
        )
    """)

    # LATE PAYMENT
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Late_Payment (
            late_payment_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            amount          REAL NOT NULL,
            rental_id       INTEGER NOT NULL,
            payment_id      INTEGER DEFAULT NULL,
            FOREIGN KEY (rental_id)  REFERENCES Rental_Bill(rental_id),
            FOREIGN KEY (payment_id) REFERENCES Payment(payment_id)
        )
    """)

    conn.commit()
    conn.close()
    print("Database created successfully with all tables.")


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


if __name__ == "__main__":
    create_database()