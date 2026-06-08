import string
from bolao.services import gerar_classificacao_grupo
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, time, timedelta
from .models import Jogo, Palpite, Selecao
from django.contrib.auth.models import User
from django.db.models import Sum
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout
from django.http import HttpResponse
from django.core.management import call_command


def tabela_campeonato_view(request):
    # Copa 2026 tem 12 grupos: A, B, C, D, E, F, G, H, I, J, K, L
    letras_grupos = list(string.ascii_uppercase[:12])

    # Monta um dicionário onde a chave é a letra e o valor é a lista classificada
    classificacao_copa = {}
    for letra in letras_grupos:
        classificacao_copa[letra] = gerar_classificacao_grupo(letra)

    # 🚀 OTIMIZAÇÃO 1: select_related traz as seleções no mesmo SELECT (Elimina mais de 200 queries de N+1)
    # Carregamos TODOS os jogos uma única vez para a memória
    jogos_copa = list(Jogo.objects.select_related(
        'selecao_casa', 'selecao_fora').order_by('data_hora'))

    # 🚀 OTIMIZAÇÃO 2: Filtra as fases na memória RAM usando Python em vez de fazer 5 queries novas ao banco
    fases_mata_mata = [
        {
            'id': '16_AVOS',
            'titulo': '⚡ 16 avos de Final',
            'bg_class': 'bg-danger-subtle text-danger-emphasis border-bottom border-danger-subtle',
            'jogos': [j for j in jogos_copa if j.fase == '16_AVOS']
        },
        {
            'id': 'OITAVAS',
            'titulo': '💥 Oitavas de Final',
            'bg_class': 'bg-primary-subtle text-primary-emphasis border-bottom border-primary-subtle',
            'jogos': [j for j in jogos_copa if j.fase == 'OITAVAS']
        },
        {
            'id': 'QUARTAS',
            'titulo': '🛡️ Quartas de Final',
            'bg_class': 'bg-info text-dark',
            'jogos': [j for j in jogos_copa if j.fase == 'QUARTAS']
        },
        {
            'id': 'SEMIFINAL',
            'titulo': '🔥 Semifinal',
            'bg_class': 'bg-primary',
            'jogos': [j for j in jogos_copa if j.fase == 'SEMIFINAL']
        },
        {
            'id': 'FINAL',
            'titulo': '🏆 Grande Final',
            'bg_class': 'bg-warning text-dark',
            'jogos': [j for j in jogos_copa if j.fase == 'FINAL']
        },
    ]

    context = {
        'classificacao_copa': classificacao_copa,
        'jogos_copa': jogos_copa,
        'fases_mata_mata': fases_mata_mata,
    }
    return render(request, 'bolao/classificacao.html', context)


@login_required
def lista_palpites_view(request):
    # 🚀 OTIMIZAÇÃO 3: select_related evita lentidão ao carregar as bandeiras/nomes na tela de palpites
    jogos = Jogo.objects.select_related(
        'selecao_casa', 'selecao_fora').order_by('data_hora')

    palpites_existentes = Palpite.objects.filter(usuario=request.user)
    meus_palpites = {p.jogo_id: p for p in palpites_existentes}

    context = {
        'jogos': jogos,
        'meus_palpites': meus_palpites,
    }
    return render(request, 'bolao/palpites.html', context)


@login_required
def salvar_palpite_view(request, jogo_id):
    if request.method == 'POST':
        # Mantido select_related aqui para garantir velocidade na mensagem de sucesso que usa os nomes
        jogo = get_object_or_404(Jogo.objects.select_related(
            'selecao_casa', 'selecao_fora'), id=jogo_id)

        if jogo.bloqueado:
            messages.error(
                request, "Tempo esgotado! As apostas fecham 1 hora antes do início.")
            return redirect(f"{request.META.get('HTTP_REFERER', '/palpites/')}#jogo-{jogo_id}")

        gols_casa_raw = request.POST.get('gols_casa')
        gols_fora_raw = request.POST.get('gols_fora')

        try:
            gols_casa = int(
                gols_casa_raw) if gols_casa_raw and gols_casa_raw.isdigit() else 0
            gols_fora = int(
                gols_fora_raw) if gols_fora_raw and gols_fora_raw.isdigit() else 0

            Palpite.objects.update_or_create(
                usuario=request.user,
                jogo=jogo,
                defaults={'gols_casa': gols_casa, 'gols_fora': gols_fora}
            )
            messages.success(
                request, f"Palpite salvo para {jogo.selecao_casa.nome} x {jogo.selecao_fora.nome}!")
        except Exception as e:
            messages.error(request, "Erro ao salvar o palpite.")

    return redirect(f"{request.META.get('HTTP_REFERER', '/palpites/')}#jogo-{jogo_id}")


def classificacao_bolao_view(request):
    ranking = User.objects.annotate(
        total_pontos=Sum('palpites__pontos_ganhos')
    ).order_by('-total_pontos')
    return render(request, 'bolao/classificacao_bolao.html', {'ranking': ranking})


def cadastro_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, "Conta criada com sucesso! Bem-vindo ao Bolão.")
            return redirect('lista_palpites')
        else:
            messages.error(request, "Erro ao criar conta. Verifique os dados.")
    else:
        form = UserCreationForm()
        for field in form.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'

    return render(request, 'bolao/cadastro.html', {'form': form})


@login_required
def dashboard_view(request):
    ranking = User.objects.annotate(
        total_pontos=Sum('palpites__pontos_ganhos')
    ).order_by('-total_pontos')

    agora = timezone.now()
    dia_limite = agora.date() + timedelta(days=3)
    data_limite_completa = datetime.combine(dia_limite, time.max)
    data_limite = timezone.make_aware(
        data_limite_completa, timezone.get_current_timezone())

    # 🚀 OTIMIZAÇÃO 4: Adicionado select_related para a listagem rápida na Home
    proximos_jogos = Jogo.objects.select_related('selecao_casa', 'selecao_fora').filter(
        data_hora__gte=agora, data_hora__lte=data_limite
    )

    context = {
        'ranking': ranking,
        'proximos_jogos': proximos_jogos,
    }
    return render(request, 'bolao/home.html', context)


def logout_personalizado_view(request):
    logout(request)
    return redirect('login')


def trigger_atualizacao(request):
    call_command('importar_jogos')
    return HttpResponse("Jogos atualizados com sucesso!")
