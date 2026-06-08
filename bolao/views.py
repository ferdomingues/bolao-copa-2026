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

    jogos_copa = Jogo.objects.all().order_by('data_hora')

    # 🔄 BUSCA DINÂMICA: Centraliza a ordem das fases e as queries do banco de dados
    # 🔄 BUSCA DINÂMICA: Tons pastel modernos (Recomendado)
    fases_mata_mata = [
        {'id': '16_AVOS', 'titulo': '⚡ 16 avos de Final', 'bg_class': 'bg-danger-subtle text-danger-emphasis border-bottom border-danger-subtle',
            'jogos': Jogo.objects.filter(fase='16_AVOS').order_by('data_hora')},
        {'id': 'OITAVAS', 'titulo': '💥 Oitavas de Final', 'bg_class': 'bg-primary-subtle text-primary-emphasis border-bottom border-primary-subtle',
            'jogos': Jogo.objects.filter(fase='OITAVAS').order_by('data_hora')},
        {'id': 'QUARTAS', 'titulo': '🛡️ Quartas de Final', 'bg_class': 'bg-info text-dark',
            'jogos': Jogo.objects.filter(fase='QUARTAS').order_by('data_hora')},
        {'id': 'SEMIFINAL', 'titulo': '🔥 Semifinal', 'bg_class': 'bg-primary',
            'jogos': Jogo.objects.filter(fase='SEMIFINAL').order_by('data_hora')},
        {'id': 'FINAL', 'titulo': '🏆 Grande Final', 'bg_class': 'bg-warning text-dark',
            'jogos': Jogo.objects.filter(fase='FINAL').order_by('data_hora')},
    ]
    context = {
        'classificacao_copa': classificacao_copa,
        'jogos_copa': jogos_copa,
        'fases_mata_mata': fases_mata_mata,  # Enviando a estrutura dinâmica para o HTML
    }
    return render(request, 'bolao/classificacao.html', context)


@login_required
def lista_palpites_view(request):
    jogos = Jogo.objects.all().order_by('data_hora')
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
        jogo = get_object_or_404(Jogo, id=jogo_id)

        # 🔒 VALIDAÇÃO DE SEGURANÇA: Checa se está dentro do horário permitido
        if jogo.bloqueado:
            messages.error(
                request, "Tempo esgotado! As apostas fecham 1 hora antes do início.")
            return redirect(f"{request.META.get('HTTP_REFERER', '/palpites/')}#jogo-{jogo_id}")

        # Como o HTML agora tem um botão "Editar" que destrava o form,
        # se o form foi submetido, é porque o usuário realmente quer salvar/atualizar.
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
    # O Django faz a soma de todos os 'pontos_ganhos' de cada usuário no banco
    ranking = User.objects.annotate(
        total_pontos=Sum('palpites__pontos_ganhos')
    ).order_by('-total_pontos')

    return render(request, 'bolao/classificacao_bolao.html', {'ranking': ranking})


def cadastro_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            # Cria o usuário no banco de dados
            user = form.save()

            # Loga o usuário automaticamente após o cadastro (opcional)
            login(request, user)

            messages.success(
                request, "Conta criada com sucesso! Bem-vindo ao Bolão.")
            return redirect('lista_palpites')  # Nome da sua view de palpites
        else:
            # Se o formulário tiver erros (ex: senhas não coincidem)
            messages.error(request, "Erro ao criar conta. Verifique os dados.")
    else:
        # Se for um GET (carregamento da página), cria um form vazio
        form = UserCreationForm()
        for field in form.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'

    return render(request, 'bolao/cadastro.html', {'form': form})


@login_required
def dashboard_view(request):
    # 1. Busca o Ranking do Bolão
    ranking = User.objects.annotate(
        # Verifique se o nome do campo de pontos é esse
        total_pontos=Sum('palpites__pontos_ganhos')
    ).order_by('-total_pontos')

    # 2. Busca os Próximos Jogos (Hoje até daqui a 3 dias)
    agora = timezone.now()
    dia_limite = agora.date() + timedelta(days=3)
    data_limite_completa = datetime.combine(dia_limite, time.max)
    data_limite = timezone.make_aware(
        data_limite_completa, timezone.get_current_timezone())

    proximos_jogos = Jogo.objects.filter(
        data_hora__gte=agora, data_hora__lte=data_limite)

    context = {
        'ranking': ranking,
        'proximos_jogos': proximos_jogos,
    }
    return render(request, 'bolao/home.html', context)


def logout_personalizado_view(request):
    logout(request)
    return redirect('login')


def trigger_atualizacao(request):
    # Isto executa o seu comando 'importar_jogos' como se fosses tu no terminal
    call_command('importar_jogos')
    return HttpResponse("Jogos atualizados com sucesso!")
