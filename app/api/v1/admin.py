from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from app.db.session import get_db
from app.db.models import User, Group, Message

router = APIRouter()

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Simple admin view for MVP.
    """
    user_count = await db.scalar(select(func.count(User.id)))
    group_count = await db.scalar(select(func.count(Group.id)))
    message_count = await db.scalar(select(func.count(Message.id)))
    
    # Calculate summons (approximate by messages where is_bot=True)
    bot_msg_count = await db.scalar(select(func.count(Message.id)).where(Message.is_bot == True))

    return {
        "users": user_count,
        "groups": group_count,
        "total_messages": message_count,
        "jarvis_replies": bot_msg_count
    }
