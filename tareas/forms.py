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
            'titulo', 'descripcion', 'prioridad', 'estado',
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
            'asignada_a': forms.Select(attrs={'class': 'form-select'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'fecha_inicio_planificada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin_planificada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin_real': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'municipio': forms.Select(attrs={'class': 'form-select', 'id': 'id_municipio'}),
            'parroquia': forms.Select(attrs={'class': 'form-select', 'id': 'id_parroquia'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Observaciones adicionales...'}),
        }

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)

        # Limitar los departamentos y personal visibles según el usuario
        if self.usuario and not self.usuario.is_superuser:
            try:
                personal = self.usuario.personal
                dept_ids = personal.get_departamentos_visibles()
                self.fields['departamento'].queryset = Departamento.objects.filter(id__in=dept_ids)
                self.fields['asignada_a'].queryset = Personal.objects.filter(
                    departamento__id__in=dept_ids
                ).select_related('usuario', 'departamento')
            except Personal.DoesNotExist:
                self.fields['departamento'].queryset = Departamento.objects.none()
                self.fields['asignada_a'].queryset = Personal.objects.none()
        else:
            self.fields['asignada_a'].queryset = Personal.objects.select_related('usuario', 'departamento').all()

        # Filtrar parroquias según el municipio ya seleccionado (en edición)
        if self.instance.pk and self.instance.municipio:
            self.fields['parroquia'].queryset = Parroquia.objects.filter(
                municipio=self.instance.municipio
            )
        elif 'municipio' in self.data:
            try:
                municipio_id = int(self.data.get('municipio'))
                self.fields['parroquia'].queryset = Parroquia.objects.filter(municipio_id=municipio_id)
            except (ValueError, TypeError):
                self.fields['parroquia'].queryset = Parroquia.objects.none()
        else:
            self.fields['parroquia'].queryset = Parroquia.objects.none()

        # Labels en español
        self.fields['asignada_a'].label_from_instance = lambda obj: f"{obj.get_nombre_completo()} — {obj.departamento.nombre}"

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('fecha_inicio_planificada')
        fin = cleaned_data.get('fecha_fin_planificada')
        if inicio and fin and fin < inicio:
            raise forms.ValidationError(
                'La fecha de culminación planificada no puede ser anterior a la fecha de inicio.'
            )
        return cleaned_data
