from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    # Retorna o valor da chave, ou None se não existir
    return dictionary.get(key) if dictionary else None
