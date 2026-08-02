#!/usr/bin/env python3
"""
Hornbill Edge Gateway - Serial and Telemetry Bridge
===================================================
This script runs on the Raspberry Pi. It reads telemetry data from the Arduino
over Serial, enriches it with Pi system diagnostics (CPU temp, RAM, Wifi RSSI),
and posts it to the central dashboard web server.

Features a graceful simulation fallback if no Serial port/Arduino is detected,
allowing out-of-the-box local testing.
"""

import os
import sys
import time
import json
import random
import requests
import threading

# AI is now handled entirely on the edge device (M5Stack CoreS3)
AI_HELPERS_AVAILABLE = False

# Load configurations
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config.json: {e}")
    # Fallback default configurations
    config = {
        "device_id": "hornbill-gateway-node-01",
        "serial_port": "/dev/ttyACM0",
        "baud_rate": 9600,
        "server_url": "http://localhost:3000"
    }

# Dynamic Imports for Serial Port
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("Warning: 'pyserial' not installed. Running in SIMULATED serial mode.")

# Helper to fetch Raspberry Pi system statistics
def get_pi_diagnostics():
    diagnostics = {
        "cpu_temp": 42.5,  # Celsius
        "cpu_usage": 12.0, # Percentage
        "ram_usage": 32.5, # Percentage
        "wifi_rssi": -65,  # dBm (Excellent/Good)
        "battery_voltage": 12.1 # Volts (12V Solar panel battery simulation)
    }
    
    # Try reading real Raspberry Pi CPU Temperature if running on Linux
    if sys.platform.startswith('linux'):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as temp_file:
                diagnostics["cpu_temp"] = float(temp_file.read().strip()) / 1000.0
            # Read CPU usage
            with open("/proc/loadavg", "r") as load_file:
                diagnostics["cpu_usage"] = float(load_file.read().split()[0]) * 100.0 / 4.0
        except Exception:
            pass # Keep simulated default values on non-Pi platforms
            
    # Add random fluctuation to simulated parameters for aesthetic variation
    else:
        diagnostics["cpu_temp"] = round(45.0 + random.uniform(-2.0, 2.0), 1)
        diagnostics["cpu_usage"] = round(10.0 + random.uniform(-5.0, 15.0), 1)
        diagnostics["ram_usage"] = round(28.0 + random.uniform(-1.0, 3.0), 1)
        diagnostics["wifi_rssi"] = random.randint(-72, -58)
        diagnostics["battery_voltage"] = round(12.2 + random.uniform(-0.4, 0.4), 2)
        
    return diagnostics

# Main Telemetry Processing and Forwarding
def forward_data(payload, ser_device=None):
    url = f"{config['server_url']}/api/telemetry"
    headers = {'Content-Type': 'application/json'}
    
    # 1. Post to Local Basecamp Dashboard
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        if response.status_code == 200 or response.status_code == 201:
            print(f"[OK] Gateway Sent Local: Temp={payload['temperature']} C, Humid={payload['humidity']}%, Motion={payload['motion']}")
            
            # Check for downstream display commands from the server
            try:
                res_data = response.json()
                commands = res_data.get("commands", [])
                if commands and ser_device:
                    for cmd in commands:
                        if cmd.get("action") == "display":
                            species = cmd.get("species", "Unknown")
                            confidence = int(float(cmd.get("confidence", 0.0)) * 100)
                            # Format for Arduino: [ALERT:Species,Confidence]
                            alert_msg = f"[ALERT:{species},{confidence}]\n"
                            print(f"[*] Gateway: Writing command to Arduino: {alert_msg.strip()}")
                            ser_device.write(alert_msg.encode('utf-8'))
            except Exception as je:
                pass # Silent ignore json parse errors
        else:
            print(f"[FAIL] Local server rejected payload: {response.status_code}")
    except requests.RequestException as e:
        print(f"[WARN] Local server connection failed ({config['server_url']}). Error: {e}")

    # 2. Mirror to Remote Cloud Endpoint if configured
    if config.get("cloud_url"):
        def post_telemetry_to_cloud():
            try:
                # Post direct JSON to remote cloud sync
                cloud_response = requests.post(config["cloud_url"], json=payload, headers=headers, timeout=4)
                if cloud_response.status_code in [200, 201]:
                    print(f"[OK] Cloud Sync Successful: Telemetry mirrored to remote cloud!")
                else:
                    print(f"[FAIL] Cloud rejected telemetry: {cloud_response.status_code}")
            except Exception as ex:
                print(f"[WARN] Cloud telemetry sync failed. Error: {ex}")
                
        threading.Thread(target=post_telemetry_to_cloud, daemon=True).start()

# Read from Serial (Standard Live Mode supporting USB and Bluetooth RFCOMM Serial)
def run_serial_listener():
    baud = config["baud_rate"]
    interfaces_to_try = []
    
    if config.get("bluetooth_port"):
        interfaces_to_try.append(("Bluetooth Link", config["bluetooth_port"]))
    if config.get("serial_port"):
        interfaces_to_try.append(("USB Serial Interface", config["serial_port"]))
        
    ser = None
    connected_interface = None
    
    for label, port in interfaces_to_try:
        print(f"Attempting to connect to Arduino on {label} ({port}) at {baud} baud...")
        try:
            ser = serial.Serial(port, baud, timeout=1)
            # Flush input buffer
            ser.flush()
            connected_interface = port
            print(f"[SUCCESS] Connected to Arduino on {label} ({port})!")
            break
        except serial.SerialException as e:
            print(f"[!] Could not open {label} on {port}: {e}")
            
    if not ser:
        print("\n[!] No physical connections (USB Serial or Bluetooth) could be established.")
        print("Switching to GATEWAY SIMULATOR fallback mode...\n")
        run_simulated_listener()
        return
        
    connection_type = "Bluetooth" if connected_interface == config.get("bluetooth_port") else "Serial"
    print(f"Gateway Running: Listening for Arduino telemetry streams on {connected_interface} ({connection_type})...")
    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                try:
                    # Arduino outputs JSON strings
                    data = json.loads(line)
                    
                    if data.get("type") == "telemetry":
                        # Fetch diagnostics and merge with sensor data
                        diagnostics = get_pi_diagnostics()
                        sound_level = data.get("sound_level", 0)
                        payload = {
                            "device_id": config["device_id"],
                            "timestamp": time.time(),
                            "temperature": data.get("temperature", 0.0),
                            "humidity": data.get("humidity", 0.0),
                            "motion": data.get("motion", False),
                            "sound_level": sound_level,
                            "connection_type": connection_type,
                            "diagnostics": diagnostics
                        }
                        # Send in background thread so serial reads are never delayed
                        threading.Thread(target=forward_data, args=(payload, ser)).start()
                        
                    elif data.get("type") == "ai_detection":
                        species = data.get("species", "Unknown")
                        confidence = data.get("confidence", 0.0)
                        print(f"[AI ALERT] Edge detection received: {species} ({confidence*100:.1f}%)")
                        trigger_payload = {
                            "device_id": config["device_id"],
                            "timestamp": time.time(),
                            "event_type": "AI_DETECTION",
                            "species": species,
                            "confidence": confidence
                        }
                        threading.Thread(
                            target=requests.post, 
                            args=(f"{config['server_url']}/api/events",), 
                            kwargs={"json": trigger_payload, "timeout": 2}
                        ).start()
                        
                        if config.get("cloud_url"):
                            threading.Thread(
                                target=requests.post, 
                                args=(config["cloud_url"],), 
                                kwargs={"json": trigger_payload, "timeout": 2}
                            ).start()
                                                
                    elif data.get("type") == "event":
                        # Fast alert triggering
                        print(f"[ALERT] Arduino Event Triggered: {data.get('event')}")
                        trigger_payload = {
                            "device_id": config["device_id"],
                            "timestamp": time.time(),
                            "event_type": data.get("event"),
                            "sound_level": data.get("sound_level", 0)
                        }
                        threading.Thread(
                            target=requests.post, 
                            args=(f"{config['server_url']}/api/events",), 
                            kwargs={"json": trigger_payload, "timeout": 2}
                        ).start()
                        
                        # Mirror event alert to cloud if configured
                        if config.get("cloud_url"):
                            threading.Thread(
                                target=requests.post, 
                                args=(config["cloud_url"],), 
                                kwargs={"json": trigger_payload, "timeout": 2}
                            ).start()
                        
                except json.JSONDecodeError:
                    # Ignore corrupted/partial packets during startup/noise
                    pass
            time.sleep(0.05)
            
    except serial.SerialException as e:
        print(f"\n[!] Serial Interface Error: {e}")
        print("Connection lost. Switching to GATEWAY SIMULATOR fallback mode...\n")
        run_simulated_listener()

# Simulated Arduino Data Generator (Demo/Fallback Mode)
def run_simulated_listener():
    print("====================================================")
    print("      RUNNING GATEWAY IN SIMULATED ARDUINO MODE     ")
    print("   Generates realistic sensory & environmental data ")
    print("====================================================")
    
    sim_temp = 26.5
    sim_humid = 82.0
    
    while True:
        # Gradually shift temp & humidity with brownian motion
        sim_temp += random.uniform(-0.15, 0.15)
        sim_humid += random.uniform(-0.3, 0.3)
        sim_temp = max(18.0, min(38.0, sim_temp))
        sim_humid = max(40.0, min(99.0, sim_humid))
        
        # Simulate occasional motion trigger (10% chance per interval)
        motion_triggered = random.choice([True] + [False]*9)
        sim_sound = random.randint(10, 180)
        
        if motion_triggered:
            sim_sound = random.randint(300, 800) # Louder sound on motion
            print(f"[ALERT] Motion Sensor Triggered!")
            trigger_payload = {
                "device_id": config["device_id"],
                "timestamp": time.time(),
                "event_type": "MOTION_DETECTED",
                "sound_level": sim_sound
            }
            threading.Thread(
                target=requests.post, 
                args=(f"{config['server_url']}/api/events",), 
                kwargs={"json": trigger_payload, "timeout": 2}
            ).start()
            
        # Get Pi stats
        diagnostics = get_pi_diagnostics()
        
        payload = {
            "device_id": config["device_id"],
            "timestamp": time.time(),
            "temperature": round(sim_temp, 1),
            "humidity": round(sim_humid, 1),
            "motion": motion_triggered,
            "sound_level": sim_sound,
            "connection_type": "Simulated",
            "diagnostics": diagnostics
        }
        
        # Send telemetry
        forward_data(payload)
        
        # Wait for telemetry interval
        time.sleep(2.0)

if __name__ == "__main__":
    print(f"Starting Hornbill AI & IoT Edge Gateway Node: {config['device_id']}")
    
    if SERIAL_AVAILABLE:
        run_serial_listener()
    else:
        run_simulated_listener()
