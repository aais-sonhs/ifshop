from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet chỉ trả về bản ghi chưa xóa"""
    def delete(self):
        """Soft delete tất cả bản ghi trong queryset"""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Xóa vĩnh viễn"""
        return super().delete()

    def alive(self):
        """Chỉ bản ghi chưa xóa"""
        return self.filter(is_deleted=False)

    def dead(self):
        """Chỉ bản ghi đã xóa"""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager mặc định chỉ trả về bản ghi chưa xóa"""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager trả về TẤT CẢ bản ghi (kể cả đã xóa)"""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """Abstract model hỗ trợ xóa mềm"""
    is_deleted = models.BooleanField(default=False, verbose_name='Đã xóa')
    deleted_at = models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Override delete để soft delete"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """Xóa vĩnh viễn"""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Khôi phục bản ghi đã xóa"""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])
