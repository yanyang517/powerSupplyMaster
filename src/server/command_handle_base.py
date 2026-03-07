import asyncio
import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod


# Registry to store all command handlers
COMMAND_REGISTRY: Dict[str, type] = {}


class CommandHandler(ABC):
    """Abstract base class for command handlers with auto-registration"""

    # Class variable to store the command name for this handler
    command_name: Optional[str] = None
    
    def __init_subclass__(cls, **kwargs):
        """Automatically register subclasses when they are defined"""
        super().__init_subclass__(**kwargs)
        
        # Auto-register if the subclass defines a command_name
        if hasattr(cls, 'command_name') and cls.command_name:
            COMMAND_REGISTRY[cls.command_name] = cls
            logging.info(f"Auto-registered command handler '{cls.command_name}': {cls.__name__}")
    
    # make positive response
    def _make_positive_response(self, data: Dict[str, Any]) -> tuple:
        return ('ok', {'status': 'success', 'data': data})
    
    def _make_error_response(self, error_message: str) -> tuple:
        return ('error', {'status': 'error', 'message': error_message})

    async def before_handle(self, data: Dict[str, Any], addr: tuple) -> tuple:
        """Pre-processing hook before handling command"""
        return self._make_positive_response(data)

    @abstractmethod
    async def handle(self, data: Dict[str, Any], addr: tuple) :
        """Handle command and return response"""
        return self._make_error_response("Not implemented")
    
    @classmethod
    def get_registered_handlers(cls) -> Dict[str, type]:
        """Get all registered command handlers"""
        return COMMAND_REGISTRY.copy()
    
    @classmethod
    def create_handler(cls, command_name: str) -> Optional['CommandHandler']:
        """Create an instance of a command handler by command name"""
        handler_class = COMMAND_REGISTRY.get(command_name)
        if handler_class:
            return handler_class()
        return None
