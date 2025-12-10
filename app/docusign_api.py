from flask import Blueprint, request, jsonify
from docusign_esign import ApiClient, ApiException, EnvelopesApi
from docusign_esign.models import Document, EnvelopeDefinition, Signer, SignHere, Tabs, Recipients
import base64, time, logging, os, json

docusign_bp = Blueprint("docusign", __name__)

_CACHED_PRIVATE_KEY = None

logging.basicConfig(level=logging.INFO)
logging.info("DocuSign API initialized")

def load_private_key():
  global _CACHED_PRIVATE_KEY
  if _CACHED_PRIVATE_KEY:
    return _CACHED_PRIVATE_KEY

  private_key_path = os.getenv("DOCUSIGN_PRIVATE_KEY_PATH")
  if not private_key_path:
    raise ValueError("DOCUSIGN_PRIVATE_KEY_PATH environment variable is not set")

  if not os.path.isfile(private_key_path):
    raise FileNotFoundError(f"Private key file not found at path: {private_key_path}")

  # Read as bytes and decode to text (PEM keys are textual). Cache as string.
  with open(private_key_path, "rb") as f:
    _CACHED_PRIVATE_KEY = f.read().decode("utf-8")
  return _CACHED_PRIVATE_KEY

DOCUSIGN_TOKEN_CACHE = {
  "access_token": None,
  "expires_at": 0
}

def get_docusign_token(data):
  # If cached token is still valid then reuse it
  if DOCUSIGN_TOKEN_CACHE["access_token"] and DOCUSIGN_TOKEN_CACHE["expires_at"] > time.time():
    return DOCUSIGN_TOKEN_CACHE["access_token"]

  private_key = load_private_key()
  integrator_key = data.get("integrator_key")
  user_id = data.get("user_id")
  auth_server = "account-d.docusign.com" if os.getenv("DOCUSIGN_ENV")=="demo" else "account.docusign.com"

  logging.info("Requesting DocuSign JWT token")

  api_client = ApiClient()
  api_client.set_oauth_host_name(auth_server)

  try:
    token_response = api_client.request_jwt_user_token(
      client_id=integrator_key,
      user_id=user_id,
      oauth_host_name=auth_server,
      private_key_bytes=private_key.encode("utf-8"),
      expires_in=3600,
      scopes=["signature", "impersonation"]
    )

    access_token = token_response.access_token

    # Store token in cache
    DOCUSIGN_TOKEN_CACHE["access_token"] = access_token
    DOCUSIGN_TOKEN_CACHE["expires_at"] = time.time() + 3500

    logging.info("New DocuSign JWT token created")

    return access_token
  except ApiException as e:
    logging.error("DocuSign JWT error: %s", e)
    raise e

# Prepare document object
def get_document():
  # Fetch PDF file
  file = request.files.get("file")
  if not file:
    return jsonify({"error": "Missing PDF file"}), 400
  logging.info("Received file")

  # Convert PDF to Base64
  pdf_base64 = base64.b64encode(file.read()).decode("utf-8")

  document = Document(
    document_base64=pdf_base64,
    name="Document à signer",
    file_extension="pdf",
    document_id="1"
  )

  logging.info("Prepared document for DocuSign")
  return document

# Prepare SignHere tab
def get_sign_here_tab():
  sign_here = SignHere(
    anchor_string="SIGN_HERE",
    anchor_units="pixels",
    anchor_x_offset="100",
    anchor_y_offset="100"
  )
  return sign_here

# Prepare signers object
def get_signers(data, sign_here):
  signers_data = data.get("signers")
  if not signers_data:
    return jsonify({"error": "Missing signers information"}), 400
  
  # Format signers into json
  try:
    if not signers_data.strip().startswith('['):
      signers_data = f'[{signers_data}]'
    signers_data = json.loads(signers_data)

  except json.JSONDecodeError:
    logging.error("Failed to decode signers JSON string: %s", signers_data)
    return jsonify({"error": "Invalid signers format. Must be a valid JSON string."}), 400
  
  # Create every signers
  signers = []
  for i, signer_info in enumerate(signers_data):
    recipient_id = str(i + 1)

    email = signer_info.get("email")
    name = signer_info.get("name")

    signer = Signer(
      email=email,
      name=name,
      recipient_id=recipient_id,
      routing_order=1,
    )
    signers.append(signer)

    signer.tabs = Tabs(
      sign_here_tabs=[sign_here]
    )
    logging.info(f"Added signer {i}: {name} <{email}>")
  
  logging.info(f"Total signers added: {len(signers)}")
  return signers

# Prepare envelope definition
def get_envelope_definition(document, recipients):
  envelope_definition = EnvelopeDefinition(
    email_subject="Veuillez signer le document",
    documents=[document],
    recipients=recipients,
    status="sent"
  )
  return envelope_definition

@docusign_bp.route("/send-pdf", methods=["POST"])
def send_pdf():
  try:
    # Fetching data
    data = request.form
    if not data:
      return jsonify({"error": "Missing data"}), 400
    logging.info("Received data")

    document = get_document()
    sign_here = get_sign_here_tab()
    signers = get_signers(data, sign_here)
    recipients = Recipients(signers=signers)
    envelope_definition = get_envelope_definition(document, recipients) 

    # Get DocuSign token
    access_token = get_docusign_token(data)

    account_id = data.get("account_id")
    base_path = "https://demo.docusign.net/restapi" if os.getenv("DOCUSIGN_ENV")=="demo" else "https://www.docusign.net/restapi"

    logging.info("Sending envelope...")

    api_client = ApiClient()
    api_client.host = base_path
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    envelope_api = EnvelopesApi(api_client)
    results = envelope_api.create_envelope(account_id, envelope_definition=envelope_definition)

    logging.info(f"Envelope sent with ID: {results.envelope_id}")

    return jsonify({"envelope_id": results.envelope_id}), 200

  except ApiException as e:
    logging.error("DocuSign error: %s", e)
    return jsonify({"error": str(e)}), 500
