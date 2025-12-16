from flask import Blueprint, request, jsonify
from docusign_esign import ApiClient, ApiException, EnvelopesApi, EventNotification
from docusign_esign.models import Document, EnvelopeDefinition, Signer, SignHere, Tabs, Recipients, EnvelopeEvent
import base64, time, logging, os, json, requests
from datetime import datetime
from .models import db, EnvelopeTracking

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
  
  logging.info("Prepared sign here tab for DocuSign")
  return sign_here

# Prepare signers object
def get_signers(data, sign_here):
  signers_data = data.get("signers")
  if not signers_data:
    logging.error("Missing signers information")
    raise ValueError("Missing signers information")
  
  # Format signers into json
  try:
    if not signers_data.strip().startswith('['):
      signers_data = f'[{signers_data}]'
    signers_data = json.loads(signers_data)

  except json.JSONDecodeError:
    logging.error("Failed to decode signers JSON string: %s", signers_data)
    raise ValueError("Invalid signers format. Must be valid JSON string.")
  
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
def get_envelope_definition(document, recipients, webhook_url):
  # Add event notification for webhook
  event_notification = EventNotification(
    url=webhook_url,
    logging_enabled="true",
    require_acknowledgment="true",
    use_soap_interface="false",
    include_certificate_with_soap="false",
    sign_message_with_x509_cert="false",
    include_documents="true",
    include_envelope_void_reason="true",
    include_time_zone="true",
    include_sender_account_as_custom_field="true",
    include_document_fields="true",
    include_certificate_of_completion="true",
    envelope_events=[
      EnvelopeEvent(envelope_event_status_code="completed"),
      EnvelopeEvent(envelope_event_status_code="declined"),
      EnvelopeEvent(envelope_event_status_code="voided")
    ]
  )
  
  envelope_definition = EnvelopeDefinition(
    email_subject="Veuillez signer le document",
    documents=[document],
    recipients=recipients,
    status="sent",
    event_notification=event_notification
  )
  
  logging.info("Prepared envelope definition for DocuSign")
  return envelope_definition

@docusign_bp.route("/send-pdf", methods=["POST"])
def send_pdf():
  try:
    # Fetching data
    data = request.form
    logging.info("Received data")

    # Get callback URL from request
    callback_url = data.get("callback_url")
    if not callback_url:
      return jsonify({"error": "Missing callback_url"}), 400

    # Get requester host from request headers
    requester_host = request.headers.get('X-Forwarded-For', request.remote_addr)
    if 'Origin' in request.headers:
      requester_host = request.headers.get('Origin')
    elif 'Referer' in request.headers:
      requester_host = request.headers.get('Referer')

    document = get_document()
    sign_here = get_sign_here_tab()
    signers = get_signers(data, sign_here)
    recipients = Recipients(signers=signers)
    
    # Get the webhook URL for DocuSign to call our API
    internal_api_base_url = os.getenv("INTERNAL_API_BASE_URL", "http://localhost:5001")
    webhook_url = f"{internal_api_base_url}/api/webhook/docusign"
    
    envelope_definition = get_envelope_definition(document, recipients, webhook_url) 

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

    # Store envelope tracking information in database
    try:
      tracking = EnvelopeTracking(
        envelope_id=results.envelope_id,
        callback_url=callback_url,
        requester_host=requester_host,
        status='sent'
      )
      db.session.add(tracking)
      db.session.commit()
      logging.info(f"Stored tracking info for envelope {results.envelope_id}")
    except Exception as db_error:
      logging.error(f"Failed to store tracking info: {db_error}")
      db.session.rollback()

    return jsonify({
      "envelope_id": results.envelope_id,
      "webhook_url": webhook_url,
      "tracking_id": tracking.id if 'tracking' in locals() else None
    }), 200
    
  except ValueError as e:
    return jsonify({"error": str(e)}), 400

  except ApiException as e:
    logging.error("DocuSign error: %s", e)
    return jsonify({"error": str(e)}), 500


def notify_external_site(envelope_id, status, tracking):
  """Send notification to external site about envelope status"""
  try:
    payload = {
      "envelope_id": envelope_id,
      "status": status,
      "requester_host": tracking.requester_host,
      "signed_at": tracking.signed_at.isoformat() if tracking.signed_at else None,
      "created_at": tracking.created_at.isoformat() if tracking.created_at else None
    }
    
    logging.info(f"Notifying {tracking.callback_url} about envelope {envelope_id}")
    
    response = requests.post(
      tracking.callback_url,
      json=payload,
      timeout=10,
      headers={'Content-Type': 'application/json'}
    )
    
    tracking.notified_at = datetime.utcnow()
    tracking.notification_status = f"success_{response.status_code}"
    db.session.commit()
    
    logging.info(f"Successfully notified {tracking.callback_url} - Status: {response.status_code}")
    return True
    
  except requests.exceptions.RequestException as e:
    logging.error(f"Failed to notify {tracking.callback_url}: {e}")
    tracking.notification_status = f"failed_{str(e)[:100]}"
    db.session.commit()
    return False


@docusign_bp.route("/webhook/docusign", methods=["POST"])
def docusign_webhook():
  """Handle DocuSign webhook events"""
  try:
    # DocuSign sends XML, but we can also receive JSON
    content_type = request.headers.get('Content-Type', '')
    
    if 'json' in content_type:
      data = request.get_json()
    else:
      # DocuSign typically sends XML
      import xml.etree.ElementTree as ET
      xml_data = request.data.decode('utf-8')
      logging.info(f"Received webhook XML: {xml_data[:500]}")
      
      root = ET.fromstring(xml_data)
      
      # Parse envelope ID and status from XML
      envelope_id = None
      status = None
      
      # Find EnvelopeStatus node
      for envelope_status in root.findall('.//EnvelopeStatus'):
        envelope_id_elem = envelope_status.find('EnvelopeID')
        status_elem = envelope_status.find('Status')
        
        if envelope_id_elem is not None:
          envelope_id = envelope_id_elem.text
        if status_elem is not None:
          status = status_elem.text.lower()
      
      if not envelope_id:
        logging.warning("No envelope ID found in webhook")
        return jsonify({"status": "ignored", "reason": "no envelope ID"}), 200
      
      data = {
        "envelope_id": envelope_id,
        "status": status
      }
    
    envelope_id = data.get("envelope_id") or data.get("envelopeId")
    status = data.get("status", "").lower()
    
    logging.info(f"Webhook received for envelope {envelope_id} with status {status}")
    
    # Find the tracking record
    tracking = EnvelopeTracking.query.filter_by(envelope_id=envelope_id).first()
    
    if not tracking:
      logging.warning(f"No tracking record found for envelope {envelope_id}")
      return jsonify({"status": "ignored", "reason": "envelope not tracked"}), 200
    
    # Update tracking status
    tracking.status = status
    
    # If envelope is completed (signed), record the timestamp
    if status == 'completed':
      tracking.signed_at = datetime.utcnow()
      logging.info(f"Envelope {envelope_id} completed at {tracking.signed_at}")
    
    db.session.commit()
    
    # Notify the external site
    if status in ['completed', 'declined', 'voided']:
      notify_external_site(envelope_id, status, tracking)
    
    return jsonify({"status": "processed", "envelope_id": envelope_id}), 200
    
  except Exception as e:
    logging.error(f"Webhook processing error: {e}")
    return jsonify({"error": str(e)}), 500


@docusign_bp.route("/envelope/<envelope_id>/status", methods=["GET"])
def get_envelope_status(envelope_id):
  """Get the status of an envelope"""
  try:
    tracking = EnvelopeTracking.query.filter_by(envelope_id=envelope_id).first()
    
    if not tracking:
      return jsonify({"error": "Envelope not found"}), 404
    
    return jsonify(tracking.to_dict()), 200
    
  except Exception as e:
    logging.error(f"Error getting envelope status: {e}")
    return jsonify({"error": str(e)}), 500


@docusign_bp.route("/envelopes", methods=["GET"])
def list_envelopes():
  """List all tracked envelopes"""
  try:
    envelopes = EnvelopeTracking.query.order_by(EnvelopeTracking.created_at.desc()).all()
    return jsonify([env.to_dict() for env in envelopes]), 200
    
  except Exception as e:
    logging.error(f"Error listing envelopes: {e}")
    return jsonify({"error": str(e)}), 500
