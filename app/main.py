import asyncio
import json
import random
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Kinetic Capacitor Guardian Backend", version="1.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMAGES
IMG_CLEAN = "IMAGE_DATA_CLEAN_OK"
IMG_FIRE  = "IMAGE_DATA_FIRE_DETECTED_CRITICAL"

class SystemState:
    def __init__(self):
        self.running = True
        self.chaos_mode = False
        self.derated = False
        self.risk_level = 0.0
        self.technician_dispatched = False
        self.part_inventory = {"KOM-204296": 5}
        self.current_temp = 55.0
        self.temp_velocity = 0.0

state = SystemState()

# --- MODELS ---
class TelemetryData(BaseModel):
    timestamp: str
    unit_id: str
    cumulative_operating_hours: float
    hybrid_bus_voltage: float
    capacitor_current: float
    inverter_temp: float
    swing_motor_torque: float
    risk_score: float
    system_status: str

class VisionResponse(BaseModel):
    fire_detected: bool
    confidence: float
    timestamp: str
    camera_source: str

# --- WEBSOCKETS ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try: await connection.send_text(message)
            except: pass

manager = ConnectionManager()

# --- PHYSICS ENGINE (DEMO OPTIMIZED) ---
async def generate_telemetry():
    hours = 4520.0
    while True:
        if state.running:
            hours += 0.0002
            
            # 1. Determine Target Temperature
            if state.derated:
                # Force target very low to ensure rapid drop to Green
                target_temp = 45.0 
            elif state.chaos_mode:
                target_temp = 150.0 
            else:
                target_temp = 55.0

            # 2. Move Current Temp towards Target
            if state.current_temp < target_temp:
                # Heating up (Standard rate)
                state.current_temp += 1.0 + random.uniform(0, 0.5)
            elif state.current_temp > target_temp:
                # Cooling down
                # DEMO FIX: Cooling is 10x faster when derated
                cooling_rate = 12.0 if state.derated else 1.0
                state.current_temp -= cooling_rate

            # 3. Clamp
            final_temp = max(20.0, state.current_temp)
            
            # 4. Risk Calculation (Thresholds)
            if final_temp > 90.0: state.risk_level = 1.0     # RED
            elif final_temp > 80.0: state.risk_level = 0.7   # ORANGE
            elif final_temp > 70.0: state.risk_level = 0.4   # YELLOW
            else: state.risk_level = 0.0                     # GREEN
            
            # 5. Torque & Current Physics
            if state.derated:
                swing_torque = 50.0
                capacitor_current = 60.0
            elif state.chaos_mode:
                swing_torque = 100.0
                capacitor_current = 150.0 + random.uniform(-20, 20)
            else:
                swing_torque = 100.0
                capacitor_current = 40.0 + random.uniform(-2, 2)

            payload = TelemetryData(
                timestamp=datetime.now().isoformat(),
                unit_id="HB-001",
                cumulative_operating_hours=round(hours, 2),
                hybrid_bus_voltage=580.0,
                capacitor_current=round(capacitor_current, 1),
                inverter_temp=round(final_temp, 1),
                swing_motor_torque=swing_torque,
                risk_score=round(state.risk_level, 2),
                system_status="DERATED" if state.derated else ("CRITICAL" if state.chaos_mode else "NORMAL")
            )
            await manager.broadcast(json.dumps(payload.dict()))
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(generate_telemetry())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)

# --- ENDPOINTS ---

@app.post("/simulation/inject-fault")
async def inject_fault():
    state.chaos_mode = True
    return {"status": "CHAOS"}

@app.post("/simulation/reset")
async def reset_sim():
    state.chaos_mode = False
    state.derated = False
    state.current_temp = 55.0
    return {"status": "NORMAL"}

@app.get("/vision/camera")
async def get_camera_feed():
    img = IMG_FIRE if state.chaos_mode else IMG_CLEAN
    status = "FIRE" if state.chaos_mode else "CLEAN"
    return {"image_base64": img, "status": status}

@app.get("/vision/validate", response_model=VisionResponse)
async def validate_vision():
    is_fire = state.chaos_mode
    return VisionResponse(
        fire_detected=is_fire,
        confidence=0.99,
        timestamp=datetime.now().isoformat(),
        camera_source="HB-001-CAM"
    )

@app.get("/inventory/check")
async def check_inventory(part_id: str = "KOM-204296"):
    return {"part_id": part_id, "quantity_available": 5, "location": "Warehouse-Austin-01"}

@app.post("/service/ticket")
async def create_ticket(severity: str = "CRITICAL", description: str = "Thermal Runaway"):
    return {"ticket_id": f"CASE-{uuid.uuid4().hex[:8].upper()}", "status": "OPEN"}

@app.post("/field-service/dispatch")
async def dispatch_technician(location: str = "Austin Site"):
    return {"technician": "Sarah Jenkins", "eta": "2 hours"}

@app.post("/iot/derate")
async def derate_machine(torque_limit: int = 50):
    state.derated = True
    return {"command": "SET_TORQUE_LIMIT", "value": torque_limit}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return "<h1>Backend Active</h1>"