from flask import Flask
from .routes import api_bp
from .docusign_api import docusign_bp
import os

def create_app():
  app = Flask(__name__)

  app.config["INTERNAL_API_BASE_URL"] = os.environ.get("INTERNAL_API_BASE_URL", "http://localhost:5001")

  app.register_blueprint(api_bp, url_prefix="/api")
  app.register_blueprint(docusign_bp)
  
  @app.route('/')
  def helloWord():
    return "Hello World!\n", 200

  return app