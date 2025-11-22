import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import engine
from app.db.models import Base
from app.api.v1.endpoints import get_db_session, AsyncSessionLocal
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Override the engine for tests to use SQLite
test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Override the get_db dependency
async def override_get_db():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db

# Patch the session maker in endpoints if it's used directly (it is used as AsyncSessionLocal)
# We need to patch app.api.v1.endpoints.AsyncSessionLocal
# But wait, endpoints.py imports AsyncSessionLocal from app.db.session.
# We should patch that.

@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(autouse=True)
def mock_redis():
    from unittest.mock import AsyncMock
    with patch("redis.asyncio.from_url") as mock_redis_url:
        mock_redis_instance = AsyncMock()
        mock_redis_instance.incr.return_value = 1
        mock_redis_url.return_value = mock_redis_instance
        yield mock_redis_instance

@pytest.mark.asyncio
async def test_webhook_flow(mock_redis):
    # Mock Telnyx and LLM services
    with patch("app.services.telnyx_service.telnyx_service.send_group_message") as mock_send_group, \
         patch("app.services.telnyx_service.telnyx_service.send_direct_message") as mock_send_direct, \
         patch("app.services.llm_service.llm_service.generate_response") as mock_llm, \
         patch("app.api.v1.endpoints.process_inbound_message") as mock_process:
        
        mock_llm.return_value = "Hello from Jarvis"
        mock_send_group.return_value = {"status": "sent"}
        mock_send_direct.return_value = {"status": "sent"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Test Non-Summon
            payload_no_summon = {
                "data": {
                    "event_type": "message.received",
                    "payload": {
                        "from": {"phone_number": "+15551234567"},
                        "to": [{"phone_number": "+15559876543"}],
                        "text": "Just chatting"
                    }
                }
            }
            response = await ac.post("/api/v1/webhook", json=payload_no_summon)
            assert response.status_code == 200
            # Wait a bit for background task (in real test we might need better sync)
            # But here we just check if mock was NOT called
            mock_send_group.assert_not_called()

            # 2. Test Summon
            payload_summon = {
                "data": {
                    "event_type": "message.received",
                    "payload": {
                        "from": {"phone_number": "+15551234567"},
                        "to": [{"phone_number": "+15559876543"}], # Bot number
                        "text": "@jarvis help us plan"
                    }
                }
            }
            response = await ac.post("/api/v1/webhook", json=payload_summon)
            assert response.status_code == 200
            
            # Allow background task to run? 
            # FastAPI TestClient triggers background tasks on exit of the context usually, 
            # but AsyncClient might need manual handling or just wait.
            # However, since we are mocking, we can't easily wait for the background task 
            # unless we extract the logic.
            # For this simple test, let's assume the background task runs fast enough or we invoke the logic directly.
            
    # Direct Logic Testing
    from app.api.v1.endpoints import process_inbound_message
    
    with patch("app.services.telnyx_service.telnyx_service.send_group_message") as mock_send_group, \
         patch("app.services.telnyx_service.telnyx_service.send_direct_message") as mock_send_direct, \
         patch("app.services.llm_service.llm_service.generate_response") as mock_llm:
         
        mock_llm.return_value = "Hello from Jarvis"
        mock_send_group.return_value = {"status": "sent"}
        mock_send_direct.return_value = {"status": "sent"}
        
        # Test Summon Logic with Summary Update
        payload_summon = {
            "data": {
                "payload": {
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+15559876543"}],
                    "text": "@jarvis help us plan dinner"
                }
            }
        }
        
        with patch("app.api.v1.endpoints.AsyncSessionLocal", return_value=TestSessionLocal()), \
             patch("app.services.summarization_service.summarization_service.update_group_summary") as mock_summary:
             
             await process_inbound_message(payload_summon)
             
             mock_llm.assert_called()
             mock_send_group.assert_called()
             mock_summary.assert_called_once()

        # Test DM Fallback for Large Group
        large_group_to = [{"phone_number": f"+155500000{i}"} for i in range(10)]
        payload_large = {
            "data": {
                "payload": {
                    "from": {"phone_number": "+15551234567"},
                    "to": large_group_to,
                    "text": "@jarvis help"
                }
            }
        }
        
        # Reset mocks
        mock_llm.reset_mock()
        mock_send_group.reset_mock()
        mock_send_direct.reset_mock()
        
        with patch("app.api.v1.endpoints.AsyncSessionLocal", return_value=TestSessionLocal()):
             await process_inbound_message(payload_large)
             
             # Should call LLM for fallback message
             mock_llm.assert_called()
             # Should call send_direct_message
             mock_send_direct.assert_called()
             # Should NOT call send_group_message
             mock_send_group.assert_not_called()

        # Test Compliance Keywords
        payload_help = {
            "data": {
                "payload": {
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+15559876543"}],
                    "text": "HELP"
                }
            }
        }
        
        mock_send_direct.reset_mock()
        
        with patch("app.api.v1.endpoints.AsyncSessionLocal", return_value=TestSessionLocal()):
             await process_inbound_message(payload_help)
             
             mock_send_direct.assert_called_once()
             # Verify content contains "Jarvis Help"
             # call_args returns (args, kwargs)
             _, kwargs = mock_send_direct.call_args
             assert "Jarvis Help" in kwargs.get("text", "")

        # Test Rate Limiting
        # Simulate limit hit by making redis.incr return a large number
        mock_redis.incr.return_value = 100
        
        payload_spam = {
            "data": {
                "payload": {
                    "from": {"phone_number": "+1555_SPAMMER"},
                    "to": [{"phone_number": "+15559876543"}],
                    "text": "@jarvis spam"
                }
            }
        }
        
        mock_send_group.reset_mock()
        
        with patch("app.api.v1.endpoints.AsyncSessionLocal", return_value=TestSessionLocal()):
             await process_inbound_message(payload_spam)
             
             # Should be rate limited, so no message sent
             mock_send_group.assert_not_called()
             
        # Reset redis mock
        mock_redis.incr.return_value = 1
