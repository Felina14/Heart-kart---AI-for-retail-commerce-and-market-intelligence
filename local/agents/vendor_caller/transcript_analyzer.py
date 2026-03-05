"""
Transcript Analyzer - Uses AI to analyze call transcripts and extract vendor decisions
"""

import json
import boto3
from typing import Dict, Any
from agent_prompts import get_transcript_analysis_prompt, detect_decision_from_text


class TranscriptAnalyzer:
    """Analyzes call transcripts to determine vendor decision (YES/NO/MAYBE)"""
    
    def __init__(self):
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        self.model_id = 'us.amazon.nova-lite-v1:0'
    
    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Analyze full call transcript using AI
        
        Args:
            transcript: Full conversation transcript
            
        Returns:
            {
                'decision': 'YES' | 'NO' | 'MAYBE',
                'confidence': float (0-1),
                'reasoning': str,
                'key_quote': str
            }
        """
        try:
            # First try quick keyword detection - trust for clear YES/NO, regardless of length
            quick_decision = detect_decision_from_text(transcript)
            
            if quick_decision in ['YES', 'NO']:
                return {
                    'decision': quick_decision,
                    'confidence': 0.9,
                    'reasoning': f'Clear {quick_decision} detected via keyword analysis',
                    'key_quote': self._extract_key_quote(transcript, quick_decision),
                    'method': 'keyword'
                }
            
            # Use AI for more complex / unclear cases (MAYBE/UNCLEAR)
            prompt = get_transcript_analysis_prompt(transcript)
            
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    'messages': [
                        {
                            'role': 'user',
                            'content': [{'text': prompt}]
                        }
                    ],
                    'inferenceConfig': {
                        'temperature': 0.1,  # Low temperature for consistent analysis
                        'maxTokens': 500
                    }
                })
            )
            
            result = json.loads(response['body'].read())
            response_text = result['output']['message']['content'][0]['text']
            
            # Parse JSON response
            analysis = self._parse_ai_response(response_text)
            analysis['method'] = 'ai'
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing transcript: {e}")
            # Fallback to keyword detection
            return {
                'decision': detect_decision_from_text(transcript),
                'confidence': 0.5,
                'reasoning': f'Fallback to keyword detection due to error: {str(e)}',
                'key_quote': '',
                'method': 'fallback'
            }
    
    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response JSON"""
        try:
            # Try to extract JSON from response
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                json_str = response_text.split('```')[1].split('```')[0].strip()
            else:
                json_str = response_text.strip()
            
            analysis = json.loads(json_str)
            
            # Validate required fields
            if 'decision' not in analysis:
                raise ValueError("Missing 'decision' field")
            
            # Ensure decision is uppercase
            analysis['decision'] = analysis['decision'].upper()
            
            # Set defaults for optional fields
            analysis.setdefault('confidence', 0.7)
            analysis.setdefault('reasoning', 'AI analysis')
            analysis.setdefault('key_quote', '')
            
            return analysis
            
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            print(f"Response text: {response_text}")
            # Return default
            return {
                'decision': 'UNCLEAR',
                'confidence': 0.3,
                'reasoning': f'Failed to parse AI response: {str(e)}',
                'key_quote': ''
            }
    
    def _extract_key_quote(self, transcript: str, decision: str) -> str:
        """Extract a relevant quote from transcript"""
        lines = transcript.split('\n')
        
        # Look for vendor responses (not agent)
        for line in lines:
            line_lower = line.lower()
            if decision == 'YES' and any(word in line_lower for word in ['yes', 'sure', 'we can']):
                return line.strip()
            elif decision == 'NO' and any(word in line_lower for word in ['no', 'can\'t', 'sorry']):
                return line.strip()
        
        # Return first non-empty line as fallback
        for line in lines:
            if line.strip():
                return line.strip()
        
        return ''
    
    def analyze_real_time(self, partial_transcript: str) -> Dict[str, Any]:
        """
        Quick analysis during call for real-time decision making
        Uses keyword detection for speed
        
        Args:
            partial_transcript: Transcript so far (may be incomplete)
            
        Returns:
            {
                'decision': 'YES' | 'NO' | 'MAYBE' | 'UNCLEAR',
                'confidence': float,
                'should_end_call': bool
            }
        """
        decision = detect_decision_from_text(partial_transcript)
        
        # Determine if we should end the call
        should_end = decision in ['YES', 'NO']
        
        # Confidence based on clarity
        confidence = 0.8 if should_end else 0.4
        
        return {
            'decision': decision,
            'confidence': confidence,
            'should_end_call': should_end,
            'method': 'real_time'
        }
    
    def get_decision_summary(self, analysis: Dict[str, Any]) -> str:
        """
        Get human-readable summary of decision
        """
        decision = analysis.get('decision', 'UNCLEAR')
        confidence = analysis.get('confidence', 0)
        reasoning = analysis.get('reasoning', '')
        
        emoji = {
            'YES': '✅',
            'NO': '❌',
            'MAYBE': '🤔',
            'UNCLEAR': '❓'
        }.get(decision, '❓')
        
        return f"{emoji} {decision} (confidence: {confidence:.0%}) - {reasoning}"


# Convenience function for quick analysis
def analyze_call_transcript(transcript: str) -> Dict[str, Any]:
    """
    Quick function to analyze a transcript
    
    Usage:
        result = analyze_call_transcript(transcript)
        if result['decision'] == 'YES':
            # Generate PO
        elif result['decision'] == 'NO':
            # Try next vendor
    """
    analyzer = TranscriptAnalyzer()
    return analyzer.analyze_transcript(transcript)


if __name__ == '__main__':
    # Test the analyzer
    test_transcripts = [
        {
            'name': 'Clear YES',
            'transcript': '''
Agent: Can you fulfill this order for 500 Valentine ornaments?
Vendor: Yes, we can definitely do that. No problem at all.
Agent: Great! Thank you.
'''
        },
        {
            'name': 'Clear NO',
            'transcript': '''
Agent: Can you fulfill this order for 500 Valentine ornaments?
Vendor: Sorry, we're completely out of stock on those items.
Agent: I understand. Thank you.
'''
        },
        {
            'name': 'Maybe',
            'transcript': '''
Agent: Can you fulfill this order for 500 Valentine ornaments?
Vendor: Let me check with our warehouse and get back to you.
Agent: Okay, thank you.
'''
        }
    ]
    
    analyzer = TranscriptAnalyzer()
    
    print("=" * 70)
    print("TRANSCRIPT ANALYZER TEST")
    print("=" * 70)
    print()
    
    for test in test_transcripts:
        print(f"Test: {test['name']}")
        print(f"Transcript: {test['transcript'][:100]}...")
        
        result = analyzer.analyze_transcript(test['transcript'])
        print(f"Result: {analyzer.get_decision_summary(result)}")
        print(f"Key Quote: {result.get('key_quote', 'N/A')}")
        print()
