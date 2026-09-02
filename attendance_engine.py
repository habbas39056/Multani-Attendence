"""
Attendance Processing Engine for Multani Attendance & Payroll System
Calculates daily in/out times, late minutes, early departures, overtime hours, and attendance statuses.
"""
from datetime import datetime, date, timedelta, time
import json
from database import get_db_connection

def parse_time_str(t_str):
    """Parses 'HH:MM:SS' or 'HH:MM' string to datetime.time object."""
    if not t_str:
        return None
    try:
        parts = t_str.strip().split(':')
        if len(parts) == 3:
            return time(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None

def time_diff_minutes(t1, t2):
    """Calculates minutes between t1 and t2 on the same day (t2 - t1 in minutes)."""
    if not t1 or not t2:
        return 0
    dt1 = datetime(2000, 1, 1, t1.hour, t1.minute, t1.second)
    dt2 = datetime(2000, 1, 1, t2.hour, t2.minute, t2.second)
    return int((dt2 - dt1).total_seconds() / 60)

def process_attendance_for_date(target_date_str: str):
    """
    Processes all employee attendance for a specific date (YYYY-MM-DD).
    Target date format: 'YYYY-MM-DD'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        conn.close()
        return {"error": "Invalid date format. Expected YYYY-MM-DD"}

    day_name = target_dt.strftime("%a") # e.g. 'Mon', 'Sun'

    # Get active employees
    cursor.execute("""
        SELECT e.*, s.name as shift_name, s.start_time, s.end_time, 
               s.grace_minutes, s.half_day_hours, s.full_day_hours, 
               s.min_overtime_minutes, s.work_days
        FROM employees e
        LEFT JOIN shifts s ON e.shift_id = s.id
        WHERE e.is_active = 1
    """)
    employees = cursor.fetchall()

    # Get approved leaves for this date
    cursor.execute("""
        SELECT employee_id, leave_type, reason 
        FROM leaves 
        WHERE ? BETWEEN start_date AND end_date AND status = 'Approved'
    """, (target_date_str,))
    leaves_by_emp = {row["employee_id"]: row for row in cursor.fetchall()}

    processed_count = 0

    for emp in employees:
        emp_id = emp["id"]
        bio_id = emp["biometric_id"]

        # Check if manual override exists and is locked
        cursor.execute("SELECT is_manual_override FROM daily_attendance WHERE employee_id = ? AND date = ?", (emp_id, target_date_str))
        existing = cursor.fetchone()
        if existing and existing["is_manual_override"] == 1:
            continue # Respect manual supervisor override

        # Shift timings (Uses employee custom schedule if configured, otherwise shift default)
        shift_start = parse_time_str(emp["start_time"] or "09:00")
        shift_end = parse_time_str(emp["end_time"] or "18:00")
        grace_mins = emp["grace_minutes"] if emp["grace_minutes"] is not None else 15
        full_day_hrs = emp["work_hours"] if "work_hours" in emp.keys() and emp["work_hours"] is not None else 8.0
        half_day_hrs = round(full_day_hrs / 2.0, 1)
        min_ot_mins = emp["min_overtime_minutes"] if "min_overtime_minutes" in emp.keys() and emp["min_overtime_minutes"] is not None else 30
        work_days = (emp["work_days"] or "Mon,Tue,Wed,Thu,Fri,Sat").split(",")

        is_work_day = day_name in [d.strip() for d in work_days]

        # Fetch all raw punches for this employee on this date
        cursor.execute("""
            SELECT punch_time, punch_type 
            FROM raw_attendance_logs 
            WHERE biometric_id = ? AND DATE(punch_time) = ?
            ORDER BY punch_time ASC
        """, (str(bio_id), target_date_str))
        punches = cursor.fetchall()

        # Check leave status
        on_leave = leaves_by_emp.get(emp_id)

        if not punches:
            # Zero punches on this day
            if on_leave:
                status = f"Leave ({on_leave['leave_type']})"
                notes = on_leave["reason"] or "Approved Leave"
            elif not is_work_day:
                status = "Weekly Off"
                notes = "Weekend / Scheduled Off"
            else:
                status = "Absent"
                notes = "No punch recorded"

            cursor.execute("""
                INSERT OR REPLACE INTO daily_attendance 
                (employee_id, date, first_in, last_out, all_punches, total_hours, regular_hours, overtime_hours, late_minutes, early_leave_minutes, status, is_manual_override, notes, updated_at)
                VALUES (?, ?, NULL, NULL, '[]', 0.0, 0.0, 0.0, 0, 0, ?, 0, ?, CURRENT_TIMESTAMP)
            """, (emp_id, target_date_str, status, notes))
            processed_count += 1
            continue

        # Punches exist!
        punch_times = []
        for p in punches:
            pt_str = str(p["punch_time"])
            # Extract time part
            if " " in pt_str:
                punch_times.append(pt_str.split(" ")[1])
            elif "T" in pt_str:
                punch_times.append(pt_str.split("T")[1].split(".")[0])
            else:
                punch_times.append(pt_str)

        first_in_str = punch_times[0]
        last_out_str = punch_times[-1] if len(punch_times) > 1 else punch_times[0]

        first_in_time = parse_time_str(first_in_str)
        last_out_time = parse_time_str(last_out_str)

        # Calculate total duration
        if len(punch_times) == 1:
            total_duration_hours = 0.0
            last_out_str = None
            notes = "Single punch only (Missing Check-Out)"
        else:
            dt_in = datetime.combine(target_dt, first_in_time)
            dt_out = datetime.combine(target_dt, last_out_time)
            if dt_out < dt_in:
                # Overnight shift support
                dt_out += timedelta(days=1)
            duration_secs = (dt_out - dt_in).total_seconds()
            total_duration_hours = round(duration_secs / 3600.0, 2)
            notes = ""

        # Late In calculation
        late_minutes = 0
        if first_in_time and shift_start:
            mins_from_start = time_diff_minutes(shift_start, first_in_time)
            if mins_from_start > grace_mins:
                late_minutes = mins_from_start

        # Early Out calculation
        early_leave_minutes = 0
        if last_out_time and shift_end and len(punch_times) > 1:
            mins_before_end = time_diff_minutes(last_out_time, shift_end)
            if mins_before_end > 0:
                early_leave_minutes = mins_before_end

        # Overtime calculation
        overtime_hours = 0.0
        if last_out_time and shift_end and len(punch_times) > 1:
            mins_after_end = time_diff_minutes(shift_end, last_out_time)
            if mins_after_end >= min_ot_mins:
                overtime_hours = round(mins_after_end / 60.0, 2)
        elif total_duration_hours > full_day_hrs:
            overtime_hours = round(total_duration_hours - full_day_hrs, 2)

        # Regular hours
        regular_hours = min(total_duration_hours, full_day_hrs)

        # Determine status
        if on_leave:
            status = f"Leave ({on_leave['leave_type']})"
        elif not is_work_day:
            status = "Holiday Present" if total_duration_hours > 0 else "Weekly Off"
        elif total_duration_hours > 0 and total_duration_hours < half_day_hrs:
            status = "Half Day"
        elif late_minutes > 0:
            status = "Late"
        elif early_leave_minutes > 15:
            status = "Early Leave"
        else:
            status = "Present"

        all_punches_json = json.dumps(punch_times)

        cursor.execute("""
            INSERT OR REPLACE INTO daily_attendance 
            (employee_id, date, first_in, last_out, all_punches, total_hours, regular_hours, overtime_hours, late_minutes, early_leave_minutes, status, is_manual_override, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
        """, (emp_id, target_date_str, first_in_str, last_out_str, all_punches_json, total_duration_hours, regular_hours, overtime_hours, late_minutes, early_leave_minutes, status, notes))

        processed_count += 1

    conn.commit()
    conn.close()
    return {"status": "success", "processed_employees": processed_count, "date": target_date_str}

def process_attendance_range(start_date_str: str, end_date_str: str):
    """Processes attendance for a date range."""
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    curr = start_dt
    days_processed = 0
    while curr <= end_dt:
        process_attendance_for_date(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
        days_processed += 1

    return {"status": "success", "days_processed": days_processed}
