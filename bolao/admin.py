from django.contrib import admin
from .models import Selecao, Jogo, Palpite

# Registrando os modelos para que apareçam no painel visual
admin.site.register(Selecao)
admin.site.register(Jogo)
admin.site.register(Palpite)
