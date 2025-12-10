from flask import Flask
from flask_swagger_ui import get_swaggerui_blueprint
from .docusign_api import docusign_bp
import os

def create_app():
  app = Flask(__name__)
  
  SWAGGER_URL = '/docs'
  API_URL = '/static/swagger.yaml'
  
  swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "DocuSign API Service"}
  )
  
  app.config["INTERNAL_API_BASE_URL"] = os.environ.get("INTERNAL_API_BASE_URL", "http://localhost:5001")
  app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB
  
  app.register_blueprint(docusign_bp, url_prefix="/api")
  app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
  
  @app.route('/')
  def helloWord():
    return "Hello World!\n", 200

  return app