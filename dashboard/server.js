const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const sqlite3 = require('sqlite3').verbose();

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = process.env.PORT || 3000;

// Initialize SQLite Database
const db = new sqlite3.Database(path.join(__dirname, 'database.sqlite'), (err) => {
  if (err) console.error('Error opening database', err);
  else console.log('Connected to SQLite database.');
});

// Create tables
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS detections (
    id TEXT PRIMARY KEY,
    device_id TEXT,
    timestamp REAL,
    species TEXT,
    scientific_name TEXT,
    confidence REAL,
    frequency TEXT,
    danger_status TEXT,
    audio_url TEXT,
    description TEXT,
    latitude REAL,
    longitude REAL,
    bearing REAL,
    distance REAL,
    is_hornbill INTEGER
  )`);
});

// Ensure directories exist
const publicDir = path.join(__dirname, 'public');
const recordingsDir = path.join(publicDir, 'recordings');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir);
}
if (!fs.existsSync(recordingsDir)) {
  fs.mkdirSync(recordingsDir);
}

// Middleware
app.use(express.json());
app.use(express.static(publicDir));

// Multer Storage Configuration for Audio WAV Uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, recordingsDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, 'call-' + uniqueSuffix + path.extname(file.originalname || '.wav'));
  }
});
const upload = multer({ storage: storage });

let detectionHistory = [];

// Load last 50 detections into memory for fast WebSocket init
db.all(`SELECT * FROM detections ORDER BY timestamp DESC LIMIT 50`, [], (err, rows) => {
  if (!err) {
    detectionHistory = rows.reverse();
    console.log(`Loaded ${detectionHistory.length} historical detections from database.`);
  }
});

// ------------------------------------------------------------------
// REST API ENDPOINTS
// ------------------------------------------------------------------

// 1. Post new AI audio detection
app.post('/api/detections', upload.single('audio'), (req, res) => {
  const payloadStr = req.body.payload || req.body;
  let payload;
  
  if (typeof payloadStr === 'string') {
    try { payload = JSON.parse(payloadStr); } 
    catch (e) { return res.status(400).json({ error: "Invalid JSON payload" }); }
  } else {
    payload = payloadStr;
  }

  // Create standardized detection event
  const detectionEvent = {
    id: 'det_' + Date.now() + '_' + Math.floor(Math.random()*1000),
    device_id: payload.device_id || 'unknown',
    timestamp: Date.now(),
    species: payload.species || 'Unknown Bird',
    confidence: payload.confidence || 0.0,
    latitude: payload.latitude || 4.5975, // Default near Temenggor
    longitude: payload.longitude || 101.0901,
    audio_filename: req.file ? req.file.filename : null
  };

  // Insert into SQLite
  const stmt = db.prepare(`INSERT INTO detections (
    id, device_id, timestamp, species, confidence, latitude, longitude, audio_url
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`);
  
  stmt.run([
    detectionEvent.id, detectionEvent.device_id, detectionEvent.timestamp,
    detectionEvent.species, detectionEvent.confidence, detectionEvent.latitude,
    detectionEvent.longitude, detectionEvent.audio_filename
  ], function(err) {
    if (err) console.error("Database Insert Error:", err);
  });
  stmt.finalize();

  // Update memory array
  detectionHistory.push(detectionEvent);
  if (detectionHistory.length > 50) detectionHistory.shift();

  // Broadcast to all connected Web UI clients
  broadcastToClients({ type: 'detection', data: detectionEvent });
  
  console.log(`[API] Logged detection: ${detectionEvent.species} (${detectionEvent.confidence*100}%)`);
  res.status(201).json({ status: 'success', id: detectionEvent.id });
});

// ------------------------------------------------------------------
// WEBSOCKET SERVER
// ------------------------------------------------------------------

wss.on('connection', (ws) => {
  console.log('[WebSocket] Dashboard Client connected.');
  
  // Send immediate initialization state
  ws.send(JSON.stringify({
    type: 'init',
    detections: detectionHistory
  }));
});

function broadcastToClients(messageObj) {
  const messageStr = JSON.stringify(messageObj);
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(messageStr);
    }
  });
}

// ------------------------------------------------------------------
// START SERVER
// ------------------------------------------------------------------
server.listen(PORT, '0.0.0.0', () => {
  console.log(`--------------------------------------------------`);
  console.log(`BioShield AI Gateway Server running on port ${PORT}`);
  console.log(`Waiting for acoustic detections...`);
  console.log(`--------------------------------------------------`);
});
