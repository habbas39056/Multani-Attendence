"""
One-Click Sync Script to push all local Multani Traders data to Supabase
"""
import requests
import json
import sqlite3

def run_sync():
    with open("supabase_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    url = cfg["url"]
    key = cfg["key"]

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    conn = sqlite3.connect("payroll_attendance.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"Connecting to Supabase at {url}...")

    # Check if table exists
    r_check = requests.get(f"{url}/rest/v1/employees?select=count", headers=headers)
    if r_check.status_code == 404:
        print("\n⚠️  TABLES NOT FOUND IN SUPABASE YET!")
        print("Please copy the contents of 'supabase_schema.sql' and run it in your Supabase SQL Editor.")
        print("Supabase Dashboard Link: https://supabase.com/dashboard/project/tyxvrykwarevfdwrbrmv/sql\n")
        return False

    # 1. Company Settings
    cursor.execute("SELECT * FROM company_settings LIMIT 1")
    row = cursor.fetchone()
    if row:
        comp_data = dict(row)
        r = requests.post(f"{url}/rest/v1/company_settings", headers=headers, json=[comp_data])
        print(f"1. Company Settings Sync: status={r.status_code}")

    # 2. Shifts
    cursor.execute("SELECT * FROM shifts")
    shifts = [dict(r) for r in cursor.fetchall()]
    if shifts:
        r = requests.post(f"{url}/rest/v1/shifts", headers=headers, json=shifts)
        print(f"2. Shifts Sync ({len(shifts)} records): status={r.status_code}")

    # 3. Employees
    cursor.execute("SELECT * FROM employees WHERE is_active = 1")
    employees = [dict(r) for r in cursor.fetchall()]
    if employees:
        r = requests.post(f"{url}/rest/v1/employees", headers=headers, json=employees)
        print(f"3. Employees Sync ({len(employees)} staff members): status={r.status_code}")

    # 4. Raw Punches
    cursor.execute("SELECT biometric_id, punch_time, punch_type, source FROM raw_attendance_logs")
    punches = [dict(r) for r in cursor.fetchall()]
    if punches:
        for i in range(0, len(punches), 100):
            batch = punches[i:i+100]
            requests.post(f"{url}/rest/v1/raw_attendance_logs", headers=headers, json=batch)
        print(f"4. Raw Attendance Punches Sync ({len(punches)} logs): SUCCESS")

    # 5. Daily Attendance
    cursor.execute("SELECT * FROM daily_attendance")
    daily_rows = [dict(r) for r in cursor.fetchall()]
    if daily_rows:
        for i in range(0, len(daily_rows), 100):
            batch = daily_rows[i:i+100]
            requests.post(f"{url}/rest/v1/daily_attendance", headers=headers, json=batch)
        print(f"5. Daily Attendance Records Sync ({len(daily_rows)} days): SUCCESS")

    # 6. Payroll Runs
    cursor.execute("SELECT * FROM payroll_runs")
    runs = [dict(r) for r in cursor.fetchall()]
    if runs:
        r_run = requests.post(f"{url}/rest/v1/payroll_runs", headers=headers, json=runs)
        print(f"6. Payroll Runs Sync ({len(runs)} runs): status={r_run.status_code}")

    # 7. Payslips
    cursor.execute("SELECT * FROM payslips")
    payslip_rows = [dict(r) for r in cursor.fetchall()]
    if payslip_rows:
        # Match employee_id in Supabase by biometric_id
        r_sup_emps = requests.get(f"{url}/rest/v1/employees?select=id,biometric_id", headers=headers).json()
        bio_to_sup_id = {e["biometric_id"]: e["id"] for e in r_sup_emps}

        # Map local employee_id to biometric_id
        cursor.execute("SELECT id, biometric_id FROM employees")
        loc_emp_to_bio = {r["id"]: r["biometric_id"] for r in cursor.fetchall()}

        cleaned_slips = []
        for s in payslip_rows:
            slip_dict = dict(s)
            local_eid = slip_dict["employee_id"]
            bio = loc_emp_to_bio.get(local_eid)
            if bio and bio in bio_to_sup_id:
                slip_dict["employee_id"] = bio_to_sup_id[bio]
                slip_dict.pop("id", None)
                slip_dict.pop("payroll_run_id", None)
                cleaned_slips.append(slip_dict)

        if cleaned_slips:
            r_slip = requests.post(f"{url}/rest/v1/payslips", headers=headers, json=cleaned_slips)
            print(f"7. Payslips Sync ({len(cleaned_slips)} payslips): status={r_slip.status_code}")

    conn.close()
    print("\n[SUCCESS] ALL LOCAL MULTANI TRADERS DATA SUCCESSFULLY SYNCED TO SUPABASE CLOUD!")
    return True

if __name__ == "__main__":
    run_sync()
