"""커스텀 예외 클래스 모듈"""
from exceptions.base import BaseAppException
from exceptions.repository import (
    RepositoryException,
    EntityNotFoundError,
    EntityCreationError,
    EntityUpdateError,
    DatabaseConnectionError
)
from exceptions.service import (
    ServiceException,
    ActionExecutionError,
    AIServiceError,
    ModerationError
)
from exceptions.worker import (
    WorkerException,
    WorkerTaskError,
    LockAcquisitionError
)

__all__ = [
    "BaseAppException",
    "RepositoryException",
    "EntityNotFoundError",
    "EntityCreationError",
    "EntityUpdateError",
    "DatabaseConnectionError",
    "ServiceException",
    "ActionExecutionError",
    "AIServiceError",
    "ModerationError",
    "WorkerException",
    "WorkerTaskError",
    "LockAcquisitionError",
]
