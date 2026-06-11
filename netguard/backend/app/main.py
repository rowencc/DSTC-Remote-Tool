from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import config
from app.api import devices, alerts, system

app = FastAPI(
    title=config["app"]["name"],
    version=config["app"]["version"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(system.router, prefix="/api/system", tags=["system"])

@app.get("/")
def root():
    return {"message": "NetGuard API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
