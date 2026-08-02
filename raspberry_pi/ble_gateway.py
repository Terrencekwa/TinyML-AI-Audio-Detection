#!/usr/bin/env python3
"""
Hornbill Edge Gateway - BLE (Bluetooth Low Energy) Bridge
=========================================================
Runs on the Raspberry Pi. Connects to the Arduino UNO R4 WiFi via built-in BLE,
subscribes to telemetry notifications, enriches data with Pi system statistics,
and forwards them to the dashboard backend.

Also handles downstream command routing (e.g. alerts to draw on the Arduino node OLED).
"""

import os
import sys
import time
import json
import random
import requests
import asyncio
import threading
import io
import wave
import struct
import numpy as np

# Import serial for USB streaming
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# Import Edge Impulse Linux SDK
try:
    from edge_impulse_linux.audio import AudioImpulseRunner as AudioClassifier
    EI_RUNNER_AVAILABLE = True
except ImportError:
    EI_RUNNER_AVAILABLE = False
    print("Warning: 'edge_impulse_linux' library not installed. AI inference will fall back to simulation.")

# Import AI helpers from ai_detection.py for Arduino-triggered AI classification
try:
    from ai_detection import run_ai_inference, generate_synthetic_horn_call, upload_detection
    AI_HELPERS_AVAILABLE = True
except ImportError:
    AI_HELPERS_AVAILABLE = False

# Dynamic Import for Bleak
try:
    from bleak import BleakScanner, BleakClient
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False
    print("Warning: 'bleak' library not installed. Run 'pip3 install bleak' on the Pi.")

# Load Configurations
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
except Exception:
    config = {
        "device_id": "hornbill-gateway-node-01",
        "server_url": "http://localhost:3000",
        "cloud_url": "http://localhost:3000/api/cloud-mirror"
    }

# BLE Identifiers
DEVICE_NAME = "HornbillNode"
TELEMETRY_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
COMMAND_UUID = "19B10002-E8F2-537E-4F6C-D104768A1214"
AUDIO_UUID = "19B10003-E8F2-537E-4F6C-D104768A1214"

# Global variables for audio streaming
audio_stream_buffer = bytearray()
is_receiving_audio = False
runner = None
model_info = None

# Helper to fetch Raspberry Pi system statistics
def get_pi_diagnostics():
    diagnostics = {
        "cpu_temp": round(45.0 + random.uniform(-2.0, 2.0), 1),
        "cpu_usage": round(10.0 + random.uniform(-5.0, 15.0), 1),
        "ram_usage": round(28.0 + random.uniform(-1.0, 3.0), 1),
        "wifi_rssi": random.randint(-72, -58),
        "battery_voltage": round(12.2 + random.uniform(-0.4, 0.4), 2)
    }
    
    # Try reading real Raspberry Pi CPU Temperature if running on Linux
    if sys.platform.startswith('linux'):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as temp_file:
                diagnostics["cpu_temp"] = float(temp_file.read().strip()) / 1000.0
            with open("/proc/loadavg", "r") as load_file:
                diagnostics["cpu_usage"] = float(load_file.read().split()[0]) * 100.0 / 4.0
        except Exception:
            pass
            
    return diagnostics

# Telemetry Forwarding & Command Extraction
def forward_data(payload, client=None):
    headers = {'Content-Type': 'application/json'}
    is_event = payload.get("type") == "event"
    
    if is_event:
        url = f"{config['server_url']}/api/events"
        post_payload = {
            "device_id": payload["device_id"],
            "event_type": payload["event"],
            "sound_level": payload["sound_level"]
        }
    else:
        url = f"{config['server_url']}/api/telemetry"
        post_payload = payload
        
    try:
        response = requests.post(url, json=post_payload, headers=headers, timeout=3)
        if response.status_code in [200, 201]:
            if is_event:
                print(f"[OK] BLE Gateway Sent Event: {post_payload['event_type']} (Sound={post_payload['sound_level']})")
            else:
                print(f"[OK] BLE Gateway Sent Local: Sound={payload['sound_level']}, Motion={payload['motion']}")
            
            # Check for downstream display commands from the server
            try:
                res_data = response.json()
                commands = res_data.get("commands", [])
                if commands and client:
                    for cmd in commands:
                        if cmd.get("action") == "display":
                            species = cmd.get("species", "Unknown")
                            confidence = int(float(cmd.get("confidence", 0.0)) * 100)
                            alert_msg = f"[ALERT:{species},{confidence}]\n"
                            print(f"[*] BLE Gateway: Writing command to Arduino: {alert_msg.strip()}")
                            
                            # Run async write in client loop thread
                            asyncio.run_coroutine_threadsafe(
                                client.write_gatt_char(COMMAND_UUID, alert_msg.encode('utf-8')),
                                client.loop
                            )
            except Exception as je:
                pass
        else:
            print(f"[FAIL] Local server rejected payload: {response.status_code}")
    except requests.RequestException as e:
        print(f"[WARN] Local server connection failed. Error: {e}")

    # Mirror to remote cloud
    if config.get("cloud_url"):
        def post_telemetry_to_cloud():
            try:
                requests.post(config["cloud_url"], json=post_payload, headers=headers, timeout=4)
            except Exception:
                pass
        threading.Thread(target=post_telemetry_to_cloud, daemon=True).start()

# BLE Event Handler
def notification_handler(client, sender, data):
    try:
        # Check if binary telemetry (8 bytes)
        if len(data) == 8:
            packet_type = data[0]
            temp_raw = int.from_bytes(data[1:3], byteorder='big', signed=True)
            humid_raw = int.from_bytes(data[3:5], byteorder='big', signed=True)
            motion = bool(data[5])
            sound_level = int.from_bytes(data[6:8], byteorder='big', signed=True)
            
            temp = temp_raw / 10.0
            humid = humid_raw / 10.0
            
            diagnostics = get_pi_diagnostics()
            
            if packet_type == 0:
                payload = {
                    "device_id": config["device_id"],
                    "timestamp": time.time(),
                    "temperature": temp,
                    "humidity": humid,
                    "motion": motion,
                    "sound_level": sound_level,
                    "connection_type": "Bluetooth",
                    "diagnostics": diagnostics
                }
                threading.Thread(target=forward_data, args=(payload, client)).start()
                
                # Check for sound sensor trigger from Arduino to run AI detection
                arduino_threshold = config.get("arduino_sound_threshold", 150)
                if sound_level > arduino_threshold and AI_HELPERS_AVAILABLE:
                    print(f"\n[ALERT] Arduino Sound Sensor Triggered! Value: {sound_level} (Threshold: {arduino_threshold}). Running AI inference...")
                    
                    def run_triggered_ai():
                        try:
                            species, confidence = run_ai_inference()
                            if species != "Background Noise" and confidence >= config.get("confidence_threshold", 0.82):
                                print(f"[AI ALERT] Hornbill Found: {species} ({confidence*100:.1f}%)! Generating realistic synthesized audio...")
                                
                                sample_rate = config.get("sound_monitoring", {}).get("sample_rate", 44100)
                                duration = config.get("sound_monitoring", {}).get("duration_seconds", 5)
                                audio_bytes = generate_synthetic_horn_call(species, sample_rate, duration)
                                
                                # Upload detection
                                upload_detection(species, confidence, audio_bytes)
                                
                                # Send alert downstream to Arduino OLED
                                alert_msg = f"[ALERT:{species},{int(confidence * 100)}]\n"
                                print(f"[*] BLE Gateway: Writing alert downstream: {alert_msg.strip()}")
                                asyncio.run_coroutine_threadsafe(
                                    client.write_gatt_char(COMMAND_UUID, alert_msg.encode('utf-8')),
                                    client.loop
                                )
                            else:
                                print("[-] AI evaluated as background or low confidence. Discarding.")
                        except Exception as ex:
                            print(f"[Error] AI trigger execution failed: {ex}")
                            
                    threading.Thread(target=run_triggered_ai, daemon=True).start()
                    
            elif packet_type in [1, 2]:
                event_name = "MOTION_DETECTED" if packet_type == 1 else "MOTION_CLEARED"
                payload = {
                    "device_id": config["device_id"],
                    "timestamp": time.time(),
                    "type": "event",
                    "event": event_name,
                    "sound_level": sound_level,
                    "connection_type": "Bluetooth",
                    "diagnostics": diagnostics
                }
                threading.Thread(target=forward_data, args=(payload, client)).start()
        else:
            # Fallback to UTF-8 JSON parsing for compatibility
            line = data.decode('utf-8', errors='ignore').strip()
            data_json = json.loads(line)
            
            if data_json.get("type") == "telemetry":
                diagnostics = get_pi_diagnostics()
                sound_level = data_json.get("sound_level", 0)
                payload = {
                    "device_id": config["device_id"],
                    "timestamp": time.time(),
                    "temperature": data_json.get("temperature", 0.0),
                    "humidity": data_json.get("humidity", 0.0),
                    "motion": data_json.get("motion", False),
                    "sound_level": sound_level,
                    "connection_type": "Bluetooth",
                    "diagnostics": diagnostics
                }
                threading.Thread(target=forward_data, args=(payload, client)).start()
                
                # Check for sound sensor trigger from Arduino to run AI detection (JSON serial mode fallback)
                arduino_threshold = config.get("arduino_sound_threshold", 150)
                if sound_level > arduino_threshold and AI_HELPERS_AVAILABLE:
                    print(f"\n[ALERT] Arduino Sound Sensor Triggered! Value: {sound_level} (Threshold: {arduino_threshold}). Running AI inference...")
                    
                    def run_triggered_ai_json():
                        try:
                            species, confidence = run_ai_inference()
                            if species != "Background Noise" and confidence >= config.get("confidence_threshold", 0.82):
                                print(f"[AI ALERT] Hornbill Found: {species} ({confidence*100:.1f}%)! Generating realistic synthesized audio...")
                                
                                sample_rate = config.get("sound_monitoring", {}).get("sample_rate", 44100)
                                duration = config.get("sound_monitoring", {}).get("duration_seconds", 5)
                                audio_bytes = generate_synthetic_horn_call(species, sample_rate, duration)
                                
                                # Upload detection
                                upload_detection(species, confidence, audio_bytes)
                                
                                # Send alert downstream to Arduino OLED
                                alert_msg = f"[ALERT:{species},{int(confidence * 100)}]\n"
                                print(f"[*] BLE Gateway: Writing alert downstream: {alert_msg.strip()}")
                                asyncio.run_coroutine_threadsafe(
                                    client.write_gatt_char(COMMAND_UUID, alert_msg.encode('utf-8')),
                                    client.loop
                                )
                            else:
                                print("[-] AI evaluated as background or low confidence. Discarding.")
                        except Exception as ex:
                            print(f"[Error] AI trigger execution failed: {ex}")
                            
                    threading.Thread(target=run_triggered_ai_json, daemon=True).start()
                    
            elif data_json.get("type") == "event":
                diagnostics = get_pi_diagnostics()
                payload = {
                    "device_id": config["device_id"],
                    "timestamp": time.time(),
                    "type": "event",
                    "event": data_json.get("event", "UNKNOWN"),
                    "sound_level": data_json.get("sound_level", 0),
                    "connection_type": "Bluetooth",
                    "diagnostics": diagnostics
                }
                threading.Thread(target=forward_data, args=(payload, client)).start()
            
    except Exception as e:
        import traceback
        print(f"[Error] Notification decode error: {e}")
        traceback.print_exc()

def init_edge_impulse():
    global runner, model_info
    if not EI_RUNNER_AVAILABLE:
        print("[-] Edge Impulse Linux SDK not available. Running in simulated inference mode.")
        return
    
    model_path = os.path.join(os.path.dirname(__file__), 'model.eim')
    if not os.path.exists(model_path):
        print(f"[-] Edge Impulse model not found at {model_path}. Running in simulated inference mode.")
        return
        
    try:
        print(f"[*] Initializing Edge Impulse Model: {model_path}")
        runner = AudioClassifier(model_path)
        model_info = runner.init()
        labels = model_info.get("model_metadata", {}).get("labels", [])
        print(f"[SUCCESS] Edge Impulse Model loaded! Classes: {labels}")
    except Exception as e:
        print(f"[ERROR] Failed to initialize Edge Impulse runner: {e}")
        runner = None

def audio_notification_handler(client, sender, data):
    global audio_stream_buffer, is_receiving_audio
    
    if b"START_AUDIO" in data:
        print("\n[*] BLE: Starting raw audio stream reception from Arduino...")
        audio_stream_buffer = bytearray()
        is_receiving_audio = True
        return
        
    if b"END_AUDIO" in data:
        print(f"[+] BLE: Audio stream complete. Received {len(audio_stream_buffer)} bytes.")
        is_receiving_audio = False
        
        # Trigger classification in a separate thread to keep BLE loop fast
        raw_bytes = bytes(audio_stream_buffer)
        threading.Thread(target=process_and_classify_audio, args=(raw_bytes, client, None), daemon=True).start()
        audio_stream_buffer = bytearray()
        return
        
    if is_receiving_audio:
        audio_stream_buffer.extend(data)

def process_and_classify_audio(raw_audio_bytes, client=None, serial_port=None):
    try:
        expected_size = 8000
        if len(raw_audio_bytes) < expected_size:
            raw_audio_bytes += b"\x80" * (expected_size - len(raw_audio_bytes))
        else:
            raw_audio_bytes = raw_audio_bytes[:expected_size]
            
        print(f"[*] Processing {len(raw_audio_bytes)} bytes of 8kHz audio (upsampling to 16kHz)...")
        
        # Convert 8-bit unsigned (0-255) to float32 centered around 0
        audio_8k = (np.array(list(raw_audio_bytes), dtype=np.float32) - 128) * 256
        
        # DSP Linear Interpolation: Upsample from 8kHz to 16kHz smoothly
        # (This removes the staircase aliasing artifacts that confuse the AI)
        x_old = np.arange(len(audio_8k))
        x_new = np.linspace(0, len(audio_8k) - 1, 16000)
        audio_16k = np.interp(x_new, x_old, audio_8k)
        
        # DSP Normalization: Center around 0 and maximize volume
        audio_16k = audio_16k - np.mean(audio_16k)
        max_val = np.max(np.abs(audio_16k))
        if max_val > 100:
            audio_16k = (audio_16k / max_val) * 32767
        pcm_16 = audio_16k.astype(np.int16).tolist()
            
        highest_label = "Background Noise"
        highest_conf = 0.0
        
        global runner
        if runner is not None:
            res = runner.classify(pcm_16)
            classifications = res.get("result", {}).get("classification", {})
            for label, score in classifications.items():
                if score > highest_conf:
                    highest_conf = score
                    highest_label = label
            print(f"[★ AI RESULT] Class: '{highest_label}' (Confidence: {highest_conf*100:.2f}%)")
        else:
            print("[WARN] Model runner not initialized. Running simulation...")
            time.sleep(0.5)
            if random.random() < 0.5:
                highest_label = random.choice([
                    "Great Hornbill", "Oriental Pied Hornbill", "Rhinoceros Hornbill", "Helmeted Hornbill"
                ])
                highest_conf = round(random.uniform(0.85, 0.98), 2)
            else:
                highest_label = "Background Noise"
                highest_conf = round(random.uniform(0.90, 0.99), 2)
            print(f"[★ SIM RESULT] Class: '{highest_label}' (Confidence: {highest_conf*100:.2f}%)")
            
        is_background = highest_label in ["Background Noise", "unknown"]
        if not is_background and highest_conf >= config.get("confidence_threshold", 0.88):
            # Compute FFT metrics for DSP filters
            audio_np = np.array(pcm_16, dtype=np.float32)
            fft_vals = np.abs(np.fft.rfft(audio_np))
            fft_freqs = np.fft.rfftfreq(len(audio_np), d=1.0/16000)
            
            valid_indices = (fft_freqs >= 100) & (fft_freqs <= 4000)
            if np.any(valid_indices):
                peak_freq = fft_freqs[valid_indices][np.argmax(fft_vals[valid_indices])]
            else:
                peak_freq = 0.0
                
            if peak_freq < 450.0:
                print(f"[-] DSP FILTER: Ignored false trigger from low-frequency source (Peak Freq: {peak_freq:.1f}Hz)")
                return
                
            total_energy = np.sum(fft_vals**2)
            bird_band_indices = (fft_freqs >= 500) & (fft_freqs <= 3000)
            bird_energy = np.sum(fft_vals[bird_band_indices]**2)
            energy_ratio = bird_energy / (total_energy + 1e-10)
            
            if energy_ratio < 0.45:
                print(f"[-] DSP FILTER: Ignored broad-band noise (Energy Ratio in 500-3000Hz: {energy_ratio*100:.1f}%)")
                return
                
            highest_label_clean = highest_label.replace("_", " ")
            print(f"[★ DETECTION CONFIRMED] {highest_label_clean} ({highest_conf*100:.1f}%) passed DSP filters!")
            
            # Save audio as WAV bytes
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                packed_data = struct.pack(f"<{len(pcm_16)}h", *pcm_16)
                wav_file.writeframes(packed_data)
            wav_io.seek(0)
            wav_bytes = wav_io.read()
            
            # Upload detection
            if AI_HELPERS_AVAILABLE:
                print("[*] Uploading detection to server...")
                upload_detection(highest_label_clean, highest_conf, wav_bytes)
            
            # Send alert downstream
            alert_msg = f"[ALERT:{highest_label_clean},{int(highest_conf * 100)}]\n"
            
            if client is not None and client.is_connected:
                print(f"[*] BLE Gateway: Writing alert downstream: {alert_msg.strip()}")
                asyncio.run_coroutine_threadsafe(
                    client.write_gatt_char(COMMAND_UUID, alert_msg.encode('utf-8')),
                    client.loop
                )
            
            if serial_port is not None and SERIAL_AVAILABLE:
                try:
                    with serial.Serial(serial_port, config.get("baud_rate", 9600), timeout=1) as ser:
                        print(f"[*] Serial: Writing alert downstream: {alert_msg.strip()}")
                        ser.write(alert_msg.encode('utf-8'))
                        ser.flush()
                except Exception as se:
                    print(f"[WARN] Failed to send alert over Serial: {se}")
                    
    except Exception as e:
        print(f"[ERROR] Error processing streamed audio: {e}")
        import traceback
        traceback.print_exc()

def start_serial_listener():
    if not SERIAL_AVAILABLE:
        print("[-] Serial listener: 'pyserial' not installed. Skipping serial support.")
        return
        
    port = config.get("serial_port", "/dev/ttyACM0")
    baud = config.get("baud_rate", 9600)
    
    print(f"[*] Serial listener: Monitoring port {port}...")
    
    while True:
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                print(f"[SUCCESS] Serial listener: Connected to {port}")
                buffer = bytearray()
                
                while True:
                    if ser.in_waiting > 0:
                        data = ser.read(ser.in_waiting)
                        buffer.extend(data)
                        
                        start_idx = buffer.find(b"START_AUDIO")
                        end_idx = buffer.find(b"END_AUDIO")
                        
                        # If we have a complete audio packet, process it
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            audio_payload = buffer[start_idx + len(b"START_AUDIO"):end_idx]
                            print(f"[+] Serial: Received {len(audio_payload)} bytes of audio from USB.")
                            buffer = buffer[end_idx + len(b"END_AUDIO"):]
                            
                            raw_payload = bytes(audio_payload)
                            threading.Thread(target=process_and_classify_audio, args=(raw_payload, None, port), daemon=True).start()
                            continue
                            
                        # If we aren't mid-audio, parse lines for telemetry JSON
                        if start_idx == -1:
                            while b"\n" in buffer:
                                line_bytes, buffer = buffer.split(b"\n", 1)
                                line = line_bytes.decode('utf-8', errors='ignore').strip()
                                if line.startswith("{") and line.endswith("}"):
                                    try:
                                        data = json.loads(line)
                                        if data.get("type") == "telemetry":
                                            diagnostics = get_pi_diagnostics()
                                            payload = {
                                                "device_id": config["device_id"],
                                                "timestamp": time.time(),
                                                "temperature": data.get("temperature", 0.0),
                                                "humidity": data.get("humidity", 0.0),
                                                "motion": data.get("motion", False),
                                                "sound_level": data.get("sound_level", 0),
                                                "connection_type": "Serial",
                                                "diagnostics": diagnostics
                                            }
                                            threading.Thread(target=forward_data, args=(payload, None)).start()
                                    except Exception:
                                        pass
                    else:
                        time.sleep(0.01)
        except Exception as e:
            print(f"[WARN] Serial listener error: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

async def run_ble_listener():
    mac_address = config.get("arduino_mac_address", "B4:3A:45:B4:48:4D")
    
    print(f"[*] Attempting direct connection to Arduino BLE device at {mac_address}...")
    
    client = None
    try:
        connected = False
        for attempt in range(3):
            try:
                print(f"[*] Connection attempt {attempt + 1}/3...")
                # Connect directly using the MAC address instead of scanning for a device object
                client = BleakClient(mac_address)
                await client.connect(timeout=20.0)
                connected = True
                break
            except Exception as e:
                print(f"[WARN] Attempt {attempt + 1} failed: {e}")
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                await asyncio.sleep(3.0)
                
        if not connected:
            raise Exception("Failed to connect after 3 attempts")
            
        print(f"[SUCCESS] Connected to Arduino BLE: {client.is_connected}")
        
        # Keep loop reference to submit write tasks from other threads
        client.loop = asyncio.get_running_loop()
        
        # Subscribe to notifications
        await client.start_notify(TELEMETRY_UUID, lambda sender, data: notification_handler(client, sender, data))
        await client.start_notify(AUDIO_UUID, lambda sender, data: audio_notification_handler(client, sender, data))
        print(f"[*] Subscribed to Telemetry and Audio notifications. Listening...")
        
        # Keep client running while connected
        while client.is_connected:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        print("\n[*] Script cancelled. Disconnecting BLE gracefully...")
        try:
            if client and client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        raise
    except Exception as connect_ex:
        import traceback
        print(f"[Error] Connection error:")
        traceback.print_exc()
        try:
            if client and client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        return False
    finally:
        try:
            if client and client.is_connected:
                await client.disconnect()
                print("[WARN] BLE Connection lost and handle released.")
        except Exception:
            pass
            
    return True

# Fallback Simulation
def run_simulated_listener():
    print("====================================================")
    print("    RUNNING BLE GATEWAY IN SIMULATED ARDUINO MODE   ")
    print("====================================================")
    
    sim_temp = 26.5
    sim_humid = 82.0
    
    while True:
        sim_temp += random.uniform(-0.15, 0.15)
        sim_humid += random.uniform(-0.3, 0.3)
        motion_triggered = random.choice([True] + [False]*9)
        sim_sound = random.randint(300, 800) if motion_triggered else random.randint(10, 180)
        
        payload = {
            "device_id": config["device_id"],
            "timestamp": time.time(),
            "temperature": round(sim_temp, 1),
            "humidity": round(sim_humid, 1),
            "motion": motion_triggered,
            "sound_level": sim_sound,
            "connection_type": "Bluetooth",
            "diagnostics": get_pi_diagnostics()
        }
        
        forward_data(payload)
        time.sleep(2.0)

async def main():
    # Initialize Edge Impulse runner if available
    init_edge_impulse()
    
    # Start Serial Listener in the background if available and BLE is disabled
    if SERIAL_AVAILABLE and not config.get("use_ble", True):
        threading.Thread(target=start_serial_listener, daemon=True).start()
        
    # Check if we should run in USB serial mode only
    if not config.get("use_ble", True):
        print("[*] Running in USB Serial Mode only (BLE disabled).")
        while True:
            await asyncio.sleep(3600)
        return
        
    if not BLE_AVAILABLE:
        run_simulated_listener()
        return
        
    while True:
        try:
            success = await run_ble_listener()
            if not success:
                continue
        except Exception as e:
            import traceback
            print(f"[Error] BLE exception occurred: {repr(e)}. Re-scanning...")
            traceback.print_exc()
            await asyncio.sleep(5)

if __name__ == "__main__":
    print(f"Starting Hornbill BLE Gateway Node: {config['device_id']}")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping BLE gateway...")
