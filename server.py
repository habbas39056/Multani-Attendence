"""
FastAPI Server & REST API for Multani Biometric Attendance & Payroll System
"""
import os
import json
from datetime import datetime, date
from typing import Optional, List
from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from database import init_db, get_db_connection
from zk_sync import sync_manager
from attendance_engine import process_attendance_for_date, process_attendance_range
from payroll_engine import calculate_monthly_payroll, get_payslip_details

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    sync_manager.start_auto_sync_background()
    yield
    # Shutdown
    sync_manager.stop_auto_sync()

app = FastAPI(title="Multani Biometric Attendance & Payroll System", lifespan=lifespan)

# -------------------------------------------------------------
# ADMS / iClock Webhook Endpoints (For Biometric Devices Pushing Data)
# -------------------------------------------------------------
@app.get("/iclock/cdata")
async def iclock_cdata_get(request: Request):
    """
    Standard handshake and initialization endpoint for ZKTeco / ADMS firmware.
    """
    params = dict(request.query_params)
    sn = params.get("SN", "Unknown")
    sync_manager.add_feed_entry(f"ADMS Device Handshake received from SN: {sn}", "info", f"ADMS:{sn}")
    # Return standard OK response expected by ADMS terminals
    return Response(content="OK", media_type="text/plain")

@app.post("/iclock/cdata")
async def iclock_cdata_post(request: Request):
    """
    Receives real-time attendance punch pushes directly from biometric fingerprint machine.
    """
    params = dict(request.query_params)
    sn = params.get("SN", "Biometric Terminal")
    body = (await request.body()).decode("utf-8", errors="ignore")
    
    # ADMS payload lines format: USER_PIN \t DATETIME \t VERIFY_MODE \t INOUT_STATE ...
    lines = body.strip().split("\n")
    processed_count = 0

    for line in lines:
        parts = line.strip().split("\t")
        if len(parts) >= 2:
            bio_id = parts[0].strip()
            punch_time_str = parts[1].strip()
            # Punch state: 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
            state_code = parts[3].strip() if len(parts) > 3 else "0"
            state_map = {"0": "Check-In", "1": "Check-Out", "2": "Break-Out", "3": "Break-In"}
            p_type = state_map.get(state_code, "Auto")

            if bio_id and punch_time_str:
                sync_manager.record_punch(bio_id, punch_time_str, p_type, None, "adms_push")
                processed_count += 1

    return Response(content=f"OK: {processed_count}", media_type="text/plain")

@app.get("/iclock/getrequest")
async def iclock_getrequest(request: Request):
    return Response(content="OK", media_type="text/plain")

# -------------------------------------------------------------
# Dashboard Statistics API
# -------------------------------------------------------------
@app.get("/api/dashboard/stats")
def get_dashboard_stats(target_date: Optional[str] = None):
    if not target_date:
        target_date = date.today().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Total Active Employees
    cursor.execute("SELECT COUNT(*) as cnt FROM employees WHERE is_active = 1")
    total_employees = cursor.fetchone()["cnt"]

    # Today's Attendance breakdown
    cursor.execute("""
        SELECT status, COUNT(*) as cnt 
        FROM daily_attendance 
        WHERE date = ? 
        GROUP BY status
    """, (target_date,))
    status_rows = cursor.fetchall()
    
    status_counts = {
        "present": 0,
        "late": 0,
        "absent": 0,
        "half_day": 0,
        "leave": 0,
        "early_leave": 0,
        "off": 0
    }

    for row in status_rows:
        st = row["status"] or ""
        cnt = row["cnt"]
        if st in ["Present", "Holiday Present"]:
            status_counts["present"] += cnt
        elif st == "Late":
            status_counts["late"] += cnt
            status_counts["present"] += cnt # Late is also present
        elif st == "Early Leave":
            status_counts["early_leave"] += cnt
            status_counts["present"] += cnt
        elif st == "Half Day":
            status_counts["half_day"] += cnt
        elif "Leave" in st:
            status_counts["leave"] += cnt
        elif st in ["Weekly Off", "Holiday"]:
            status_counts["off"] += cnt
        elif st == "Absent":
            status_counts["absent"] += cnt

    # Biometric Devices status
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN last_status LIKE 'Online%' OR last_status LIKE 'Ready%' THEN 1 ELSE 0 END) as online_cnt FROM biometric_devices WHERE is_active = 1")
    dev_stats = cursor.fetchone()
    total_devices = dev_stats["total"] or 0
    online_devices = dev_stats["online_cnt"] or 0

    # Current month payroll total
    curr_month = target_date[:7]
    cursor.execute("SELECT total_gross_salary, total_net_salary, status FROM payroll_runs WHERE month = ?", (curr_month,))
    pr_row = cursor.fetchone()
    payroll_summary = {
        "month": curr_month,
        "gross": pr_row["total_gross_salary"] if pr_row else 0.0,
        "net": pr_row["total_net_salary"] if pr_row else 0.0,
        "status": pr_row["status"] if pr_row else "Not Generated"
    }

    # Recent 10 raw punches
    cursor.execute("""
        SELECT r.*, e.name as employee_name, e.department 
        FROM raw_attendance_logs r
        LEFT JOIN employees e ON r.biometric_id = e.biometric_id
        ORDER BY r.punch_time DESC 
        LIMIT 10
    """)
    recent_punches = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "date": target_date,
        "total_employees": total_employees,
        "status_counts": status_counts,
        "devices": {
            "total": total_devices,
            "online": online_devices
        },
        "payroll": payroll_summary,
        "recent_punches": recent_punches,
        "sync_feed": sync_manager.sync_logs_feed[:15]
    }

# -------------------------------------------------------------
# Biometric Devices API
# -------------------------------------------------------------
@app.get("/api/devices")
def list_devices():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM biometric_devices ORDER BY id ASC")
    devices = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return devices

class DeviceModel(BaseModel):
    name: str
    ip_address: str
    port: int = 8080
    protocol: str = "auto"
    username: Optional[str] = "admin"
    password: Optional[str] = ""
    device_model: str = "Hikvision / Biometric Terminal"
    auto_sync: int = 1
    sync_interval_sec: int = 60

@app.post("/api/devices")
def create_device(dev: DeviceModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO biometric_devices (name, ip_address, port, protocol, username, password, device_model, auto_sync, sync_interval_sec, last_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Configured')
    """, (dev.name, dev.ip_address, dev.port, dev.protocol, dev.username, dev.password, dev.device_model, dev.auto_sync, dev.sync_interval_sec))
    conn.commit()
    dev_id = cursor.lastrowid
    conn.close()
    sync_manager.add_feed_entry(f"Added new biometric device: {dev.name} ({dev.ip_address}:{dev.port})", "info")
    return {"id": dev_id, "status": "created"}

@app.put("/api/devices/{device_id}")
def update_device(device_id: int, dev: DeviceModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE biometric_devices 
        SET name = ?, ip_address = ?, port = ?, protocol = ?, username = ?, password = ?, device_model = ?, auto_sync = ?, sync_interval_sec = ?
        WHERE id = ?
    """, (dev.name, dev.ip_address, dev.port, dev.protocol, dev.username, dev.password, dev.device_model, dev.auto_sync, dev.sync_interval_sec, device_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM biometric_devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@app.post("/api/devices/{device_id}/test")
def test_device_connection(device_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ip_address, port, name FROM biometric_devices WHERE id = ?", (device_id,))
    dev = cursor.fetchone()
    conn.close()

    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")

    res = sync_manager.test_connection(dev["ip_address"], dev["port"])
    return res

@app.post("/api/devices/{device_id}/sync")
def trigger_device_sync(device_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM biometric_devices WHERE id = ?", (device_id,))
    dev = cursor.fetchone()
    conn.close()

    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")

    # If it's a Hikvision machine with credentials, fetch logs with range
    ip = dev["ip_address"]
    port = dev["port"]
    username = dev["username"] if "username" in dev.keys() and dev["username"] else "admin"
    password = dev["password"] if "password" in dev.keys() and dev["password"] else ""

    if password:
        return sync_manager.fetch_hikvision_punches(ip, port, username, password, start_date, end_date)
    else:
        return sync_manager.sync_device(device_id)

@app.get("/api/sync-feed")
def get_sync_feed():
    return {"feed": sync_manager.sync_logs_feed}

# -------------------------------------------------------------
# Employees API
# -------------------------------------------------------------
@app.get("/api/employees")
def list_employees():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, s.name as shift_name, s.start_time, s.end_time
        FROM employees e
        LEFT JOIN shifts s ON e.shift_id = s.id
        WHERE e.is_active = 1
        ORDER BY CAST(e.biometric_id AS INTEGER) ASC, e.id ASC
    """)
    employees = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return employees

class EmployeeModel(BaseModel):
    biometric_id: str
    name: str
    department: str = "General"
    designation: str = "Staff"
    phone: str = ""
    email: str = ""
    joining_date: str = ""
    shift_id: Optional[int] = 1
    salary_type: str = "Monthly"
    basic_salary: float = 30000.0
    housing_allowance: float = 0.0
    transport_allowance: float = 0.0
    medical_allowance: float = 0.0
    other_allowance: float = 0.0
    tax_deduction_rate: float = 0.0
    start_time: Optional[str] = "09:00"
    end_time: Optional[str] = "18:00"
    grace_minutes: Optional[int] = 15
    work_hours: Optional[float] = 8.0
    work_days: Optional[str] = "Mon,Tue,Wed,Thu,Fri,Sat"
    off_day: Optional[str] = "Sun"

@app.post("/api/employees")
def create_employee(emp: EmployeeModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO employees (
                biometric_id, name, department, designation, phone, email, 
                joining_date, shift_id, salary_type, basic_salary, housing_allowance, 
                transport_allowance, medical_allowance, other_allowance, tax_deduction_rate,
                start_time, end_time, grace_minutes, work_hours, work_days, off_day
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            emp.biometric_id, emp.name, emp.department, emp.designation, emp.phone, emp.email,
            emp.joining_date, emp.shift_id or 1, emp.salary_type, emp.basic_salary, emp.housing_allowance,
            emp.transport_allowance, emp.medical_allowance, emp.other_allowance, emp.tax_deduction_rate,
            emp.start_time or "09:00", emp.end_time or "18:00", emp.grace_minutes or 15,
            emp.work_hours or 8.0, emp.work_days or "Mon,Tue,Wed,Thu,Fri,Sat", emp.off_day or "Sun"
        ))
        conn.commit()
        emp_id = cursor.lastrowid
        conn.close()
        return {"id": emp_id, "status": "created"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error creating employee (Biometric ID may already exist): {str(e)}")

@app.put("/api/employees/{employee_id}")
def update_employee(employee_id: int, emp: EmployeeModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE employees SET
            biometric_id = ?, name = ?, department = ?, designation = ?, phone = ?, email = ?,
            joining_date = ?, shift_id = ?, salary_type = ?, basic_salary = ?, housing_allowance = ?,
            transport_allowance = ?, medical_allowance = ?, other_allowance = ?, tax_deduction_rate = ?,
            start_time = ?, end_time = ?, grace_minutes = ?, work_hours = ?, work_days = ?, off_day = ?
        WHERE id = ?
    """, (
        emp.biometric_id, emp.name, emp.department, emp.designation, emp.phone, emp.email,
        emp.joining_date, emp.shift_id or 1, emp.salary_type, emp.basic_salary, emp.housing_allowance,
        emp.transport_allowance, emp.medical_allowance, emp.other_allowance, emp.tax_deduction_rate,
        emp.start_time or "09:00", emp.end_time or "18:00", emp.grace_minutes or 15,
        emp.work_hours or 8.0, emp.work_days or "Mon,Tue,Wed,Thu,Fri,Sat", emp.off_day or "Sun",
        employee_id
    ))
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/api/employees/{employee_id}")
def delete_employee(employee_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET is_active = 0 WHERE id = ?", (employee_id,))
    conn.commit()
    conn.close()
    return {"status": "deactivated"}

# -------------------------------------------------------------
# Shifts API
# -------------------------------------------------------------
@app.get("/api/shifts")
def list_shifts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shifts WHERE is_active = 1 ORDER BY id ASC")
    shifts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return shifts

class ShiftModel(BaseModel):
    name: str
    start_time: str = "09:00"
    end_time: str = "18:00"
    grace_minutes: int = 15
    half_day_hours: float = 4.0
    full_day_hours: float = 8.0
    min_overtime_minutes: int = 30
    work_days: str = "Mon,Tue,Wed,Thu,Fri,Sat"

@app.post("/api/shifts")
def create_shift(shift: ShiftModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO shifts (name, start_time, end_time, grace_minutes, half_day_hours, full_day_hours, min_overtime_minutes, work_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (shift.name, shift.start_time, shift.end_time, shift.grace_minutes, shift.half_day_hours, shift.full_day_hours, shift.min_overtime_minutes, shift.work_days))
    conn.commit()
    shift_id = cursor.lastrowid
    conn.close()
    return {"id": shift_id, "status": "created"}

# -------------------------------------------------------------
# Attendance API (Daily & Monthly Matrix)
# -------------------------------------------------------------
@app.get("/api/attendance/daily")
def get_daily_attendance(date_str: Optional[str] = Query(None, alias="date")):
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")

    # Ensure processed
    process_attendance_for_date(date_str)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.*, e.name as employee_name, e.biometric_id, e.department, e.designation,
               s.name as shift_name, s.start_time as shift_start, s.end_time as shift_end
        FROM daily_attendance d
        JOIN employees e ON d.employee_id = e.id
        LEFT JOIN shifts s ON e.shift_id = s.id
        WHERE d.date = ?
        ORDER BY CAST(e.biometric_id AS INTEGER) ASC
    """, (date_str,))
    records = []
    for r in cursor.fetchall():
        item = dict(r)
        if item.get("all_punches"):
            try:
                item["punches_list"] = json.loads(item["all_punches"])
            except Exception:
                item["punches_list"] = []
        records.append(item)

    conn.close()
    return {"date": date_str, "records": records}

@app.post("/api/attendance/recalculate")
def recalculate_attendance(date_str: str = Query(..., alias="date")):
    return process_attendance_for_date(date_str)

class ManualAttendanceModel(BaseModel):
    employee_id: int
    date: str
    first_in: Optional[str] = None
    last_out: Optional[str] = None
    status: str
    total_hours: Optional[float] = None
    overtime_hours: Optional[float] = 0.0
    notes: Optional[str] = ""

@app.post("/api/attendance/manual")
def manual_attendance_override(data: ManualAttendanceModel):
    conn = get_db_connection()
    cursor = conn.cursor()

    total_hrs = data.total_hours
    if total_hrs is None:
        if data.status in ["Present", "Holiday Present"]:
            total_hrs = 8.0
        elif data.status == "Half Day":
            total_hrs = 4.0
        elif data.status == "Absent":
            total_hrs = 0.0
        else:
            total_hrs = 8.0 if data.first_in and data.last_out else 0.0

    cursor.execute("""
        INSERT INTO daily_attendance (
            employee_id, date, first_in, last_out, total_hours, regular_hours, overtime_hours, status, is_manual_override, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(employee_id, date) DO UPDATE SET
            first_in = excluded.first_in,
            last_out = excluded.last_out,
            total_hours = excluded.total_hours,
            regular_hours = excluded.regular_hours,
            overtime_hours = excluded.overtime_hours,
            status = excluded.status,
            is_manual_override = 1,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
    """, (
        data.employee_id, data.date, data.first_in, data.last_out,
        total_hrs, total_hrs, data.overtime_hours or 0.0, data.status, data.notes
    ))
    conn.commit()
    conn.close()
    return {"status": "saved", "message": f"Attendance successfully marked as {data.status} for {data.date}"}

@app.get("/api/attendance/monthly")
def get_monthly_attendance_matrix(month: str = Query(..., description="YYYY-MM")):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT e.id, e.name, e.biometric_id, e.department, 
               d.date, d.status, d.total_hours, d.overtime_hours, d.late_minutes
        FROM employees e
        LEFT JOIN daily_attendance d ON e.id = d.employee_id AND d.date LIKE ?
        WHERE e.is_active = 1
        ORDER BY CAST(e.biometric_id AS INTEGER) ASC, d.date ASC
    """, (f"{month}%",))
    rows = cursor.fetchall()

    # Aggregate by employee
    emp_map = {}
    for r in rows:
        eid = r["id"]
        if eid not in emp_map:
            emp_map[eid] = {
                "id": eid,
                "name": r["name"],
                "biometric_id": r["biometric_id"],
                "department": r["department"],
                "days": {},
                "summary": {"present": 0, "late": 0, "absent": 0, "leave": 0, "half_day": 0, "ot_hours": 0.0}
            }
        
        if r["date"]:
            day_num = r["date"].split("-")[2] # '01', '02', etc.
            st = r["status"] or "Absent"
            ot = float(r["overtime_hours"] or 0.0)
            emp_map[eid]["days"][day_num] = {
                "status": st,
                "hours": r["total_hours"],
                "ot": ot,
                "late": r["late_minutes"]
            }
            if st in ["Present", "Holiday Present"]:
                emp_map[eid]["summary"]["present"] += 1
            elif st == "Late":
                emp_map[eid]["summary"]["present"] += 1
                emp_map[eid]["summary"]["late"] += 1
            elif st == "Half Day":
                emp_map[eid]["summary"]["half_day"] += 1
            elif "Leave" in st:
                emp_map[eid]["summary"]["leave"] += 1
            elif st == "Absent":
                emp_map[eid]["summary"]["absent"] += 1
            emp_map[eid]["summary"]["ot_hours"] += ot

    conn.close()
    return {"month": month, "matrix": list(emp_map.values())}

# -------------------------------------------------------------
# Leaves API
# -------------------------------------------------------------
@app.get("/api/leaves")
def list_leaves():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, e.name as employee_name, e.biometric_id, e.department
        FROM leaves l
        JOIN employees e ON l.employee_id = e.id
        ORDER BY l.start_date DESC
    """)
    leaves = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return leaves

class LeaveModel(BaseModel):
    employee_id: int
    leave_type: str = "Casual"
    start_date: str
    end_date: str
    days_count: float = 1.0
    reason: str = ""

@app.post("/api/leaves")
def create_leave(data: LeaveModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO leaves (employee_id, leave_type, start_date, end_date, days_count, reason, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Approved')
    """, (data.employee_id, data.leave_type, data.start_date, data.end_date, data.days_count, data.reason))
    conn.commit()
    conn.close()

    # Reprocess dates for attendance
    process_attendance_range(data.start_date, data.end_date)
    return {"status": "approved"}

@app.delete("/api/leaves/{leave_id}")
def delete_leave(leave_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT start_date, end_date FROM leaves WHERE id = ?", (leave_id,))
    l = cursor.fetchone()
    if l:
        cursor.execute("DELETE FROM leaves WHERE id = ?", (leave_id,))
        conn.commit()
        process_attendance_range(l["start_date"], l["end_date"])
    conn.close()
    return {"status": "deleted"}

# -------------------------------------------------------------
# Payroll API & Payslips
# -------------------------------------------------------------
@app.post("/api/payroll/generate")
def generate_payroll(month: str = Query(..., description="YYYY-MM")):
    return calculate_monthly_payroll(month)

@app.get("/api/payroll/runs")
def list_payroll_runs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payroll_runs ORDER BY month DESC")
    runs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return runs

@app.get("/api/payroll/payslips")
def list_payslips(month: str = Query(..., description="YYYY-MM")):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, e.name as employee_name, e.biometric_id, e.department, e.designation, e.salary_type
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.month = ?
        ORDER BY CAST(e.biometric_id AS INTEGER) ASC
    """, (month,))
    payslips = []
    for r in cursor.fetchall():
        item = dict(r)
        if item.get("breakdown_json"):
            try:
                item["breakdown"] = json.loads(item["breakdown_json"])
            except Exception:
                item["breakdown"] = {}
        payslips.append(item)
    conn.close()
    return payslips

@app.get("/api/payroll/payslip/{payslip_id}")
def get_single_payslip(payslip_id: int):
    details = get_payslip_details(payslip_id)
    if not details:
        raise HTTPException(status_code=404, detail="Payslip not found")
    return details

class PayslipUpdateModel(BaseModel):
    bonus: Optional[float] = 0.0
    other_deduction: Optional[float] = 0.0
    payment_status: Optional[str] = "Unpaid"
    payment_method: Optional[str] = "Cash"
    remarks: Optional[str] = ""

@app.put("/api/payroll/payslip/{payslip_id}")
def update_single_payslip(payslip_id: int, data: PayslipUpdateModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payslips WHERE id = ?", (payslip_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Payslip not found")

    basic = row["basic_salary"]
    allowances = row["housing_allowance"] + row["transport_allowance"] + row["medical_allowance"] + row["other_allowance"]
    ot_pay = row["overtime_pay"]
    bonus = data.bonus if data.bonus is not None else row["bonus"]
    gross = basic + allowances + ot_pay + bonus

    absent_ded = row["absent_deduction"]
    late_ded = row["late_deduction"]
    tax_ded = row["tax_deduction"]
    other_ded = data.other_deduction if data.other_deduction is not None else row["other_deduction"]
    total_ded = absent_ded + late_ded + tax_ded + other_ded

    net = max(0.0, round(gross - total_ded, 2))

    cursor.execute("""
        UPDATE payslips SET
            bonus = ?, other_deduction = ?, gross_salary = ?, total_deductions = ?,
            net_salary = ?, payment_status = ?, payment_method = ?, remarks = ?
        WHERE id = ?
    """, (bonus, other_ded, gross, total_ded, net, data.payment_status, data.payment_method, data.remarks, payslip_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "net_salary": net}

@app.post("/api/payroll/payslip/{payslip_id}/pay")
def mark_payslip_paid(payslip_id: int, method: str = Query("Cash")):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_date = date.today().strftime("%Y-%m-%d")
    cursor.execute("""
        UPDATE payslips 
        SET payment_status = 'Paid', payment_date = ?, payment_method = ?
        WHERE id = ?
    """, (now_date, method, payslip_id))
    conn.commit()
    conn.close()
    return {"status": "paid", "date": now_date}

# -------------------------------------------------------------
# Simulation & CSV Import Endpoints
# -------------------------------------------------------------
class PunchSimulatorModel(BaseModel):
    biometric_id: str
    punch_time: str
    punch_type: str = "Auto"

@app.post("/api/simulate-punch")
def simulate_single_punch(data: PunchSimulatorModel):
    res = sync_manager.record_punch(data.biometric_id, data.punch_time, data.punch_type, None, "simulator")
    return {"status": "recorded" if res else "duplicate_ignored"}

@app.post("/api/import-csv")
async def import_csv_punches(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8", errors="ignore")
    res = sync_manager.import_csv_punches(content)
    return res

# -------------------------------------------------------------
# Company Settings API
# -------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM company_settings LIMIT 1")
    settings = cursor.fetchone()
    conn.close()
    return dict(settings) if settings else {}

class SettingsModel(BaseModel):
    company_name: str = "Multani Enterprises"
    currency: str = "PKR"
    working_days_per_month: int = 26
    overtime_multiplier: float = 1.5
    late_grace_minutes: int = 15
    late_deduction_type: Optional[str] = "percentage"
    late_penalty_percent: Optional[float] = 5.0
    late_fixed_amount: Optional[float] = 100.0
    late_penalty_days: Optional[float] = 1.0
    late_threshold_count: Optional[int] = 3
    auto_sync_interval_seconds: int = 60
    address: str = ""
    phone: str = ""
    email: str = ""

@app.post("/api/settings")
def save_settings(s: SettingsModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_settings SET
            company_name = ?, currency = ?, working_days_per_month = ?, overtime_multiplier = ?,
            late_grace_minutes = ?, late_deduction_type = ?, late_penalty_percent = ?, late_fixed_amount = ?,
            late_penalty_days = ?, late_threshold_count = ?,
            auto_sync_interval_seconds = ?, address = ?, phone = ?, email = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (
        s.company_name, s.currency, s.working_days_per_month, s.overtime_multiplier,
        s.late_grace_minutes, s.late_deduction_type or "percentage", s.late_penalty_percent or 5.0, s.late_fixed_amount or 100.0,
        s.late_penalty_days or 1.0, s.late_threshold_count or 3,
        s.auto_sync_interval_seconds, s.address, s.phone, s.email
    ))
    conn.commit()
    conn.close()
    return {"status": "saved"}

# -------------------------------------------------------------
# Shifts API
# -------------------------------------------------------------
@app.get("/api/shifts")
def get_shifts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shifts ORDER BY id ASC")
    shifts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return shifts

class ShiftUpdateModel(BaseModel):
    name: Optional[str] = "Standard Shift"
    start_time: str = "09:00"
    end_time: str = "18:00"
    grace_minutes: int = 15
    full_day_hours: float = 8.0
    half_day_hours: float = 4.0

@app.put("/api/shifts/{shift_id}")
def update_shift(shift_id: int, s: ShiftUpdateModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE shifts SET
            name = ?, start_time = ?, end_time = ?, grace_minutes = ?,
            full_day_hours = ?, half_day_hours = ?
        WHERE id = ?
    """, (s.name, s.start_time, s.end_time, s.grace_minutes, s.full_day_hours, s.half_day_hours, shift_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}

# -------------------------------------------------------------
# Supabase Cloud Database API
# -------------------------------------------------------------
from supabase_manager import supabase_manager

@app.get("/api/supabase/status")
def get_supabase_status():
    return supabase_manager.get_status()

class SupabaseConfigModel(BaseModel):
    url: str
    key: str

@app.post("/api/supabase/config")
def save_supabase_config(cfg: SupabaseConfigModel):
    return supabase_manager.save_config(cfg.url, cfg.key)

@app.post("/api/supabase/test")
def test_supabase(cfg: Optional[SupabaseConfigModel] = None):
    url = cfg.url if cfg else None
    key = cfg.key if cfg else None
    return supabase_manager.test_connection(url, key)

@app.post("/api/supabase/push")
def push_to_supabase():
    return supabase_manager.sync_local_to_supabase()

# -------------------------------------------------------------
# Static Frontend Serving
# -------------------------------------------------------------
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Multani Biometric Attendance & Payroll System Backend Ready.</h1>"

if __name__ == "__main__":
    import uvicorn
    print("=========================================================")
    print("  Multani Payroll & Biometric Attendance System")
    print("  Web Server active on http://127.0.0.1:8000")
    print("=========================================================")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
