"""
Script to import August attendance report from august.xls
"""
import os
import re
import sqlite3
import json
from datetime import datetime
from database import init_db
from payroll_engine import calculate_monthly_payroll

def run_import():
    init_db()
    path = r"C:\Users\MM COMPUTERS\Downloads\august.xls"
    if not os.path.exists(path):
        print(f"Error: File not found at {path}")
        return

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    # Extract all <td>...</td>
    td_matches = re.findall(r"<td[^>]*>(.*?)</td>", text, re.DOTALL | re.IGNORECASE)
    clean_cells = [re.sub(r"<[^>]+>", "", c).strip().replace("&nbsp;", " ") for c in td_matches]

    header_idx = -1
    for i in range(len(clean_cells) - 10):
        if clean_cells[i] == "No." and clean_cells[i+1] == "Person ID" and clean_cells[i+2] == "Name":
            header_idx = i
            break

    if header_idx == -1:
        print("Header row not found in file.")
        return

    data_cells = clean_cells[header_idx + 20:]
    COLS_COUNT = 20

    conn = sqlite3.connect("payroll_attendance.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE company_settings SET company_name = 'Multani Traders', address = 'Multani Shop' WHERE id = 1")

    employees_map = {}
    raw_punches_count = 0
    daily_records_count = 0

    for idx in range(0, len(data_cells), COLS_COUNT):
        chunk = data_cells[idx:idx+COLS_COUNT]
        if len(chunk) < COLS_COUNT:
            break
        
        no = chunk[0]
        pid = chunk[1].strip()
        name = chunk[2].strip()
        dept = chunk[3].strip() or "Multani Shop"
        pos = chunk[4].strip() or "Staff"
        dt = chunk[6].strip()
        cin = chunk[9].strip()
        cout = chunk[10].strip()
        late_m = int(chunk[14].strip()) if chunk[14].strip().isdigit() else 0
        ot_m = int(chunk[12].strip()) if chunk[12].strip().isdigit() else 0
        raw_punches = chunk[19].strip()

        if not (pid and name and len(dt) == 10 and dt.startswith("2026-")):
            continue

        # Insert or update employee
        if pid not in employees_map:
            cursor.execute("""
                INSERT INTO employees (biometric_id, name, department, designation, shift_id, basic_salary, housing_allowance, transport_allowance, is_active)
                VALUES (?, ?, ?, ?, 1, 40000.0, 5000.0, 3000.0, 1)
                ON CONFLICT(biometric_id) DO UPDATE SET name = excluded.name, department = excluded.department
            """, (pid, name, dept, pos))
            cursor.execute("SELECT id FROM employees WHERE biometric_id = ?", (pid,))
            emp_id = cursor.fetchone()[0]
            employees_map[pid] = emp_id

        emp_id = employees_map[pid]

        # Extract punch timestamps
        punch_times_list = []
        if raw_punches and raw_punches != "-":
            times = [t.strip() for t in raw_punches.split() if ":" in t]
            for t in times:
                p_full = f"{dt} {t}"
                cursor.execute("""
                    INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source)
                    VALUES (?, ?, 'Auto', 'august_xls_import')
                """, (pid, p_full))
                punch_times_list.append(t)
                raw_punches_count += 1
        elif cin != "-" or cout != "-":
            if cin != "-":
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'august_xls_import')", (pid, f"{dt} {cin}"))
                punch_times_list.append(cin)
                raw_punches_count += 1
            if cout != "-" and cout != cin:
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'august_xls_import')", (pid, f"{dt} {cout}"))
                punch_times_list.append(cout)
                raw_punches_count += 1

        # Calculate duration and status
        total_hours = 0.0
        first_in_val = cin if cin != "-" else (punch_times_list[0] if punch_times_list else None)
        last_out_val = cout if cout != "-" else (punch_times_list[-1] if len(punch_times_list) > 1 else None)

        if first_in_val and last_out_val and first_in_val != last_out_val:
            try:
                t1 = datetime.strptime(f"{dt} {first_in_val}", "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(f"{dt} {last_out_val}", "%Y-%m-%d %H:%M:%S")
                total_hours = round((t2 - t1).total_seconds() / 3600.0, 2)
            except Exception:
                pass

        ot_hours = round(ot_m / 60.0, 2)
        weekday = datetime.strptime(dt, "%Y-%m-%d").weekday()

        if punch_times_list or cin != "-" or cout != "-":
            if late_m > 15:
                status_str = "Late"
            elif total_hours > 0 and total_hours < 4.0:
                status_str = "Half Day"
            else:
                status_str = "Present"
        else:
            if weekday == 6: # Sunday
                status_str = "Weekly Off"
            else:
                status_str = "Absent"

        cursor.execute("""
            INSERT OR REPLACE INTO daily_attendance (
                employee_id, date, first_in, last_out, all_punches, total_hours, regular_hours, 
                overtime_hours, late_minutes, status, is_manual_override, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        """, (emp_id, dt, first_in_val, last_out_val, json.dumps(punch_times_list), total_hours, min(total_hours, 8.0), ot_hours, late_m, status_str))
        daily_records_count += 1

    conn.commit()
    conn.close()

    print(f"Import Complete!")
    print(f"Imported {len(employees_map)} Employees, {raw_punches_count} Raw Punches, and {daily_records_count} Daily Attendance Records for August 2026!")

    # Run payroll calculation for August 2026
    pay_res = calculate_monthly_payroll("2026-08")
    print("August 2026 Payroll Summary:", pay_res)

if __name__ == "__main__":
    run_import()
