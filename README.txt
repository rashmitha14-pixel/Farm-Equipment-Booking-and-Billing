AgriSetu – Farm Equipment Booking & Billing (new standalone prototype)

IMPORTANT: This is a new version with its own agrisetu.db schema. DO NOT overwrite your old project or rename/copy the old farm_equipment.db into this folder. Keep your old project as a backup.

Windows setup:
1. Install Python 3.10+.
2. Open terminal in this AgriSetu_Ready folder.
3. Run: py -m pip install -r requirements.txt
4. Run: py app.py
5. Open http://127.0.0.1:5000

Demo accounts (change via OWNER_USERNAME / OWNER_PASSWORD / OFFICER_USERNAME / OFFICER_PASSWORD environment variables before sharing):
Owner/Manager: owner / owner123
Officer: admin / admin123
Farmers: register first; first farmer gets FE0001; use Farmer ID or mobile and chosen password.

SQLite database agrisetu.db is created automatically on first run. Copy it separately for judges after you have entered demonstration data. SQLite can be inspected with any SQLite database viewer.

Core rules: no overlap, end-to-start allowed, service machines blocked, 1–10 booked hours, future booking only, bill based on actual hours, payment capped at pending, monthly report.
Manager can book on behalf of farmers who phone in. This is a manual entry workflow, NOT an automated telephone integration. Cash/UPI/Bank Transfer are recorded payment methods; this app does not process online payments or send real SMS.

Prototype only: use HTTPS, CSRF protection, hardened admin authentication, audit logs and deployment security before production. Do not expose Flask to public internet as-is.
