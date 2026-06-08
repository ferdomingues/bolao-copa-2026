from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import LoginFormPersonalizado

urlpatterns = [
    # Raiz do site abre a classificação da Copa
    path('classificacao/', views.tabela_campeonato_view, name='tabela_campeonato'),

    # Palpites
    path('palpites/', views.lista_palpites_view, name='lista_palpites'),
    path('palpites/salvar/<int:jogo_id>/',
         views.salvar_palpite_view, name='salvar_palpite'),

    # Bolão
    path('classificacao-bolao/', views.classificacao_bolao_view,
         name='classificacao_bolao'),
    path('cadastro/', views.cadastro_view, name='cadastro'),
    path('', views.dashboard_view, name='home'),

    # Autenticação (Apenas uma de cada!)
    path('login/', auth_views.LoginView.as_view(
        template_name='bolao/login.html',
        authentication_form=LoginFormPersonalizado
    ), name='login'),

    path('logout/', views.logout_personalizado_view, name='logout'),]
