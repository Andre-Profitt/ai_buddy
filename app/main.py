from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.endpoints import router as api_router
from app.api.v1.admin import router as admin_router

app = FastAPI(title=settings.PROJECT_NAME)

app.include_router(api_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")

@app.get("/")
async def root():
    return {"message": "Jarvis is online"}
