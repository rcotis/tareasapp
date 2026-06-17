from django.db import models
from django.contrib.auth.models import User


# ============================================================
# UBICACIÓN GEOGRÁFICA
# ============================================================

class EstadoVenezuela(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Estado"
        verbose_name_plural = "Estados"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Municipio(models.Model):
    nombre = models.CharField(max_length=100)
    estado = models.ForeignKey(
        EstadoVenezuela,
        on_delete=models.CASCADE,
        related_name='municipios',
        null=True,
        blank=True,
        verbose_name="Estado"
    )

    class Meta:
        verbose_name = "Municipio"
        verbose_name_plural = "Municipios"
        ordering = ['estado__nombre', 'nombre']
        unique_together = ('nombre', 'estado')

    def __str__(self):
        if self.estado:
            return f"{self.nombre} ({self.estado.nombre})"
        return self.nombre


class Parroquia(models.Model):
    nombre = models.CharField(max_length=100)
    municipio = models.ForeignKey(
        Municipio,
        on_delete=models.CASCADE,
        related_name='parroquias'
    )

    class Meta:
        verbose_name = "Parroquia"
        verbose_name_plural = "Parroquias"
        ordering = ['municipio__estado__nombre', 'municipio__nombre', 'nombre']
        unique_together = ('nombre', 'municipio')

    def __str__(self):
        return f"{self.nombre} ({self.municipio.nombre}, {self.municipio.estado.nombre if self.municipio.estado else '—'})"


# ============================================================
# ESTRUCTURA JERÁRQUICA DE DEPARTAMENTOS
# ============================================================

class Departamento(models.Model):

    class Nivel(models.IntegerChoices):
        COORDINACION = 1, 'Coordinación'
        UNIDAD = 2, 'Unidad'
        SECCION = 3, 'Sección'

    nombre = models.CharField(max_length=150)
    nivel = models.IntegerField(choices=Nivel.choices)
    departamento_padre = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinados',
        help_text="Dejar vacío si es una Coordinación (nivel raíz)"
    )

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        ordering = ['nivel', 'nombre']

    def __str__(self):
        return f"{self.get_nivel_display()} - {self.nombre}"

    def get_todos_los_subordinados(self):
        """
        Retorna recursivamente todos los departamentos subordinados
        (hijos, nietos, etc.) de este departamento.
        """
        subordinados = []
        for sub in self.subordinados.all():
            subordinados.append(sub)
            subordinados.extend(sub.get_todos_los_subordinados())
        return subordinados


# ============================================================
# PERSONAL (perfil vinculado al usuario de Django)
# ============================================================

class Personal(models.Model):
    class Rol(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        SUPERVISOR = 'SUPER', 'Supervisor'
        USUARIO = 'USER', 'Usuario Normal'

    usuario = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        related_name='personal',
        null=True,
        blank=True
    )
    rol = models.CharField(
        max_length=10,
        choices=Rol.choices,
        default=Rol.USUARIO,
        verbose_name="Rol de Usuario"
    )
    nombres = models.CharField(max_length=100, null=True, blank=True)
    apellidos = models.CharField(max_length=100, null=True, blank=True)
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name='miembros'
    )
    cedula = models.CharField(max_length=15, unique=True, verbose_name="Cédula")
    telefono = models.CharField(max_length=20, blank=True, null=True)
    cargo = models.CharField(max_length=150, blank=True)
    es_jefe = models.BooleanField(
        default=False,
        help_text="Indica si este trabajador es el jefe/responsable de su departamento"
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Personal"
        verbose_name_plural = "Personal"
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f"{self.get_nombre_completo()} ({self.departamento.nombre})"

    def get_nombre_completo(self):
        if self.nombres and self.apellidos:
            return f"{self.nombres} {self.apellidos}"
        if self.usuario:
            return self.usuario.get_full_name() or self.usuario.username
        return self.cedula

    def get_departamentos_visibles(self):
        """
        Retorna los IDs de los departamentos cuyas tareas este
        usuario puede ver, según su nivel jerárquico.
        """
        if self.rol == self.Rol.ADMIN:
            # Administrador ve todo
            return [d.id for d in Departamento.objects.all()]
        
        dept = self.departamento
        if self.rol == self.Rol.SUPERVISOR or self.es_jefe:
            # Supervisor (o jefe antiguo) ve su departamento y subordinados
            departamentos = [dept] + dept.get_todos_los_subordinados()
            return [d.id for d in departamentos]
        else:
            # Solo ve su propio departamento
            return [dept.id]

    @property
    def es_coordinador(self):
        """
        Retorna True si el usuario pertenece a una Coordinación (Nivel 1).
        """
        return self.departamento.nivel == Departamento.Nivel.COORDINACION


class HistorialMovimientoPersonal(models.Model):
    class TipoMovimiento(models.TextChoices):
        DESACTIVACION = 'DE', 'Desactivación'
        ACTIVACION = 'AC', 'Activación'
        MODIFICACION = 'MO', 'Modificación'
        OTRO = 'OT', 'Otro'

    personal = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='historial_movimientos')
    tipo_movimiento = models.CharField(max_length=2, choices=TipoMovimiento.choices, default=TipoMovimiento.OTRO)
    razon = models.TextField(verbose_name="Razón / Motivo")
    fecha = models.DateTimeField(auto_now_add=True)
    usuario_responsable = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Historial de Movimiento"
        verbose_name_plural = "Historial de Movimientos"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_movimiento_display()} - {self.personal.get_nombre_completo()} ({self.fecha.strftime('%Y-%m-%d')})"



# ============================================================
# TAREAS
# ============================================================

class Tarea(models.Model):

    class Estado(models.TextChoices):
        PENDIENTE = 'PE', 'Pendiente'
        EN_PROGRESO = 'EP', 'En Progreso'
        COMPLETADA = 'CO', 'Completada'
        CANCELADA = 'CA', 'Cancelada'
        ELIMINADA = 'EL', 'Eliminada'

    class Prioridad(models.TextChoices):
        BAJA = 'BJ', 'Baja'
        MEDIA = 'ME', 'Media'
        ALTA = 'AL', 'Alta'
        URGENTE = 'UR', 'Urgente'

    titulo = models.CharField(max_length=200, verbose_name="Título")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")

    # Relaciones con personal
    creada_por = models.ForeignKey(
        Personal,
        on_delete=models.PROTECT,
        related_name='tareas_creadas',
        verbose_name="Creada por"
    )
    asignada_a = models.ForeignKey(
        Personal,
        on_delete=models.PROTECT,
        related_name='tareas_asignadas',
        verbose_name="Asignada a"
    )
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name='tareas',
        verbose_name="Departamento responsable"
    )

    # Estado y prioridad
    estado = models.CharField(
        max_length=2,
        choices=Estado.choices,
        default=Estado.PENDIENTE
    )
    prioridad = models.CharField(
        max_length=2,
        choices=Prioridad.choices,
        default=Prioridad.MEDIA
    )
    porcentaje_avance = models.PositiveIntegerField(
        default=0,
        verbose_name="Porcentaje de avance"
    )

    # Fechas
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_inicio_planificada = models.DateTimeField(verbose_name="Fecha de inicio planificada")
    fecha_fin_planificada = models.DateTimeField(verbose_name="Fecha de culminación planificada")
    fecha_fin_real = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de finalización real",
        help_text="Completar cuando la tarea finalice. Por defecto toma la fecha y hora actual."
    )

    # Ubicación geográfica (opcionales)
    estado_geo = models.ForeignKey(
        EstadoVenezuela,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tareas',
        verbose_name="Estado (Venezuela)"
    )
    municipio = models.ForeignKey(
        Municipio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tareas',
        verbose_name="Municipio"
    )
    parroquia = models.ForeignKey(
        Parroquia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tareas',
        verbose_name="Parroquia"
    )

    # Observaciones finales
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")

    class Meta:
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"[{self.get_estado_display()}] {self.titulo} → {self.asignada_a.get_nombre_completo()}"

    def esta_vencida(self):
        """Retorna True si la tarea no está completada y superó su fecha de culminación planificada."""
        from django.utils import timezone
        ahora = timezone.now()
        return self.estado not in [self.Estado.COMPLETADA, self.Estado.CANCELADA] and ahora > self.fecha_fin_planificada

    def tiene_retraso(self):
        """Retorna True si la fecha de finalización real es posterior a la planificada."""
        if self.fecha_fin_real and self.fecha_fin_real > self.fecha_fin_planificada:
            return True
        return False

    @property
    def dias_retraso(self):
        """
        Retorna la cantidad de días de retraso si la tarea está vencida o finalizó con retraso.
        Si no hay retraso, retorna 0.
        """
        from django.utils import timezone
        import math
        
        limite = self.fecha_fin_planificada
        
        if self.fecha_fin_real:
            fin = self.fecha_fin_real
        elif self.estado not in [self.Estado.COMPLETADA, self.Estado.CANCELADA]:
            fin = timezone.now()
        else:
            return 0
            
        if fin > limite:
            delta = fin - limite
            segundos = delta.total_seconds()
            return math.ceil(segundos / 86400)
        return 0


# ============================================================
# BITÁCORA / AUDITORÍA
# ============================================================

class Bitacora(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    fecha_hora = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora")
    actividad = models.TextField(verbose_name="Actividad")
    modulo = models.CharField(max_length=100, verbose_name="Módulo")
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Dirección IP")

    class Meta:
        verbose_name = "Entrada de Bitácora"
        verbose_name_plural = "Entradas de Bitácora"
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"{self.usuario.username if self.usuario else 'Anónimo'} - {self.actividad} ({self.fecha_hora})"
