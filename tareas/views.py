from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from .models import Tarea, Personal, Municipio, Parroquia, Departamento
from .forms import TareaForm, LoginForm


# ============================================================
# AUTENTICACIÓN
# ============================================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('tareas:dashboard')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('tareas:dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'tareas/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('tareas:login')


# ============================================================
# MIXIN / HELPER DE VISIBILIDAD
# ============================================================

def get_tareas_visibles(user):
    """
    Retorna el queryset de tareas visibles según el nivel jerárquico del usuario.
    - Coordinadores (jefe nivel 1): ven toda su cadena de mando.
    - Jefes de Unidad/Sección: ven su departamento y secciones subordinadas.
    - Personal regular: solo sus tareas asignadas.
    - Superusuarios: ven todo.
    """
    if user.is_superuser:
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).all()

    try:
        personal = user.personal
    except Personal.DoesNotExist:
        return Tarea.objects.none()

    if personal.es_jefe:
        dept_ids = personal.get_departamentos_visibles()
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).filter(departamento__id__in=dept_ids)
    else:
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).filter(asignada_a=personal)


# ============================================================
# DASHBOARD
# ============================================================

@login_required
def dashboard(request):
    tareas = get_tareas_visibles(request.user)
    hoy = timezone.now().date()

    stats = {
        'total': tareas.count(),
        'pendientes': tareas.filter(estado='PE').count(),
        'en_progreso': tareas.filter(estado='EP').count(),
        'completadas': tareas.filter(estado='CO').count(),
        'vencidas': tareas.filter(
            estado__in=['PE', 'EP'],
            fecha_fin_planificada__lt=hoy
        ).count(),
    }

    tareas_recientes = tareas.order_by('-fecha_creacion')[:5]
    tareas_vencidas = tareas.filter(
        estado__in=['PE', 'EP'],
        fecha_fin_planificada__lt=hoy
    ).order_by('fecha_fin_planificada')[:5]

    try:
        personal = request.user.personal
    except Personal.DoesNotExist:
        personal = None

    context = {
        'stats': stats,
        'tareas_recientes': tareas_recientes,
        'tareas_vencidas': tareas_vencidas,
        'personal': personal,
        'hoy': hoy,
    }
    return render(request, 'tareas/dashboard.html', context)


# ============================================================
# LISTADO DE TAREAS
# ============================================================

@login_required
def lista_tareas(request):
    tareas = get_tareas_visibles(request.user)
    hoy = timezone.now().date()

    # Filtros desde GET
    estado = request.GET.get('estado', '')
    prioridad = request.GET.get('prioridad', '')
    municipio_id = request.GET.get('municipio', '')
    busqueda = request.GET.get('q', '')

    if estado:
        tareas = tareas.filter(estado=estado)
    if prioridad:
        tareas = tareas.filter(prioridad=prioridad)
    if municipio_id:
        tareas = tareas.filter(municipio__id=municipio_id)
    if busqueda:
        tareas = tareas.filter(
            Q(titulo__icontains=busqueda) |
            Q(descripcion__icontains=busqueda) |
            Q(asignada_a__usuario__first_name__icontains=busqueda) |
            Q(asignada_a__usuario__last_name__icontains=busqueda)
        )

    context = {
        'tareas': tareas.order_by('-fecha_creacion'),
        'municipios': Municipio.objects.all(),
        'estado_choices': Tarea.Estado.choices,
        'prioridad_choices': Tarea.Prioridad.choices,
        'filtros': {
            'estado': estado,
            'prioridad': prioridad,
            'municipio': municipio_id,
            'q': busqueda,
        },
        'hoy': hoy,
    }
    return render(request, 'tareas/lista_tareas.html', context)


# ============================================================
# DETALLE DE TAREA
# ============================================================

@login_required
def detalle_tarea(request, pk):
    tarea = get_object_or_404(get_tareas_visibles(request.user), pk=pk)
    return render(request, 'tareas/detalle_tarea.html', {
        'tarea': tarea,
        'hoy': timezone.now().date()
    })


# ============================================================
# CREAR TAREA
# ============================================================

@login_required
def crear_tarea(request):
    try:
        personal = request.user.personal
    except Personal.DoesNotExist:
        messages.error(request, 'Tu usuario no tiene un perfil de personal asociado.')
        return redirect('tareas:lista_tareas')

    if request.method == 'POST':
        form = TareaForm(request.POST, usuario=request.user)
        if form.is_valid():
            tarea = form.save(commit=False)
            tarea.creada_por = personal
            tarea.save()
            messages.success(request, f'Tarea "{tarea.titulo}" creada exitosamente.')
            return redirect('tareas:detalle_tarea', pk=tarea.pk)
    else:
        form = TareaForm(usuario=request.user)

    return render(request, 'tareas/form_tarea.html', {
        'form': form,
        'titulo_pagina': 'Nueva Tarea',
        'accion': 'Crear',
    })


# ============================================================
# EDITAR TAREA
# ============================================================

@login_required
def editar_tarea(request, pk):
    tarea = get_object_or_404(get_tareas_visibles(request.user), pk=pk)

    if request.method == 'POST':
        form = TareaForm(request.POST, instance=tarea, usuario=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Tarea "{tarea.titulo}" actualizada correctamente.')
            return redirect('tareas:detalle_tarea', pk=tarea.pk)
    else:
        form = TareaForm(instance=tarea, usuario=request.user)

    return render(request, 'tareas/form_tarea.html', {
        'form': form,
        'titulo_pagina': f'Editar: {tarea.titulo}',
        'accion': 'Guardar Cambios',
        'tarea': tarea,
    })


# ============================================================
# ELIMINAR TAREA
# ============================================================

@login_required
def eliminar_tarea(request, pk):
    tarea = get_object_or_404(get_tareas_visibles(request.user), pk=pk)
    if request.method == 'POST':
        titulo = tarea.titulo
        tarea.delete()
        messages.success(request, f'La tarea "{titulo}" fue eliminada.')
        return redirect('tareas:lista_tareas')
    return render(request, 'tareas/confirmar_eliminar.html', {'tarea': tarea})


# ============================================================
# AJAX: Cargar parroquias según municipio seleccionado
# ============================================================

@login_required
def cargar_parroquias(request):
    from django.http import JsonResponse
    municipio_id = request.GET.get('municipio_id')
    parroquias = Parroquia.objects.filter(municipio_id=municipio_id).order_by('nombre')
    data = [{'id': p.id, 'nombre': p.nombre} for p in parroquias]
    return JsonResponse({'parroquias': data})
