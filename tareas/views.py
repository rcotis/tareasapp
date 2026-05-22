from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from .models import Tarea, Personal, Municipio, Parroquia, Departamento, HistorialMovimientoPersonal
from .forms import TareaForm, LoginForm, PersonalForm, CambioEstadoPersonalForm, VerificarCedulaForm, VincularUsuarioForm
from django.contrib.auth.forms import UserCreationForm


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
        ).exclude(estado=Tarea.Estado.ELIMINADA)

    try:
        personal = user.personal
    except Personal.DoesNotExist:
        return Tarea.objects.none()

    if personal.rol == Personal.Rol.ADMIN:
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).exclude(estado=Tarea.Estado.ELIMINADA)

    if personal.rol == Personal.Rol.SUPERVISOR or personal.es_jefe:
        dept_ids = personal.get_departamentos_visibles()
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).filter(departamento__id__in=dept_ids).exclude(estado=Tarea.Estado.ELIMINADA)
    else:
        return Tarea.objects.select_related(
            'asignada_a__usuario', 'asignada_a__departamento',
            'creada_por__usuario', 'departamento', 'municipio', 'parroquia'
        ).filter(asignada_a=personal).exclude(estado=Tarea.Estado.ELIMINADA)


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
    solo_mias = request.GET.get('solo_mias') == 'on'

    if solo_mias:
        try:
            tareas = tareas.filter(asignada_a=request.user.personal)
        except Personal.DoesNotExist:
            pass
    
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

    # Paginación
    paginator = Paginator(tareas.order_by('-fecha_creacion'), 10) # 10 por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'municipios': Municipio.objects.all(),
        'estado_choices': Tarea.Estado.choices,
        'prioridad_choices': Tarea.Prioridad.choices,
        'filtros': {
            'estado': estado,
            'prioridad': prioridad,
            'municipio': municipio_id,
            'q': busqueda,
            'solo_mias': solo_mias,
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
        tarea.estado = Tarea.Estado.ELIMINADA
        tarea.save()
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


# ============================================================
# REGISTRO DE PERSONAL
# ============================================================

@login_required
def lista_personal(request):
    mostrar_inactivos = request.GET.get('mostrar_inactivos') == 'true'
    
    if mostrar_inactivos:
        personal_list = Personal.objects.select_related('departamento').filter(activo=False).order_by('apellidos', 'nombres')
    else:
        personal_list = Personal.objects.select_related('departamento').filter(activo=True).order_by('apellidos', 'nombres')
    
    q = request.GET.get('q', '')
    if q:
        personal_list = personal_list.filter(
            Q(nombres__icontains=q) |
            Q(apellidos__icontains=q) |
            Q(cedula__icontains=q)
        )
        
    es_admin = False
    try:
        if request.user.is_staff or request.user.personal.rol == Personal.Rol.ADMIN:
            es_admin = True
    except Personal.DoesNotExist:
        es_admin = request.user.is_staff

    # Paginación
    paginator = Paginator(personal_list, 10) # 10 por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tareas/lista_personal.html', {
        'page_obj': page_obj,
        'q': q,
        'mostrar_inactivos': mostrar_inactivos,
        'es_admin': es_admin
    })

@login_required
def registrar_personal(request):
    try:
        es_admin = request.user.is_staff or request.user.personal.rol == Personal.Rol.ADMIN
    except Personal.DoesNotExist:
        es_admin = request.user.is_staff

    if not es_admin:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('tareas:lista_personal')

    if request.method == 'POST':
        form = PersonalForm(request.POST)
        if form.is_valid():
            personal = form.save()
            messages.success(request, f'El personal "{personal.get_nombre_completo()}" fue registrado exitosamente.')
            return redirect('tareas:lista_personal')
    else:
        form = PersonalForm()

    return render(request, 'tareas/form_personal.html', {
        'form': form,
        'titulo_pagina': 'Registrar Personal',
        'accion': 'Registrar',
    })

@login_required
def editar_personal(request, pk):
    try:
        es_admin = request.user.is_staff or request.user.personal.rol == Personal.Rol.ADMIN
    except Personal.DoesNotExist:
        es_admin = request.user.is_staff

    if not es_admin:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('tareas:lista_personal')

    personal = get_object_or_404(Personal, pk=pk)
    if request.method == 'POST':
        form = PersonalForm(request.POST, instance=personal)
        if form.is_valid():
            personal = form.save()
            messages.success(request, f'El perfil de "{personal.get_nombre_completo()}" fue actualizado correctamente.')
            return redirect('tareas:lista_personal')
    else:
        form = PersonalForm(instance=personal)

    return render(request, 'tareas/form_personal.html', {
        'form': form,
        'titulo_pagina': f'Editar Personal: {personal.get_nombre_completo()}',
        'accion': 'Guardar Cambios',
        'personal': personal,
    })

@login_required
def toggle_estado_personal(request, pk):
    try:
        es_admin = request.user.is_staff or request.user.personal.rol == Personal.Rol.ADMIN
    except Personal.DoesNotExist:
        es_admin = request.user.is_staff

    if not es_admin:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('tareas:lista_personal')

    personal = get_object_or_404(Personal, pk=pk)
    nuevo_estado = not personal.activo
    accion_str = "Reactivar" if nuevo_estado else "Desactivar"

    if request.method == 'POST':
        form = CambioEstadoPersonalForm(request.POST)
        if form.is_valid():
            razon = form.cleaned_data['razon']
            personal.activo = nuevo_estado
            personal.save()

            tipo_mov = HistorialMovimientoPersonal.TipoMovimiento.ACTIVACION if nuevo_estado else HistorialMovimientoPersonal.TipoMovimiento.DESACTIVACION
            
            HistorialMovimientoPersonal.objects.create(
                personal=personal,
                tipo_movimiento=tipo_mov,
                razon=razon,
                usuario_responsable=request.user
            )

            estado_texto = "reactivado" if nuevo_estado else "desactivado"
            messages.success(request, f'El trabajador "{personal.get_nombre_completo()}" fue {estado_texto} correctamente.')
            return redirect('tareas:lista_personal')
    else:
        form = CambioEstadoPersonalForm()

    return render(request, 'tareas/confirmar_estado_personal.html', {
        'form': form,
        'personal': personal,
        'accion_str': accion_str,
        'nuevo_estado': nuevo_estado
    })

# ============================================================
# REGISTRO DE NUEVOS USUARIOS
# ============================================================

def verificar_cedula_registro(request):
    # Solo redirigimos si ya está autenticado y NO es administrador
    try:
        es_admin = request.user.is_authenticated and (request.user.is_staff or request.user.personal.rol == Personal.Rol.ADMIN)
    except:
        es_admin = request.user.is_authenticated and request.user.is_staff
        
    if request.user.is_authenticated and not es_admin:
        return redirect('tareas:dashboard')

    if request.method == 'POST':
        form = VerificarCedulaForm(request.POST)
        if form.is_valid():
            cedula = form.cleaned_data['cedula']
            request.session['registro_cedula_valida'] = cedula
            return redirect('tareas:registro_usuario')
    else:
        form = VerificarCedulaForm()

    return render(request, 'tareas/registro_paso1.html', {'form': form})


def registro_usuario(request):
    # Solo redirigimos si ya está autenticado y NO es administrador
    if request.user.is_authenticated and not request.user.is_staff:
        return redirect('tareas:dashboard')

    cedula_autorizada = request.session.get('registro_cedula_valida')
    if not cedula_autorizada:
        messages.error(request, 'Debes verificar tu cédula antes de registrarte.')
        return redirect('tareas:verificar_cedula_registro')

    try:
        persona = Personal.objects.get(cedula=cedula_autorizada, activo=True, usuario__isnull=True)
    except Personal.DoesNotExist:
        messages.error(request, 'La verificación de cédula ha expirado o es inválida.')
        return redirect('tareas:verificar_cedula_registro')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = persona.nombres if persona.nombres else ''
            user.last_name = persona.apellidos if persona.apellidos else ''
            user.save()

            persona.usuario = user
            persona.save()

            del request.session['registro_cedula_valida']
            messages.success(request, f'La cuenta para {persona.get_nombre_completo()} ha sido creada exitosamente.')
            
            # Si el que registra es un admin, volvemos al listado de usuarios
            if request.user.is_authenticated and request.user.is_staff:
                return redirect('tareas:lista_usuarios')
            return redirect('tareas:login')
    else:
        form = UserCreationForm()

    return render(request, 'tareas/registro_paso2.html', {
        'form': form,
        'persona': persona
    })

@login_required
def lista_usuarios(request):
    es_admin = False
    try:
        if request.user.personal.rol == Personal.Rol.ADMIN:
            es_admin = True
    except Personal.DoesNotExist:
        pass

    if not request.user.is_staff and not es_admin:
        messages.error(request, 'No tienes permisos para acceder a este módulo.')
        return redirect('tareas:dashboard')
    
    q = request.GET.get('q', '')
    # Obtenemos usuarios que tengan vinculación con Personal para ver sus datos completos
    usuarios = User.objects.select_related('personal__departamento').all().order_by('-date_joined')
    
    if q:
        usuarios = usuarios.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(personal__cedula__icontains=q)
        )
    
    # Paginación
    paginator = Paginator(usuarios, 10) # 10 por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'tareas/lista_usuarios.html', {
        'page_obj': page_obj,
        'q': q,
        'rol_choices': Personal.Rol.choices
    })


@login_required
def cambiar_rol_usuario(request, user_id):
    # Verificación de permisos de administrador
    es_admin = False
    try:
        if request.user.personal.rol == Personal.Rol.ADMIN:
            es_admin = True
    except Personal.DoesNotExist:
        pass

    if not request.user.is_staff and not es_admin:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('tareas:dashboard')

    if request.method == 'POST':
        user_to_change = get_object_or_404(User, id=user_id)
        nuevo_rol = request.POST.get('rol')
        
        if nuevo_rol in dict(Personal.Rol.choices):
            try:
                personal = user_to_change.personal
                personal.rol = nuevo_rol
                
                # Sincronizar con is_staff si es Administrador del sistema
                if nuevo_rol == Personal.Rol.ADMIN:
                    user_to_change.is_staff = True
                else:
                    # Opcional: remover is_staff si ya no es admin (depende de la política del sistema)
                    # user_to_change.is_staff = False 
                    pass
                
                personal.save()
                user_to_change.save()
                
                messages.success(request, f'Rol de {user_to_change.username} actualizado a {personal.get_rol_display()}.')
            except Personal.DoesNotExist:
                messages.error(request, 'Este usuario no tiene un perfil de personal asociado.')
        else:
            messages.error(request, 'Rol no válido.')
            
    return redirect('tareas:lista_usuarios')
@login_required
def vincular_usuario_personal(request, pk):
    # Verificación de permisos de administrador
    es_admin = False
    try:
        if request.user.personal.rol == Personal.Rol.ADMIN or request.user.is_staff:
            es_admin = True
    except Personal.DoesNotExist:
        es_admin = request.user.is_staff

    if not es_admin:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('tareas:dashboard')

    persona = get_object_or_404(Personal, pk=pk)
    
    if persona.usuario:
        messages.warning(request, f'El trabajador {persona.get_nombre_completo()} ya tiene una cuenta de usuario.')
        return redirect('tareas:lista_personal')

    if request.method == 'POST':
        form = VincularUsuarioForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            # Crear el usuario
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=persona.nombres or '',
                last_name=persona.apellidos or ''
            )
            
            # Vincular con el personal
            persona.usuario = user
            persona.save()
            
            messages.success(request, f'Cuenta de usuario para {persona.get_nombre_completo()} creada exitosamente.')
            return redirect('tareas:lista_usuarios')
    else:
        form = VincularUsuarioForm()

    return render(request, 'tareas/vincular_usuario.html', {
        'form': form,
        'persona': persona
    })
