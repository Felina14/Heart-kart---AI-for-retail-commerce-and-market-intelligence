"""
Agent Prompts for Vendor Calling with YES/NO Detection
Optimized for clear vendor responses and easy analysis
"""

def get_vendor_call_system_prompt(vendor_name: str, order_details: dict) -> str:
    """
    System prompt for Nova Sonic agent - optimized for YES/NO detection
    """
    return f"""You are Sarah, a professional procurement agent from HeartKart calling {vendor_name}.

YOUR GOAL: Get a clear YES or NO answer about order fulfillment.

ORDER DETAILS:
- Product: {order_details.get('product_name', 'products')}
- Quantity: {order_details.get('quantity', 0)} units
- Delivery needed by: {order_details.get('delivery_date', 'as soon as possible')}
- Estimated value: ${order_details.get('total_amount', 0):.2f}

CONVERSATION FLOW:
1. Greet professionally and introduce yourself
2. Ask if you're speaking with the right person
3. Clearly state the order requirements
4. Ask directly: "Can you fulfill this order?"
5. Listen for their response (YES or NO)
6. If YES: Confirm delivery date and pricing, thank them, end call
7. If NO: Ask why (optional), thank them politely, end call
8. Keep the call under 60 seconds

CRITICAL RULES:
- Be polite but direct
- Get a clear YES or NO answer
- Don't negotiate or discuss alternatives
- If they say "maybe" or "let me check", treat it as NO for now
- End the call once you have their answer
- Use natural, conversational language

EXAMPLE GOOD RESPONSES TO LISTEN FOR:
YES signals: "Yes", "Sure", "We can do that", "No problem", "Absolutely", "Yes we can"
NO signals: "No", "Sorry", "Can't", "Unable to", "Out of stock", "Not available", "We don't have"

Remember: Your job is to get a clear answer quickly and professionally."""


def get_transcript_analysis_prompt(transcript: str) -> str:
    """
    Prompt for analyzing call transcript to extract vendor decision
    """
    return f"""Analyze this vendor call transcript and determine the vendor's decision.

TRANSCRIPT:
{transcript}

TASK: Determine if the vendor agreed to fulfill the order.

DECISION RULES:
- Return "YES" if vendor clearly agreed (e.g., "yes", "sure", "we can do that", "no problem")
- Return "NO" if vendor declined (e.g., "no", "can't", "unable", "out of stock", "sorry")
- Return "MAYBE" if vendor was uncertain or needs more time (e.g., "let me check", "I'll get back to you")

IMPORTANT:
- Look at the VENDOR's responses, not the agent's questions
- Focus on the final answer, not preliminary discussion
- If vendor gives mixed signals, use the last clear statement
- "Maybe" or "I need to check" = treat as NO for now

OUTPUT FORMAT (JSON):
{{
    "decision": "YES" | "NO" | "MAYBE",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of why you chose this decision",
    "key_quote": "The exact vendor quote that led to this decision"
}}

Return ONLY valid JSON, nothing else."""


def get_vendor_greeting_prompt(vendor_name: str = 'the vendor', contact_person: str = None) -> str:
    """
    Opening greeting for the call
    """
    if contact_person and contact_person != "there":
        return f"Hello, this is Sarah from HeartKart. I'm calling to speak with {contact_person} from {vendor_name}."
    else:
        return f"Hello, this is Sarah from HeartKart. I'm calling {vendor_name} regarding a potential order."


def get_order_presentation_prompt(order_details: dict) -> str:
    """
    How to present the order clearly
    """
    items_desc = ", ".join([f"{item.get('quantity', 0)} units of {item.get('name', 'product')}" 
                            for item in order_details.get('items', [])])
    
    if not items_desc:
        items_desc = f"{order_details.get('quantity', 0)} units of {order_details.get('product_name', 'products')}"
    
    return f"""Great! I'd like to place an order with you. Here are the details:

We need {items_desc}.

We need delivery by {order_details.get('delivery_date', 'as soon as possible')}.

Can you fulfill this order?"""


def get_yes_confirmation_prompt(order_details: dict) -> str:
    """
    What to say when vendor says YES
    """
    return f"""Excellent! Thank you so much. 

Just to confirm:
- Delivery by {order_details.get('delivery_date', 'the requested date')}
- Total estimated cost: ${order_details.get('total_amount', 0):.2f}

Is that correct? ... Great! We'll send you a formal purchase order via email shortly. Thank you for your time!"""


def get_no_acknowledgment_prompt() -> str:
    """
    What to say when vendor says NO
    """
    return "I understand. Thank you for your time and honesty. We appreciate it. Have a great day!"


def get_clarification_prompt() -> str:
    """
    What to say if vendor response is unclear
    """
    return "I want to make sure I understand correctly - are you able to fulfill this order, yes or no?"


# Real-time decision detection keywords
YES_KEYWORDS = [
    "yes", "yeah", "yep", "sure", "absolutely", "definitely",
    "we can", "no problem", "of course", "certainly", "affirmative",
    "sounds good", "that works", "we'll do it", "count on us"
]

NO_KEYWORDS = [
    "no", "nope", "can't", "cannot", "unable", "sorry",
    "out of stock", "don't have", "not available", "won't work",
    "impossible", "can't do", "not possible", "unavailable",
    # Explicit refusal / closed phrases commonly heard from vendors
    "not taking any purchase order",
    "not taking purchase orders",
    "not taking any orders",
    "not accepting orders",
    "not accepting any orders",
    "we are closed",
    "we're closed",
    "pre closed",
    "closed for orders",
    "we are not taking orders",
    "we're not taking orders"
]

MAYBE_KEYWORDS = [
    "maybe", "possibly", "let me check", "need to verify",
    "have to see", "not sure", "uncertain", "might be able"
]


def detect_decision_from_text(text: str) -> str:
    """
    Quick keyword-based decision detection for real-time use
    Returns: YES, NO, MAYBE, or UNCLEAR
    """
    text_lower = text.lower()
    
    # Check for YES signals
    yes_count = sum(1 for keyword in YES_KEYWORDS if keyword in text_lower)
    
    # Check for NO signals
    no_count = sum(1 for keyword in NO_KEYWORDS if keyword in text_lower)
    
    # Check for MAYBE signals
    maybe_count = sum(1 for keyword in MAYBE_KEYWORDS if keyword in text_lower)
    
    # Determine decision based on keyword counts
    if yes_count > no_count and yes_count > maybe_count:
        return "YES"
    elif no_count > yes_count:
        return "NO"
    elif maybe_count > 0:
        return "MAYBE"
    else:
        return "UNCLEAR"
