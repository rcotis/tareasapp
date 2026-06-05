from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .models import Bitacora

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Registra cada inicio de sesión exitoso en la bitácora.
    """
    # Obtener la IP del usuario
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    Bitacora.objects.create(
        usuario=user,
        actividad="Inicio de sesión exitoso",
        modulo="Seguridad",
        ip=ip
    )
@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """
    Registra cada cierre de sesión en la bitácora.
    """
    if not user:
        return

    # Obtener la IP del usuario
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    Bitacora.objects.create(
        usuario=user,
        actividad="Cierre de sesión",
        modulo="Seguridad",
        ip=ip
    )
