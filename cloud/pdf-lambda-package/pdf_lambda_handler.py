#!/usr/bin/env python3
"""
Standalone AWS Lambda handler for generating HeartKart PO PDFs.

This Lambda is intentionally small and focused: it only depends on ReportLab
and the replenishment planner PDF generator, so it can be packaged separately
from the main backend lambda.

Event contract (invoked by other Lambdas or API Gateway):

    {
      "po": { ... full PO dict ... }
    }

The handler returns a small JSON object with a base64-encoded PDF:

    {
      "pdf_base64": "<base64 PDF bytes>",
      "po_number": "PO-2025...."
    }
"""

import base64
import json
from typing import Any, Dict

from agents.replenishment_planner.pdf_generator_v2 import create_po_pdf


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda entrypoint for PDF generation."""
    try:
        # Accept either a direct PO dict or a JSON string in "body"
        if "po" in event:
            po = event["po"]
        elif "body" in event:
            # API Gateway / Lambda proxy style
            body = event["body"]
            if isinstance(body, str):
                body = json.loads(body)
            po = body.get("po")
        else:
            return {
                "status": "error",
                "error": "Missing 'po' in event payload",
            }

        if not isinstance(po, dict):
            return {
                "status": "error",
                "error": "Invalid 'po' format – expected an object",
            }

        pdf_bytes = create_po_pdf(po)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return {
            "status": "success",
            "po_number": po.get("po_number"),
            "pdf_base64": pdf_b64,
        }

    except Exception as exc:
        # Include traceback for debugging
        import traceback
        error_msg = str(exc)
        tb = traceback.format_exc()
        # Log to CloudWatch
        print(f"PDF Lambda Error: {error_msg}")
        print(tb)
        # Keep response simple so the caller can surface errors
        return {
            "status": "error",
            "error": error_msg,
            "traceback": tb if len(tb) < 500 else tb[:500] + "..."
        }


