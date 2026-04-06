from django.urls import path
from . import views

app_name = 'tareas'

urlpatterns = [
    # Autenticación
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Tareas
    path('tareas/', views.lista_tareas, name='lista_tareas'),
    path('tareas/nueva/', views.crear_tarea, name='crear_tarea'),
    path('tareas/<int:pk>/', views.detalle_tarea, name='detalle_tarea'),
    path('tareas/<int:pk>/editar/', views.editar_tarea, name='editar_tarea'),
    path('tareas/<int:pk>/eliminar/', views.eliminar_tarea, name='eliminar_tarea'),

    # AJAX
    path('ajax/parroquias/', views.cargar_parroquias, name='cargar_parroquias'),
]
