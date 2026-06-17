from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from .models import Tarea, Personal, Municipio, Parroquia, Departamento, HistorialMovimientoPersonal, Bitacora
from .forms import TareaForm, LoginForm, PersonalForm, CambioEstadoPersonalForm, VerificarCedulaForm, VincularUsuarioForm
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm


# ============================================================
# UTILS / LOGGING
# ============================================================

def registrar_log(request, actividad, modulo):
    """
    Función auxiliar para registrar una actividad en la bitácora.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    Bitacora.objects.create(
        usuario=request.user,
        actividad=actividad,
        modulo=modulo,
        ip=ip
    )


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


@login_required
def cambio_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Importante para no perder la sesión
            messages.success(request, 'Tu contraseña ha sido actualizada exitosamente.')
            return redirect('tareas:dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores a continuación.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'tareas/cambio_password.html', {
        'form': form
    })


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
    # Use timezone-aware datetime for DB comparisons
    now = timezone.now()
    hoy = now.date()

    stats = {
        'total': tareas.count(),
        'pendientes': tareas.filter(estado='PE').count(),
        'en_progreso': tareas.filter(estado='EP').count(),
        'completadas': tareas.filter(estado='CO').count(),
        'vencidas': tareas.filter(
            estado__in=['PE', 'EP'],
            fecha_fin_planificada__lt=now
        ).count(),
    }



    tareas_recientes = tareas.order_by('-fecha_creacion')[:5]
    tareas_vencidas = tareas.filter(
        estado__in=['PE', 'EP'],
        fecha_fin_planificada__lt=now
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

def filtrar_tareas_request(request, tareas):
    """
    Filtra un queryset de tareas según los parámetros GET de la solicitud.
    Retorna el queryset filtrado y un diccionario con los valores de los filtros.
    """
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
    
    if estado == '':
        tareas = tareas.exclude(estado=Tarea.Estado.COMPLETADA)
    elif estado == 'todas':
        pass
    else:
        tareas = tareas.filter(estado=estado)
    if prioridad:
        tareas = tareas.filter(prioridad=prioridad)
    if municipio_id:
        tareas = tareas.filter(municipio__id=municipio_id)
    if busqueda:
        tareas = tareas.filter(
            Q(titulo__icontains=busqueda) |
            Q(descripcion__icontains=busqueda) |
            Q(asignada_a__nombres__icontains=busqueda) |
            Q(asignada_a__apellidos__icontains=busqueda) |
            Q(creada_por__nombres__icontains=busqueda) |
            Q(creada_por__apellidos__icontains=busqueda) |
            Q(asignada_a__usuario__username__icontains=busqueda) |
            Q(creada_por__usuario__username__icontains=busqueda)
        )
    
    return tareas, {
        'estado': estado,
        'prioridad': prioridad,
        'municipio': municipio_id,
        'q': busqueda,
        'solo_mias': solo_mias,
    }


@login_required
def lista_tareas(request):
    tareas_visibles = get_tareas_visibles(request.user)
    tareas, filtros = filtrar_tareas_request(request, tareas_visibles)
    now = timezone.now()
    hoy = now.date()

    # Paginación
    paginator = Paginator(tareas.order_by('-fecha_creacion'), 10) # 10 por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'estado_choices': Tarea.Estado.choices,
        'prioridad_choices': Tarea.Prioridad.choices,
        'filtros': filtros,
        'hoy': hoy,
        'now': now,
    }
    registrar_log(request, "Visualizó el listado de tareas", "Tareas")
    return render(request, 'tareas/lista_tareas.html', context)


@login_required
def reporte_tareas_pdf(request):
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas
    from django.utils import timezone

    tareas_visibles = get_tareas_visibles(request.user)
    tareas, filtros = filtrar_tareas_request(request, tareas_visibles)

    # Ordenar por fecha_creacion descendente como en la vista
    tareas = tareas.order_by('-fecha_creacion')

    # Configurar respuesta HTTP
    response = HttpResponse(content_type='application/pdf')
    hoy_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="reporte_tareas_{hoy_str}.pdf"'

    # Documento en Landscape con margenes de 0.5 pulg (36pt)
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=54
    )

    story = []
    styles = getSampleStyleSheet()

    # Estilos de ReportLab
    style_title = ParagraphStyle(
        name='Title_Custom',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1e40af'),
        fontName='Helvetica-Bold',
        spaceAfter=4
    )
    style_subtitle = ParagraphStyle(
        name='Subtitle_Custom',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569'),
        spaceAfter=15
    )
    style_normal = ParagraphStyle(
        name='Normal_Custom',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0f172a')
    )
    style_header = ParagraphStyle(
        name='Header_Custom',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )

    # Agregar Título del Reporte
    story.append(Paragraph("Reporte de Tareas Asignadas", style_title))

    # Construir resumen de filtros aplicados
    filtros_aplicados = []
    if filtros.get('q'):
        filtros_aplicados.append(f"Búsqueda: '{filtros['q']}'")
    if filtros.get('estado'):
        if filtros['estado'] == 'todas':
            filtros_aplicados.append("Estado: Todas")
        else:
            estado_lbl = dict(Tarea.Estado.choices).get(filtros['estado'], filtros['estado'])
            filtros_aplicados.append(f"Estado: {estado_lbl}")
    else:
        filtros_aplicados.append("Estado: Activas")

    if filtros.get('prioridad'):
        prioridad_lbl = dict(Tarea.Prioridad.choices).get(filtros['prioridad'], filtros['prioridad'])
        filtros_aplicados.append(f"Prioridad: {prioridad_lbl}")
    if filtros.get('solo_mias'):
        filtros_aplicados.append("Solo mis tareas")

    filtro_summary = " | ".join(filtros_aplicados) if filtros_aplicados else "Ninguno"
    fecha_generacion = timezone.now().strftime('%d/%m/%Y %I:%M %p')
    
    meta_info = f"<b>Filtros aplicados:</b> {filtro_summary} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Generado por:</b> {request.user.get_full_name() or request.user.username} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha:</b> {fecha_generacion} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Total tareas:</b> {tareas.count()}"
    story.append(Paragraph(meta_info, style_subtitle))

    # Crear la tabla de datos
    headers = [
        Paragraph("Tarea", style_header),
        Paragraph("Asignada a", style_header),
        Paragraph("Departamento", style_header),
        Paragraph("Estado", style_header),
        Paragraph("Prioridad", style_header),
        Paragraph("Avance", style_header),
        Paragraph("Inicio", style_header),
        Paragraph("Culminación", style_header),
        Paragraph("Municipio", style_header),
    ]

    data = [headers]

    for t in tareas:
        estado_display = t.get_estado_display()
        if t.estado == 'PE':
            estado_html = f'<font color="#854d0e"><b>{estado_display}</b></font>'
        elif t.estado == 'EP':
            estado_html = f'<font color="#1e40af"><b>{estado_display}</b></font>'
        elif t.estado == 'CO':
            estado_html = f'<font color="#166534"><b>{estado_display}</b></font>'
        elif t.estado == 'CA':
            estado_html = f'<font color="#475569"><b>{estado_display}</b></font>'
        else:
            estado_html = f'<b>{estado_display}</b>'

        prioridad_display = t.get_prioridad_display()
        if t.prioridad == 'BJ':
            prioridad_html = f'<font color="#475569">{prioridad_display}</font>'
        elif t.prioridad == 'ME':
            prioridad_html = f'<font color="#92400e">{prioridad_display}</font>'
        elif t.prioridad == 'AL':
            prioridad_html = f'<font color="#9a3412"><b>{prioridad_display}</b></font>'
        elif t.prioridad == 'UR':
            prioridad_html = f'<font color="#991b1b"><b>{prioridad_display}</b></font>'
        else:
            prioridad_html = prioridad_display

        fecha_ini = t.fecha_inicio_planificada.strftime('%d/%m/%Y') if t.fecha_inicio_planificada else "—"
        fecha_fin = t.fecha_fin_planificada.strftime('%d/%m/%Y') if t.fecha_fin_planificada else "—"

        row = [
            Paragraph(t.titulo, style_normal),
            Paragraph(t.asignada_a.get_nombre_completo() if t.asignada_a else "—", style_normal),
            Paragraph(t.departamento.nombre if t.departamento else "—", style_normal),
            Paragraph(estado_html, style_normal),
            Paragraph(prioridad_html, style_normal),
            Paragraph(f"{t.porcentaje_avance}%", style_normal),
            Paragraph(fecha_ini, style_normal),
            Paragraph(fecha_fin, style_normal),
            Paragraph(t.municipio.nombre if t.municipio else "—", style_normal),
        ]
        data.append(row)

    col_widths = [180, 100, 80, 65, 60, 50, 60, 60, 65]
    t_table = Table(data, colWidths=col_widths, repeatRows=1)
    
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ])

    for i in range(1, len(data)):
        if i % 2 == 0:
            table_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f8fafc'))

    t_table.setStyle(table_style)
    story.append(t_table)

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_number(num_pages)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def draw_page_number(self, page_count):
            self.saveState()
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor('#64748b'))
            
            page_text = f"Página {self._pageNumber} de {page_count}"
            self.drawRightString(792 - 36, 20, page_text)
            self.drawString(36, 20, "Sistema de Control de Tareas — Reporte generado automáticamente")
            
            self.setStrokeColor(colors.HexColor('#cbd5e1'))
            self.setLineWidth(0.5)
            self.line(36, 32, 792 - 36, 32)
            
            self.restoreState()

    doc.build(story, canvasmaker=NumberedCanvas)
    
    registrar_log(request, f"Generó reporte PDF de tareas visibles ({tareas.count()} tareas)", "Tareas")

    return response


# ============================================================
# DETALLE DE TAREA
# ============================================================

@login_required
def detalle_tarea(request, pk):
    tarea = get_object_or_404(get_tareas_visibles(request.user), pk=pk)
    registrar_log(request, f"Visualizó el detalle de la tarea: {tarea.titulo}", "Tareas")
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
            registrar_log(request, f"Creó la tarea: {tarea.titulo}", "Tareas")
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
    
    # Valores anteriores para la bitácora
    estado_anterior = tarea.get_estado_display()
    progreso_anterior = tarea.porcentaje_avance

    if request.method == 'POST':
        form = TareaForm(request.POST, instance=tarea, usuario=request.user)
        if form.is_valid():
            tarea = form.save()
            
            # Determinar qué cambió para el log
            detalles_cambio = []
            if progreso_anterior != tarea.porcentaje_avance:
                detalles_cambio.append(f"progreso: {progreso_anterior}% -> {tarea.porcentaje_avance}%")
            if estado_anterior != tarea.get_estado_display():
                detalles_cambio.append(f"estado: {estado_anterior} -> {tarea.get_estado_display()}")
            
            msg_log = f"Editó la tarea: {tarea.titulo}"
            if detalles_cambio:
                msg_log += f" ({', '.join(detalles_cambio)})"
            
            registrar_log(request, msg_log, "Tareas")
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
        registrar_log(request, f"Eliminó la tarea: {titulo}", "Tareas")
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
    paginator = Paginator(personal_list, 6) # 10 por página
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
    paginator = Paginator(usuarios, 6) # 10 por página
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
def restablecer_password_usuario(request, user_id):
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

    user_to_reset = get_object_or_404(User, id=user_id)
    
    # Importar SetPasswordForm de django
    from django.contrib.auth.forms import SetPasswordForm

    if request.method == 'POST':
        form = SetPasswordForm(user_to_reset, request.POST)
        if form.is_valid():
            form.save()
            
            # Registrar en la bitácora
            Bitacora.objects.create(
                usuario=request.user,
                modulo='USUARIOS',
                actividad=f'Restableció la contraseña del usuario {user_to_reset.username}.'
            )
            
            messages.success(request, f'La contraseña de {user_to_reset.username} ha sido restablecida exitosamente.')
            return redirect('tareas:lista_usuarios')
    else:
        form = SetPasswordForm(user_to_reset)

    return render(request, 'tareas/restablecer_password_usuario.html', {
        'form': form,
        'user_to_reset': user_to_reset
    })
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


# ============================================================
# BITÁCORA (SOLO COORDINADORES)
# ============================================================

@login_required
def lista_bitacora(request):
    # Verificación de permisos
    es_admin = False
    es_coordinador = False
    
    try:
        personal = request.user.personal
        es_admin = personal.rol == Personal.Rol.ADMIN
        es_coordinador = personal.es_coordinador
    except Personal.DoesNotExist:
        pass
        
    if not request.user.is_staff and not es_admin and not es_coordinador:
        messages.error(request, 'No tienes permisos para acceder a la bitácora.')
        return redirect('tareas:dashboard')

    logs = Bitacora.objects.select_related('usuario').all().order_by('-fecha_hora')
    
    # Filtros
    q = request.GET.get('q', '')
    modulo = request.GET.get('modulo', '')
    
    if q:
        logs = logs.filter(
            Q(usuario__username__icontains=q) |
            Q(usuario__first_name__icontains=q) |
            Q(usuario__last_name__icontains=q) |
            Q(actividad__icontains=q)
        )
    if modulo:
        logs = logs.filter(modulo=modulo)

    # Paginación
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener módulos únicos para el filtro
    modulos = Bitacora.objects.values_list('modulo', flat=True).distinct()

    return render(request, 'tareas/lista_bitacora.html', {
        'page_obj': page_obj,
        'q': q,
        'modulo_actual': modulo,
        'modulos': modulos
    })
