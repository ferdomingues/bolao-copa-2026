from django.db import transaction
from django.db.models import Q,Sum
from bolao.models import Jogo, Palpite, PerfilUsuario, Selecao


def gerar_classificacao_grupo(letra_grupo):
    # 1. Busca todas as seleções do grupo específico
    selecoes = Selecao.objects.filter(grupo=letra_grupo.upper())

    # 2. Inicializa o dicionário de estatísticas para cada seleção
    tabela = {}
    for s in selecoes:
        tabela[s.id] = {
            'selecao': s,
            'pontos': 0,
            'jogos': 0,
            'vitorias': 0,
            'empates': 0,
            'derrotas': 0,
            'gols_pro': 0,
            'gols_contra': 0,
            'saldo_gols': 0
        }

    # 3. Busca apenas os jogos da fase de grupos que JÁ ACONTECERAM (com placar preenchido)
    jogos = Jogo.objects.filter(
        fase='GRUPOS',
        gols_casa__isnull=False,
        gols_fora__isnull=False
    ).filter(
        Q(selecao_casa__grupo=letra_grupo.upper()) |
        Q(selecao_fora__grupo=letra_grupo.upper())
    ).distinct()

    # 4. Processa o resultado de cada jogo para somar os pontos
    for jogo in jogos:
        g_casa = jogo.gols_casa
        g_fora = jogo.gols_fora

        # Se a seleção da casa pertence a este grupo, calcula as estatísticas dela
        if jogo.selecao_casa.id in tabela:
            stats = tabela[jogo.selecao_casa.id]
            stats['jogos'] += 1
            stats['gols_pro'] += g_casa
            stats['gols_contra'] += g_fora

            if g_casa > g_fora:
                stats['pontos'] += 3
                stats['vitorias'] += 1
            elif g_casa == g_fora:
                stats['pontos'] += 1
                stats['empates'] += 1
            else:
                stats['derrotas'] += 1

        # Se a seleção de fora pertence a este grupo, calcula as estatísticas dela
        if jogo.selecao_fora.id in tabela:
            stats = tabela[jogo.selecao_fora.id]
            stats['jogos'] += 1
            stats['gols_pro'] += g_fora
            stats['gols_contra'] += g_casa

            if g_fora > g_casa:
                stats['pontos'] += 3
                stats['vitorias'] += 1
            elif g_casa == g_fora:
                stats['pontos'] += 1
                stats['empates'] += 1
            else:
                stats['derrotas'] += 1

    # 5. Calcula o saldo de gols e transforma o dicionário em uma lista
    lista_classificacao = []
    for s_id, stats in tabela.items():
        stats['saldo_gols'] = stats['gols_pro'] - stats['gols_contra']
        lista_classificacao.append(stats)

    # 6. Ordena pelos critérios de desempate da FIFA: Pontos -> Vitórias -> Saldo de Gols -> Gols Pró
    lista_classificacao.sort(
        key=lambda x: (x['pontos'], x['vitorias'],
                       x['saldo_gols'], x['gols_pro']),
        reverse=True
    )

    return lista_classificacao


def computar_pontos_do_jogo(jogo_id):
    """
    Calcula os pontos dos palpites de um jogo e atualiza o ranking.
    Inclui logs de depuração para rastreamento no terminal.
    """
    print(f"🔍 [Motor] Iniciando computação para o Jogo ID: {jogo_id}")

    try:
        jogo = Jogo.objects.get(id=jogo_id)
    except Jogo.DoesNotExist:
        return f"❌ Erro: Jogo {jogo_id} não encontrado."

    if jogo.gols_casa is None or jogo.gols_fora is None:
        return "⚠️ Jogo sem placar oficial definido."

    # Busca os palpites vinculados a ESTE jogo específico
    palpites = Palpite.objects.filter(jogo=jogo)
    print(
        f"📊 [Motor] Total de palpites encontrados para este jogo: {palpites.count()}")

    if not palpites.exists():
        return "⚠️ Nenhum palpite foi registrado para este jogo. Nada a calcular."

    palpites_para_salvar = []
    usuarios_afetados = set()

    r_casa = int(jogo.gols_casa)
    r_fora = int(jogo.gols_fora)
    vencedor_real = 'CASA' if r_casa > r_fora else 'FORA' if r_fora > r_casa else 'EMPATE'

    for palpite in palpites:
        # Garante o uso de gols_casa e gols_fora limpos
        p_casa = int(palpite.gols_casa if palpite.gols_casa is not None else 0)
        p_fora = int(palpite.gols_fora if palpite.gols_fora is not None else 0)
        vencedor_palpite = 'CASA' if p_casa > p_fora else 'FORA' if p_fora > p_casa else 'EMPATE'

        # Lógica de Pontuação (Seus novos pesos: 3 e 1)
        if p_casa == r_casa and p_fora == r_fora:
            pontos = 3  # Placar Cheio
        elif vencedor_palpite == vencedor_real:
            if p_casa == r_casa or p_fora == r_fora:
                pontos = 1  # Placar parcial
            else:
                # Placar parcial (se mantiver 1 para qualquer acerto de vencedor)
                pontos = 1
        else:
            pontos = 0

        palpite.pontos_ganhos = pontos
        palpites_para_salvar.append(palpite)
        usuarios_afetados.add(palpite.usuario.id)

    # Salva os palpites atualizados
    if p_casa is not None:  # Verificação de segurança de escopo
        if palpites_para_salvar:
            Palpite.objects.bulk_update(
                palpites_para_salvar, ['pontos_ganhos'])
            print(
                f"💾 [Motor] {len(palpites_para_salvar)} palpites updated via bulk_update.")

    # Atualiza o Ranking Geral (PerfilUsuario)
    print(
        f"👥 [Motor] Atualizando o perfil de {len(usuarios_afetados)} usuários afetados...")
    with transaction.atomic():
        perfis_para_salvar = []
        perfis = PerfilUsuario.objects.filter(usuario_id__in=usuarios_afetados)

        for perfil in perfis:
            total_pontos = Palpite.objects.filter(usuario=perfil.usuario).aggregate(
                total=Sum('pontos_ganhos'))['total'] or 0

            # 🔥 CORRIGIDO: Agora busca por 3 pontos, casando com a sua regra de placar cheio!
            total_cheios = Palpite.objects.filter(
                usuario=perfil.usuario, pontos_ganhos=3).count()

            perfil.pontos_totais = total_pontos
            perfil.placares_cheios = total_cheios
            perfis_para_salvar.append(perfil)

        if perfis_para_salvar:
            PerfilUsuario.objects.bulk_update(
                perfis_para_salvar, ['pontos_totais', 'placares_cheios'])
            print("🏆 [Motor] Ranking Geral atualizado com sucesso!")

    return f"Sucesso: {len(palpites_para_salvar)} palpites processados."
