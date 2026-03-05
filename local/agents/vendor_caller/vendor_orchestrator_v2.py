"""
Vendor Orchestrator V2 - Automatic fallback with YES/NO detection
Tries vendors in sequence until one accepts the order
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List
import sys
import os

from currency_utils import usd_to_inr

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import from same directory - try relative first, then absolute
try:
    from .vendor_database import VendorDatabase
    from .transcript_analyzer import TranscriptAnalyzer
    from .po_generator import generate_purchase_order
    from .notification_creator import create_notification, create_failure_notification, create_rejection_notification
except ImportError:
    # Fall back to absolute imports if relative doesn't work
    from vendor_database import VendorDatabase
    from transcript_analyzer import TranscriptAnalyzer
    from po_generator import generate_purchase_order
    from notification_creator import create_notification, create_failure_notification, create_rejection_notification


class VendorOrchestratorV2:
    """
    Orchestrates vendor calling with automatic fallback
    
    Flow:
    1. Get list of vendors for product category
    2. Call vendor 1
    3. Analyze response (YES/NO)
    4. If YES: Generate PO, draft email, create notification
    5. If NO: Call vendor 2
    6. Repeat until success or out of vendors
    """
    
    def __init__(self):
        self.vendor_db = VendorDatabase()
        self.transcript_analyzer = TranscriptAnalyzer()
        # Hard cap: never make more than 2 calls per order
        # This is intended to enforce "1 UI vendor + 1 fallback" behaviour.
        self.max_attempts = 2
    
    async def place_order_with_fallback(self, product_info: Dict[str, Any], 
                                       order_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main orchestration method - tries vendors until one accepts
        
        Args:
            product_info: {
                'name': 'Valentine Ornaments',
                'category': 'Ornaments',
                'sku': 'ORN-001'
            }
            order_details: {
                'items': [...],
                'quantity': 500,
                'delivery_date': '2025-12-15',
                'total_amount': 2500.00
            }
            
        Returns:
            {
                'final_status': 'success' | 'failed',
                'successful_vendor': 'Vendor Name' or None,
                'po_number': 'PO-XXX' or None,
                'email_draft': {...} or None,
                'notification': {...} or None,
                'attempts': [list of all attempts],
                'call_sid': 'CAXXXX' or None
            }
        """
        print("=" * 70)
        print("🤖 VENDOR ORCHESTRATOR V2 - Starting Order Placement")
        print("=" * 70)
        print(f"Product: {product_info.get('name')}")
        print(f"Category: {product_info.get('category')}")
        print(f"Quantity: {order_details.get('quantity')}")
        print()
        
        # Step 1: Get vendors for this product/category
        try:
            vendors = self._get_vendors_for_order(product_info)
            
            # Deduplicate vendors by name to ensure we don't call the same vendor twice
            unique_vendors = []
            seen_names = set()
            for v in vendors:
                name = v['name'].strip()
                if name not in seen_names:
                    seen_names.add(name)
                    unique_vendors.append(v)
            # Keep at most the first 2 unique vendors:
            # - UI‑selected vendor (if any) will already be first
            # - Followed by at most one real fallback vendor.
            vendors = unique_vendors[: self.max_attempts]
            
        except Exception as e:
            print(f"❌ Error getting vendors: {e}")
            import traceback
            traceback.print_exc()
            return {
                'final_status': 'failed',
                'error': f'Error querying vendors: {str(e)}',
                'attempts': []
            }
        
        if not vendors:
            print("❌ No vendors found for this product/category")
            return {
                'final_status': 'failed',
                'error': 'No vendors available',
                'attempts': []
            }
        
        print(f"📋 Found {len(vendors)} potential vendors:")
        for i, v in enumerate(vendors, 1):
            print(f"   {i}. {v['name']} (priority: {v['priority']})")
        print()
        
        # Override all vendor phone numbers to use the same verified Twilio number
        verified_phone = os.getenv('VERIFIED_PHONE_NUMBER', '')
        print(f"📞 Using verified Twilio number for all vendors: {verified_phone}")
        for vendor in vendors:
            original_phone = vendor.get('phone', 'N/A')
            vendor['phone'] = verified_phone
            print(f"   {vendor['name']}: {original_phone} → {verified_phone}")
        print()
        
        # Step 2: Try vendors in sequence with automatic fallback
        attempts = []
        rejection_notifications = []  # One per vendor that says NO
        incomplete_call = False  # Track if we bailed out due to an incomplete call
        max_vendors_to_try = min(self.max_attempts, len(vendors))
        
        for attempt_num in range(1, max_vendors_to_try + 1):
            vendor = vendors[attempt_num - 1]
            
            print("=" * 70)
            print(f"📞 Attempt {attempt_num}/{max_vendors_to_try}: Calling {vendor['name']}")
            print(f"   Phone: {vendor['phone']}")
            print(f"   Vendor Details: {json.dumps(vendor, default=str)}")
            print(f"   Total vendors available: {len(vendors)}")
            print()
            
            # Make the call
            print(f"   🚀 Initiating call attempt {attempt_num}...")
            call_result = await self._make_vendor_call(
                vendor=vendor,
                product_info=product_info,
                order_details=order_details,
                attempt_number=attempt_num
            )
            
            attempts.append(call_result)
            print(f"   📝 Call result added to attempts list. Current attempts count: {len(attempts)}")
            
            # Check if call was initiated successfully
            if not call_result.get('call_sid'):
                print(f"   ❌ Call failed to initiate - trying next vendor")
                if attempt_num < max_vendors_to_try:
                    print(f"   🔄 Automatically trying next vendor...")
                    print()
                    continue
                else:
                    print(f"   ⏹️  No more vendors to try")
                    print()
                    break
            
            # Wait for call to complete and check status first
            call_status = None
            if call_result.get('call_sid'):
                print(f"   ⏳ Waiting for call to complete...")
                print(f"   📞 Call SID: {call_result['call_sid']}")
                
                # First, check call status and wait until call has fully ended
                call_status = await self._check_call_status(call_result['call_sid'])
                call_result['status'] = call_status
                print(f"   📊 Final call status: {call_status}")
                
                if call_status in ['no-answer', 'busy', 'failed', 'canceled']:
                    # Call never actually connected (no-answer/busy/failed/etc.)
                    # Per requirement: DO NOT trigger second vendor unless first call fully completed.
                    print(f"   ❌ Call status: {call_status} - call did not complete, will NOT try next vendor")
                    call_result['decision'] = 'NO'
                    call_result['confidence'] = 1.0
                    call_result['reasoning'] = f'Call failed with status: {call_status}'
                    call_result['transcript'] = f"[System: Call did not connect. Status: {call_status}. No transcript generated.]"
                    incomplete_call = True
                    
                    # Stop trying further vendors; break out of the attempts loop
                    print(f"   🛑 Breaking out of vendor loop due to incomplete call")
                    break
                
                # Call completed - wait for transcript
                if call_status == 'completed':
                    print(f"   ✅ Call completed - waiting for transcript...")
                    # Wait longer for transcript to ensure we capture it even for short calls
                    transcript = await self._wait_for_transcript(call_result['call_sid'], max_wait=120)
                    
                    if transcript:
                        call_result['transcript'] = transcript
                        print(f"   ✅ Transcript received ({len(transcript)} chars)")
                    else:
                        print(f"   ⚠️  No transcript available after waiting")
                        call_result['transcript'] = ''
                        
                        # Try to force a fetch one last time
                        try:
                            import requests
                            api_url = os.getenv('API_URL', 'http://localhost:5000')
                            resp = requests.get(f'{api_url}/api/get-transcript/{call_result["call_sid"]}', timeout=5)
                            if resp.status_code == 200 and resp.json().get('transcript'):
                                call_result['transcript'] = resp.json().get('transcript')
                                print(f"   ✅ Transcript recovered via final fetch ({len(call_result['transcript'])} chars)")
                        except:
                            pass
                else:
                    # Call still in progress or unknown status
                    print(f"   ⏳ Call status: {call_status} - waiting for completion...")
                    transcript = await self._wait_for_transcript(call_result['call_sid'])
                    call_result['transcript'] = transcript if transcript else ''
            
            # Analyze transcript to determine YES/NO (prefer backend Nova decision)
            decision_result = None
            decision = 'UNKNOWN'
            
            # Prefer decision computed at /api/store-transcript (Nova TranscriptAnalyzer)
            backend_decision = None
            try:
                if call_result.get('call_sid'):
                    import requests
                    api_url = os.getenv('API_URL', 'http://localhost:5000')
                    resp = requests.get(
                        f'{api_url}/api/get-transcript/{call_result["call_sid"]}',
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        backend_decision = data.get('decision')
                        backend_analysis = data.get('analysis')
                        if backend_decision:
                            decision = backend_decision
                            decision_result = backend_analysis or {'decision': backend_decision, 'method': 'backend'}
                            print(f"   📊 Decision from backend: {decision} (method: {decision_result.get('method', 'unknown')})")
            except Exception as e:
                print(f"   ⚠️  Error fetching decision from backend: {e}")
            
            # If backend didn't give us a clear YES/NO, fall back to local analysis
            if decision not in ['YES', 'NO'] and call_result.get('transcript'):
                print(f"   🔍 Analyzing transcript locally (fallback)...")
                print(f"   📄 Transcript preview: {call_result['transcript'][:200]}...")
                
                try:
                    decision_result = self.transcript_analyzer.analyze_transcript(call_result['transcript'])
                    decision = decision_result.get('decision', 'UNKNOWN')
                    confidence = decision_result.get('confidence', 0.0)
                    reasoning = decision_result.get('reasoning', '')
                    
                    print(f"   📊 Decision: {decision} (confidence: {confidence:.2f})")
                    if reasoning:
                        print(f"   💭 Reasoning: {reasoning}")
                    if decision_result.get('key_quote'):
                        print(f"   💬 Key quote: {decision_result.get('key_quote')}")
                    
                    # Update call_result with analysis
                    call_result['decision'] = decision
                    call_result['confidence'] = confidence
                    call_result['reasoning'] = reasoning
                    call_result['key_quote'] = decision_result.get('key_quote', '')
                except Exception as e:
                    print(f"   ⚠️  Error analyzing transcript: {e}")
                    # Fallback: try keyword detection
                    from agent_prompts import detect_decision_from_text
                    decision = detect_decision_from_text(call_result['transcript'])
                    print(f"   📊 Decision (fallback keywords): {decision}")
                    call_result['decision'] = decision
                    call_result['confidence'] = 0.5
                    call_result['reasoning'] = f'Fallback keyword detection due to analysis error: {str(e)}'
            else:
                # No transcript available and no backend decision - assume NO to be safe
                if decision not in ['YES', 'NO']:
                    print(f"   ⚠️  No transcript or backend decision available - assuming NO")
                    decision = 'NO'
                    call_result['decision'] = 'NO'
                    call_result['confidence'] = 0.0
                    call_result['reasoning'] = 'No transcript/decision available'
            
            print()
            
            # If vendor says YES, we're done!
            if decision == 'YES':
                print("=" * 70)
                print("✅ ORDER ACCEPTED!")
                print(f"   Vendor: {vendor['name']}")
                print("=" * 70)
                print()
                
                success_result = await self._handle_success(
                    vendor=vendor,
                    product_info=product_info,
                    order_details=order_details,
                    call_result=call_result,
                    attempts=attempts
                )
                success_result['rejection_notifications'] = rejection_notifications

                return success_result
            
            # Vendor said NO or UNKNOWN - create rejection notification, then try next vendor
            if decision in ['NO', 'UNKNOWN']:
                print(f"   ❌ {vendor['name']} {'declined' if decision == 'NO' else 'gave unclear response'}")
                print(f"   📊 Decision details: {decision} (confidence: {call_result.get('confidence', 0):.2f})")

                # Create rejection notification for this vendor
                rejection_reason = call_result.get('reasoning', '') or call_result.get('key_quote', '') or 'Vendor declined the order'
                print(f"   🔔 Creating rejection notification for {vendor['name']}: {rejection_reason}")
                rejection_notif = create_rejection_notification(
                    vendor=vendor,
                    product_info=product_info,
                    order_details=order_details,
                    call_result=call_result,
                    rejection_reason=rejection_reason
                )
                rejection_notifications.append(rejection_notif)

                if attempt_num < max_vendors_to_try:
                    next_vendor = vendors[attempt_num] if attempt_num < len(vendors) else None
                    if next_vendor:
                        # Small delay to ensure previous call + Nova Sonic stream are fully torn down
                        try:
                            delay_seconds = int(os.getenv('NEXT_VENDOR_DELAY_SECONDS', '5'))
                        except ValueError:
                            delay_seconds = 5
                        if delay_seconds > 0:
                            print(f"   ⏳ Waiting {delay_seconds}s before calling next vendor to avoid Twilio/Nova overlap...")
                            await asyncio.sleep(delay_seconds)
                        print(f"   🔄 Automatically trying next vendor: {next_vendor['name']}...")
                        print()
                        # Continue to next iteration
                        continue
                    else:
                        print(f"   ⚠️  No next vendor available")
                        print()
                else:
                    print(f"   ⏹️  No more vendors to try (reached max attempts: {max_vendors_to_try})")
                    print()
            else:
                # Unexpected decision - log and continue
                print(f"   ⚠️  Unexpected decision: {decision} - trying next vendor")
                if attempt_num < max_vendors_to_try:
                    next_vendor = vendors[attempt_num] if attempt_num < len(vendors) else None
                    if next_vendor:
                        print(f"   🔄 Trying next vendor: {next_vendor['name']}...")
                        print()
                        continue
                    else:
                        print(f"   ⚠️  No next vendor available")
                        print()
        # If we broke out because the call never properly connected, do NOT
        # create an "all vendors declined" failure notification yet. That
        # would be misleading while the call may still be wrapping up /
        # transcripts may arrive slightly later.
        if incomplete_call and attempts:
            print("=" * 70)
            print("⏹️ CALL DID NOT COMPLETE - NOT CREATING FAILURE NOTIFICATION")
            print("=" * 70)
            print(f"Tried {len(attempts)} vendor(s) before call failed:")
            for attempt in attempts:
                print(f"   - {attempt.get('vendor_name')}: status={attempt.get('status')}, decision={attempt.get('decision', 'UNKNOWN')}")
            print()
        
            return {
                'final_status': 'failed',
                'error': f"Call did not complete (status: {attempts[-1].get('status')})",
                'attempts': attempts,
                'successful_vendor': None,
                'po_number': None,
                'email_draft': None,
                'notification': None,  # important: no 'order not placed' card yet
                'rejection_notifications': rejection_notifications,
                'call_sid': attempts[-1].get('call_sid'),
            }

        # If we get here, all vendors declined with a proper NO/UNKNOWN
        print("=" * 70)
        print("❌ ALL VENDORS DECLINED")
        print("=" * 70)
        print(f"Tried {len(attempts)} vendor(s):")
        for attempt in attempts:
            decision = attempt.get('decision', 'UNKNOWN')
            print(f"   - {attempt.get('vendor_name')}: {decision}")
        print()

        # Create a failure notification so the dashboard still shows a clear outcome
        failure_notification = create_failure_notification(
            product_info=product_info,
            order_details=order_details,
            attempts=attempts,
        )
        
        return {
            'final_status': 'failed',
            'error': 'All vendors declined the order',
            'attempts': attempts,
            'successful_vendor': None,
            'po_number': None,
            'email_draft': None,
            'notification': failure_notification,
            'rejection_notifications': rejection_notifications,
            'call_sid': attempts[-1].get('call_sid') if attempts else None,
        }
    
    def _get_vendors_for_order(self, product_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get list of vendors who can supply this product.
        
        Preference rule:
        - If the frontend passes a preferred vendor name (from the UI row,
          e.g., 'Holiday Decor Wholesale'), always try that vendor FIRST.
        - Then fall back to other vendors from the catalog.
        """
        vendors = self.vendor_db.get_vendors_for_product(
            product_name=product_info.get('name'),
            category=product_info.get('category'),
            sku=product_info.get('sku')
        )

        # If no vendors found in database, use default test vendors
        if not vendors:
            print("⚠️  No vendors found in database, using default test vendors")
            vendors = [
                {
                    'name': 'Holiday Supplies Inc',
                    'phone': os.getenv('VERIFIED_PHONE_NUMBER', ''),
                    'email': 'orders@holidaysupplies.com',
                    'priority': 1
                },
                {
                    'name': 'Festive Goods Co',
                    'phone': os.getenv('VERIFIED_PHONE_NUMBER', ''),
                    'email': 'sales@festivegoods.com',
                    'priority': 2
                }
            ]

        # Reorder vendors so the UI-selected vendor (from the row) is always first.
        preferred_vendor_name = (product_info.get('preferred_vendor_name') or '').strip()
        if preferred_vendor_name:
            preferred_lower = preferred_vendor_name.lower()
            # Look for an exact (case-insensitive) match in the vendor list
            match_index = None
            for idx, v in enumerate(vendors):
                if v.get('name', '').strip().lower() == preferred_lower:
                    match_index = idx
                    break

            if match_index is not None:
                # Move the matching vendor to the front of the list
                preferred_vendor = vendors.pop(match_index)
                vendors.insert(0, preferred_vendor)
                print(f"   ✅ Prioritizing UI-selected vendor first: {preferred_vendor_name}")
            else:
                # If the vendor name from the UI isn't in the catalog (different naming),
                # synthesize a first vendor entry using the preferred name and test phone.
                synthetic_vendor = {
                    'name': preferred_vendor_name,
                    'phone': os.getenv('VERIFIED_PHONE_NUMBER', ''),
                    'email': '',
                    'priority': 0
                }
                vendors.insert(0, synthetic_vendor)
                print(f"   ✅ Added UI-selected vendor to front of list: {preferred_vendor_name}")

        return vendors
    
    async def _make_vendor_call(self, vendor: Dict[str, Any], product_info: Dict[str, Any],
                                order_details: Dict[str, Any], attempt_number: int) -> Dict[str, Any]:
        """
        Make actual phone call to vendor using Nova Sonic via API endpoint
        
        Returns:
            {
                'vendor_name': str,
                'phone': str,
                'call_sid': str,
                'transcript': str,
                'decision': 'YES' | 'NO' | 'MAYBE',
                'confidence': float,
                'reasoning': str,
                'duration': int
            }
        """
        try:
            # Use the API endpoint for consistency
            import requests
            
            api_url = os.getenv('API_URL', 'http://localhost:5000')
            
            # Prepare call data
            call_data = {
                'vendor_phone': vendor['phone'],
                'vendor_name': vendor['name'],
                'contact_person': vendor.get('contact_person', 'there'),
                'product_name': product_info.get('name'),
                'quantity': order_details.get('quantity'),
                'items': order_details.get('items', []),
                'delivery_date': order_details.get('delivery_date', 'as soon as possible'),
                'total_amount': order_details.get('total_amount', 0),
                'po_number': f"DRAFT-{vendor['name'][:3].upper()}-{attempt_number}"
            }
            
            # Make API call to initiate vendor call
            response = requests.post(
                f'{api_url}/api/call-vendor',
                json=call_data,
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    call_sid = result.get('call_sid')
                    
                    if call_sid:
                        print(f"   ✅ Call initiated: {call_sid}")
                        print(f"   ⏳ Call in progress...")
                        
                        return {
                            'vendor_name': vendor['name'],
                            'phone': vendor['phone'],
                            'call_sid': call_sid,
                            'transcript': '',  # Will be filled in later
                            'duration': 0,
                            'attempt_number': attempt_number,
                            'status': 'initiated'
                        }
                    else:
                        raise Exception("No call_sid returned from API")
                except ValueError as e:
                    # Response is not JSON
                    print(f"   ⚠️  Response is not JSON: {response.text[:200]}")
                    raise Exception(f"API returned non-JSON response: {response.text[:100]}")
            else:
                # Try to get error message from JSON, fallback to status code
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', f'HTTP {response.status_code}')
                except ValueError:
                    error_msg = f'HTTP {response.status_code}: {response.text[:100]}'
                raise Exception(f"API call failed: {error_msg}")
            
        except Exception as e:
            print(f"Error making call to {vendor['name']}: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'vendor_name': vendor['name'],
                'phone': vendor['phone'],
                'call_sid': None,
                'transcript': '',
                'decision': 'NO',
                'confidence': 0.0,
                'reasoning': f'Call failed: {str(e)}',
                'key_quote': '',
                'duration': 0,
                'attempt_number': attempt_number,
                'error': str(e)
            }
    
    async def _check_call_status(self, call_sid: str, max_wait: int = 180, poll_interval: int = 2) -> str:
        """
        Check call status from Twilio
        
        Args:
            call_sid: Twilio call SID
            max_wait: Maximum seconds to wait
            poll_interval: Seconds between polls
            
        Returns:
            Call status string (completed, no-answer, busy, failed, etc.)
        """
        import time
        import requests
        
        api_url = os.getenv('API_URL', 'http://localhost:5000')
        start_time = time.time()
        ringing_start_time = None
        # Allow more time for second (and subsequent) calls to actually start ringing
        # Default to 90s, but allow override via environment variable.
        try:
            ringing_timeout = int(os.getenv('CALL_RINGING_TIMEOUT', '90'))
        except ValueError:
            ringing_timeout = 90
        
        while time.time() - start_time < max_wait:
            try:
                status_response = requests.get(
                    f'{api_url}/api/get-call-status/{call_sid}',
                    timeout=5
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    call_status = status_data.get('status', '')
                    print(f"   📞 Current call status from Twilio: {call_status}")
                    
                    # Track how long call has been ringing
                    if call_status in ['ringing', 'queued', 'initiated']:
                        if ringing_start_time is None:
                            ringing_start_time = time.time()
                            print(f"   📞 Call status: {call_status} - waiting for answer...")
                        
                        # If ringing for too long, treat as no-answer
                        if ringing_start_time and (time.time() - ringing_start_time) > ringing_timeout:
                            print(f"   ⏰ Call has been ringing for {ringing_timeout}s - treating as no-answer")
                            return 'no-answer'
                    else:
                        # Call moved to a different state, reset ringing timer
                        ringing_start_time = None
                    
                    # If call has ended (successfully or not), return status
                    if call_status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
                        return call_status
                
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                print(f"   ⚠️  Error checking call status: {e}")
                await asyncio.sleep(poll_interval)
        
        # Timeout - if we were ringing, treat as no-answer, otherwise return unknown
        if ringing_start_time:
            print(f"   ⏰ Timeout waiting for call - was ringing, treating as no-answer")
            return 'no-answer'
        return 'unknown'
    
    async def _wait_for_transcript(self, call_sid: str, max_wait: int = 120, poll_interval: int = 3) -> str:
        """
        Wait for call to complete and retrieve transcript from stored transcripts
        
        Args:
            call_sid: Twilio call SID
            max_wait: Maximum seconds to wait
            poll_interval: Seconds between polls
            
        Returns:
            Transcript text or empty string if not available
        """
        import time
        import requests
        
        api_url = os.getenv('API_URL', 'http://localhost:5000')
        start_time = time.time()
        call_completed = False
        
        print(f"   🔍 Waiting for transcript (max {max_wait}s)...")
        
        while time.time() - start_time < max_wait:
            try:
                # First, check if call is completed
                if not call_completed:
                    try:
                        status_response = requests.get(
                            f'{api_url}/api/get-call-status/{call_sid}',
                            timeout=5
                        )
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            call_status = status_data.get('status', '')
                            
                            if call_status in ['completed', 'failed', 'busy', 'no-answer']:
                                call_completed = True
                                print(f"   ✅ Call {call_status}, waiting for transcript...")
                                # Wait a bit for transcript to be stored
                                await asyncio.sleep(5)
                    except Exception as e:
                        pass
                
                # Try to get transcript directly (faster)
                try:
                    transcript_response = requests.get(
                        f'{api_url}/api/get-transcript/{call_sid}',
                        timeout=5
                    )
                    
                    if transcript_response.status_code == 200:
                        transcript_data = transcript_response.json()
                        if transcript_data.get('success') and transcript_data.get('transcript'):
                            transcript = transcript_data.get('transcript')
                            print(f"   ✅ Transcript retrieved ({len(transcript)} chars)")
                            return transcript
                except Exception as e:
                    pass
                
                # Fallback: Check via call logs API
                try:
                    response = requests.get(
                        f'{api_url}/api/call-logs',
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('success'):
                            calls = data.get('calls', [])
                            for call in calls:
                                if call.get('call_sid') == call_sid:
                                    transcript = call.get('transcript')
                                    if transcript:
                                        print(f"   ✅ Transcript found via call-logs ({len(transcript)} chars)")
                                        return transcript
                except:
                    pass
                
                # If API is not available, try direct access to call_transcripts_store
                # This only works if running in same process as app_agents.py
                try:
                    import sys
                    if 'app_agents' in sys.modules:
                        from app_agents import call_transcripts_store
                        stored = call_transcripts_store.get(call_sid, {})
                        transcript = stored.get('transcript')
                        if transcript:
                            print(f"   ✅ Transcript found in memory ({len(transcript)} chars)")
                            return transcript
                except:
                    pass
                
                # Wait before checking again
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:  # Print every 10 seconds
                    print(f"   ⏳ Still waiting... ({elapsed}s/{max_wait}s)")
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                print(f"   ⚠️  Error checking transcript: {e}")
                await asyncio.sleep(poll_interval)
        
        print(f"   ⏰ Timeout waiting for transcript (waited {max_wait}s)")
        return ""
    
    async def _handle_success(self, vendor: Dict[str, Any], product_info: Dict[str, Any],
                              order_details: Dict[str, Any], call_result: Dict[str, Any],
                              attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle successful order acceptance
        - Generate PO
        - Draft email
        - Create notification
        """
        print("📄 Generating Purchase Order...")
        
        # Generate PO
        po = generate_purchase_order(
            vendor=vendor,
            product_info=product_info,
            order_details=order_details,
            call_transcript=call_result.get('transcript', '')
        )
        
        print(f"   ✅ PO Generated: {po['po_number']}")
        print()
        
        # Draft email
        print("📧 Drafting confirmation email...")
        
        email_draft = await self._draft_confirmation_email(
            vendor=vendor,
            po=po,
            call_result=call_result
        )
        
        print(f"   ✅ Email drafted")
        print()
        
        # Create notification
        print("🔔 Creating notification...")
        
        notification = create_notification(
            po=po,
            vendor=vendor,
            email_draft=email_draft,
            call_result=call_result
        )
        
        print(f"   ✅ Notification created")
        print()
        
        print("=" * 70)
        print("✅ ORDER PLACEMENT COMPLETE")
        print("=" * 70)
        print(f"Vendor: {vendor['name']}")
        print(f"PO Number: {po['po_number']}")
        print(f"Total Amount: ₹{usd_to_inr(po['total_amount']):.2f}")
        print(f"Delivery Date: {po['delivery_date']}")
        print()
        
        return {
            'final_status': 'success',
            'successful_vendor': vendor['name'],
            'po_number': po['po_number'],
            'po': po,
            'email_draft': email_draft,
            'notification': notification,
            'attempts': attempts,
            'call_sid': call_result.get('call_sid'),
            'transcript': call_result.get('transcript')
        }
    
    async def _draft_confirmation_email(self, vendor: Dict[str, Any], po: Dict[str, Any],
                                       call_result: Dict[str, Any]) -> Dict[str, Any]:
        """Draft confirmation email to vendor"""
        try:
            # Import email drafter
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'email_drafter'))
            from email_drafter_agent import EmailDrafterAgent
            
            email_drafter = EmailDrafterAgent()
            
            # Extract items from PO
            items = po.get('items', [])
            
            email = email_drafter.draft_po_email(
                vendor_name=vendor['name'],
                contact_person=vendor.get('contact_person', 'there'),
                po_number=po['po_number'],
                items=items,
                total_amount=po['total_amount'],
                delivery_date=po['delivery_date'],
                call_transcript=call_result.get('transcript', ''),
                call_summary=f"Order confirmed via phone call. {vendor['name']} accepted the order."
            )
            
            return email
            
        except Exception as e:
            print(f"Error drafting email: {e}")
            # Return basic email template
            return {
                'subject': f"Purchase Order {po['po_number']} - {vendor['name']}",
                'body': f"""Dear {vendor['name']},

Thank you for accepting our order during our phone conversation.

Please find attached Purchase Order {po['po_number']} for your reference.

Order Details:
- PO Number: {po['po_number']}
- Total Amount: ₹{usd_to_inr(po['total_amount']):.2f}
- Delivery Date: {po['delivery_date']}

Please confirm receipt of this email.

Best regards,
HeartKart Procurement Team
""",
                'to': vendor.get('email', ''),
                'attachments': [f"{po['po_number']}.pdf"]
            }


# Convenience function
async def place_order_with_automatic_fallback(product_info: Dict[str, Any],
                                              order_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quick function to place order with automatic vendor fallback
    
    Usage:
        result = await place_order_with_automatic_fallback(
            product_info={'name': 'Valentine Ornaments', 'category': 'Ornaments'},
            order_details={'quantity': 500, 'delivery_date': '2025-12-15', 'total_amount': 2500}
        )
        
        if result['final_status'] == 'success':
            print(f"Order placed with {result['successful_vendor']}")
            print(f"PO: {result['po_number']}")
    """
    orchestrator = VendorOrchestratorV2()
    return await orchestrator.place_order_with_fallback(product_info, order_details)


if __name__ == '__main__':
    # Test the orchestrator
    import asyncio
    
    test_product = {
        'name': 'Valentine Ornaments',
        'category': 'Ornaments',
        'sku': 'ORN-001'
    }
    
    test_order = {
        'items': [
            {'name': 'Red Heart Ornaments', 'quantity': 300, 'unit_price': 5.00},
            {'name': 'Gold Heart Ornaments', 'quantity': 200, 'unit_price': 5.50}
        ],
        'quantity': 500,
        'delivery_date': '2025-12-15',
        'total_amount': 2600.00
    }
    
    print("Testing Vendor Orchestrator V2")
    print()
    
    result = asyncio.run(place_order_with_automatic_fallback(test_product, test_order))
    
    print()
    print("FINAL RESULT:")
    print(json.dumps(result, indent=2, default=str))
