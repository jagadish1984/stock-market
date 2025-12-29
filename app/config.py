from __future__ import annotations
import os
from typing import Optional, Set
from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self):
        self.NSE_SFTP_HOST: Optional[str] = os.getenv("NSE_SFTP_HOST")
        self.NSE_SFTP_PORT: int = int(os.getenv("NSE_SFTP_PORT", "22"))
        self.NSE_SFTP_USER: Optional[str] = os.getenv("NSE_SFTP_USER")
        self.NSE_SFTP_PASSWORD: Optional[str] = os.getenv("NSE_SFTP_PASSWORD")
        self.NSE_SFTP_PRIVATE_KEY_PATH: Optional[str] = os.getenv("NSE_SFTP_PRIVATE_KEY_PATH")
        self.NSE_SFTP_REMOTE_ROOT: Optional[str] = os.getenv("NSE_SFTP_REMOTE_ROOT")
        self.NSE_PRODUCTS: str = os.getenv("NSE_PRODUCTS", "")
        self.WATCHLIST: Optional[str] = os.getenv("WATCHLIST")
        self.SCHEDULE_MINUTES: int = int(os.getenv("SCHEDULE_MINUTES", "10"))
        self.TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/market_data.db")
        
        # Symbol filtering configuration
        self.INSTRUMENTS_MASTER_PATH: Optional[str] = os.getenv("INSTRUMENTS_MASTER_PATH")
        self.ALLOWED_SERIES: Set[str] = self._parse_comma_separated(
            os.getenv("ALLOWED_SERIES", "EQ")
        )
        self.SYMBOL_DENYLIST: Set[str] = self._parse_comma_separated(
            os.getenv("SYMBOL_DENYLIST", "AAA,BBB,CCC,TEST,DUMMY")
        )
        self.ENABLE_SYMBOL_FILTERING: bool = os.getenv("ENABLE_SYMBOL_FILTERING", "true").lower() == "true"
    
    @staticmethod
    def _parse_comma_separated(value: str) -> Set[str]:
        """Parse comma-separated string into a set of uppercase values."""
        if not value:
            return set()
        return {item.strip().upper() for item in value.split(",") if item.strip()}


settings = Settings()
