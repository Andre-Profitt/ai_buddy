import httpx
from app.core.config import settings
from typing import List

TELNYX_MESSAGING_URL = "https://api.telnyx.com/v2/messages"

class TelnyxService:
    def __init__(self):
        self.api_key = settings.TELNYX_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def send_group_message(self, group_id: str, text: str, to_numbers: List[str]):
        """
        Sends a Group MMS.
        Note: Telnyx Group MMS API might differ slightly from standard SMS.
        For MVP, we assume we can send to a list of numbers or a group ID if supported.
        If 'group_id' is a Telnyx-managed group ID, we use that.
        Otherwise, we might need to construct a group MMS payload.
        """
        # MVP Implementation: Using standard message creation with multiple recipients if supported
        # or iterating (which is not true MMS).
        # Real Group MMS usually requires a specific payload or 'group_id'.
        # For this MVP, we will assume the 'to' field accepts a list or we use the group_id if Telnyx provides one.
        
        # According to Telnyx docs, Group MMS is often handled by sending to multiple recipients
        # and setting 'subject' or 'group_id' context, or it's handled automatically by the carrier
        # if we send to multiple numbers.
        # Let's try sending to the list of numbers.
        
        payload = {
            "from": settings.TELNYX_PHONE_NUMBER,
            "to": to_numbers,
            "text": text,
            "subject": "Jarvis Group Chat" # Optional, helps some carriers treat as group
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(TELNYX_MESSAGING_URL, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_direct_message(self, to_number: str, text: str):
        """
        Sends a direct SMS/MMS.
        """
        payload = {
            "from": settings.TELNYX_PHONE_NUMBER,
            "to": to_number,
            "text": text
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(TELNYX_MESSAGING_URL, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

telnyx_service = TelnyxService()
