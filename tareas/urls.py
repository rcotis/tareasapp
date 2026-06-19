from django.urls import path
from . import views

app_name = 'tareas'

urlpatterns = [
    # Autenticación
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/verificar/', views.verificar_cedula_registro, name='verificar_cedula_registro'),
    path('registro/crear/', views.registro_usuario, name='registro_usuario'),
    path('perfil/cambio-password/', views.cambio_password, name='cambio_password'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Tareas
    path('tareas/', views.lista_tareas, name='lista_tareas'),
    path('tareas/reporte-pdf/', views.reporte_tareas_pdf, name='reporte_tareas_pdf'),
    path('tareas/nueva/', views.crear_tarea, name='crear_tarea'),
    path('tareas/<int:pk>/', views.detalle_tarea, name='detalle_tarea'),
    path('tareas/<int:pk>/editar/', views.editar_tarea, name='editar_tarea'),
    path('tareas/<int:pk>/eliminar/', views.eliminar_tarea, name='eliminar_tarea'),

    # Personal
    path('personal/', views.lista_personal, name='lista_personal'),
    path('personal/nuevo/', views.registrar_personal, name='registrar_personal'),
    path('personal/<int:pk>/editar/', views.editar_personal, name='editar_personal'),
    path('personal/<int:pk>/estado/', views.toggle_estado_personal, name='toggle_estado_personal'),
    
    # Usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/cambiar-rol/<int:user_id>/', views.cambiar_rol_usuario, name='cambiar_rol_usuario'),
    path('usuarios/restablecer-password/<int:user_id>/', views.restablecer_password_usuario, name='restablecer_password_usuario'),
    path('usuarios/vincular/<int:pk>/', views.vincular_usuario_personal, name='vincular_usuario_personal'),
    
    # Bitácora
    path('bitacora/', views.lista_bitacora, name='lista_bitacora'),

    # AJAX
    path('ajax/parroquias/', views.cargar_parroquias, name='cargar_parroquias'),
    path('ajax/personal-departamento/', views.cargar_personal_departamento, name='cargar_personal_departamento'),
]

