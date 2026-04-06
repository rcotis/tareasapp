from django.contrib import admin
from .models import EstadoVenezuela, Municipio, Parroquia, Departamento, Personal, Tarea


# ============================================================
# UBICACIÓN GEOGRÁFICA
# ============================================================

@admin.register(EstadoVenezuela)
class EstadoVenezuelaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'estado')
    list_filter = ('estado',)
    search_fields = ('nombre', 'estado__nombre')


@admin.register(Parroquia)
class ParroquiaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'municipio', 'get_estado')
    list_filter = ('municipio__estado', 'municipio')
    search_fields = ('nombre', 'municipio__nombre', 'municipio__estado__nombre')

    def get_estado(self, obj):
        return obj.municipio.estado
    get_estado.short_description = 'Estado'


# ============================================================
# DEPARTAMENTOS
# ============================================================

@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'nivel', 'departamento_padre')
    list_filter = ('nivel',)
    search_fields = ('nombre',)


# ============================================================
# PERSONAL
# ============================================================

@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ('get_nombre', 'cedula', 'cargo', 'departamento', 'es_jefe', 'get_usuario')
    list_filter = ('departamento', 'es_jefe')
    search_fields = ('usuario__first_name', 'usuario__last_name', 'cedula', 'cargo')
    raw_id_fields = ('usuario',)

    def get_nombre(self, obj):
        return obj.get_nombre_completo()
    get_nombre.short_description = 'Nombre Completo'

    def get_usuario(self, obj):
        return obj.usuario.username
    get_usuario.short_description = 'Usuario'


# ============================================================
# TAREAS
# ============================================================

class TareaAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'estado', 'prioridad',
        'asignada_a', 'departamento',
        'fecha_inicio_planificada', 'fecha_fin_planificada',
        'fecha_fin_real', 'get_estado_geo', 'municipio', 'parroquia',
        'esta_vencida'
    )
    list_filter = ('estado', 'prioridad', 'departamento', 'estado_geo', 'municipio')
    search_fields = ('titulo', 'descripcion', 'asignada_a__usuario__last_name')
    date_hierarchy = 'fecha_creacion'
    raw_id_fields = ('creada_por', 'asignada_a')

    fieldsets = (
        ('Información General', {
            'fields': ('titulo', 'descripcion', 'prioridad', 'estado')
        }),
        ('Asignación', {
            'fields': ('creada_por', 'asignada_a', 'departamento')
        }),
        ('Fechas', {
            'fields': (
                'fecha_inicio_planificada',
                'fecha_fin_planificada',
                'fecha_fin_real',
            )
        }),
        ('Ubicación Geográfica', {
            'fields': ('estado_geo', 'municipio', 'parroquia'),
            'classes': ('collapse',),
        }),
        ('Observaciones', {
            'fields': ('observaciones',),
            'classes': ('collapse',),
        }),
    )

    def get_estado_geo(self, obj):
        return obj.estado_geo
    get_estado_geo.short_description = 'Estado'

    def esta_vencida(self, obj):
        return obj.esta_vencida()
    esta_vencida.boolean = True
    esta_vencida.short_description = '¿Vencida?'

    def get_queryset(self, request):
        """
        Filtra las tareas según el nivel jerárquico del usuario logueado.
        - Superusuarios y staff: ven todo.
        - Jefes: ven las tareas de su departamento y sus subordinados.
        - Personal regular: solo sus tareas asignadas.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            personal = request.user.personal
            if personal.es_jefe:
                dept_ids = personal.get_departamentos_visibles()
                return qs.filter(departamento__id__in=dept_ids)
            else:
                return qs.filter(asignada_a=personal)
        except Personal.DoesNotExist:
            return qs.none()


admin.site.register(Tarea, TareaAdmin)

# Personalización del panel de administración
admin.site.site_header = "Sistema de Control de Tareas"
admin.site.site_title = "Control de Tareas"
admin.site.index_title = "Panel de Administración"
