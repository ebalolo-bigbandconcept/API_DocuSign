from flask import Blueprint, request, jsonify
from docusign_esign import ApiClient, ApiException, EnvelopesApi
from docusign_esign.models import Document, EnvelopeDefinition, Signer, SignHere, Tabs, Recipients
import base64, time, logging, os

docusign_bp = Blueprint("docusign", __name__)

# Cache token so we don't request a new one every time
DOCUSIGN_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0
}

def get_docusign_token(data):
    """Generate JWT token based on external request data"""

    # If cached token is still valid → reuse it
    if DOCUSIGN_TOKEN_CACHE["access_token"] and DOCUSIGN_TOKEN_CACHE["expires_at"] > time.time():
        return DOCUSIGN_TOKEN_CACHE["access_token"]

    private_key = base64.b64decode(data.get("private_key_b64")).decode('utf-8')
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


@docusign_bp.route("/send-pdf", methods=["POST"])
def send_pdf():
    try:
        data = request.form  # text fields
        logging.info("Received data")
        file = request.files.get("file")  # PDF file
        logging.info("Received file")

        if not data:
            return jsonify({"error": "Missing data"}), 400

        if not file:
            return jsonify({"error": "Missing PDF file"}), 400

        # Extract signer info
        email = data.get("email")
        name = data.get("name")

        # Convert PDF → Base64
        pdf_base64 = base64.b64encode(file.read()).decode("utf-8")

        document = Document(
            document_base64=pdf_base64,
            name="Document à signer",
            file_extension="pdf",
            document_id="1"
        )

        # Place signature using anchor
        sign_here = SignHere(
            anchor_string="SIGN_HERE",
            anchor_units="pixels",
            anchor_x_offset="100",
            anchor_y_offset="100"
        )

        signer = Signer(
            email=email,
            name=name,
            recipient_id="1",
            routing_order="1",
            tabs=Tabs(sign_here_tabs=[sign_here])
        )

        recipients = Recipients(signers=[signer])

        envelope_definition = EnvelopeDefinition(
            email_subject="Veuillez signer le document",
            documents=[document],
            recipients=recipients,
            status="sent"
        )

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
