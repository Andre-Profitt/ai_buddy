from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.services.telnyx_service import telnyx_service
from app.services.summon_service import summon_service
from app.services.llm_service import llm_service
from app.db.session import AsyncSessionLocal
from app.db.models import User, Group, Message
import logging
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/webhook")
async def telnyx_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives inbound webhooks from Telnyx.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("data", {}).get("event_type")
    
    if event_type == "message.received":
        background_tasks.add_task(process_inbound_message, payload)
    
    return {"status": "received"}

async def process_inbound_message(payload: dict):
    """
    Core logic to handle the inbound message.
    """
    data = payload.get("data", {}).get("payload", {})
    sender_num = data.get("from", {}).get("phone_number")
    text = data.get("text", "")
    to_list = data.get("to", [])
    
    # Normalize participants
    # 'to_list' contains all recipients including the bot if it's a group message
    # We need to extract all phone numbers to form the group signature
    participant_nums = sorted([p.get("phone_number") for p in to_list] + [sender_num])
    participant_nums = list(set(participant_nums)) # Deduplicate

    # Compliance Keywords
    keyword = text.strip().upper()
    if keyword == "STOP":
        # Telnyx handles opt-out automatically usually, but we should acknowledge or cleanup
        # For MVP, just return
        return {"status": "opt-out-processed"}
    elif keyword == "START":
        # Opt-in
        return {"status": "opt-in-processed"}
    elif keyword == "HELP":
        # Send help message
        await telnyx_service.send_direct_message(
            to_number=sender_num,
            text="Jarvis Help: Mention @jarvis in a group to get planning help. I only reply when summoned."
        )
        return {"status": "help-sent"}

    # Create a new DB session for this background task
    async with AsyncSessionLocal() as db:
        # 1. Persist/Update User (Sender)
        result = await db.execute(select(User).where(User.phone_number == sender_num))
        user = result.scalars().first()
        if not user:
            user = User(phone_number=sender_num)
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # 2. Persist/Update Group
        # For MVP, we identify groups by the sorted list of participants
        # In reality, Telnyx might provide a group_id, but let's stick to participant hash for now if needed,
        # or just check if a group exists with these exact participants.
        # Postgres ARRAY comparison can be tricky, so let's try to find a match.
        # For simplicity in MVP, we might just assume if it's a group MMS, we treat it as a group.
        
        # Check if it's a group message (more than 2 participants usually, or explicit group type)
        # Telnyx payload might have 'type': 'MMS' or similar.
        # Let's assume > 2 participants = Group, or if we want to support 1:1 DM as a "Group of 2".
        
        # Let's try to find a group with these exact participants
        # This is a naive search, might need optimization later.
        result = await db.execute(select(Group).filter(Group.participants == participant_nums))
        group = result.scalars().first()
        
        if not group:
            group = Group(participants=participant_nums)
            db.add(group)
            await db.commit()
            await db.refresh(group)

        # 3. Log Message
        message = Message(
            group_id=group.id,
            sender_id=user.id,
            content=text,
            is_bot=False
        )
        db.add(message)
        await db.commit()

        # 4. Summon Check
        if summon_service.is_summon(text):
            logger.info(f"Summon detected from {sender_num} in group {group.id}")
            
            # Rate Limit Checks
            from app.services.rate_limiter import rate_limiter
            
            if not await rate_limiter.check_user_limit(str(user.id)):
                logger.warning(f"User {user.id} hit rate limit")
                # Optionally send a "too many requests" DM
                return {"status": "rate_limited"}

            if not await rate_limiter.check_group_limit(str(group.id)):
                logger.warning(f"Group {group.id} hit rate limit")
                # Optionally send a "cooling down" message to group
                return {"status": "rate_limited"}
            
            # 5. Routing Logic
            if len(participant_nums) <= 8:
                # Group Reply
                group_summary = group.summary or "No previous context."
                system_prompt = (
                    f"You are Jarvis in a group text. "
                    f"Context: {group_summary} "
                    f"Respond only to the tagged request. Be concise and action-oriented. "
                    f"End with a next step (one question max)."
                )
                response_text = await llm_service.generate_response(system_prompt, text)
                
                await telnyx_service.send_group_message(
                    group_id=str(group.id),
                    text=response_text,
                    to_numbers=participant_nums
                )
                
                # Log Bot Response
                bot_msg = Message(
                    group_id=group.id,
                    sender_id=None, # Bot
                    content=response_text,
                    is_bot=True
                )
                db.add(bot_msg)
                await db.commit()
                
                # Trigger Summarization (Fire and Forget)
                # We pass the recent context or just the new interaction
                # For MVP, let's just summarize the last few messages including this one
                # ideally this should be a separate background task to not block
                # But since we are already in a background task, we can do it here or spawn another.
                # Let's spawn another to keep response fast if we were not already async.
                # Since we are awaiting LLM above, we are already "slow".
                
                # Let's just do it here for simplicity of state
                from app.services.summarization_service import summarization_service
                await summarization_service.update_group_summary(db, group, [f"{sender_num}: {text}", f"Jarvis: {response_text}"])
                
            else:
                # DM Fallback
                system_prompt = (
                    "You are Jarvis. The user tried to summon you in a group that is too large (>8 participants). "
                    "Explain that you can't reply to the group directly due to carrier limits. "
                    "Provide the answer to their request here in the DM, and suggest they paste it back to the group. "
                    "Keep it helpful and polite."
                )
                response_text = await llm_service.generate_response(system_prompt, text)
                
                await telnyx_service.send_direct_message(
                    to_number=sender_num,
                    text=response_text
                )
