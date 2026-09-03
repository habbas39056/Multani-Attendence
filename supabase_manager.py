"""
Supabase Cloud Database Integration Manager for Multani Attendance & Payroll System
Handles cloud synchronization, connection verification, and automatic migration.
"""
import os
import json
import sqlite3
from typing import Dict, Any, Optional
import requests
from database import get_db_connection

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "supabase_config.json")

class SupabaseManager:
    def __init__(self):
        self.url = ""
        self.key = ""
        self.is_enabled = False
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.url = data.get("url", "").strip().rstrip("/")
                    self.key = data.get("key", "").strip()
                    self.is_enabled = bool(self.url and self.key)
            except Exception:
                pass

    def save_config(self, url: str, key: str):
        self.url = url.strip().rstrip("/")
        self.key = key.strip()
        self.is_enabled = bool(self.url and self.key)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"url": self.url, "key": self.key}, f, indent=2)
        return {"status": "saved", "is_enabled": self.is_enabled}

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": bool(self.url and self.key),
            "url": self.url[:25] + "..." if len(self.url) > 25 else self.url,
            "has_key": bool(self.key)
        }

    def test_connection(self, url: Optional[str] = None, key: Optional[str] = None) -> Dict[str, Any]:
        test_url = (url or self.url).strip().rstrip("/")
        test_key = (key or self.key).strip()

        if not test_url or not test_key:
            return {"success": False, "message": "Supabase Project URL and Key are required."}

        # Check REST API endpoint
        rest_url = f"{test_url}/rest/v1/"
        headers = {
            "apikey": test_key,
            "Authorization": f"Bearer {test_key}"
        }

        try:
            resp = requests.get(rest_url, headers=headers, timeout=8)
            if resp.status_code in [200, 204]:
                return {"success": True, "message": "Successfully connected to Supabase Cloud Database!"}
            elif resp.status_code == 401:
                return {"success": False, "message": "Authentication failed. Check your Supabase API Key."}
            else:
                return {"success": True, "message": f"Connected to Supabase endpoint (Status {resp.status_code})."}
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}

    def sync_local_to_supabase(self) -> Dict[str, Any]:
        """
        Pushes all local SQLite data (Company, Shifts, Employees, Raw Punches, Daily Attendance, Payslips) to Supabase.
        """
        if not self.url or not self.key:
            return {"success": False, "message": "Supabase is not configured yet. Please enter your Project URL and Key."}

        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }

        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        stats = {}

        try:
            # 1. Company Settings
            cursor.execute("SELECT * FROM company_settings LIMIT 1")
            row = cursor.fetchone()
            if row:
                comp_data = dict(row)
                comp_data["id"] = 1
                r = requests.post(f"{self.url}/rest/v1/company_settings", headers=headers, json=[comp_data], timeout=10)
                stats["settings"] = "Synced" if r.status_code in [200, 201, 204] else f"Error {r.status_code}"

            # 2. Shifts
            cursor.execute("SELECT * FROM shifts")
            shifts = [dict(r) for r in cursor.fetchall()]
            if shifts:
                r = requests.post(f"{self.url}/rest/v1/shifts", headers=headers, json=shifts, timeout=10)
                stats["shifts"] = len(shifts) if r.status_code in [200, 201, 204] else f"Error {r.status_code}"

            # 3. Employees
            cursor.execute("SELECT * FROM employees WHERE is_active = 1")
            employees = [dict(r) for r in cursor.fetchall()]
            if employees:
                # Remove SQLite specific columns if needed
                r = requests.post(f"{self.url}/rest/v1/employees", headers=headers, json=employees, timeout=10)
                stats["employees"] = len(employees) if r.status_code in [200, 201, 204] else f"Error {r.status_code}"

            # 4. Raw Punches
            cursor.execute("SELECT biometric_id, punch_time, punch_type, source FROM raw_attendance_logs")
            punches = [dict(r) for r in cursor.fetchall()]
            if punches:
                # Chunk into batches of 100
                for i in range(0, len(punches), 100):
                    batch = punches[i:i+100]
                    requests.post(f"{self.url}/rest/v1/raw_attendance_logs", headers=headers, json=batch, timeout=10)
                stats["raw_punches"] = len(punches)

            # 5. Daily Attendance
            cursor.execute("SELECT * FROM daily_attendance")
            daily_rows = [dict(r) for r in cursor.fetchall()]
            if daily_rows:
                r_sup_emps = requests.get(f"{self.url}/rest/v1/employees?select=id,biometric_id", headers=headers, timeout=10).json()
                bio_to_sup_id = {e["biometric_id"]: e["id"] for e in r_sup_emps}
                cursor.execute("SELECT id, biometric_id FROM employees")
                loc_emp_to_bio = {r["id"]: r["biometric_id"] for r in cursor.fetchall()}

                cleaned_daily = []
                seen_daily = set()
                for d in daily_rows:
                    d_dict = dict(d)
                    bio = loc_emp_to_bio.get(d_dict["employee_id"])
                    if bio and bio in bio_to_sup_id:
                        d_dict["employee_id"] = bio_to_sup_id[bio]
                        d_dict.pop("id", None)
                        k = (d_dict["employee_id"], str(d_dict["date"]))
                        if k not in seen_daily:
                            seen_daily.add(k)
                            cleaned_daily.append(d_dict)

                for i in range(0, len(cleaned_daily), 100):
                    batch = cleaned_daily[i:i+100]
                    requests.post(f"{self.url}/rest/v1/daily_attendance?on_conflict=employee_id,date", headers=headers, json=batch, timeout=10)
                stats["daily_attendance"] = len(cleaned_daily)

            # 6. Payroll Runs
            cursor.execute("SELECT month, total_employees, total_gross_salary, total_deductions, total_net_salary, status FROM payroll_runs")
            runs = [dict(r) for r in cursor.fetchall()]
            if runs:
                requests.post(f"{self.url}/rest/v1/payroll_runs?on_conflict=month", headers=headers, json=runs, timeout=10)
                stats["payroll_runs"] = len(runs)

            # 7. Payslips
            cursor.execute("SELECT * FROM payslips")
            payslip_rows = [dict(r) for r in cursor.fetchall()]
            if payslip_rows:
                r_sup_emps = requests.get(f"{self.url}/rest/v1/employees?select=id,biometric_id", headers=headers, timeout=10).json()
                bio_to_sup_id = {e["biometric_id"]: e["id"] for e in r_sup_emps}
                cursor.execute("SELECT id, biometric_id FROM employees")
                loc_emp_to_bio = {r["id"]: r["biometric_id"] for r in cursor.fetchall()}

                cleaned_slips = []
                seen_slips = set()
                for s in payslip_rows:
                    slip_dict = dict(s)
                    bio = loc_emp_to_bio.get(slip_dict["employee_id"])
                    if bio and bio in bio_to_sup_id:
                        slip_dict["employee_id"] = bio_to_sup_id[bio]
                        slip_dict.pop("id", None)
                        slip_dict.pop("payroll_run_id", None)
                        k = (slip_dict["employee_id"], slip_dict["month"])
                        if k not in seen_slips:
                            seen_slips.add(k)
                            cleaned_slips.append(slip_dict)

                if cleaned_slips:
                    r_p = requests.post(f"{self.url}/rest/v1/payslips?on_conflict=employee_id,month", headers=headers, json=cleaned_slips, timeout=10)
                    stats["payslips"] = len(cleaned_slips) if r_p.status_code in [200, 201, 204] else f"Error {r_p.status_code}"

            conn.close()
            return {
                "success": True,
                "message": f"Successfully synced all data to Supabase Cloud Database!",
                "synced_stats": stats
            }

        except Exception as e:
            conn.close()
            return {"success": False, "message": f"Sync failed: {str(e)}"}

    def delete_employee_cascade(self, emp_id: int, bio_id: Optional[str] = None):
        """Cascades deletion of employee and all related attendance/payroll records in Supabase Cloud."""
        if not self.is_enabled:
            return
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}"
        }
        try:
            requests.delete(f"{self.url}/rest/v1/daily_attendance?employee_id=eq.{emp_id}", headers=headers, timeout=5)
            requests.delete(f"{self.url}/rest/v1/payslips?employee_id=eq.{emp_id}", headers=headers, timeout=5)
            requests.delete(f"{self.url}/rest/v1/leaves?employee_id=eq.{emp_id}", headers=headers, timeout=5)
            if bio_id:
                requests.delete(f"{self.url}/rest/v1/raw_attendance_logs?biometric_id=eq.{bio_id}", headers=headers, timeout=5)
            requests.delete(f"{self.url}/rest/v1/employees?id=eq.{emp_id}", headers=headers, timeout=5)
        except Exception:
            pass

supabase_manager = SupabaseManager()
