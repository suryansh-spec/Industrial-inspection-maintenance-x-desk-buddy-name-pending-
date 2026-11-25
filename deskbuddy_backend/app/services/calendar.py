"""
Calendar Service - Google Calendar / Outlook integration.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


class CalendarEvent:
    """Calendar event model."""
    def __init__(
        self,
        id: str,
        title: str,
        start: datetime,
        end: datetime,
        location: str = "",
        description: str = "",
        all_day: bool = False,
        calendar_id: str = ""
    ):
        self.id = id
        self.title = title
        self.start = start
        self.end = end
        self.location = location
        self.description = description
        self.all_day = all_day
        self.calendar_id = calendar_id
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "description": self.description,
            "all_day": self.all_day,
            "calendar_id": self.calendar_id
        }


class CalendarService:
    """
    Calendar service supporting Google Calendar and Outlook.
    """
    
    def __init__(self):
        self.initialized = False
        self._provider = None  # "google", "outlook", "mock"
        self._service = None
    
    async def initialize(self):
        """Initialize calendar service."""
        # Try Google Calendar first
        if await self._try_google():
            self._provider = "google"
        elif await self._try_outlook():
            self._provider = "outlook"
        else:
            self._provider = "mock"
            logger.warning("Using mock calendar (no real calendar configured)")
        
        self.initialized = True
        logger.info(f"Calendar service initialized: {self._provider}")
    
    async def _try_google(self) -> bool:
        """Try to initialize Google Calendar."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request
            
            creds_path = os.path.expanduser(settings.google_credentials_path or "~/.config/google-calendar/credentials.json")
            token_path = os.path.expanduser(settings.google_token_path or "~/.config/google-calendar/token.json")
            
            if not os.path.exists(creds_path):
                return False
            
            creds = None
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, ['https://www.googleapis.com/auth/calendar.readonly'])
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    await asyncio.to_thread(creds.refresh, Request())
                else:
                    return False

            self._service = await asyncio.to_thread(build, 'calendar', 'v3', credentials=creds)
            return True
        except Exception as e:
            logger.debug(f"Google Calendar not available: {e}")
            return False
    
    async def _try_outlook(self) -> bool:
        """Try to initialize Outlook Calendar."""
        try:
            import msal
            import requests
            
            client_id = os.getenv("OUTLOOK_CLIENT_ID")
            client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
            tenant_id = os.getenv("OUTLOOK_TENANT_ID")
            
            if not all([client_id, client_secret, tenant_id]):
                return False
            
            # Initialize MSAL client
            app = msal.ConfidentialClientApplication(
                client_id,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                client_credential=client_secret
            )
            
            # Token acquisition and Microsoft Graph API integration not yet implemented
            return False
        except Exception as e:
            logger.debug(f"Outlook Calendar not available: {e}")
            return False
    
    async def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary"
    ) -> List[CalendarEvent]:
        """Get events in date range."""
        if self._provider == "google":
            return await self._get_google_events(start, end, calendar_id)
        elif self._provider == "outlook":
            return await self._get_outlook_events(start, end, calendar_id)
        else:
            return self._get_mock_events(start, end)
    
    @staticmethod
    def _to_rfc3339_utc(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    async def _get_google_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str
    ) -> List[CalendarEvent]:
        """Get events from Google Calendar."""
        try:
            time_min = self._to_rfc3339_utc(start)
            time_max = self._to_rfc3339_utc(end)
            events_result = await asyncio.to_thread(
                lambda: self._service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            )
            
            events = events_result.get('items', [])
            result = []
            
            for event in events:
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                end_str = event['end'].get('dateTime', event['end'].get('date'))
                
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                
                result.append(CalendarEvent(
                    id=event['id'],
                    title=event.get('summary', 'Untitled'),
                    start=start_dt,
                    end=end_dt,
                    location=event.get('location', ''),
                    description=event.get('description', ''),
                    all_day='date' in event['start'],
                    calendar_id=calendar_id
                ))
            
            return result
        except Exception as e:
            logger.error(f"Google Calendar error: {e}")
            return []
    
    async def _get_outlook_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str
    ) -> List[CalendarEvent]:
        """Get events from Outlook Calendar."""
        # Implementation would use Microsoft Graph API
        return []
    
    def _get_mock_events(
        self,
        start: datetime,
        end: datetime
    ) -> List[CalendarEvent]:
        """Generate mock events for testing."""
        mock_events = [
            CalendarEvent(
                id="evt_1",
                title="Team Standup",
                start=datetime.now().replace(hour=9, minute=0, second=0),
                end=datetime.now().replace(hour=9, minute=30),
                location="Meeting Room A"
            ),
            CalendarEvent(
                id="evt_2",
                title="Design Review",
                start=datetime.now().replace(hour=11, minute=0),
                end=datetime.now().replace(hour=12, minute=0),
                location="Conference Room B"
            ),
            CalendarEvent(
                id="evt_3",
                title="1:1 with Manager",
                start=datetime.now().replace(hour=14, minute=0),
                end=datetime.now().replace(hour=14, minute=30),
                location="Zoom"
            ),
            CalendarEvent(
                id="evt_4",
                title="Code Review",
                start=datetime.now().replace(hour=16, minute=0),
                end=datetime.now().replace(hour=17, minute=0),
                location="Slack Huddle"
            )
        ]
        
        return [e for e in mock_events if start <= e.start < end]
    
    async def get_next_event(self) -> Optional[CalendarEvent]:
        """Get the next upcoming event."""
        now = datetime.now(timezone.utc)
        events = await self.get_events(now, now + timedelta(days=7))
        return events[0] if events else None
    
    async def create_event(self, event_data: dict) -> CalendarEvent:
        """Create a new calendar event."""
        if self._provider == "google":
            return await self._create_google_event(event_data)
        elif self._provider == "outlook":
            return await self._create_outlook_event(event_data)
        else:
            return self._create_mock_event(event_data)
    
    async def _create_google_event(self, event_data: dict) -> CalendarEvent:
        """Create event in Google Calendar."""
        try:
            event = {
                'summary': event_data['title'],
                'location': event_data.get('location', ''),
                'description': event_data.get('description', ''),
                'start': {
                    'dateTime': event_data['start'],
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': event_data['end'],
                    'timeZone': 'UTC',
                },
            }
            
            created = await asyncio.to_thread(
                lambda: self._service.events().insert(calendarId='primary', body=event).execute()
            )
            
            start_dt = datetime.fromisoformat(event_data['start'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(event_data['end'].replace('Z', '+00:00'))
            
            return CalendarEvent(
                id=created['id'],
                title=created['summary'],
                start=start_dt,
                end=end_dt,
                location=created.get('location', ''),
                description=created.get('description', ''),
                all_day=False
            )
        except Exception as e:
            logger.error(f"Google Calendar create error: {e}")
            raise
    
    async def _create_outlook_event(self, event_data: dict) -> CalendarEvent:
        """Create event in Outlook Calendar."""
        # Implementation would use Microsoft Graph API
        raise NotImplementedError("Outlook event creation not implemented")
    
    def _create_mock_event(self, event_data: dict) -> CalendarEvent:
        """Create mock event."""
        return CalendarEvent(
            id=f"evt_{datetime.now().timestamp()}",
            title=event_data['title'],
            start=datetime.fromisoformat(event_data['start']),
            end=datetime.fromisoformat(event_data['end']),
            location=event_data.get('location', ''),
            description=event_data.get('description', ''),
            all_day=event_data.get('all_day', False)
        )
    
    async def cleanup(self):
        """Cleanup resources."""
        self.initialized = False


# Global instance
calendar_service = CalendarService()