import psutil
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from flask import Flask, render_template, jsonify
import threading
import configparser

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Flask app for UI
app = Flask(__name__)

# Server details
server_name = config['SERVER']['name']
public_ip = requests.get("https://ipinfo.io/ip").text.strip()  # Fetching the public IP

# Constants for thresholds
THRESHOLD = 90

# Email configuration
smtp_server = config['SMTP']['server']
smtp_port = int(config['SMTP']['port'])
smtp_username = config['SMTP']['username']
smtp_password = config['SMTP']['password']
sender = f"Alert <{smtp_username}>"
recipients = ['shubham.kumar@deskera.org']

# Avoid sending multiple alerts for the same issue within a short interval
last_alert_time = {"cpu": 0, "memory": 0, "disk": 0}
alert_interval = 300  # 5 minutes interval between repeated alerts

# Global variables to store system stats
system_stats = {
    "cpu": [],
    "memory": [],
    "disk": []
}

# Function to send an email alert
def send_email_alert(subject, body):
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender, recipients, msg.as_string())
            print("Email alert sent successfully.")
    except Exception as e:
        print(f"Failed to send email. Error: {e}")

# Function to get top processes by both CPU and memory
def get_top_processes():
    processes = [(proc.info['pid'], proc.info['name'], proc.info['cpu_percent'], proc.info['memory_percent'])
                 for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent'])]
    processes.sort(key=lambda x: x[2], reverse=True)  # Sort by CPU usage
    top_cpu_processes = processes[:5]  # Top 5 by CPU

    processes.sort(key=lambda x: x[3], reverse=True)  # Sort by memory usage
    top_memory_processes = processes[:5]  # Top 5 by memory

    return top_cpu_processes, top_memory_processes

# Check CPU usage
def check_cpu_usage():
    cpu_usage = psutil.cpu_percent(interval=1)
    system_stats["cpu"].append(cpu_usage)
    if len(system_stats["cpu"]) > 60:  # Limit to last 60 records
        system_stats["cpu"].pop(0)

    if cpu_usage > THRESHOLD and time.time() - last_alert_time['cpu'] > alert_interval:
        last_alert_time['cpu'] = time.time()

        # Get top processes
        top_cpu_processes, _ = get_top_processes()
        process_details = "\n".join([f"PID: {pid}, Name: {name}, CPU: {cpu}%" for pid, name, cpu, _ in top_cpu_processes])
        
        subject = f"🚨 {server_name}: High CPU Usage Alert on IP: {public_ip} 🚨"
        email_body = f"🔥 Current CPU Usage: {cpu_usage}%\n\n📊 *Top Processes by CPU Usage:*\n{process_details}"
        send_email_alert(subject, email_body)

# Check memory usage
def check_memory_usage():
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    system_stats["memory"].append(memory_usage)
    if len(system_stats["memory"]) > 60:  # Limit to last 60 records
        system_stats["memory"].pop(0)

    if memory_usage > THRESHOLD and time.time() - last_alert_time['memory'] > alert_interval:
        last_alert_time['memory'] = time.time()

        _, top_memory_processes = get_top_processes()
        process_details = "\n".join([f"PID: {pid}, Name: {name}, Memory: {mem}%" for pid, name, _, mem in top_memory_processes])
        
        subject = f"🚨 {server_name}: High Memory Usage Alert on IP: {public_ip} 🚨"
        email_body = f"🔥 Current Memory Usage: {memory_usage}%\n\n📊 *Top Processes by Memory Usage:*\n{process_details}"
        send_email_alert(subject, email_body)

# Function to check disk usage for specific disks
def check_disk_usage():
    mount_points = {'/': '/dev/vda1', '/mnt/volume_blr1_02': '/dev/sda'}
    for mount_point, device in mount_points.items():
        if os.path.ismount(mount_point):
            try:
                disk_usage = psutil.disk_usage(mount_point).percent
                system_stats["disk"].append(disk_usage)
                if len(system_stats["disk"]) > 60:  # Limit to last 60 records
                    system_stats["disk"].pop(0)
                
                if disk_usage > THRESHOLD:                  
                    subject = f"🚨 {server_name}: High Disk Usage Alert on IP: {public_ip} 🚨"
                    email_body = f"🔥 Current Disk Usage: {disk_usage}% on {device} mounted on {mount_point}"
                    send_email_alert(subject, email_body)

            except PermissionError:
                print(f"Permission error accessing {mount_point}.")
        else:
            print(f"{mount_point} is not mounted.")

# Function for monitoring system
def monitor_system():
    while True:
        check_cpu_usage()
        check_memory_usage()
        check_disk_usage()
        time.sleep(5)

# Function to start the monitoring in a background thread
def start_monitoring():
    monitor_thread = threading.Thread(target=monitor_system)
    monitor_thread.daemon = True
    monitor_thread.start()

# Flask routes to serve the UI
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cpu')
def cpu_data():
    return jsonify(system_stats['cpu'])

@app.route('/memory')
def memory_data():
    return jsonify(system_stats['memory'])

@app.route('/disk')
def disk_data():
    return jsonify(system_stats['disk'])

# Add this to your existing Flask application

@app.route('/processes', methods=['GET'])
def get_processes():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            # Append the process info to the list
            processes.append({
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'cpu_percent': proc.info['cpu_percent'],
                'memory_percent': proc.info['memory_percent'],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return jsonify(processes)

# Add these functions to your existing Flask application

@app.route('/system_info', methods=['GET'])
def get_system_info():
    cpu_count = psutil.cpu_count(logical=True)
    cpu_usage = psutil.cpu_percent(interval=1)
    free_cpu = 100 - cpu_usage

    memory = psutil.virtual_memory()
    free_memory = memory.available / (1024 ** 2)  # Convert to MB
    total_memory = memory.total / (1024 ** 2)  # Convert to MB
    memory_usage = memory.percent

    disk = psutil.disk_usage('/')
    free_disk = disk.free / (1024 ** 3)  # Convert to GB
    total_disk = disk.total / (1024 ** 3)  # Convert to GB
    disk_usage = disk.percent

    system_info = {
        'cpu_count': cpu_count,
        'cpu_usage': cpu_usage,
        'free_cpu': free_cpu,
        'total_memory': total_memory,
        'free_memory': free_memory,
        'memory_usage': memory_usage,
        'total_disk': total_disk,
        'free_disk': free_disk,
        'disk_usage': disk_usage,
    }
    return jsonify(system_info)



if __name__ == "__main__":
    start_monitoring()
    app.run(host='0.0.0.0', port=5000)
