from django.contrib.auth.forms import AuthenticationForm


class LoginFormPersonalizado(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adiciona a classe 'form-control' automaticamente aos campos
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
