import requests
from django.core.management.base import BaseCommand
from bolao.models import Selecao, Jogo
from datetime import datetime


class Command(BaseCommand):
    help = 'Carga 100% real: Seleções e Jogos consumidos diretamente da API Zafronix'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            'Iniciando integração oficial com a API da Copa...'))

        headers = {"X-API-Key": "zwc_free_bed2100142b87a3f4e55d3c7"}

        # ==========================================
        # PASSO 1: CARREGAR AS SELEÇÕES
        # ==========================================
        url_selecoes = "https://api.zafronix.com/fifa/worldcup/v1/tournaments/2026"
        self.stdout.write('Buscando e atualizando seleções na API...')

        try:
            res_selecoes = requests.get(
                url_selecoes, headers=headers, timeout=10)
            res_selecoes.raise_for_status()
            dados_torneio = res_selecoes.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(
                f"Erro ao buscar seleções: {e}"))
            return

        for time_data in dados_torneio.get('teams', []):
            grupo_info = time_data.get('groupStage', {})
            letra_grupo = grupo_info.get('group', 'A')

            flag_info = time_data.get('flag', {})
            url_bandeira = flag_info.get('flagUrl', '')

            selecao, criada = Selecao.objects.update_or_create(
                nome=time_data['name'],
                defaults={
                    'sigla': time_data['code'],
                    'grupo': letra_grupo,
                    'bandeira_url': url_bandeira
                }
            )
            if criada:
                self.stdout.write(
                    f"  [+] Seleção cadastrada: {selecao.nome} ({selecao.sigla})")

        # ==========================================
        # PASSO 2: CARREGAR OS JOGOS (TRATANDO NULOS DO MATA-MATA)
        # ==========================================
        url_jogos = "https://api.zafronix.com/fifa/worldcup/v1/matches?year=2026"
        self.stdout.write('\nBuscando calendário oficial de partidas...')

        try:
            res_jogos = requests.get(url_jogos, headers=headers, timeout=10)
            res_jogos.raise_for_status()
            dados_jogos = res_jogos.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Erro ao buscar jogos: {e}"))
            return

        lista_partidas = dados_jogos.get('data', [])
        self.stdout.write(
            f"Processando {len(lista_partidas)} jogos encontrados...")

        MAPA_NOMES = {
            'USA': 'United States',
            'IR Iran': 'Iran',
            'Korea Republic': 'South Korea',
            'Türkiye': 'Turkey',
            'Côte d\'Ivoire': 'Ivory Coast',
            'Cabo Verde': 'Cape Verde',
            'Czechia': 'Czech Republic',
            'Congo DR': 'DR Congo',
            'Democratic Republic of the Congo': 'DR Congo'
        }

        for jogo_data in lista_partidas:
            nome_casa_raw = jogo_data.get('homeTeam')
            nome_fora_raw = jogo_data.get('awayTeam')

            # 🛠️ CORREÇÃO 1: Normalização robusta de todas as fases da Copa
            # 🌪️ SUPER CHECAGEM COMPLETA + LOG DE SEGURANÇA
            stage_raw = jogo_data.get('stage', '').upper()

            if 'GROUP' in stage_raw:
                fase_normalizada = 'GRUPOS'
            elif '32' in stage_raw or 'ROUND_32' in stage_raw or 'R32' in stage_raw:
                fase_normalizada = '16_AVOS'
            elif '16' in stage_raw or 'ROUND_16' in stage_raw or 'R16' in stage_raw or 'OITAVAS' in stage_raw:
                fase_normalizada = 'OITAVAS'
            # Adicionado 'QF' para capturar abreviações da API
            elif '8' in stage_raw or 'QUARTER' in stage_raw or 'QUARTAS' in stage_raw or 'QF' in stage_raw:
                fase_normalizada = 'QUARTAS'
            # Adicionado 'SF' para capturar abreviações da API
            elif '4' in stage_raw or 'SEMI' in stage_raw or 'SF' in stage_raw:
                fase_normalizada = 'SEMIFINAL'
            elif 'FINAL' in stage_raw:
                fase_normalizada = 'FINAL'
            else:
                fase_normalizada = 'GRUPOS'
                # 📢 Se a API mandar algo bizarro, você verá exatamente o texto no terminal:
                print(
                    f"⚠️ Alerta: Texto da fase não reconhecido pela checagem: '{stage_raw}'")

            # 🛠️ CORREÇÃO 2: Busca segura das seleções (permite salvar como None se não existirem)
            casa = None
            if nome_casa_raw:
                nome_casa = MAPA_NOMES.get(nome_casa_raw, nome_casa_raw)
                casa = Selecao.objects.filter(nome=nome_casa).first()

            fora = None
            if nome_fora_raw:
                nome_fora = MAPA_NOMES.get(nome_fora_raw, nome_fora_raw)
                fora = Selecao.objects.filter(nome=nome_fora).first()

            # Converte a data
            string_data = jogo_data['kickoffUtc'].replace('Z', '+00:00')
            data_partida = datetime.fromisoformat(string_data)

            # 🛠️ CORREÇÃO 3: Chave de busca inteligente (Evita duplicidade se os times mudarem)
            # Nota: Se o seu modelo Jogo tiver um campo de "id_externo" ou "numero_jogo", use-o aqui no lugar de data_hora e fase.
            jogo, criado = Jogo.objects.update_or_create(
                numero_jogo=jogo_data.get('matchNo'),
                defaults={
                    'data_hora': data_partida,
                    'fase': fase_normalizada,
                    'selecao_casa': casa,
                    'selecao_fora': fora,
                    'gols_casa': jogo_data.get('homeScore'),
                    'gols_fora': jogo_data.get('awayScore'),
                }
            )

            # Sincronização e logs de console amigáveis
            if criado:
                self.stdout.write(
                    f"  [+] Jogo criado: {casa or 'A definir'} x {fora or 'A definir'} ({fase_normalizada})")
            else:
                # Se o placar mudou, força o save para disparar recalculis de bolão se necessário
                novo_placar_casa = jogo_data.get('homeScore')
                novo_placar_fora = jogo_data.get('awayScore')
                if (jogo.gols_casa != novo_placar_casa) or (jogo.gols_fora != novo_placar_fora):
                    jogo.gols_casa = novo_placar_casa
                    jogo.gols_fora = novo_placar_fora
                    jogo.save()
                    self.stdout.write(self.style.SUCCESS(
                        f" [!] Placar atualizado: {jogo}"))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f"  [~] Jogo sincronizado: {jogo}"))

        self.stdout.write(self.style.SUCCESS(
            '\nSincronização com a API concluída com sucesso total!'))
