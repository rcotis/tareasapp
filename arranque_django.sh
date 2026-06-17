#!/bin/bash
## Inicia el Sistema de  Asignación de Tareas
echo "Iniciando Servicios..."
clear
echo "Iniciando la aplicación"
cd /home/jefe/tareasapp
/home/jefe/tareasapp/venv/bin/python3 manage.py runserver 0.0.0.0:5000
