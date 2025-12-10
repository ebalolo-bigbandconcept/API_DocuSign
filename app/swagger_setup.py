from flasgger import Swagger
import os

def init_swagger(app):
    """
    Initialise Flasgger en chargeant le fichier YAML situé dans app/static/swagger.yaml.
    L'UI sera disponible par défaut sur /apidocs/.
    """
    swag_path = os.path.join(app.root_path, "static", "swagger.yaml")
    # Swagger accepte directement le chemin via template_file
    Swagger(app, template_file=swag_path, config={
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_1",
                "route": "/apispec_1.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs/"
    })