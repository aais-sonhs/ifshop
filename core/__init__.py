"""Public API của package core.

Các lớp soft-delete được khai báo một lần trong `core.soft_delete` rồi re-export
tại đây để tránh trùng code nhưng vẫn giữ tương thích với import cũ.
"""

from .soft_delete import AllObjectsManager, SoftDeleteManager, SoftDeleteModel, SoftDeleteQuerySet

__all__ = [
    'AllObjectsManager',
    'SoftDeleteManager',
    'SoftDeleteModel',
    'SoftDeleteQuerySet',
]
