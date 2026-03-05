"""
HeartKart Vendor Caller — Cloud Server
=======================================
Unified HTTP + WebSocket server for AWS App Runner deployment.
Replaces the local ngrok-based setup with a production cloud deployment.

Architecture:
  ┌────────────┐      ┌────────────────────────────────┐      ┌────────────┐
  │  Twilio    │◄────►│  This server (App Runner)      │◄────►│ Nova Sonic │
  │  PSTN      │ WSS  │  aiohttp HTTP + WebSocket      │ SDK  │ Bedrock    │
  │  (vendor)  │ mulaw│  /media-stream  (audio bridge)  │ PCM  │ (AI voice) │
  └────────────┘ 8kHz └────────────────────────────────┘16/24k└────────────┘
                                ▲
                                │  REST API
                                ▼
                       ┌────────────────┐
                       │  Lambda / FE   │
                       │  POST /api/... │
                       └────────────────┘

Endpoints:
  GET  /health                         — Health check (App Runner)
  GET  /api/info                       — Service info + WebSocket URL
  POST /api/initiate-call              — Start a Twilio call
  GET  /api/call-metadata/{call_sid}   — Get call metadata
  GET  /api/call-status/{order_id}     — Get order chain status
  POST /api/store-transcript           — Store transcript + trigger fallback
  GET  /api/calls                      — List all calls
  GET  /media-stream                   — Twilio WebSocket (bidirectional audio)
"""

import asyncio
import audioop
import base64
import json
import os
import traceback
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from aiohttp import web
import boto3

from nova_sonic_voice_agent import NovaSonicVendorAgent
from product_data_access import (
    get_all_products,
    get_product_by_sku,
    get_products_by_category,
)

# ======================================================================
# CONFIGURATION
# ======================================================================

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
USD_TO_INR_RATE = float(os.getenv("USD_TO_INR", "89.6"))
SERVICE_URL = os.getenv("SERVICE_URL", "")  # Set to App Runner URL after deploy
PORT = int(os.getenv("PORT", "8080"))


def usd_to_inr(amount_usd: float) -> float:
    try:
        return round(float(amount_usd) * USD_TO_INR_RATE, 2)
    except Exception:
        return 0.0


# ======================================================================
# IN-MEMORY STORES
# ======================================================================

call_metadata_store: Dict[str, Dict] = {}
call_transcripts_store: Dict[str, Dict] = {}
order_chains: Dict[str, Dict] = {}
active_calls: Dict[str, Dict] = {}


# ======================================================================
# PER-CALL AUDIO CONVERTER (thread-safe state per call)
# ======================================================================


class AudioConverter:
    """Stateful audio converter for a single call session."""

    def __init__(self):
        self._state_in = None
        self._state_out = None

    def mulaw_to_pcm(self, mulaw_data, rate_in=8000, rate_out=16000):
        try:
            if not mulaw_data:
                return b""
            pcm = audioop.ulaw2lin(mulaw_data, 2)
            if rate_in != rate_out:
                pcm, self._state_in = audioop.ratecv(
                    pcm, 2, 1, rate_in, rate_out, self._state_in
                )
            return pcm
        except Exception as e:
            print(f"⚠️  mulaw→pcm error: {e}")
            self._state_in = None
            return b""

    def pcm_to_mulaw(self, pcm_data, rate_in=24000, rate_out=8000):
        try:
            if not pcm_data:
                return b""
            if len(pcm_data) % 2 != 0:
                pcm_data = pcm_data[:-1]
            if rate_in != rate_out:
                pcm_data, self._state_out = audioop.ratecv(
                    pcm_data, 2, 1, rate_in, rate_out, self._state_out
                )
            return audioop.lin2ulaw(pcm_data, 2)
        except Exception as e:
            print(f"⚠️  pcm→mulaw error: {e}")
            self._state_out = None
            return b""


# ======================================================================
# VENDOR DECISION DETECTION
# ======================================================================


def detect_vendor_decision(conversation_history: list) -> str:
    """Analyse conversation to detect YES / NO / UNKNOWN."""
    if not conversation_history:
        return "UNKNOWN"

    def _text(msgs, role):
        return " ".join(
            (
                m.get("content", "")
                if isinstance(m.get("content"), str)
                else (
                    m["content"][0].get("text", "")
                    if isinstance(m.get("content"), list) and m["content"]
                    else ""
                )
            )
            for m in msgs
            if m.get("role") == role
        ).lower()

    vendor = _text(conversation_history, "user")
    ai = _text(conversation_history, "assistant")

    # AI reached closing step → confirmed
    if "purchase order document to your email" in ai or "wonderful" in ai:
        return "YES"
    if "thank you for letting me know" in ai and "we'll be in touch" in ai:
        return "NO"

    yes_kw = [
        "yes", "yeah", "sure", "okay", "ok", "absolutely", "definitely",
        "of course", "no problem", "we can do that", "confirmed", "confirm",
        "approved", "accepted", "can fulfil", "can fulfill", "we will",
        "we'll do it", "consider it done", "right away", "go ahead",
        "sounds good", "deal", "agreed", "we can", "will do",
    ]
    no_kw = [
        "no", "nope", "cannot", "can't", "unable", "unfortunately",
        "not possible", "out of stock", "unavailable", "don't have",
        "do not have", "sorry", "regret", "decline", "reject",
        "not available", "can not", "won't be able", "impossible",
        "not in stock", "backorder", "discontinued",
    ]

    y = sum(1 for k in yes_kw if k in vendor)
    n = sum(1 for k in no_kw if k in vendor)
    if y > n and y > 0:
        return "YES"
    if n > y and n > 0:
        return "NO"
    return "UNKNOWN"


# ======================================================================
# VENDOR LOOKUP / FALLBACK
# ======================================================================


def find_alternative_vendor(category: str, vendors_tried: list) -> Optional[Dict]:
    try:
        products = get_all_products(limit=1000)
        tried = {v.lower() for v in vendors_tried}

        # Same-category first
        for p in products:
            vn = p.get("vendor_name", "")
            cat = p.get("category", "")
            if not vn or vn.lower() in tried:
                continue
            if category and cat and category.lower() in cat.lower():
                return {
                    "vendor_name": vn,
                    "contact_person": p.get("vendor_contact", "Purchasing Manager"),
                    "phone_number": p.get("vendor_phone", ""),
                    "category": cat,
                }
        # Any vendor
        for p in products:
            vn = p.get("vendor_name", "")
            if vn and vn.lower() not in tried:
                return {
                    "vendor_name": vn,
                    "contact_person": p.get("vendor_contact", "Purchasing Manager"),
                    "phone_number": p.get("vendor_phone", ""),
                    "category": p.get("category", ""),
                }
        return None
    except Exception as e:
        print(f"Error finding alternative vendor: {e}")
        return None


# ======================================================================
# TWILIO CALL INITIATION
# ======================================================================


def initiate_twilio_call(
    vendor_name: str,
    contact_person: str,
    vendor_phone: str,
    items: list,
    total_amount: float,
    delivery_date: str,
    order_id: str = None,
    po_number: str = None,
) -> Dict:
    try:
        from twilio.rest import Client

        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
            return {"status": "error", "error": "Twilio credentials not configured"}
        if not SERVICE_URL:
            return {"status": "error", "error": "SERVICE_URL not set"}

        order_id = order_id or str(uuid.uuid4())
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        ws_url = SERVICE_URL.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/media-stream" />
    </Connect>
</Response>"""

        call = client.calls.create(
            twiml=twiml, to=vendor_phone, from_=TWILIO_PHONE_NUMBER
        )

        print(f"✅ Call initiated: {vendor_name} ({vendor_phone}) SID={call.sid}")

        call_metadata_store[call.sid] = {
            "vendor_name": vendor_name,
            "contact_person": contact_person,
            "product_name": ", ".join(i.get("name", "item") for i in items),
            "quantity": sum(i.get("quantity", 0) for i in items),
            "total_amount": total_amount,
            "total_amount_inr": total_amount,  # Frontend already sends INR
            "delivery_date": delivery_date,
            "po_number": po_number
            or f"PO-{datetime.now().strftime('%Y%m%d-%H%M')}",
            "order_id": order_id,
            "call_started_at": datetime.now().isoformat(),
        }

        if order_id not in order_chains:
            order_chains[order_id] = {
                "order_details": {
                    "items": items,
                    "total_amount": total_amount,
                    "delivery_date": delivery_date,
                    "category": items[0].get("category", "") if items else "",
                },
                "vendor_phone": vendor_phone,  # preserve for fallback calls
                "first_call_sid": call.sid,     # track original call for frontend polling
                "vendors_tried": [vendor_name],
                "attempt_number": 1,
                "max_attempts": 3,
                "status": "CALLING",
                "current_decision": "PENDING",
                "call_sids": [call.sid],
            }
        else:
            chain = order_chains[order_id]
            chain["vendors_tried"].append(vendor_name)
            chain["attempt_number"] = len(chain["vendors_tried"])
            chain["status"] = "CALLING"
            chain["current_decision"] = "PENDING"
            chain["call_sids"].append(call.sid)

        return {
            "status": "call_initiated",
            "call_sid": call.sid,
            "order_id": order_id,
            "vendor_name": vendor_name,
            "vendor_phone": vendor_phone,
            "websocket_url": f"{ws_url}/media-stream",
            "attempt_number": order_chains[order_id]["attempt_number"],
        }
    except Exception as e:
        print(f"❌ Twilio call error: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ======================================================================
# VENDOR DECISION + FALLBACK HANDLER
# ======================================================================


def handle_vendor_decision(call_sid: str, decision: str) -> Dict:
    meta = call_metadata_store.get(call_sid, {})
    order_id = meta.get("order_id", "")
    vendor_name = meta.get("vendor_name", "Unknown")

    if not order_id or order_id not in order_chains:
        return {"status": "no_order_chain", "decision": decision}

    chain = order_chains[order_id]
    chain["current_decision"] = decision

    if decision == "YES":
        chain["status"] = "FULFILLED"
        return {
            "status": "fulfilled",
            "order_id": order_id,
            "fulfilled_by": vendor_name,
            "attempts": chain["attempt_number"],
        }

    if decision == "NO":
        if chain["attempt_number"] >= chain["max_attempts"]:
            chain["status"] = "FAILED"
            return {
                "status": "failed",
                "order_id": order_id,
                "vendors_tried": chain["vendors_tried"],
                "message": f"All {chain['max_attempts']} attempts exhausted.",
            }
        category = chain["order_details"].get("category", "")
        alt = find_alternative_vendor(category, chain["vendors_tried"])
        if not alt:
            chain["status"] = "FAILED"
            return {
                "status": "failed",
                "order_id": order_id,
                "vendors_tried": chain["vendors_tried"],
                "message": "No alternative vendors found.",
            }
        chain["status"] = "FALLBACK_IN_PROGRESS"

        # Use the original verified phone number (DB numbers are placeholders)
        fallback_phone = chain.get("vendor_phone", alt.get("phone_number", ""))

        result = initiate_twilio_call(
            vendor_name=alt["vendor_name"],
            contact_person=alt.get("contact_person", "Purchasing Manager"),
            vendor_phone=fallback_phone,
            items=chain["order_details"]["items"],
            total_amount=chain["order_details"]["total_amount"],
            delivery_date=chain["order_details"]["delivery_date"],
            order_id=order_id,
        )
        return {
            "status": "fallback_initiated",
            "order_id": order_id,
            "previous_vendor": vendor_name,
            "new_vendor": alt["vendor_name"],
            "attempt": chain["attempt_number"],
            "call_result": result,
        }

    chain["status"] = "UNKNOWN"
    return {
        "status": "unknown",
        "order_id": order_id,
        "vendor_name": vendor_name,
        "message": "Vendor decision unclear — manual follow-up needed.",
    }


# ======================================================================
# HTTP HANDLERS
# ======================================================================


async def health_handler(request):
    return web.json_response(
        {
            "status": "healthy",
            "service": "heartkart-vendor-caller",
            "active_calls": len(active_calls),
            "total_calls": len(call_metadata_store),
            "timestamp": datetime.now().isoformat(),
        }
    )


async def info_handler(request):
    ws_url = (
        SERVICE_URL.replace("https://", "wss://") + "/media-stream"
        if SERVICE_URL
        else "Not configured — set SERVICE_URL"
    )
    return web.json_response(
        {
            "service": "heartkart-vendor-caller",
            "service_url": SERVICE_URL,
            "websocket_url": ws_url,
            "twilio_configured": bool(
                TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER
            ),
            "active_calls": len(active_calls),
            "total_calls": len(call_metadata_store),
        }
    )


async def initiate_call_api(request):
    try:
        data = await request.json()
        result = initiate_twilio_call(
            vendor_name=data.get("vendor_name", "Unknown Vendor"),
            contact_person=data.get("contact_person", "Purchasing Manager"),
            vendor_phone=data.get("vendor_phone", ""),
            items=data.get("items", []),
            total_amount=float(data.get("total_amount", 0)),
            delivery_date=data.get("delivery_date", "As soon as possible"),
            order_id=data.get("order_id"),
            po_number=data.get("po_number"),
        )
        return web.json_response(result)
    except Exception as e:
        traceback.print_exc()
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def call_metadata_api(request):
    call_sid = request.match_info["call_sid"]
    meta = call_metadata_store.get(call_sid)
    if meta:
        return web.json_response({"success": True, **meta})
    return web.json_response(
        {"success": False, "error": f"Call {call_sid} not found"}, status=404
    )


async def order_status_api(request):
    order_id = request.match_info["order_id"]
    if order_id in order_chains:
        return web.json_response(
            {"status": "success", "order_chain": order_chains[order_id]}
        )
    return web.json_response(
        {"status": "error", "error": f"Order {order_id} not found"}, status=404
    )


async def store_transcript_api(request):
    try:
        data = await request.json()
        call_sid = data.get("call_sid", "")
        transcript = data.get("transcript", "")
        history = data.get("conversation_history", [])
        decision = data.get("decision", "UNKNOWN")

        if not transcript and history:
            lines = []
            for m in history:
                role = "AI (Priya)" if m.get("role") == "assistant" else "Vendor"
                c = m.get("content", "")
                if isinstance(c, list) and c:
                    c = c[0].get("text", "")
                lines.append(f"{role}: {c}")
            transcript = "\n".join(lines)

        call_transcripts_store[call_sid] = {
            "transcript": transcript,
            "conversation_history": history,
            "decision": decision,
            "stored_at": datetime.now().isoformat(),
        }

        fallback = handle_vendor_decision(call_sid, decision)
        return web.json_response(
            {
                "success": True,
                "call_sid": call_sid,
                "transcript_length": len(transcript),
                "decision": decision,
                "fallback_result": fallback,
            }
        )
    except Exception as e:
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def list_calls_api(request):
    calls = [
        {
            "call_sid": sid,
            "vendor_name": m.get("vendor_name"),
            "status": "active" if sid in active_calls else "completed",
            "started_at": m.get("call_started_at"),
        }
        for sid, m in call_metadata_store.items()
    ]
    return web.json_response({"calls": calls, "total": len(calls)})


async def get_transcript_api(request):
    call_sid = request.match_info["call_sid"]
    t = call_transcripts_store.get(call_sid)
    if t:
        return web.json_response({"success": True, "call_sid": call_sid, **t})
    return web.json_response(
        {"success": False, "error": f"Transcript for {call_sid} not found"}, status=404
    )


# ======================================================================
# WEBSOCKET HANDLER  (Twilio ↔ Nova Sonic bidirectional bridge)
# ======================================================================


async def media_stream_handler(request):
    """Handle Twilio WebSocket media-stream connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("\n🔌 WebSocket connected")

    call_sid = None
    stream_sid = None
    agent = None
    forward_task = None
    converter = AudioConverter()

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                event = data.get("event")

                # ───── CALL STARTED ─────
                if event == "start":
                    call_sid = data["start"]["callSid"]
                    stream_sid = data["start"]["streamSid"]
                    print(f"\n📞 Call started: SID={call_sid}")

                    # Look up vendor context from metadata store
                    vendor_context = None
                    meta = call_metadata_store.get(call_sid)
                    if meta:
                        vn = meta.get("vendor_name", "the vendor")
                        cp = meta.get("contact_person", "there")
                        pn = meta.get("product_name", "products")
                        qty = meta.get("quantity", 0) or 0
                        inr = meta.get("total_amount_inr", 0) or 0
                        dd = meta.get("delivery_date", "as soon as possible")
                        vendor_context = {
                            "vendor_name": vn,
                            "contact_person": cp,
                            "purpose": "place a purchase order",
                            "order_details": {
                                "items": [{"name": pn, "quantity": qty}],
                                "total_amount": f"₹{inr:,.2f} (Indian Rupees)",
                                "delivery_date": dd,
                            },
                        }
                        print(f"   🧩 Context: {vn} / {cp}")

                    if not vendor_context:
                        print("   ⚠️  No metadata — using generic context")
                        vendor_context = {
                            "vendor_name": "the vendor",
                            "contact_person": "there",
                            "purpose": "place a purchase order",
                            "order_details": {
                                "items": [],
                                "total_amount": "to be confirmed",
                                "delivery_date": "as soon as possible",
                            },
                        }

                    # Create Nova Sonic agent, start bidirectional session
                    agent = NovaSonicVendorAgent(vendor_context)
                    await agent.start_session()
                    await agent.start_audio_input()
                    print("   ✅ Nova Sonic session active")

                    # Background: forward Nova Sonic audio → Twilio
                    # Buffer audio and send in consistent 20ms chunks for
                    # smooth playback (160 bytes µ-law at 8kHz = 20ms).
                    MULAW_CHUNK = 160  # 20ms at 8kHz µ-law

                    async def _forward_audio():
                        mulaw_buffer = bytearray()

                        async def _drain_buffer():
                            """Send all complete 20ms chunks from the buffer."""
                            nonlocal mulaw_buffer
                            while len(mulaw_buffer) >= MULAW_CHUNK:
                                chunk = bytes(mulaw_buffer[:MULAW_CHUNK])
                                del mulaw_buffer[:MULAW_CHUNK]
                                b64 = base64.b64encode(chunk).decode("utf-8")
                                await ws.send_str(
                                    json.dumps(
                                        {
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {"payload": b64},
                                        }
                                    )
                                )
                                # Pace output at ~20ms per chunk for smooth playback
                                await asyncio.sleep(0.018)

                        while agent.is_active:
                            try:
                                audio_bytes = await agent.audio_queue.get()
                                if audio_bytes is None:
                                    print("   Nova Sonic stream ended, stopping audio forward")
                                    # Flush remaining buffer
                                    if mulaw_buffer:
                                        b64 = base64.b64encode(bytes(mulaw_buffer)).decode("utf-8")
                                        await ws.send_str(
                                            json.dumps(
                                                {
                                                    "event": "media",
                                                    "streamSid": stream_sid,
                                                    "media": {"payload": b64},
                                                }
                                            )
                                        )
                                    break
                                if not audio_bytes:
                                    continue
                                if len(audio_bytes) % 2 != 0:
                                    audio_bytes += b"\x00"
                                mulaw = converter.pcm_to_mulaw(audio_bytes, 24000, 8000)
                                if mulaw:
                                    mulaw_buffer.extend(mulaw)
                                    await _drain_buffer()
                            except asyncio.CancelledError:
                                break
                            except Exception as e:
                                if "close" in str(e).lower():
                                    agent.is_active = False
                                    break
                                print(f"   ⚠️  forward error: {e}")

                    forward_task = asyncio.create_task(_forward_audio())
                    active_calls[call_sid] = {
                        "agent": agent,
                        "forward_task": forward_task,
                    }

                # ───── INCOMING AUDIO ─────
                elif event == "media":
                    if agent and agent.is_active:
                        try:
                            payload = data["media"]["payload"]
                            mulaw = base64.b64decode(payload)
                            if mulaw:
                                pcm = converter.mulaw_to_pcm(mulaw, 8000, 16000)
                                await agent.send_audio_chunk(pcm)
                        except Exception as e:
                            print(f"   ⚠️  audio-in error: {e}")

                # ───── CALL ENDED ─────
                elif event == "stop":
                    print(f"\n📞 Call ended: {call_sid}")
                    if call_sid and call_sid in active_calls:
                        cd = active_calls[call_sid]
                        agent = cd["agent"]
                        agent.is_active = False
                        cd["forward_task"].cancel()

                        try:
                            await agent.end_audio_input()
                        except Exception:
                            pass
                        try:
                            await agent.end_session()
                        except Exception:
                            pass

                        summary = agent.get_conversation_summary()
                        decision = detect_vendor_decision(
                            summary.get("conversation_history", [])
                        )
                        print(f"   🎯 Decision: {decision}")

                        # Build transcript
                        lines = []
                        for m in summary.get("conversation_history", []):
                            r = (
                                "AI (Priya)"
                                if m.get("role") == "assistant"
                                else "Vendor"
                            )
                            lines.append(f"{r}: {m.get('content', '')}")
                        transcript_text = "\n".join(lines)

                        call_transcripts_store[call_sid] = {
                            "transcript": transcript_text,
                            "conversation_history": summary.get(
                                "conversation_history", []
                            ),
                            "decision": decision,
                            "stored_at": datetime.now().isoformat(),
                        }

                        # Persist to DynamoDB
                        try:
                            ddb = boto3.resource("dynamodb", region_name="us-east-1")
                            ddb.Table("heartkart-call-logs").put_item(
                                Item={
                                    "call_sid": call_sid,
                                    "vendor_name": call_metadata_store.get(
                                        call_sid, {}
                                    ).get("vendor_name", ""),
                                    "transcript": transcript_text,
                                    "decision": decision,
                                    "call_date": datetime.now().isoformat(),
                                    "conversation_history": json.dumps(
                                        summary.get("conversation_history", [])
                                    ),
                                }
                            )
                            print("   ✅ Call log saved to DynamoDB")
                        except Exception as e:
                            print(f"   ⚠️  DynamoDB save failed: {e}")

                        # Trigger fallback logic
                        fb = handle_vendor_decision(call_sid, decision)
                        print(f"   📋 Fallback: {json.dumps(fb, default=str)}")

                        # If this is a fallback call (not the first call),
                        # store ONLY this call's transcript under the FIRST
                        # call_sid so the frontend (which polls the original
                        # call_sid) can see the latest result.  Each individual
                        # call keeps its own transcript on its own SID.
                        meta = call_metadata_store.get(call_sid, {})
                        oid = meta.get("order_id", "")
                        if oid and oid in order_chains:
                            first_sid = order_chains[oid].get("first_call_sid")
                            if first_sid and first_sid != call_sid:
                                call_transcripts_store[first_sid] = {
                                    "transcript": transcript_text,
                                    "conversation_history": summary.get(
                                        "conversation_history", []
                                    ),
                                    "decision": decision,
                                    "stored_at": datetime.now().isoformat(),
                                }
                                print(f"   ✅ Updated first call {first_sid} with fallback result (own transcript only)")

                        del active_calls[call_sid]
                    break

            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break

    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        traceback.print_exc()
    finally:
        if forward_task and not forward_task.done():
            forward_task.cancel()
        if agent and agent.is_active:
            # Unexpected disconnect — end_session wasn't called yet
            try:
                await agent.end_session()
            except Exception:
                pass
        print("🔌 WebSocket disconnected")

    return ws


# ======================================================================
# APPLICATION SETUP
# ======================================================================

app = web.Application()

# Health
app.router.add_get("/health", health_handler)
app.router.add_get("/", health_handler)

# Service info
app.router.add_get("/api/info", info_handler)

# Call management REST API
app.router.add_post("/api/initiate-call", initiate_call_api)
app.router.add_get("/api/call-metadata/{call_sid}", call_metadata_api)
app.router.add_get("/api/call-status/{order_id}", order_status_api)
app.router.add_post("/api/store-transcript", store_transcript_api)
app.router.add_get("/api/calls", list_calls_api)
app.router.add_get("/api/transcript/{call_sid}", get_transcript_api)

# Twilio WebSocket
app.router.add_get("/media-stream", media_stream_handler)

# ======================================================================
# ENTRYPOINT
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 HeartKart Vendor Caller — Cloud Server")
    print("=" * 60)
    print(f"   Port:      {PORT}")
    print(f"   Health:    http://0.0.0.0:{PORT}/health")
    print(f"   WebSocket: ws://0.0.0.0:{PORT}/media-stream")
    print(f"   REST API:  http://0.0.0.0:{PORT}/api/info")
    print(f"   Twilio:    {'✅ configured' if TWILIO_ACCOUNT_SID else '❌ not set'}")
    print(f"   URL:       {SERVICE_URL or '(will be set after deployment)'}")
    print("=" * 60)
    web.run_app(app, host="0.0.0.0", port=PORT)
