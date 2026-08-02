#!/usr/bin/env python3
"""
Hornbill Edge Gateway - MQTT Bridge for Remote M5Stack
======================================================
This script runs alongside your main pi_gateway.py.
It subscribes to a public Cloud MQTT broker to receive data from a remote M5Stack,
and forwards that data into your local dashboard web server.
"""

import os
import json
import time
import requests
import paho.mqtt.client as mqtt

# Configuration for Cloud MQTT
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "hornbill/telemetry/m5stack"

# Load local dashboard configuration to know where to send data
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        SERVER_URL = config.get("server_url", "http://localhost:3000")
except Exception as e:
    print(f"Error loading config.json: {e}")
    SERVER_URL = "http://localhost:3000"

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[OK] Connected to Cloud MQTT Broker: {MQTT_BROKER}")
        client.subscribe(MQTT_TOPIC)
        print(f"[*] Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"[FAIL] Failed to connect to MQTT broker, return code {rc}")

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode('utf-8')
    print(f"\n[+] MQTT Message received on {msg.topic}: {payload_str}")
    
    try:
        data = json.loads(payload_str)
        
        # Handle AI Detection Alerts
        if data.get("event_type") == "AI_DETECTION":
            url = f"{SERVER_URL}/api/events"
            # Format expected by the /api/events endpoint
            payload = {
                "device_id": data.get("device_id", "m5stack-remote-01"),
                "timestamp": time.time(),
                "event_type": "AI_DETECTION",
                "species": data.get("species", "Unknown"),
                "confidence": data.get("confidence", 0.0)
            }
        else:
            # Handle regular telemetry
            url = f"{SERVER_URL}/api/telemetry"
            payload = {
                "device_id": data.get("device_id", "m5stack-remote-01"),
                "timestamp": time.time(),
                "temperature": data.get("temperature", 0.0),
                "humidity": data.get("humidity", 0.0),
                "motion": data.get("motion", False),
                "sound_level": data.get("sound_level", 0),
                "connection_type": "Cloud_MQTT",
                "diagnostics": {
                    "wifi_rssi": data.get("wifi_rssi", -60),
                    "battery_voltage": data.get("battery_voltage", 3.7)
                }
            }

        # Forward to Local Dashboard
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        if response.status_code in [200, 201]:
            print(f"[OK] Forwarded M5Stack data to Dashboard ({SERVER_URL})")
        else:
            print(f"[FAIL] Dashboard rejected payload: {response.status_code}")

    except json.JSONDecodeError:
        print("[WARN] Received malformed JSON from MQTT")
    except requests.RequestException as e:
        print(f"[WARN] Failed to forward to local dashboard. Error: {e}")

if __name__ == "__main__":
    print(f"Starting Hornbill Cloud MQTT Bridge...")
    print(f"Target Dashboard: {SERVER_URL}")
    
    # Use CallbackAPIVersion.VERSION2 for paho-mqtt 2.0.0+
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hornbill-pi-gateway-" + str(time.time()))
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        # Blocking call that processes network traffic, dispatches callbacks and handles reconnecting
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nExiting MQTT Bridge.")
        client.disconnect()
    except Exception as e:
        print(f"Error connecting to MQTT: {e}")
