"""追蹤任務管理服務"""

import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session as default_session
from app.models.user import User
from app.models.tracking_task import TrackingTask, TaskStatus, NotifyMode

logger = logging.getLogger(__name__)


class TrackerService:
    """管理用戶的看診追蹤任務"""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or default_session

    async def _get_or_create_user(self, session: AsyncSession, line_user_id: str) -> User:
        """取得或建立用戶"""
        result = await session.execute(
            select(User).where(User.line_user_id == line_user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(line_user_id=line_user_id)
            session.add(user)
            await session.flush()
        return user

    async def create_task(
        self,
        line_user_id: str,
        hospital_code: str,
        department: str,
        doctor_name: str | None,
        clinic_room: str | None,
        user_number: int,
        threshold: int = 5,
        notify_mode: str = NotifyMode.LIGHT.value,
        session_time: str | None = None,
    ) -> TrackingTask:
        """建立追蹤任務"""
        async with self._session_factory() as session:
            user = await self._get_or_create_user(session, line_user_id)

            task = TrackingTask(
                user_id=user.id,
                hospital_code=hospital_code,
                department=department,
                doctor_name=doctor_name,
                clinic_room=clinic_room,
                user_number=user_number,
                threshold=threshold,
                notify_mode=notify_mode,
                session=session_time,
                status=TaskStatus.ACTIVE,
            )
            session.add(task)
            await session.commit()
            logger.info(
                f"建立追蹤: user={line_user_id} hospital={hospital_code} "
                f"dept={department} number={user_number}"
            )
            return task

    async def get_active_tasks(self, line_user_id: str) -> list[TrackingTask]:
        """取得某用戶的所有活躍追蹤任務"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrackingTask)
                .join(User, TrackingTask.user_id == User.id)
                .where(
                    User.line_user_id == line_user_id,
                    TrackingTask.status == TaskStatus.ACTIVE,
                )
            )
            return list(result.scalars().all())

    async def get_all_active_tasks(self) -> list[tuple[TrackingTask, str | None]]:
        """取得所有活躍追蹤任務（所有來源），用於 Celery 通知比對

        回傳 (task, line_user_id)，web/guest 追蹤的 line_user_id 為 None
        """
        async with self._session_factory() as session:
            # LINE 追蹤：JOIN User 取得 line_user_id
            line_result = await session.execute(
                select(TrackingTask, User.line_user_id)
                .join(User, TrackingTask.user_id == User.id)
                .where(TrackingTask.status == TaskStatus.ACTIVE)
            )
            line_tasks = [(row[0], row[1]) for row in line_result.all()]

            # Web/其他來源：user_id 為 NULL
            web_result = await session.execute(
                select(TrackingTask)
                .where(
                    TrackingTask.status == TaskStatus.ACTIVE,
                    TrackingTask.user_id.is_(None),
                )
            )
            web_tasks = [(row[0], None) for row in web_result.all()]

            return line_tasks + web_tasks

    async def update_last_remaining(self, task_id: int, remaining: int):
        """更新上次通知時的剩餘人數"""
        async with self._session_factory() as session:
            await session.execute(
                update(TrackingTask)
                .where(TrackingTask.id == task_id)
                .values(last_notified_remaining=remaining)
            )
            await session.commit()

    async def mark_notified(self, task_id: int):
        """標記任務已通知"""
        async with self._session_factory() as session:
            await session.execute(
                update(TrackingTask)
                .where(TrackingTask.id == task_id)
                .values(
                    status=TaskStatus.NOTIFIED,
                    notified_at=__import__("datetime").datetime.utcnow(),
                )
            )
            await session.commit()

    async def cancel_all_tasks(self, line_user_id: str) -> int:
        """取消某用戶的所有活躍追蹤任務"""
        async with self._session_factory() as session:
            user_result = await session.execute(
                select(User).where(User.line_user_id == line_user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                return 0

            result = await session.execute(
                update(TrackingTask)
                .where(
                    TrackingTask.user_id == user.id,
                    TrackingTask.status == TaskStatus.ACTIVE,
                )
                .values(status=TaskStatus.CANCELLED)
            )
            await session.commit()
            return result.rowcount
