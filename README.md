# TinyML AI Audio Detection - Hornbill Telemetry Project

This project uses TinyML to perform real-time, edge-based AI audio detection for various species of Hornbills in their natural environment. It combines an Arduino/M5Stack sensor node, a Raspberry Pi Edge Gateway, and a local web dashboard to monitor telemetry and detection events.

## Repository Structure

- `arduino/hornbill_sensor_node/`: The C++ Arduino sketch containing the Edge Impulse inferencing logic and MQTT/BLE communication for the M5Stack CoreS3 or similar ESP32 hardware.
- `raspberry_pi/`: Python scripts that act as a gateway bridge, reading telemetry/serial data from the Arduino, generating Pi system diagnostics, and forwarding everything to the dashboard.
- `dashboard/`: A Node.js and Express web application that provides a beautiful, real-time interface to view environmental telemetry and Hornbill AI detection alerts.

---

## 💻 Hardware Requirements

To fully run the end-to-end system, you will need:
- **Sensor Node:** M5Stack CoreS3 (or similar ESP32-based microcontroller with a microphone).
- **Edge Gateway:** Raspberry Pi (3B, 4, or 5) running Raspberry Pi OS.
- **Server/Dashboard:** A PC, laptop, or server capable of running Node.js. (Can also be hosted on the Raspberry Pi if desired).
- **Connectivity:** A local Wi-Fi network for the MQTT/HTTP communication.

---

## 🛠 Setup & Installation

### 1. Dashboard Setup
The web dashboard runs on Node.js and serves the real-time UI.
1. Ensure you have [Node.js](https://nodejs.org/) installed on your machine.
2. Navigate to the dashboard directory:
   ```bash
   cd dashboard
   ```
3. Install the dependencies:
   ```bash
   npm install
   ```

### 2. Raspberry Pi Gateway Setup
The gateway reads data from the sensor node and forwards it to the dashboard.
1. Ensure you have Python 3 installed.
2. Navigate to the Raspberry Pi directory:
   ```bash
   cd raspberry_pi
   ```
3. Install the required Python dependencies (such as `pyserial` and `requests`). You can use `pip`:
   ```bash
   pip install pyserial requests
   ```
4. Review `config.json` in the `raspberry_pi` directory to ensure the `server_url` matches where your dashboard will run (e.g., `http://localhost:3000` or the specific IP of the dashboard machine) and the `serial_port` matches your Arduino.

### 3. Arduino / M5Stack Setup
1. Open the `arduino/hornbill_sensor_node/hornbill_sensor_node.ino` file using the Arduino IDE.
2. Make sure you have installed the **M5Unified** and **PubSubClient** libraries.
3. You will also need the specific **Edge Impulse Inferencing Library** (`Coconutmilk-project-1_inferencing.h`). If this is not installed, you'll need to export the library from your Edge Impulse project as an Arduino library and add it via `Sketch > Include Library > Add .ZIP Library`.
4. Configure your WiFi credentials within the `hornbill_sensor_node.ino` file:
   ```cpp
   const char* WIFI_SSID     = "Your_SSID";
   const char* WIFI_PASSWORD = "Your_PASSWORD";
   ```
5. Compile and upload the sketch to your board.

---

## 🚀 Usage

To start the full telemetry and monitoring stack, follow these steps in order:

**1. Start the Dashboard**
In a terminal window, start the Node.js server:
```bash
cd dashboard
npm start
```
The dashboard will be available at `http://localhost:3000`.

**2. Start the Raspberry Pi Gateway**
In a separate terminal window, start the gateway script. It has a simulated fallback mode if no Arduino is connected, meaning you can test it immediately!
```bash
cd raspberry_pi
python pi_gateway.py
```
*(Alternatively, you can run `python mqtt_gateway.py` or `python ble_gateway.py` depending on your connection method.)*

**3. Power on the Sensor Node**
Connect the Arduino/M5Stack to power. It will begin listening to ambient audio, running inferencing, and sending telemetry data over serial or MQTT. The dashboard will automatically update with real-time graphs and Hornbill detection alerts.
