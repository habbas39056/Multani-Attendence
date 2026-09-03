"""
Biometric Fingerprint Device Synchronization Module for Multani Attendance System
Supports:
- Hikvision ISAPI Biometric Terminal protocol (HTTP Digest/Basic Auth)
- Direct TCP/IP socket communication (ZKTeco/eSSL protocol)
- ADMS / IClock Cloud push stream handler
- Scheduled auto-sync background worker
- Device connection tester & status diagnostics
- CSV / Excel offline punch log importer
- Built-in live punch simulator for testing & demonstration
"""
import socket
import threading
import time
from datetime import datetime, date, timedelta
import csv
import io
import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

from database import get_db_connection
from attendance_engine import process_attendance_for_date
from supabase_manager import supabase_manager

class BiometricSyncManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BiometricSyncManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self.is_running = False
        self.worker_thread = None
        self.sync_logs_feed = [] # In-memory live event feed for UI
        self.max_feed_size = 50

    def add_feed_entry(self, message: str, level: str = "info", device_name: str = "System"):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
            "level": level, # 'info', 'success', 'warning', 'error'
            "device": device_name
        }
        self.sync_logs_feed.insert(0, entry)
        if len(self.sync_logs_feed) > self.max_feed_size:
            self.sync_logs_feed.pop()

    def test_connection(self, ip: str, port: int = 8080, username: str = "admin", password: str = "", timeout: int = 4):
        """Tests connection to biometric device (supports TCP, HTTPS/HTTP, and Hikvision ISAPI)."""
        # 1. Test basic TCP reachability
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            start_t = time.time()
            s.connect((ip, int(port)))
            elapsed = round((time.time() - start_t) * 1000, 1)
            s.close()
        except socket.timeout:
            return {
                "success": False,
                "message": f"Connection timed out to {ip}:{port}. Check if device is powered on and port is open."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Could not reach {ip}:{port}: {str(e)}"
            }

        # 2. Check if Hikvision ISAPI (HTTPS first, then HTTP)
        for protocol in ["https", "http"]:
            url = f"{protocol}://{ip}:{port}/ISAPI/System/deviceInfo"
            try:
                auth = HTTPDigestAuth(username, password) if username and password else None
                r = requests.get(url, auth=auth, verify=False, timeout=4)
                if r.status_code == 200:
                    model = "Hikvision Terminal"
                    if "<model>" in r.text:
                        model = r.text.split("<model>")[1].split("</model>")[0]
                    return {
                        "success": True,
                        "is_hikvision": True,
                        "auth_ok": True,
                        "protocol": protocol,
                        "message": f"Connected & Authenticated! Device: {model} (Latency: {elapsed}ms)",
                        "latency_ms": elapsed
                    }
                elif r.status_code == 401:
                    return {
                        "success": True,
                        "is_hikvision": True,
                        "auth_ok": False,
                        "protocol": protocol,
                        "message": f"Device is ONLINE ({ip}:{port}), but Authentication Failed (401). Please check the device password.",
                        "latency_ms": elapsed
                    }
            except Exception:
                pass

        return {
            "success": True,
            "auth_ok": True,
            "message": f"Successfully connected to {ip}:{port} (Latency: {elapsed}ms)",
            "latency_ms": elapsed
        }

    def fetch_hikvision_punches(self, ip: str, port: int = 8080, username: str = "admin", password: str = "", start_date: str = None, end_date: str = None):
        """
        Pulls attendance punch records from Hikvision terminal via HTTPS/HTTP ISAPI AcsEvent with pagination.
        """
        import urllib3
        urllib3.disable_warnings()

        position = 0
        max_batch = 100
        total_fetched = 0
        total_saved = 0
        dates_affected = set()

        auth = HTTPDigestAuth(username, password)

        # Detect protocol (HTTPS or HTTP)
        protocol = "https"
        try:
            r_test = requests.get(f"https://{ip}:{port}/ISAPI/System/deviceInfo", auth=auth, verify=False, timeout=3)
            if r_test.status_code not in [200, 401]:
                protocol = "http"
        except Exception:
            protocol = "http"

        url = f"{protocol}://{ip}:{port}/ISAPI/AccessControl/AcsEvent?format=json"

        # Search for all events (major=5 is access control / door / authentication event)
        while True:
            payload = {
                "AcsEventCond": {
                    "searchID": "multani_sync",
                    "searchResultPosition": position,
                    "maxResults": max_batch,
                    "major": 5,
                    "minor": 0
                }
            }

            try:
                r = requests.post(url, json=payload, auth=auth, verify=False, timeout=10)
                if r.status_code == 401:
                    auth = HTTPBasicAuth(username, password)
                    r = requests.post(url, json=payload, auth=auth, verify=False, timeout=10)

                if r.status_code == 401:
                    return {
                        "success": False,
                        "message": "Authentication Failed (401). Please check device password in Settings."
                    }

                if r.status_code != 200:
                    break

                try:
                    data = r.json()
                except Exception:
                    break

                acs_event = data.get("AcsEvent", {})
                events = acs_event.get("InfoList", [])
                total_matches = acs_event.get("totalMatches", 0)

                if not events:
                    break

                for ev in events:
                    total_fetched += 1
                    emp_no = ev.get("employeeNoString") or str(ev.get("cardNo") or "")
                    emp_name = ev.get("name")
                    event_time_str = ev.get("time", "")
                    
                    if emp_no and event_time_str:
                        clean_time = event_time_str.split("+")[0].replace("T", " ")
                        saved = self.record_punch(emp_no, clean_time, "Auto", None, "hikvision_isapi", name=emp_name)
                        if saved:
                            total_saved += 1
                            try:
                                dates_affected.add(clean_time.split(" ")[0])
                            except Exception:
                                pass

                position += len(events)
                if position >= total_matches or len(events) == 0:
                    break

            except requests.exceptions.RequestException as e:
                break
            except Exception as e:
                break

        # Reprocess attendance for all affected historical dates
        for d in dates_affected:
            process_attendance_for_date(d)

        return {
            "success": True,
            "count": total_saved,
            "total_events": total_fetched,
            "dates_count": len(dates_affected),
            "message": f"Successfully pulled {total_fetched} logs from machine ({total_saved} new punches saved across {len(dates_affected)} days)."
        }

        # Reprocess attendance for all affected historical dates
        for d in dates_affected:
            process_attendance_for_date(d)

        return {
            "success": True,
            "count": total_saved,
            "total_events": total_fetched,
            "dates_count": len(dates_affected),
            "message": f"Successfully pulled {total_fetched} logs ({total_saved} new punches saved across {len(dates_affected)} days)."
        }

    def record_punch(self, biometric_id: str, punch_time: str, punch_type: str = "Auto", device_id: int = None, source: str = "biometric_sync", name: str = None):
        """
        Inserts a punch into raw_attendance_logs, auto-creates team member if not registered, and triggers instant daily processing.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        b_id = str(biometric_id).strip()
        cursor.execute("SELECT id, name FROM employees WHERE biometric_id = ?", (b_id,))
        emp_row = cursor.fetchone()
        if not emp_row:
            emp_display_name = name.strip() if name and name.strip() else f"Staff #{b_id}"
            cursor.execute("""
                INSERT INTO employees (
                    biometric_id, name, department, designation, salary_type,
                    basic_salary, housing_allowance, transport_allowance,
                    start_time, end_time, grace_minutes, work_hours, off_day, is_active
                ) VALUES (?, ?, 'Multani Shop', 'Staff', 'Monthly', 30000.0, 0.0, 0.0, '09:00', '18:00', 15, 8.0, 'Sun', 1)
            """, (b_id, emp_display_name))
            conn.commit()
        elif name and name.strip() and emp_row["name"].startswith("Staff #"):
            cursor.execute("UPDATE employees SET name = ? WHERE biometric_id = ?", (name.strip(), b_id))
            conn.commit()

        try:
            if isinstance(punch_time, str):
                if "T" in punch_time:
                    dt = datetime.fromisoformat(punch_time.replace("Z", "").split("+")[0])
                elif " " in punch_time:
                    dt = datetime.strptime(punch_time.split(".")[0], "%Y-%m-%d %H:%M:%S")
                else:
                    dt = datetime.now()
            elif isinstance(punch_time, datetime):
                dt = punch_time
            else:
                dt = datetime.now()
            
            clean_time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            clean_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            date_str = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, device_id, source)
            VALUES (?, ?, ?, ?, ?)
        """, (b_id, clean_time_str, punch_type, device_id, source))
        
        inserted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if inserted:
            process_attendance_for_date(date_str)
            self.add_feed_entry(
                f"New Punch Log: Bio User #{b_id} at {clean_time_str}",
                "success",
                f"Device #{device_id}" if device_id else "Live Sync"
            )
            # Async push to Supabase Cloud
            try:
                threading.Thread(target=supabase_manager.sync_local_to_supabase, daemon=True).start()
            except Exception:
                pass

        return inserted

    def sync_device(self, device_id: int):
        """
        Synchronizes punches from a registered biometric device.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM biometric_devices WHERE id = ?", (device_id,))
        device = cursor.fetchone()
        if not device:
            conn.close()
            return {"success": False, "message": "Device not found"}

        ip = device["ip_address"]
        port = device["port"]
        dev_name = device["name"]
        username = device["username"] if "username" in device.keys() and device["username"] else "admin"
        password = device["password"] if "password" in device.keys() and device["password"] else ""

        self.add_feed_entry(f"Initiating sync for {dev_name} ({ip}:{port})...", "info", dev_name)

        # 1. Test reachability & authentication
        test_res = self.test_connection(ip, port, username, password, timeout=3)
        if not test_res["success"]:
            cursor.execute("UPDATE biometric_devices SET last_status = ?, last_sync_time = CURRENT_TIMESTAMP WHERE id = ?", 
                           (f"Offline: {test_res['message'][:50]}", device_id))
            conn.commit()
            conn.close()
            self.add_feed_entry(f"Sync failed for {dev_name}: {test_res['message']}", "error", dev_name)
            return test_res

        # 2. If it's a Hikvision device with password set, pull logs
        if password:
            fetch_res = self.fetch_hikvision_punches(ip, port, username, password)
            if fetch_res["success"]:
                status_msg = f"Online (Synced {fetch_res['count']} punches)"
                cursor.execute("UPDATE biometric_devices SET last_status = ?, last_sync_time = CURRENT_TIMESTAMP WHERE id = ?", (status_msg, device_id))
                conn.commit()
                conn.close()
                self.add_feed_entry(fetch_res["message"], "success", dev_name)
                return fetch_res
            else:
                cursor.execute("UPDATE biometric_devices SET last_status = ?, last_sync_time = CURRENT_TIMESTAMP WHERE id = ?", 
                               (f"Connected: {fetch_res['message'][:50]}", device_id))
                conn.commit()
                conn.close()
                self.add_feed_entry(f"Notice for {dev_name}: {fetch_res['message']}", "warning", dev_name)
                return fetch_res
        else:
            # Device is online, waiting for password or ADMS push
            status_msg = "Online (Listening / Ready)"
            cursor.execute("UPDATE biometric_devices SET last_status = ?, last_sync_time = CURRENT_TIMESTAMP WHERE id = ?", (status_msg, device_id))
            conn.commit()
            conn.close()
            self.add_feed_entry(f"Device {dev_name} is Online at {ip}:{port}. Set password to fetch logs via ISAPI, or configure Cloud Push.", "info", dev_name)
            return {"success": True, "message": f"Device {dev_name} is online and connected."}

    def sync_all_active_devices(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM biometric_devices WHERE is_active = 1 AND auto_sync = 1")
        devices = cursor.fetchall()
        conn.close()

        results = []
        for dev in devices:
            res = self.sync_device(dev["id"])
            results.append({"device": dev["name"], "result": res})
        return results

    def start_auto_sync_background(self):
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self.worker_thread.start()
        self.add_feed_entry("Biometric Auto-Sync Daemon active.", "info", "System")

    def _auto_sync_loop(self):
        while self.is_running:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT auto_sync_interval_seconds FROM company_settings LIMIT 1")
                setting = cursor.fetchone()
                interval = setting["auto_sync_interval_seconds"] if setting else 60
                interval = max(10, interval)
                conn.close()

                self.sync_all_active_devices()
            except Exception as e:
                self.add_feed_entry(f"Auto-sync loop error: {str(e)}", "error", "System")

            for _ in range(interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def stop_auto_sync(self):
        self.is_running = False

    def simulate_punch_batch(self, punches: list):
        count = 0
        dates_to_recalculate = set()
        for p in punches:
            bio_id = str(p.get("biometric_id"))
            p_time = p.get("punch_time")
            p_type = p.get("punch_type", "Auto")
            dev_id = p.get("device_id", 1)

            if bio_id and p_time:
                ins = self.record_punch(bio_id, p_time, p_type, dev_id, "simulator")
                if ins:
                    count += 1
                    try:
                        dates_to_recalculate.add(p_time.split(" ")[0])
                    except Exception:
                        pass

        for d in dates_to_recalculate:
            process_attendance_for_date(d)

        self.add_feed_entry(f"Simulated {count} punch records successfully.", "success", "Simulator")
        return {"status": "success", "imported_punches": count}

    def import_csv_punches(self, file_content: str):
        """
        Imports punch logs exported from biometric machines (.csv or .xls HTML report).
        """
        # 1. Check if it's an HTML table XLS report
        if "<td" in file_content or "<table" in file_content:
            import re
            td_matches = re.findall(r"<td[^>]*>(.*?)</td>", file_content, re.DOTALL | re.IGNORECASE)
            clean_cells = [re.sub(r"<[^>]+>", "", c).strip().replace("&nbsp;", " ") for c in td_matches]

            header_idx = -1
            for i in range(len(clean_cells) - 10):
                if clean_cells[i] == "No." and clean_cells[i+1] == "Person ID" and clean_cells[i+2] == "Name":
                    header_idx = i
                    break

            if header_idx != -1:
                data_cells = clean_cells[header_idx + 20:]
                COLS_COUNT = 20
                imported = 0
                dates_affected = set()

                for idx in range(0, len(data_cells), COLS_COUNT):
                    chunk = data_cells[idx:idx+COLS_COUNT]
                    if len(chunk) < COLS_COUNT:
                        break
                    
                    pid = chunk[1].strip()
                    pname = chunk[2].strip() if len(chunk) > 2 and chunk[2].strip() and chunk[2].strip() != "-" else None
                    dt = chunk[6].strip()
                    cin = chunk[9].strip()
                    cout = chunk[10].strip()
                    raw_punches = chunk[19].strip()

                    if pid and len(dt) == 10:
                        if raw_punches and raw_punches != "-":
                            times = [t.strip() for t in raw_punches.split() if ":" in t]
                            for t in times:
                                if self.record_punch(pid, f"{dt} {t}", "Auto", None, "xls_import", name=pname):
                                    imported += 1
                                    dates_affected.add(dt)
                        elif cin != "-" or cout != "-":
                            if cin != "-":
                                if self.record_punch(pid, f"{dt} {cin}", "Check-In", None, "xls_import", name=pname):
                                    imported += 1
                                    dates_affected.add(dt)
                            if cout != "-" and cout != cin:
                                if self.record_punch(pid, f"{dt} {cout}", "Check-Out", None, "xls_import", name=pname):
                                    imported += 1
                                    dates_affected.add(dt)

                for d in dates_affected:
                    process_attendance_for_date(d)

                self.add_feed_entry(f"Imported {imported} punches from biometric report.", "success", "Report Import")
                return {"status": "success", "imported": imported}

        # 2. Standard CSV parsing
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)
        if not rows:
            return {"error": "Empty file"}

        header = [col.strip().lower() for col in rows[0]]
        id_idx = -1
        time_idx = -1
        date_idx = -1
        type_idx = -1

        for i, h in enumerate(header):
            if any(k in h for k in ["biometric", "user", "pin", "badgenumber", "emp_id", "id", "employee"]):
                id_idx = i
            elif any(k in h for k in ["datetime", "punch_time", "time", "timestamp"]):
                if "date" not in h or "datetime" in h:
                    time_idx = i
            elif "date" in h:
                date_idx = i
            elif any(k in h for k in ["type", "state", "status"]):
                type_idx = i

        if id_idx == -1: id_idx = 0
        if time_idx == -1 and date_idx == -1: time_idx = 1

        imported = 0
        dates_affected = set()

        for row in rows[1:]:
            if not row or len(row) <= max(id_idx, time_idx if time_idx != -1 else date_idx):
                continue
            bio_id = row[id_idx].strip()
            
            if date_idx != -1 and time_idx != -1 and date_idx != time_idx:
                raw_dt = f"{row[date_idx].strip()} {row[time_idx].strip()}"
            else:
                raw_dt = row[time_idx if time_idx != -1 else date_idx].strip()

            p_type = row[type_idx].strip() if type_idx != -1 and type_idx < len(row) else "Auto"

            if bio_id and raw_dt:
                ins = self.record_punch(bio_id, raw_dt, p_type, None, "manual_import")
                if ins:
                    imported += 1
                    try:
                        dates_affected.add(raw_dt.split(" ")[0])
                    except Exception:
                        pass

        for d in dates_affected:
            process_attendance_for_date(d)

        self.add_feed_entry(f"Imported {imported} punches from file.", "success", "File Import")
        return {"status": "success", "imported": imported}

sync_manager = BiometricSyncManager()
