from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Tarea, Personal, Parroquia, Departamento


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de usuario',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña',
        })
    )


class TareaForm(forms.ModelForm):

    class Meta:
        model = Tarea
        fields = [
            'titulo', 'descripcion', 'prioridad', 'estado', 'porcentaje_avance',
            'asignada_a', 'departamento',
            'fecha_inicio_planificada', 'fecha_fin_planificada', 'fecha_fin_real',
            'municipio', 'parroquia',
            'observaciones',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Título de la tarea'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción detallada...'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'porcentaje_avance': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'asignada_a': forms.Select(attrs={'class': 'form-select'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'fecha_inicio_planificada': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'class': 'form-control', 'type': 'datetime-local'}
            ),
            'fecha_fin_planificada': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'class': 'form-control', 'type': 'datetime-local'}
            ),
            'fecha_fin_real': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'class': 'form-control', 'type': 'datetime-local'}
            ),
            'municipio': forms.Select(attrs={'class': 'form-select', 'id': 'id_municipio'}),
            'parroquia': forms.Select(attrs={'class': 'form-select', 'id': 'id_parroquia'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Observaciones adicionales...'}),
        }

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)

        # Importar timezone para el valor inicial de fecha_fin_real
        from django.utils import timezone

        # Determinar si el usuario es supervisor o admin
        self.es_supervisor_o_admin = False
        if self.usuario:
            if self.usuario.is_superuser or self.usuario.is_staff:
                self.es_supervisor_o_admin = True
            else:
                try:
                    if self.usuario.personal.rol in [Personal.Rol.ADMIN, Personal.Rol.SUPERVISOR]:
                        self.es_supervisor_o_admin = True
                except Personal.DoesNotExist:
                    pass

        # Determinar si el usuario es Administrador (rol ADMIN, is_superuser, o is_staff)
        self.es_administrador = False
        if self.usuario:
            if self.usuario.is_superuser or self.usuario.is_staff:
                self.es_administrador = True
            else:
                try:
                    if self.usuario.personal.rol == Personal.Rol.ADMIN:
                        self.es_administrador = True
                except Personal.DoesNotExist:
                    pass

        # Formatear ahora en el formato que espera datetime-local
        ahora_str = timezone.now().strftime('%Y-%m-%dT%H:%M')

        # Mostrar la fecha real como deshabilitada si es una nueva tarea, en lugar de ocultarla
        if not self.instance.pk:
            if 'fecha_fin_real' in self.fields:
                self.fields['fecha_fin_real'].widget.attrs['readonly'] = True
                self.fields['fecha_fin_real'].disabled = True
                # Precargar el campo con la fecha/hora actual aunque esté deshabilitado
                self.fields['fecha_fin_real'].widget.attrs['value'] = ahora_str
            
            # Municipio por defecto: MIRANDA (ID 10)
            self.fields['municipio'].initial = 10

            # Restricción para usuarios normales: solo pueden asignarse tareas a sí mismos en su departamento
            if not self.es_supervisor_o_admin and self.usuario:
                try:
                    personal = self.usuario.personal
                    if 'asignada_a' in self.fields:
                        self.fields['asignada_a'].initial = personal
                        self.fields['asignada_a'].disabled = True
                        self.fields['asignada_a'].widget.attrs['readonly'] = True
                    if 'departamento' in self.fields:
                        self.fields['departamento'].initial = personal.departamento
                        self.fields['departamento'].disabled = True
                        self.fields['departamento'].widget.attrs['readonly'] = True
                except Personal.DoesNotExist:
                    pass
        else:
            # Es edición. Las tres fechas siempre se muestran en pantalla, pero se restringe su modificación.
            
            # 1. La fecha de inicio no se puede cambiar NUNCA (deshabilitada para todos)
            if 'fecha_inicio_planificada' in self.fields:
                self.fields['fecha_inicio_planificada'].widget.attrs['readonly'] = True
                self.fields['fecha_inicio_planificada'].disabled = True
            
            # 2. La fecha de culminación solo la pueden cambiar los administradores
            if not self.es_administrador:
                if 'fecha_fin_planificada' in self.fields:
                    self.fields['fecha_fin_planificada'].widget.attrs['readonly'] = True
                    self.fields['fecha_fin_planificada'].disabled = True
            
            # 3. La fecha de finalización real no la puede cambiar ningún usuario (se asigna automáticamente)
            if 'fecha_fin_real' in self.fields:
                self.fields['fecha_fin_real'].widget.attrs['readonly'] = True
                self.fields['fecha_fin_real'].disabled = True
                
            # 4. Los usuarios normales no pueden reasignar tareas ni cambiar el departamento
            if not self.es_supervisor_o_admin:
                if 'asignada_a' in self.fields:
                    self.fields['asignada_a'].disabled = True
                    self.fields['asignada_a'].widget.attrs['readonly'] = True
                if 'departamento' in self.fields:
                    self.fields['departamento'].disabled = True
                    self.fields['departamento'].widget.attrs['readonly'] = True

        # Filtrar choices de estado si no es administrador
        if 'estado' in self.fields:
            if not self.es_administrador:
                # Si la tarea ya está completada, deshabilitar el campo estado
                # para que no puedan cambiarlo a otra cosa tampoco.
                if self.instance.pk and self.instance.estado == Tarea.Estado.COMPLETADA:
                    self.fields['estado'].disabled = True
                    self.fields['estado'].widget.attrs['readonly'] = True
                else:
                    # Excluir 'CO' (Completada) del listado de opciones
                    self.fields['estado'].choices = [
                        choice for choice in self.fields['estado'].choices
                        if choice[0] != Tarea.Estado.COMPLETADA
                    ]

        # Limitar los departamentos y personal visibles según el usuario
        if self.usuario and not self.usuario.is_superuser:
            try:
                personal = self.usuario.personal
                dept_ids = personal.get_departamentos_visibles()
                self.fields['departamento'].queryset = Departamento.objects.filter(id__in=dept_ids)
                personal_qs = Personal.objects.filter(
                    departamento__id__in=dept_ids, activo=True
                ).select_related('usuario', 'departamento')
            except Personal.DoesNotExist:
                self.fields['departamento'].queryset = Departamento.objects.none()
                personal_qs = Personal.objects.none()
        else:
            personal_qs = Personal.objects.filter(activo=True).select_related('usuario', 'departamento')

        # Filtrar personal según el departamento seleccionado (para AJAX o carga inicial)
        departamento_id = None
        if self.instance.pk and self.instance.departamento:
            departamento_id = self.instance.departamento.id
        elif 'departamento' in self.data:
            try:
                departamento_id = int(self.data.get('departamento'))
            except (ValueError, TypeError):
                pass
        elif not self.instance.pk and 'departamento' in self.fields and self.fields['departamento'].initial:
            val = self.fields['departamento'].initial
            if hasattr(val, 'id'):
                departamento_id = val.id
            else:
                try:
                    departamento_id = int(val)
                except (ValueError, TypeError):
                    pass

        if departamento_id:
            self.fields['asignada_a'].queryset = personal_qs.filter(departamento_id=departamento_id)
            self.fields['asignada_a'].empty_label = "Seleccione una persona"
        else:
            self.fields['asignada_a'].queryset = Personal.objects.none()
            self.fields['asignada_a'].empty_label = "Seleccione un departamento responsable primero"


        # Filtrar parroquias según el municipio seleccionado (para AJAX o carga inicial)
        municipio_id = None
        if self.instance.pk and self.instance.municipio:
            municipio_id = self.instance.municipio.id
        elif 'municipio' in self.data:
            try:
                municipio_id = int(self.data.get('municipio'))
            except (ValueError, TypeError):
                pass
        elif not self.instance.pk and self.fields['municipio'].initial:
            # Usar municipio por defecto para filtrar parroquias en creación
            municipio_id = self.fields['municipio'].initial

        if municipio_id:
            self.fields['parroquia'].queryset = Parroquia.objects.filter(municipio_id=municipio_id)
            self.fields['parroquia'].empty_label = "Seleccione una parroquia"
        else:
            self.fields['parroquia'].queryset = Parroquia.objects.none()
            self.fields['parroquia'].empty_label = "Seleccione una parroquia"

        # Labels en español
        self.fields['asignada_a'].label_from_instance = lambda obj: f"{obj.get_nombre_completo()} — {obj.departamento.nombre}"

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('fecha_inicio_planificada')
        fin = cleaned_data.get('fecha_fin_planificada')
        ff_real = cleaned_data.get('fecha_fin_real')
        porcentaje = cleaned_data.get('porcentaje_avance', 0)
        estado = cleaned_data.get('estado')

        from django.utils import timezone

        # Lógica de porcentaje para no administradores (máximo 99%)
        if not self.es_administrador:
            if porcentaje > 99:
                cleaned_data['porcentaje_avance'] = 99
                porcentaje = 99

        # Si el administrador marca 100% de avance, forzar estado a COMPLETADA
        if self.es_administrador and porcentaje == 100 and estado != Tarea.Estado.COMPLETADA:
            cleaned_data['estado'] = Tarea.Estado.COMPLETADA
            estado = Tarea.Estado.COMPLETADA

        # Si el administrador ingresa una fecha real manualmente, forzar estado COMPLETADA y 100%
        if self.es_administrador and ff_real and estado != Tarea.Estado.COMPLETADA:
            cleaned_data['estado'] = Tarea.Estado.COMPLETADA
            estado = Tarea.Estado.COMPLETADA
            cleaned_data['porcentaje_avance'] = 100
            porcentaje = 100

        # Lógica de sincronización de fecha_fin_real con estado COMPLETADA
        if estado == Tarea.Estado.COMPLETADA:
            if not self.instance.pk or self.instance.estado != Tarea.Estado.COMPLETADA:
                # Cambió a completada ahora
                cleaned_data['fecha_fin_real'] = timezone.now()
                cleaned_data['porcentaje_avance'] = 100
            else:
                # Ya era completada
                cleaned_data['porcentaje_avance'] = 100
                if not ff_real:
                    cleaned_data['fecha_fin_real'] = self.instance.fecha_fin_real or timezone.now()
        else:
            # Si el estado cambió de COMPLETADA a otra cosa, limpiar fecha_fin_real
            if self.instance.pk and self.instance.estado == Tarea.Estado.COMPLETADA:
                cleaned_data['fecha_fin_real'] = None
                if porcentaje == 100:
                    cleaned_data['porcentaje_avance'] = 99
            elif not self.instance.pk:
                cleaned_data['fecha_fin_real'] = None

        if inicio and fin and fin < inicio:
            raise forms.ValidationError(
                'La fecha de culminación planificada no puede ser anterior a la fecha de inicio.'
            )

        # Validar que la persona asignada pertenezca al departamento responsable
        asignada_a = cleaned_data.get('asignada_a')
        departamento = cleaned_data.get('departamento')
        if asignada_a and departamento and asignada_a.departamento != departamento:
            raise forms.ValidationError(
                'El trabajador asignado debe pertenecer al departamento responsable.'
            )

        return cleaned_data



class PersonalForm(forms.ModelForm):
    class Meta:
        model = Personal
        fields = [
            'nombres', 'apellidos', 'cedula', 
            'telefono', 'cargo', 'departamento', 'es_jefe', 'rol', 'activo'
        ]
        widgets = {
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres'}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}),
            'cedula': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula de Identidad'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono'}),
            'cargo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cargo / Puesto'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'es_jefe': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer todos los campos obligatorios excepto es_jefe y activo (que son checkboxes)
        for field in self.fields:
            if field not in ['es_jefe', 'activo']:
                self.fields[field].required = True

    def clean_cedula(self):
        cedula = self.cleaned_data.get('cedula')
        if not cedula.isdigit():
            raise forms.ValidationError('La cédula debe contener solo números.')
        return cedula

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        if not telefono.isdigit():
            raise forms.ValidationError('El teléfono debe contener solo números.')
        return telefono

    def clean_nombres(self):
        nombres = self.cleaned_data.get('nombres')
        if nombres:
            return nombres.upper()
        return nombres

    def clean_apellidos(self):
        apellidos = self.cleaned_data.get('apellidos')
        if apellidos:
            return apellidos.upper()
        return apellidos

class CambioEstadoPersonalForm(forms.Form):
    razon = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Indique el motivo o razón del cambio de estado...',
            'required': True
        }),
        label="Razón / Motivo"
    )

class VerificarCedulaForm(forms.Form):
    cedula = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. V-12345678',
            'autofocus': True,
        }),
        label="Cédula de Identidad"
    )

    def clean_cedula(self):
        cedula = self.cleaned_data.get('cedula').strip()
        try:
            persona = Personal.objects.get(cedula=cedula)
        except Personal.DoesNotExist:
            raise forms.ValidationError('No se encontró ningún trabajador registrado con esta cédula.')
        
        if not persona.activo:
            raise forms.ValidationError('El trabajador con esta cédula se encuentra Inactivo y no puede registrarse.')

        if persona.usuario is not None:
            raise forms.ValidationError('El trabajador asociado a esta cédula ya tiene una cuenta registrada.')

        return cedula

class VincularUsuarioForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de usuario'}),
        label="Nombre de Usuario"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'}),
        label="Contraseña"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirmar Contraseña'}),
        label="Confirmar Contraseña"
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        from django.contrib.auth.models import User
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return cleaned_data

