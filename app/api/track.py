"""網頁追蹤任務 API（不需登入，用 guest_id 識別）"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime

router = APIRouter(prefix="/api/track", tags=["track"])


@router.post("/start")
async def track_start(request: Request):
    """網頁用戶開始追蹤時呼叫，建立 tracking_task 記錄"""
    body = await request.json()
    guest_id = body.get("guest_id", "")
    hospital_code = body.get("hospital_code", "")
    department = body.get("department", "")
    doctor_name = body.get("doctor_name")
    clinic_room = body.get("clinic_room")
    session = body.get("session")
    user_number = body.get("user_number", 0)
    apns_token = body.get("apns_token") or None  # iOS App 帶來的 device token（選填）

    if not guest_id or not hospital_code or not department:
        return JSONResponse({"ok": False, "error": "缺少必填欄位"}, status_code=400)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.tracking_task import TrackingTask, TaskStatus

    async with async_session() as db:
        task = TrackingTask(
            user_id=None,
            source="web",
            guest_id=guest_id,
            hospital_code=hospital_code,
            department=department,
            doctor_name=doctor_name,
            clinic_room=clinic_room,
            session=session,
            user_number=user_number,
            status=TaskStatus.ACTIVE,
            apns_token=apns_token,
            created_at=datetime.utcnow(),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    return {"ok": True, "track_id": task.id}


@router.put("/{track_id}/stop")
async def track_stop(track_id: int, request: Request):
    """停止追蹤（cancelled / completed）"""
    body = await request.json()
    guest_id = body.get("guest_id", "")
    reason = body.get("reason", "cancelled")  # cancelled | completed

    if not guest_id:
        return JSONResponse({"ok": False, "error": "缺少 guest_id"}, status_code=400)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.tracking_task import TrackingTask, TaskStatus

    status_map = {
        "completed": TaskStatus.COMPLETED,
        "cancelled": TaskStatus.CANCELLED,
    }
    new_status = status_map.get(reason, TaskStatus.CANCELLED)

    async with async_session() as db:
        result = await db.execute(
            select(TrackingTask).where(
                TrackingTask.id == track_id,
                TrackingTask.guest_id == guest_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return JSONResponse({"ok": False, "error": "追蹤不存在"}, status_code=404)
        task.status = new_status
        await db.commit()

    return {"ok": True}
