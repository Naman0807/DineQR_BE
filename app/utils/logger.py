import logging
import sys
from datetime import datetime
from typing import Optional
import json

class APILogger:
    _instance: Optional["APILogger"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance
    
    def _setup_logger(self):
        self.logger = logging.getLogger("dineqr")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _format_extra(self, extra: dict) -> str:
        if not extra:
            return ""
        return " | " + json.dumps(extra, default=str)
    
    def api_request(self, service: str, method: str, endpoint: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.info(
            f"[{service.upper()}] {method} {endpoint}{self._format_extra(extra)}"
        )
    
    def api_response(self, service: str, method: str, endpoint: str, status_code: int, **kwargs):
        extra = {"status_code": status_code, **{k: v for k, v in kwargs.items() if v is not None}}
        self.logger.info(
            f"[{service.upper()}] {method} {endpoint} -> {status_code}{self._format_extra(extra)}"
        )
    
    def api_error(self, service: str, method: str, endpoint: str, error: str, **kwargs):
        extra = {"error": error, **{k: v for k, v in kwargs.items() if v is not None}}
        self.logger.error(
            f"[{service.upper()}] {method} {endpoint} | ERROR: {error}{self._format_extra(extra)}"
        )
    
    def info(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.info(f"{message}{self._format_extra(extra)}")
    
    def error(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.error(f"{message}{self._format_extra(extra)}")
    
    def warning(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.warning(f"{message}{self._format_extra(extra)}")
    
    def debug(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.debug(f"{message}{self._format_extra(extra)}")


logger = APILogger()
