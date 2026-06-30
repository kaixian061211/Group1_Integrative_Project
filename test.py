import bcrypt
from database import get_connection

def insert_test_data():
    conn = get_connection()
    cursor = conn.cursor()

    # ── CLEAR EXISTING DATA (in reverse FK order) ─────────────────────────────
    cursor.execute("DELETE FROM Fine")
    cursor.execute("DELETE FROM Late_Payment")
    cursor.execute("DELETE FROM Rental_Bill")
    cursor.execute("DELETE FROM Payment")
    cursor.execute("DELETE FROM Maintenance")
    cursor.execute("DELETE FROM Announcement_Recipient")
    cursor.execute("DELETE FROM Announcement")
    cursor.execute("DELETE FROM Student")
    cursor.execute("DELETE FROM Application")
    cursor.execute("DELETE FROM Staff")
    cursor.execute("DELETE FROM Room")
    cursor.execute("DELETE FROM sqlite_sequence")

    # ── HASH HELPER ───────────────────────────────────────────────────────────
    def h(plain):
        return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # ── ROOMS ─────────────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Room (room_id, room_type, fee_per_month, capacity) VALUES (?, ?, ?, ?)
    """, [
        ('R101', 'single', 500.00, 1),
        ('R102', 'single', 500.00, 1),
        ('R201', 'double', 350.00, 2),
        ('R202', 'double', 350.00, 2),
        ('R301', 'triple', 250.00, 3),
        ('R302', 'triple', 250.00, 3),
    ])

    # ── STAFF ─────────────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Staff (fullname, email, password, role, phone) VALUES (?, ?, ?, ?, ?)
    """, [
        ('Ahmad Farid',    'ahmad.farid@newinti.edu.my',    h('admin123'),  'admin',  '0123456781'),
        ('Siti Nurhaliza', 'siti.nurhaliza@newinti.edu.my', h('warden123'), 'warden', '0123456782'),
        ('Raj Kumar',      'raj.kumar@newinti.edu.my',      h('warden456'), 'warden', '0123456783'),
    ])

    # ── APPLICATIONS ──────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Application (fullname, email, password, gender, phone, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        ('Lee Wei Ming',   'p24016001@student.newinti.edu.my', h('pass1234'), 'M', '0111234001', 'approved', '2026-01-05'), # App ID: 1
        ('Nurul Ain',      'p24016002@student.newinti.edu.my', h('pass1234'), 'F', '0111234002', 'approved', '2026-01-08'), # App ID: 2
        ('Tan Jia Hui',    'p24016003@student.newinti.edu.my', h('pass1234'), 'F', '0111234003', 'approved', '2026-02-10'), # App ID: 3
        ('Muhammad Haziq', 'p24016004@student.newinti.edu.my', h('pass1234'), 'M', '0111234004', 'approved', '2026-02-14'), # App ID: 4
        ('Priya Devi',     'p24016005@student.newinti.edu.my', h('pass1234'), 'F', '0111234005', 'approved', '2026-03-03'), # App ID: 5
        ('Kevin Loh',      'p24016006@student.newinti.edu.my', h('pass1234'), 'M', '0111234006', 'rejected', '2026-04-15'), # App ID: 6
        ('Amirah Zahra',   'p24016007@student.newinti.edu.my', h('pass1234'), 'F', '0111234007', 'rejected', '2026-05-20'), # App ID: 7
        ('Chong Wei Xian', 'p24016008@student.newinti.edu.my', h('pass1234'), 'M', '0111234008', 'pending',  '2026-06-01'), # App ID: 8
        ('Fatimah Zahra',  'p24016009@student.newinti.edu.my', h('pass1234'), 'F', '0111234009', 'pending',  '2026-07-10'), # App ID: 9
        ('Lim Jun Hao',    'p24016010@student.newinti.edu.my', h('pass1234'), 'M', '0111234010', 'approved', '2026-08-05'), # App ID: 10
        ('Kavitha Rao',    'p24016011@student.newinti.edu.my', h('pass1234'), 'F', '0111234011', 'approved', '2026-09-03'), # App ID: 11
        ('Hafiz Roslan',   'p24016012@student.newinti.edu.my', h('pass1234'), 'M', '0111234012', 'pending',  '2026-10-12'), # App ID: 12
        ('Ong Mei Ling',   'p24016013@student.newinti.edu.my', h('pass1234'), 'F', '0111234013', 'rejected', '2026-11-08'), # App ID: 13
        ('Danish Irfan',   'p24016014@student.newinti.edu.my', h('pass1234'), 'M', '0111234014', 'pending',  '2026-12-02'), # App ID: 14
    ])

    # ── STUDENTS ──────────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Student (student_id, fullname, email, password, gender, phone, last_read_announcement_at, application_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ('p24016001', 'Lee Wei Ming',   'p24016001@student.newinti.edu.my', h('pass1234'), 'M', '0111234001', None, 1),
        ('p24016002', 'Nurul Ain',      'p24016002@student.newinti.edu.my', h('pass1234'), 'F', '0111234002', None, 2),
        ('p24016003', 'Tan Jia Hui',    'p24016003@student.newinti.edu.my', h('pass1234'), 'F', '0111234003', None, 3),
        ('p24016004', 'Muhammad Haziq', 'p24016004@student.newinti.edu.my', h('pass1234'), 'M', '0111234004', None, 4),
        ('p24016005', 'Priya Devi',     'p24016005@student.newinti.edu.my', h('pass1234'), 'F', '0111234005', None, 5),
        ('p24016010', 'Lim Jun Hao',    'p24016010@student.newinti.edu.my', h('pass1234'), 'M', '0111234010', None, 10),
        ('p24016011', 'Kavitha Rao',    'p24016011@student.newinti.edu.my', h('pass1234'), 'F', '0111234011', None, 11),
    ])

    # ── ANNOUNCEMENTS ─────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Announcement (title, description, audience, staff_id, created_at) VALUES (?, ?, ?, ?, ?)
    """, [
        ('Welcome New Students',       'Welcome to INTI hostel for the new semester. Please collect your access card at the office.', 'all', 1, '2026-01-06'), # ID: 1
        ('Water Interruption Notice',  'There will be a water supply interruption on 15 Feb 2026 from 8AM to 12PM.',                  'all', 2, '2026-02-12'), # ID: 2
        ('Rental Payment Reminder',    'Kindly settle your March rental payment before 15 March 2026 to avoid fines.',                'all', 2, '2026-03-10'), # ID: 3
        ('Fire Drill Scheduled',       'A fire drill will be conducted on 20 April 2026 at 3PM. All residents must participate.',     'all', 3, '2026-04-15'), # ID: 4
        ('Hostel Inspection Notice',   'Room inspection will be carried out on 10 May 2026. Please ensure rooms are tidy.',           'all', 2, '2026-05-05'), # ID: 5
        ('Mid Year Reminder',          'Please update your emergency contact details at the hostel office before June 30.',           'all', 1, '2026-06-01'), # ID: 6
        ('Pest Control Notice',        'Pest control treatment will be conducted on 15 July 2026. Please vacate rooms by 9AM.',       'all', 3, '2026-07-10'), # ID: 7
        ('Semester Break Notice',      'Hostel will remain open during semester break. Notify office if you are leaving.',            'all', 1, '2026-08-01'), # ID: 8
        ('Rental Payment Reminder',    'Kindly settle your September rental payment before 15 September 2026 to avoid fines.',        'all', 2, '2026-09-08'), # ID: 9
        ('Wifi Maintenance',           'Wifi service will be interrupted on 5 Oct 2026 from 10AM to 2PM for upgrades.',               'all', 3, '2026-10-03'), # ID: 10
        ('Year End Checkout Reminder', 'Students leaving at year end must submit room checkout form by 30 November 2026.',            'all', 1, '2026-11-10'), # ID: 11
        ('Happy New Year Notice',      'Hostel office will be closed on 1 January 2027. Season greetings to all residents.',         'all', 1, '2026-12-20'), # ID: 12
        ('Overdue Payment Notice',     'Dear Resident, you have an outstanding rental payment. Please settle immediately.',          'one', 2, '2026-04-20'), # ID: 13
        ('Room Damage Charges',        'Dear Resident, damage charges have been applied to your account. Visit the office for details.', 'one', 3, '2026-06-18'), # ID: 14
    ])

    # ── ANNOUNCEMENT RECIPIENTS ───────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Announcement_Recipient (announcement_id, student_id) VALUES (?, ?)
    """, [
        (13, 'p24016004'),  # Overdue Payment Notice → Muhammad Haziq
        (14, 'p24016005'),  # Room Damage Charges    → Priya Devi
    ])

    # ── MAINTENANCE REQUESTS ──────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Maintenance (description, category, status, room_id, student_id, created_at) VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ('Ceiling fan is making loud noise',    'electrical', 'resolved',    'R101', 'p24016001', '2026-01-10'),
        ('Toilet flush not working properly',   'plumbing',   'resolved',    'R201', 'p24016002', '2026-02-05'),
        ('Window latch is broken',              'furniture',  'resolved',    'R201', 'p24016003', '2026-02-20'),
        ('Air conditioner not cooling',         'electrical', 'resolved',    'R202', 'p24016004', '2026-03-18'),
        ('Sink pipe leaking under the basin',   'plumbing',   'resolved',    'R202', 'p24016005', '2026-04-02'),
        ('Wardrobe door hinge is loose',        'furniture',  'resolved',    'R101', 'p24016001', '2026-04-25'),
        ('Light bulb in bathroom blown',        'electrical', 'resolved',    'R201', 'p24016002', '2026-05-10'),
        ('Shower drain is clogged',             'plumbing',   'resolved',    'R201', 'p24016003', '2026-05-28'),
        ('Study desk drawer is stuck',          'furniture',  'resolved',    'R202', 'p24016004', '2026-06-07'),
        ('Power socket not working',            'electrical', 'in-progress', 'R102', 'p24016001', '2026-07-03'),
        ('Water heater tripping circuit',       'electrical', 'in-progress', 'R202', 'p24016005', '2026-07-19'),
        ('Bedroom door lock is jammed',         'furniture',  'in-progress', 'R301', 'p24016011', '2026-08-11'),
        ('Ceiling water stain from upstairs',   'plumbing',   'in-progress', 'R201', 'p24016003', '2026-09-04'),
        ('Broken window glass pane',            'furniture',  'pending',     'R102', 'p24016010', '2026-10-15'),
        ('Exhaust fan not functioning',         'electrical', 'pending',     'R301', 'p24016011', '2026-11-02'),
        ('Toilet bowl cracked',                 'plumbing',   'pending',     'R202', 'p24016004', '2026-12-01'),
    ])

    # ── PAYMENTS ──────────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Payment (amount, payment_method, student_id, created_at) VALUES (?, ?, ?, ?)
    """, [
        (500.00, 'online_banking', 'p24016001', '2026-01-05'),  # ID: 1
        (350.00, 'e-wallet',       'p24016002', '2026-01-06'),  # ID: 2
        (350.00, 'cash',           'p24016003', '2026-01-07'),  # ID: 3
        (350.00, 'online_banking', 'p24016004', '2026-01-08'),  # ID: 4
        (350.00, 'e-wallet',       'p24016005', '2026-01-09'),  # ID: 5
        (500.00, 'online_banking', 'p24016001', '2026-02-04'),  # ID: 6
        (350.00, 'cash',           'p24016002', '2026-02-05'),  # ID: 7
        (350.00, 'e-wallet',       'p24016003', '2026-02-06'),  # ID: 8
        (350.00, 'online_banking', 'p24016004', '2026-02-07'),  # ID: 9
        (500.00, 'cash',           'p24016001', '2026-03-05'),  # ID: 10
        (350.00, 'online_banking', 'p24016002', '2026-03-06'),  # ID: 11
        (350.00, 'e-wallet',       'p24016003', '2026-03-07'),  # ID: 12
        (50.00,  'cash',           'p24016002', '2026-03-20'),  # ID: 13 — Late penalty payment
        (500.00, 'online_banking', 'p24016001', '2026-04-04'),  # ID: 14
        (350.00, 'cash',           'p24016002', '2026-04-05'),  # ID: 15
        (350.00, 'e-wallet',       'p24016003', '2026-04-06'),  # ID: 16
        (500.00, 'e-wallet',       'p24016001', '2026-05-05'),  # ID: 17
        (350.00, 'online_banking', 'p24016002', '2026-05-06'),  # ID: 18
        (500.00, 'online_banking', 'p24016001', '2026-06-04'),  # ID: 19
        (350.00, 'cash',           'p24016003', '2026-06-10'),  # ID: 20
        (500.00, 'online_banking', 'p24016001', '2026-07-05'),  # ID: 21
        (350.00, 'e-wallet',       'p24016002', '2026-07-06'),  # ID: 22
        (250.00, 'cash',           'p24016010', '2026-07-08'),  # ID: 23
        (500.00, 'online_banking', 'p24016001', '2026-08-05'),  # ID: 24
        (350.00, 'cash',           'p24016002', '2026-08-06'),  # ID: 25
        (250.00, 'e-wallet',       'p24016010', '2026-08-07'),  # ID: 26
        (250.00, 'online_banking', 'p24016011', '2026-08-10'),  # ID: 27
        (500.00, 'online_banking', 'p24016001', '2026-09-05'),  # ID: 28
        (350.00, 'e-wallet',       'p24016003', '2026-09-07'),  # ID: 29
        (250.00, 'cash',           'p24016011', '2026-09-08'),  # ID: 30
        (500.00, 'online_banking', 'p24016001', '2026-10-05'),  # ID: 31
        (350.00, 'cash',           'p24016002', '2026-10-06'),  # ID: 32
        (250.00, 'e-wallet',       'p24016010', '2026-10-07'),  # ID: 33
        (500.00, 'online_banking', 'p24016001', '2026-11-05'),  # ID: 34
        (350.00, 'e-wallet',       'p24016003', '2026-11-06'),  # ID: 35
        (500.00, 'online_banking', 'p24016001', '2026-12-05'),  # ID: 36
        (350.00, 'cash',           'p24016002', '2026-12-06'),  # ID: 37
        (120.00, 'online_banking', 'p24016004', '2026-05-01'),  # ID: 38 — Fine payment (Haziq)
        (80.00,  'e-wallet',       'p24016005', '2026-07-10'),  # ID: 39 — Fine payment (Priya)
    ])

    # ── RENTAL BILLS ──────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Rental_Bill (amount, start_date, end_date, student_id, payment_id, room_id) VALUES (?, ?, ?, ?, ?, ?)
    """, [
        (500.00, '2026-01-01', '2026-01-31', 'p24016001', 1,    'R101'), # ID: 1
        (350.00, '2026-01-01', '2026-01-31', 'p24016002', 2,    'R201'), # ID: 2
        (350.00, '2026-01-01', '2026-01-31', 'p24016003', 3,    'R201'), # ID: 3
        (350.00, '2026-01-01', '2026-01-31', 'p24016004', 4,    'R202'), # ID: 4
        (350.00, '2026-01-01', '2026-01-31', 'p24016005', 5,    'R202'), # ID: 5
        (500.00, '2026-02-01', '2026-02-28', 'p24016001', 6,    'R101'), # ID: 6
        (350.00, '2026-02-01', '2026-02-28', 'p24016002', 7,    'R201'), # ID: 7
        (350.00, '2026-02-01', '2026-02-28', 'p24016003', 8,    'R201'), # ID: 8
        (350.00, '2026-02-01', '2026-02-28', 'p24016004', 9,    'R202'), # ID: 9
        (350.00, '2026-02-01', '2026-02-28', 'p24016005', None, 'R202'), # ID: 10 — unpaid
        (500.00, '2026-03-01', '2026-03-31', 'p24016001', 10,   'R101'), # ID: 11
        (350.00, '2026-03-01', '2026-03-31', 'p24016002', 11,   'R201'), # ID: 12
        (350.00, '2026-03-01', '2026-03-31', 'p24016003', 12,   'R201'), # ID: 13
        (350.00, '2026-03-01', '2026-03-31', 'p24016004', None, 'R202'), # ID: 14 — unpaid
        (350.00, '2026-03-01', '2026-03-31', 'p24016005', None, 'R202'), # ID: 15 — unpaid
        (500.00, '2026-04-01', '2026-04-30', 'p24016001', 14,   'R101'), # ID: 16
    ])

    # ── FINES ─────────────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Fine (reason, amount, student_id, staff_id, payment_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ('Broken wardrobe mirror in room',  120.00, 'p24016004', 2, 38,   '2026-04-10'), # paid
        ('Scratches on study desk surface',  80.00, 'p24016005', 3, 39,   '2026-06-15'), # paid
        ('Cracked bathroom tiles',          200.00, 'p24016004', 3, None, '2026-10-20'), # unpaid
        ('Broken door handle',               60.00, 'p24016005', 3, None, '2026-12-10'), # unpaid
    ])

    # ── LATE PAYMENTS ─────────────────────────────────────────────────────────
    cursor.executemany("""
        INSERT INTO Late_Payment (amount, rental_id, payment_id) VALUES (?, ?, ?)
    """, [
        (50.00, 10, None), # Unpaid late penalty — Feb bill (Rental ID 10, Priya)
        (50.00, 13, 13),   # Paid late penalty   — Mar bill (Rental ID 13, Nurul Ain)
        (50.00, 14, None), # Unpaid late penalty — Mar bill (Rental ID 14, Haziq)
    ])

    conn.commit()
    conn.close()
    print("Test data updated and inserted successfully.")

if __name__ == "__main__":
    insert_test_data()