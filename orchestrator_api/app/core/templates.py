"""Gabarits texte du projet (app/templates) : Jenkinsfile et manifeste de départ."""
from jinja2 import Environment, PackageLoader, StrictUndefined

# Pas de HTML ici : l'échappement automatique serait faux (Groovy, YAML).
# StrictUndefined : une variable oubliée est une erreur, jamais une chaîne vide.
_env = Environment(  # noqa: S701
    loader=PackageLoader("app", "templates"),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render(template_name: str, **context) -> str:
    return _env.get_template(template_name).render(**context)
