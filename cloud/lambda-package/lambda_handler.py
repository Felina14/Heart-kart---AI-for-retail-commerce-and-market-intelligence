"""
AWS Lambda handler wrapper for HeartKart Flask backend (AgentCore edition).
Uses serverless-wsgi to translate API Gateway events ↔ Flask WSGI.
"""
import serverless_wsgi
from app_agentcore import app


def lambda_handler(event, context):
    """AWS Lambda entry point."""
    return serverless_wsgi.handle_request(app, event, context)
