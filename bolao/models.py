from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class Selecao(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    sigla = models.CharField(max_length=3, unique=True)
    grupo = models.CharField(max_length=1)
    bandeira_url = models.URLField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.nome


FASE_CHOICES = (
    ('GRUPOS', 'Fase de Grupos'),
    ('16 Avos', '16 Avos de Final'),
    ('OITAVAS', 'Oitavas de Final'),
    ('QUARTAS', 'Quartas de Final'),
    ('SEMIFINAL', 'Semifinal'),
    ('TERCEIRO', 'Disputa de 3º Lugar'),
    ('FINAL', 'Final'),
)


class Jogo(models.Model):
    numero_jogo = models.IntegerField(unique=True, null=True, blank=True)
    selecao_casa = models.ForeignKey(
        Selecao, on_delete=models.SET_NULL, related_name='jogos_como_casa', null=True, blank=True
    )
    selecao_fora = models.ForeignKey(
        Selecao, on_delete=models.SET_NULL, related_name='jogos_como_fora', null=True, blank=True
    )
    data_hora = models.DateTimeField()
    gols_casa = models.IntegerField(blank=True, null=True)
    gols_fora = models.IntegerField(blank=True, null=True)
    fase = models.CharField(
        max_length=20, choices=FASE_CHOICES, default='GRUPOS')

    def __str__(self):
        casa = self.selecao_casa.nome if self.selecao_casa else "A definir"
        fora = self.selecao_fora.nome if self.selecao_fora else "A definir"
        return f"{casa} x {fora} ({self.get_fase_display()})"

    def save(self, *args, **kwargs):
        # Lógica de cálculo movida para o services.py para evitar conflitos
        super().save(*args, **kwargs)

    @property
    def ja_comecou(self):
        return timezone.now() >= self.data_hora

    @property
    def data_fechamento(self):
        return self.data_hora - timedelta(hours=1)

    @property
    def bloqueado(self):
        return timezone.now() >= self.data_fechamento


class Palpite(models.Model):
    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='palpites', verbose_name="Palpiteiro")
    jogo = models.ForeignKey(
        Jogo, on_delete=models.CASCADE, related_name='palpites_do_jogo', verbose_name="Jogo")

    gols_casa = models.PositiveIntegerField(verbose_name="Gols Casa (Palpite)")
    gols_fora = models.PositiveIntegerField(verbose_name="Gols Fora (Palpite)")
    data_atualizacao = models.DateTimeField(
        auto_now=True, verbose_name="Última alteração")
    pontos_ganhos = models.IntegerField(
        default=0, verbose_name="Pontos Ganhos")

    class Meta:
        verbose_name = "Palpite"
        verbose_name_plural = "Palpites"
        unique_together = ('usuario', 'jogo')

    def __str__(self):
        casa = self.jogo.selecao_casa.sigla if self.jogo.selecao_casa else "???"
        fora = self.jogo.selecao_fora.sigla if self.jogo.selecao_fora else "???"
        return f"{self.usuario.username} - {casa} {self.gols_casa} x {self.gols_fora} {fora}"


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='perfil')
    pontos_totais = models.IntegerField(
        default=0, verbose_name="Pontos Totais")
    placares_cheios = models.IntegerField(
        default=0, verbose_name="Placares Cheios (Exatos)")

    def __str__(self):
        return f"Perfil de {self.usuario.username} - {self.pontos_totais} pts"


@receiver(post_save, sender=User)
def gerenciar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(usuario=instance)
    else:
        if hasattr(instance, 'perfil'):
            instance.perfil.save()
