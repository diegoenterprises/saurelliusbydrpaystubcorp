import json
import base64
import tempfile
from saurellius_application import create_app  # or from application import create_app
from utils.saurellius_multicolor import SaurrelliusMultiThemeGenerator, create_sample_paystub_data

# NOTE: This is a simple example. In production you would likely use
# AWS Lambda with a container image and API Gateway in front.

generator = SaurrelliusMultiThemeGenerator()

def lambda_handler(event, context):
    # Expecting event with optional JSON body, similar to Flask route
    try:
        body = event.get("body")
        if body and isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = {}
        theme = body.get("theme", "anxiety")

        paystub_data = create_sample_paystub_data()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
            result = generator.generate_paystub_pdf(
                paystub_data=paystub_data,
                output_path=pdf_path,
                theme=theme,
            )
        if not result.get("success", False):
            raise Exception(f"Generation failed: {result.get('error', 'unknown')}")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/pdf",
                "Content-Disposition": f"attachment; filename=saurellius-paystub-{theme}.pdf",
            },
            "isBase64Encoded": True,
            "body": base64.b64encode(pdf_bytes).decode("ascii"),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
