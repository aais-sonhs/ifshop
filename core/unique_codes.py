from django.db import IntegrityError, transaction


class DuplicateCodeError(ValueError):
    pass


def is_code_unique_conflict(error, model):
    """Return whether an IntegrityError is the model's unique-code violation."""
    cause = getattr(error, '__cause__', None)
    constraint = getattr(getattr(cause, 'diag', None), 'constraint_name', '') or ''
    table = model._meta.db_table
    if constraint:
        return constraint == f'{table}_code_key'

    message = str(error).lower()
    return f'{table}_code_key' in message or f'{table}.code' in message


def save_with_generated_code(instance, generator, auto_generated, attempts=5, **save_kwargs):
    """Save and retry safely when a concurrently inserted generated code wins."""
    total_attempts = attempts if auto_generated else 1
    for attempt in range(total_attempts):
        try:
            with transaction.atomic():
                instance.save(**save_kwargs)
            return instance
        except IntegrityError as error:
            if not is_code_unique_conflict(error, type(instance)):
                raise
            if not auto_generated or attempt == total_attempts - 1:
                label = instance._meta.verbose_name
                raise DuplicateCodeError(
                    f'Mã {label} "{instance.code}" đã tồn tại. Vui lòng dùng mã khác.'
                ) from error
            instance.code = generator()
