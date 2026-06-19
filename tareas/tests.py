from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
from .models import Tarea, Personal, Departamento
from .forms import TareaForm

class TareaBusinessRulesTestCase(TestCase):
    def setUp(self):
        # Create department
        self.depto = Departamento.objects.create(
            nombre="Tecnología",
            nivel=Departamento.Nivel.UNIDAD
        )
        
        # Create user and personal for Admin
        self.admin_user = User.objects.create_user(username="admin_user", password="password")
        self.admin_personal = Personal.objects.create(
            usuario=self.admin_user,
            rol=Personal.Rol.ADMIN,
            nombres="Admin",
            apellidos="User",
            cedula="11111111",
            departamento=self.depto
        )
        
        # Create user and personal for Normal User
        self.normal_user = User.objects.create_user(username="normal_user", password="password")
        self.normal_personal = Personal.objects.create(
            usuario=self.normal_user,
            rol=Personal.Rol.USUARIO,
            nombres="Normal",
            apellidos="User",
            cedula="22222222",
            departamento=self.depto
        )

        # Create basic task data
        self.now = timezone.now()
        self.inicio = self.now - timedelta(days=2)
        self.fin_planificada = self.now + timedelta(days=2)

    def test_dias_retraso_no_delay(self):
        # Task completed on time
        t1 = Tarea.objects.create(
            titulo="Tarea A",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            fecha_fin_real=self.now,
            estado=Tarea.Estado.COMPLETADA
        )
        self.assertEqual(t1.dias_retraso, 0)

        # Task in progress, not yet past due
        t2 = Tarea.objects.create(
            titulo="Tarea B",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            estado=Tarea.Estado.PENDIENTE
        )
        self.assertEqual(t2.dias_retraso, 0)

    def test_dias_retraso_completed_with_delay(self):
        # Task completed 2.5 days late (rounded up to 3 days)
        fin_real_tardio = self.fin_planificada + timedelta(days=2, hours=12)
        t = Tarea.objects.create(
            titulo="Tarea C",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            fecha_fin_real=fin_real_tardio,
            estado=Tarea.Estado.COMPLETADA
        )
        self.assertEqual(t.dias_retraso, 3)

    def test_dias_retraso_overdue_not_completed(self):
        # Task not completed, past due by 1.5 days (rounded up to 2 days)
        fin_planificada_pasada = self.now - timedelta(days=1, hours=12)
        t = Tarea.objects.create(
            titulo="Tarea D",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=fin_planificada_pasada,
            estado=Tarea.Estado.PENDIENTE
        )
        self.assertEqual(t.dias_retraso, 2)

    def test_form_restrictions_normal_user(self):
        # For a normal user editing an existing task
        t = Tarea.objects.create(
            titulo="Tarea E",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            estado=Tarea.Estado.PENDIENTE
        )
        
        form = TareaForm(instance=t, usuario=self.normal_user)
        # Check that completions fields/choices are restricted
        self.assertTrue(form.fields['fecha_fin_planificada'].disabled)
        self.assertTrue(form.fields['fecha_fin_real'].disabled)
        
        # Verify 'CO' is not in the choices
        choices_codes = [c[0] for c in form.fields['estado'].choices]
        self.assertNotIn(Tarea.Estado.COMPLETADA, choices_codes)

    def test_form_restrictions_admin(self):
        # For an admin user editing an existing task
        t = Tarea.objects.create(
            titulo="Tarea F",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            estado=Tarea.Estado.PENDIENTE
        )
        
        form = TareaForm(instance=t, usuario=self.admin_user)
        # Verify admin has fecha_fin_planificada enabled, but NOT fecha_fin_real (which is disabled for everyone)
        self.assertFalse(form.fields['fecha_fin_planificada'].disabled)
        self.assertTrue(form.fields['fecha_fin_real'].disabled)
        
        # Verify 'CO' is in choices
        choices_codes = [c[0] for c in form.fields['estado'].choices]
        self.assertIn(Tarea.Estado.COMPLETADA, choices_codes)

    def test_form_clean_completada_sets_date_automatically(self):
        # For an admin, changing status to Completed sets fecha_fin_real
        t = Tarea.objects.create(
            titulo="Tarea G",
            creada_por=self.admin_personal,
            asignada_a=self.normal_personal,
            departamento=self.depto,
            fecha_inicio_planificada=self.inicio,
            fecha_fin_planificada=self.fin_planificada,
            estado=Tarea.Estado.PENDIENTE
        )
        
        post_data = {
            'titulo': "Tarea G",
            'descripcion': t.descripcion,
            'prioridad': t.prioridad,
            'estado': Tarea.Estado.COMPLETADA,
            'porcentaje_avance': 50, # Admin sets 50% but marks as Completed
            'asignada_a': self.normal_personal.id,
            'departamento': self.depto.id,
            'fecha_inicio_planificada': self.inicio.strftime('%Y-%m-%dT%H:%M'),
            'fecha_fin_planificada': self.fin_planificada.strftime('%Y-%m-%dT%H:%M'),
        }
        
        form = TareaForm(data=post_data, instance=t, usuario=self.admin_user)
        self.assertTrue(form.is_valid())
        cleaned_data = form.cleaned_data
        self.assertEqual(cleaned_data['estado'], Tarea.Estado.COMPLETADA)
        self.assertEqual(cleaned_data['porcentaje_avance'], 100)
        self.assertIsNotNone(cleaned_data['fecha_fin_real'])

    def test_restablecer_password_usuario_admin_access(self):
        # Admin can access password reset page
        self.client.force_login(self.admin_user)
        from django.urls import reverse
        url = reverse('tareas:restablecer_password_usuario', args=[self.normal_user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_restablecer_password_usuario_normal_user_denied(self):
        # Normal user cannot access password reset page
        self.client.force_login(self.normal_user)
        from django.urls import reverse
        url = reverse('tareas:restablecer_password_usuario', args=[self.admin_user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # Redirects to dashboard

    def test_restablecer_password_usuario_post_success(self):
        # Admin submits valid passwords to reset user password
        self.client.force_login(self.admin_user)
        from django.urls import reverse
        url = reverse('tareas:restablecer_password_usuario', args=[self.normal_user.id])
        
        # SetPasswordForm expects 'new_password1' and 'new_password2'
        post_data = {
            'new_password1': 'NewSecurePassword123!',
            'new_password2': 'NewSecurePassword123!'
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302) # Redirects to user list
        
        # Verify password actually changed
        self.normal_user.refresh_from_db()
        self.assertTrue(self.normal_user.check_password('NewSecurePassword123!'))

    def test_ajax_cargar_personal_departamento(self):
        self.client.force_login(self.admin_user)
        from django.urls import reverse
        url = reverse('tareas:cargar_personal_departamento')
        response = self.client.get(url, {'departamento_id': self.depto.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('personal', data)
        # Check that both personal profiles are returned
        personal_ids = [p['id'] for p in data['personal']]
        self.assertIn(self.admin_personal.id, personal_ids)
        self.assertIn(self.normal_personal.id, personal_ids)

    def test_form_validation_personal_outside_department(self):
        # Create a second department and personal in it
        depto_b = Departamento.objects.create(
            nombre="Recursos Humanos",
            nivel=Departamento.Nivel.UNIDAD
        )
        personal_b = Personal.objects.create(
            rol=Personal.Rol.USUARIO,
            nombres="Pedro",
            apellidos="Perez",
            cedula="33333333",
            departamento=depto_b
        )

        post_data = {
            'titulo': "Tarea de prueba",
            'descripcion': "Prueba de validacion de departamento",
            'prioridad': Tarea.Prioridad.MEDIA,
            'estado': Tarea.Estado.PENDIENTE,
            'porcentaje_avance': 0,
            'asignada_a': personal_b.id, # Assigned to B
            'departamento': self.depto.id, # But department is A
            'fecha_inicio_planificada': self.inicio.strftime('%Y-%m-%dT%H:%M'),
            'fecha_fin_planificada': self.fin_planificada.strftime('%Y-%m-%dT%H:%M'),
        }

        form = TareaForm(data=post_data, usuario=self.admin_user)
        self.assertFalse(form.is_valid())
        self.assertIn('asignada_a', form.errors)


