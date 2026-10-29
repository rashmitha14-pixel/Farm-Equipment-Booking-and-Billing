# AgriSetu — Farm Equipment Booking & Billing System

## Windows setup
1. Extract the ZIP (do not mix these files into an older project).
2. Open the extracted `AgriSetu_Ready` folder in VS Code.
3. In its terminal, run:
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
   If `py` does not work, use `python` instead.
4. Visit http://127.0.0.1:5000/ in your browser.

## Demo login
- Owner: `owner` / `owner123`
- Officer: `admin` / `admin123`
- Farmer: register a new account, then log in with the displayed FE0001-style ID or mobile number and password.

English / ಕನ್ನಡ language buttons are in the top-right navigation. User-created data is stored in `agrisetu.db` created automatically on first run. The demo does **not** send SMS or use Twilio; notifications appear inside the farmer dashboard. Do not copy an old incompatible SQLite database into this folder.

## Required rules implemented
- Available and Under Service equipment; service machines cannot be booked.
- Date/time plus 1–10 booked hours; no past starts.
- Same-machine overlap blocked transactionally; adjacent bookings allowed.
- Confirmed bookings; manager records actual hours to complete and generate `actual hours × hourly rate` bill.
- Partial payments; payment cannot exceed remaining balance.
- Monthly machine usage, money collected by payment date, and dues for bookings starting in selected month.
- Manager phone bookings, officer account activation and audit log, farmer in-app notifications.

## Important
Local hackathon prototype, not production-ready: demo passwords are hardcoded, Flask debug mode is enabled, no SMS gateway, no CSRF protection or public hosting configuration. Change these before deployment. Do not run `app.py` from a different older folder. The included app creates its own fresh database.
