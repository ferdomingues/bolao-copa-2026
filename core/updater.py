from apscheduler.schedulers.background import BackgroundScheduler
# Importe sua lógica aqui
from .management.commands.seu_comando_de_atualizar import command


def start():
    scheduler = BackgroundScheduler()
    # Agenda para rodar a cada 1 hora
    scheduler.add_job(executar_sua_logica, 'interval', hours=1)
    scheduler.start()
