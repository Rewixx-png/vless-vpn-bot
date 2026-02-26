import os
import asyncio
import subprocess
import logging
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psutil

from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Admin API Started")
    yield
    logger.info("🛑 Admin API Stopped")

app = FastAPI(title="VLESS VPN Admin API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    from database.core import async_session_factory
    return async_session_factory

def require_admin(request: Request):
    pass

class HealthResponse(BaseModel):
    status: str
    cpu: float
    memory: float
    uptime: int

class SubListResponse(BaseModel):
    total: int
    items: list
    page: int
    per_page: int

class StatsResponse(BaseModel):
    total_subs: int
    active_subs: int
    dead_subs: int
    by_region: dict
    avg_speed: float

class SystemStatusResponse(BaseModel):
    bot: dict
    worker: dict
    beat: dict
    checker: dict
    redis: dict
    database: dict

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    uptime = int(asyncio.get_event_loop().time())
    return HealthResponse(status="ok", cpu=cpu, memory=mem, uptime=uptime)

@app.get("/api/subs", response_model=SubListResponse)
async def get_subs(
    page: int = 1,
    per_page: int = 50,
    region: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
):
    from database.repo import SubRepo
    from database.core import async_session_factory
    
    async with async_session_factory() as session:
        from sqlalchemy import select, func, desc
        from database.models import Subscription
        
        stmt = select(Subscription)
        count_stmt = select(func.count(Subscription.id))
        
        if region:
            stmt = stmt.where(Subscription.region == region)
            count_stmt = count_stmt.where(Subscription.region == region)
        
        if is_active is not None:
            stmt = stmt.where(Subscription.is_active == is_active)
            count_stmt = count_stmt.where(Subscription.is_active == is_active)
        
        if search:
            stmt = stmt.where(Subscription.vless_key.like(f"%{search}%"))
            count_stmt = count_stmt.where(Subscription.vless_key.like(f"%{search}%"))
        
        stmt = stmt.order_by(desc(Subscription.speed_mbps))
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        
        result = await session.execute(stmt)
        subs = result.scalars().all()
        
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        items = []
        for s in subs:
            items.append({
                "id": s.id,
                "region": s.region,
                "latency_ms": s.latency_ms,
                "speed_mbps": s.speed_mbps,
                "is_active": s.is_active,
                "stability_streak": s.stability_streak,
                "death_count": s.death_count,
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                "vless_key": s.vless_key[:80] + "..." if len(s.vless_key) > 80 else s.vless_key
            })
        
        return SubListResponse(total=total, items=items, page=page, per_page=per_page)

@app.delete("/api/subs/{sub_id}")
async def delete_sub(sub_id: int):
    from database.repo import SubRepo
    try:
        await SubRepo.delete_sub(sub_id)
        return {"status": "ok", "message": f"Sub {sub_id} deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/subs/cleanup")
async def cleanup_dead_subs(max_deaths: int = 3):
    from database.repo import SubRepo
    count = await SubRepo.cleanup_dead_subs(max_deaths=max_deaths)
    return {"status": "ok", "deleted": count}

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    from database.repo import SubRepo, StatsRepo
    from database.core import async_session_factory
    
    try:
        counts = await StatsRepo.get_regions_counts()
    except:
        counts = {}
    
    async with async_session_factory() as session:
        from sqlalchemy import select, func, and_
        from database.models import Subscription
        
        total_result = await session.execute(select(func.count(Subscription.id)))
        total = total_result.scalar() or 0
        
        active_result = await session.execute(
            select(func.count(Subscription.id)).where(Subscription.is_active == True)
        )
        active = active_result.scalar() or 0
        
        dead_result = await session.execute(
            select(func.count(Subscription.id)).where(Subscription.is_active == False)
        )
        dead = dead_result.scalar() or 0
        
        speed_result = await session.execute(
            select(func.avg(Subscription.speed_mbps)).where(Subscription.is_active == True)
        )
        avg_speed = speed_result.scalar() or 0.0
        
        return StatsResponse(
            total_subs=total,
            active_subs=active,
            dead_subs=dead,
            by_region=counts,
            avg_speed=round(avg_speed, 2)
        )

@app.get("/api/regions")
async def get_regions():
    from database.repo import SubRepo
    regions = await SubRepo.get_regions()
    return {"regions": regions}

class SourceResponse(BaseModel):
    id: int
    url: str
    is_enabled: bool
    last_fetch: Optional[str]

@app.get("/api/sources")
async def get_sources():
    from database.repo import SourceRepo
    sources = await SourceRepo.get_all_sources()
    return {
        "sources": [
            {
                "id": s.id,
                "url": s.url,
                "is_enabled": s.is_enabled,
                "last_fetch": s.last_fetch.isoformat() if s.last_fetch else None
            }
            for s in sources
        ]
    }

@app.post("/api/sources")
async def add_source(url: str, enabled: bool = True):
    from database.repo import SourceRepo
    await SourceRepo.add_source(url, enabled)
    return {"status": "ok"}

@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: int):
    from database.repo import SourceRepo
    await SourceRepo.delete_source(source_id)
    return {"status": "ok"}

@app.put("/api/sources/{source_id}")
async def toggle_source(source_id: int, enabled: bool):
    from database.repo import SourceRepo
    await SourceRepo.toggle_source(source_id, enabled)
    return {"status": "ok"}

class SettingsResponse(BaseModel):
    maintenance_mode: bool
    collector_enabled: bool
    external_sub_url: str
    public_domain: str

@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    from database.repo import SystemRepo
    
    maintenance = await SystemRepo.get_config("maintenance_mode")
    collector = await SystemRepo.get_config("collector_enabled")
    external_url = await SystemRepo.get_config("external_sub_url")
    
    return SettingsResponse(
        maintenance_mode=maintenance == "true",
        collector_enabled=collector != "false",
        external_sub_url=external_url or "",
        public_domain=config.public_domain or ""
    )

@app.put("/api/settings")
async def update_settings(
    maintenance_mode: Optional[bool] = None,
    collector_enabled: Optional[bool] = None,
    external_sub_url: Optional[str] = None,
    public_domain: Optional[str] = None
):
    from database.repo import SystemRepo
    
    if maintenance_mode is not None:
        await SystemRepo.set_config("maintenance_mode", str(maintenance_mode).lower())
    
    if collector_enabled is not None:
        await SystemRepo.set_config("collector_enabled", str(collector_enabled).lower())
    
    if external_sub_url is not None:
        await SystemRepo.set_config("external_sub_url", external_sub_url)
    
    return {"status": "ok"}

class UsersResponse(BaseModel):
    total: int
    items: list

@app.get("/api/users")
async def get_users(page: int = 1, per_page: int = 50):
    from database.repo import UserRepo
    
    users = await UserRepo.get_all_users()
    total = len(users)
    
    start = (page - 1) * per_page
    end = start + per_page
    page_users = users[start:end]
    
    return UsersResponse(
        total=total,
        items=[
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "subscription_limit": u.subscription_limit,
                "use_fragment": u.use_fragment,
                "is_premium": u.is_premium,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in page_users
        ]
    )

@app.get("/api/groups")
async def get_groups():
    from database.repo import GroupRepo
    groups = await GroupRepo.get_all_groups()
    return {
        "groups": [
            {
                "id": g.id,
                "user_id": g.user_id,
                "name": g.name,
                "country_filter": g.country_filter,
                "tags_filter": g.tags_filter
            }
            for g in groups
        ]
    }

@app.get("/api/system", response_model=SystemStatusResponse)
async def get_system_status():
    def get_pm2_status(name: str) -> dict:
        try:
            result = subprocess.run(
                ["pm2", "show", name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                status = "unknown"
                mem = "0mb"
                cpu = "0%"
                uptime = "0"
                for line in lines:
                    if "status" in line.lower():
                        status = line.split(":")[-1].strip()
                    if "memory" in line.lower():
                        mem = line.split(":")[-1].strip()
                    if "cpu" in line.lower():
                        cpu = line.split(":")[-1].strip()
                    if "uptime" in line.lower():
                        uptime = line.split(":")[-1].strip()
                return {"status": status, "memory": mem, "cpu": cpu, "uptime": uptime}
        except:
            pass
        return {"status": "unknown", "memory": "0mb", "cpu": "0%", "uptime": "0"}
    
    bot_status = get_pm2_status("VPN_Bot")
    worker_status = get_pm2_status("VPN_Worker")
    beat_status = get_pm2_status("VPN_Beat")
    checker_status = get_pm2_status("CheckerSVC")
    
    redis_status = {"status": "unknown"}
    try:
        result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=2)
        if "PONG" in result.stdout:
            redis_status = {"status": "online"}
    except:
        pass
    
    db_status = {"status": "unknown"}
    try:
        from database.repo import StatsRepo
        await StatsRepo.get_public_stats()
        db_status = {"status": "online"}
    except:
        pass
    
    return SystemStatusResponse(
        bot=bot_status,
        worker=worker_status,
        beat=beat_status,
        checker=checker_status,
        redis=redis_status,
        database=db_status
    )

@app.post("/api/system/restart/{service}")
async def restart_service(service: str):
    valid_services = ["VPN_Bot", "VPN_Worker", "VPN_Beat", "CheckerSVC", "hatani-bot", "tiktok-bot"]
    if service not in valid_services:
        raise HTTPException(status_code=400, detail="Invalid service name")
    
    try:
        subprocess.run(["pm2", "restart", service], timeout=30)
        return {"status": "ok", "message": f"{service} restarted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/stop/{service}")
async def stop_service(service: str):
    valid_services = ["VPN_Bot", "VPN_Worker", "VPN_Beat", "CheckerSVC"]
    if service not in valid_services:
        raise HTTPException(status_code=400, detail="Invalid service name")
    
    try:
        subprocess.run(["pm2", "stop", service], timeout=30)
        return {"status": "ok", "message": f"{service} stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/run-collector")
async def run_collector():
    from tasks import run_collector_task
    run_collector_task.delay()
    return {"status": "ok", "message": "Collector task queued"}

@app.post("/api/tasks/run-stability")
async def run_stability():
    from tasks import check_stability_task
    check_stability_task.delay()
    return {"status": "ok", "message": "Stability check task queued"}

@app.get("/api/logs/{service}")
async def get_logs(service: str, lines: int = 50):
    valid_services = ["VPN_Bot", "VPN_Worker", "VPN_Beat", "CheckerSVC"]
    if service not in valid_services:
        raise HTTPException(status_code=400, detail="Invalid service")
    
    try:
        result = subprocess.run(
            ["pm2", "logs", service, "--nostream", "--lines", str(lines)],
            capture_output=True, text=True, timeout=10
        )
        return {"logs": result.stdout + result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
