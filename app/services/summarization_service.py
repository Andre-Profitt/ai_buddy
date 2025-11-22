from app.services.llm_service import llm_service
from app.db.models import Group, User
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

class SummarizationService:
    async def update_group_summary(self, db: AsyncSession, group: Group, new_messages: list[str]):
        """
        Updates the rolling summary for a group based on new messages.
        """
        current_summary = group.summary or "No summary yet."
        messages_text = "\n".join(new_messages)
        
        system_prompt = (
            "You are a helpful assistant that summarizes group chat history for a planning bot named Jarvis. "
            "Update the current summary with the new messages. "
            "Focus on decisions made, constraints mentioned (time, location, budget), and pending questions. "
            "Keep it concise (under 200 words)."
        )
        
        user_prompt = f"Current Summary:\n{current_summary}\n\nNew Messages:\n{messages_text}\n\nUpdated Summary:"
        
        new_summary = await llm_service.generate_response(system_prompt, user_prompt)
        
        group.summary = new_summary
        db.add(group)
        await db.commit()
        logger.info(f"Updated summary for group {group.id}")

    async def update_user_summary(self, db: AsyncSession, user: User, new_messages: list[str]):
        """
        Updates the rolling summary for a user (preferences, tone).
        """
        current_preferences = user.preferences or {}
        current_summary = current_preferences.get("summary", "No details yet.")
        messages_text = "\n".join(new_messages)
        
        system_prompt = (
            "You are a helpful assistant. Extract user preferences and traits from their messages. "
            "Update the user profile summary. Focus on dietary restrictions, location preferences, and communication style. "
            "Keep it concise."
        )
        
        user_prompt = f"Current Profile:\n{current_summary}\n\nNew Messages:\n{messages_text}\n\nUpdated Profile:"
        
        new_summary = await llm_service.generate_response(system_prompt, user_prompt)
        
        # Update preferences JSON
        current_preferences["summary"] = new_summary
        user.preferences = current_preferences
        
        db.add(user)
        await db.commit()
        logger.info(f"Updated summary for user {user.id}")

summarization_service = SummarizationService()
