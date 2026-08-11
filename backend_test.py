#!/usr/bin/env python3
"""
READ-ONLY Smoke Test for Bloodhound Backend API
CRITICAL: Only GET requests allowed. No writes to Airtable or any POST/PATCH/PUT/DELETE operations.
"""

import requests
import json
from typing import Dict, Any, Optional
import time

# Base URL from frontend/.env
BASE_URL = "https://branch-verify-build.preview.emergentagent.com/api"

# Test results storage
test_results = []

def test_endpoint(endpoint: str, method: str = "GET", description: str = "") -> Dict[str, Any]:
    """
    Test a single endpoint and return results.
    
    Args:
        endpoint: The endpoint path (e.g., "/health")
        method: HTTP method (default: GET)
        description: Human-readable description
    
    Returns:
        Dict with test results
    """
    url = f"{BASE_URL}{endpoint}"
    result = {
        "endpoint": endpoint,
        "method": method,
        "url": url,
        "description": description,
        "status_code": None,
        "pass": False,
        "json_parsed": False,
        "payload_summary": "",
        "notes": ""
    }
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        else:
            result["notes"] = f"Method {method} not allowed in READ-ONLY test"
            return result
        
        result["status_code"] = response.status_code
        
        # Check if response is successful
        if 200 <= response.status_code < 300:
            result["pass"] = True
        
        # Try to parse JSON
        try:
            data = response.json()
            result["json_parsed"] = True
            
            # Generate payload summary
            if isinstance(data, list):
                result["payload_summary"] = f"List with {len(data)} items"
                if len(data) > 0 and isinstance(data[0], dict):
                    sample_keys = list(data[0].keys())
                    result["payload_summary"] += f" | Sample keys: {sample_keys[:5]}"
            elif isinstance(data, dict):
                keys = list(data.keys())
                result["payload_summary"] = f"Dict with keys: {keys[:10]}"
                if len(keys) > 10:
                    result["payload_summary"] += f" ... ({len(keys)} total)"
                
                # For nested list fields, report count
                if "opportunities" in data and isinstance(data["opportunities"], list):
                    result["payload_summary"] += f" | {len(data['opportunities'])} opportunities"
                elif "leads" in data and isinstance(data["leads"], list):
                    result["payload_summary"] += f" | {len(data['leads'])} leads"
                elif "drafts" in data and isinstance(data["drafts"], list):
                    result["payload_summary"] += f" | {len(data['drafts'])} drafts"
                elif "handoffs" in data and isinstance(data["handoffs"], list):
                    result["payload_summary"] += f" | {len(data['handoffs'])} handoffs"
                elif "playbooks" in data and isinstance(data["playbooks"], list):
                    result["payload_summary"] += f" | {len(data['playbooks'])} playbooks"
            else:
                result["payload_summary"] = f"Type: {type(data).__name__}"
                
        except json.JSONDecodeError as e:
            result["json_parsed"] = False
            result["notes"] = f"JSON parse error: {str(e)}"
            # Check if it's an SSE stream
            if "text/event-stream" in response.headers.get("content-type", ""):
                result["json_parsed"] = "N/A (SSE stream)"
                result["payload_summary"] = "SSE stream started"
                result["pass"] = True
        
        # Add response text preview for errors
        if not result["pass"] and response.text:
            result["notes"] += f" | Response: {response.text[:200]}"
            
    except requests.exceptions.Timeout:
        result["notes"] = "Request timeout (10s)"
    except requests.exceptions.ConnectionError as e:
        result["notes"] = f"Connection error: {str(e)}"
    except Exception as e:
        result["notes"] = f"Error: {str(e)}"
    
    return result


def test_sse_endpoint(endpoint: str) -> Dict[str, Any]:
    """
    Test SSE endpoint - connect and immediately disconnect.
    """
    url = f"{BASE_URL}{endpoint}"
    result = {
        "endpoint": endpoint,
        "method": "GET (SSE)",
        "url": url,
        "description": "Server-Sent Events stream",
        "status_code": None,
        "pass": False,
        "json_parsed": "N/A (SSE)",
        "payload_summary": "",
        "notes": ""
    }
    
    try:
        # Use stream=True and immediately close
        response = requests.get(url, stream=True, timeout=5)
        result["status_code"] = response.status_code
        
        if 200 <= response.status_code < 300:
            result["pass"] = True
            result["payload_summary"] = "SSE connection established"
            result["notes"] = "Connected and immediately disconnected (as required)"
        else:
            result["notes"] = f"Failed to connect: {response.status_code}"
        
        # Immediately close the connection
        response.close()
        
    except Exception as e:
        result["notes"] = f"Error: {str(e)}"
    
    return result


def print_results_table(results: list):
    """Print results in a formatted table."""
    print("\n" + "="*150)
    print("BLOODHOUND BACKEND API - READ-ONLY SMOKE TEST RESULTS")
    print("="*150)
    print(f"{'#':<4} {'Endpoint':<45} {'Method':<10} {'Status':<8} {'Pass':<6} {'JSON':<8} {'Payload Summary':<50}")
    print("-"*150)
    
    for i, r in enumerate(results, 1):
        status = str(r['status_code']) if r['status_code'] else "N/A"
        pass_str = "✓" if r['pass'] else "✗"
        json_str = "✓" if r['json_parsed'] is True else ("N/A" if r['json_parsed'] == "N/A (SSE)" else "✗")
        
        print(f"{i:<4} {r['endpoint']:<45} {r['method']:<10} {status:<8} {pass_str:<6} {json_str:<8} {r['payload_summary'][:48]:<50}")
        
        if r['notes']:
            print(f"     Notes: {r['notes']}")
    
    print("-"*150)
    
    # Summary
    total = len(results)
    passed = sum(1 for r in results if r['pass'])
    failed = total - passed
    
    print(f"\nSUMMARY: {passed}/{total} endpoints passed | {failed} failed")
    print("="*150 + "\n")


def main():
    """Run all READ-ONLY smoke tests."""
    print("Starting READ-ONLY smoke test of Bloodhound backend API...")
    print(f"Base URL: {BASE_URL}")
    print("SAFETY: Only GET requests will be sent. No writes to Airtable or database.\n")
    
    # Test basic endpoints
    test_results.append(test_endpoint("/", description="Root endpoint"))
    test_results.append(test_endpoint("/health", description="Health check"))
    test_results.append(test_endpoint("/config", description="Configuration"))
    test_results.append(test_endpoint("/schema", description="Schema information"))
    test_results.append(test_endpoint("/cache-status", description="Cache status"))
    
    # Test opportunities endpoints
    test_results.append(test_endpoint("/opportunities", description="List all opportunities"))
    test_results.append(test_endpoint("/opportunities/lanes", description="Opportunity lanes"))
    test_results.append(test_endpoint("/opportunities/top-by-lane", description="Top opportunities by lane"))
    test_results.append(test_endpoint("/opportunities/summary", description="Opportunities summary"))
    test_results.append(test_endpoint("/opportunities/missions", description="Opportunities missions"))
    test_results.append(test_endpoint("/opportunities/pipeline", description="Opportunities pipeline"))
    test_results.append(test_endpoint("/opportunities/recent", description="Recent opportunities"))
    test_results.append(test_endpoint("/opportunities/top", description="Top opportunities"))
    
    # Get a valid opportunity ID for detail endpoints
    opp_id = None
    try:
        response = requests.get(f"{BASE_URL}/opportunities", timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Response is a list of opportunities
            if isinstance(data, list) and len(data) > 0:
                opp_id = data[0].get("id")
                print(f"✓ Found opportunity ID for detail tests: {opp_id}\n")
            # Or it might be a dict with "opportunities" key
            elif isinstance(data, dict) and "opportunities" in data and len(data["opportunities"]) > 0:
                opp_id = data["opportunities"][0].get("id")
                print(f"✓ Found opportunity ID for detail tests: {opp_id}\n")
    except Exception as e:
        print(f"✗ Could not fetch opportunity ID: {e}\n")
    
    # Test opportunity detail endpoints (if we have an ID)
    if opp_id:
        test_results.append(test_endpoint(f"/opportunities/{opp_id}", description=f"Opportunity detail (ID: {opp_id})"))
        test_results.append(test_endpoint(f"/opportunities/{opp_id}/handoffs", description=f"Opportunity handoffs (ID: {opp_id})"))
    else:
        test_results.append({
            "endpoint": "/opportunities/{opp_id}",
            "method": "GET",
            "url": f"{BASE_URL}/opportunities/{{opp_id}}",
            "description": "Opportunity detail",
            "status_code": None,
            "pass": False,
            "json_parsed": False,
            "payload_summary": "",
            "notes": "Skipped - no opportunity ID available"
        })
        test_results.append({
            "endpoint": "/opportunities/{opp_id}/handoffs",
            "method": "GET",
            "url": f"{BASE_URL}/opportunities/{{opp_id}}/handoffs",
            "description": "Opportunity handoffs",
            "status_code": None,
            "pass": False,
            "json_parsed": False,
            "payload_summary": "",
            "notes": "Skipped - no opportunity ID available"
        })
    
    # Test leads endpoints
    test_results.append(test_endpoint("/leads/next-best-action", description="Next best action for leads"))
    
    # Test live endpoints
    test_results.append(test_endpoint("/live/status", description="Live status"))
    
    # Test Slack endpoints
    test_results.append(test_endpoint("/slack/alerts/status", description="Slack alerts status"))
    
    # Test playbook endpoints
    test_results.append(test_endpoint("/message-playbooks", description="Message playbooks"))
    
    # Test draft endpoints
    test_results.append(test_endpoint("/drafts", description="List drafts"))
    test_results.append(test_endpoint("/drafts/queue", description="Draft queue"))
    
    # Test handoff endpoints
    test_results.append(test_endpoint("/handoffs/recent", description="Recent handoffs"))
    
    # Test follow-up endpoints
    test_results.append(test_endpoint("/follow-ups/due", description="Due follow-ups"))
    
    # Test KPI endpoints
    test_results.append(test_endpoint("/kpis/monthly", description="Monthly KPIs"))
    
    # Test settings endpoints
    test_results.append(test_endpoint("/settings/user", description="User settings"))
    
    # Test SSE endpoint (special handling - connect and disconnect immediately)
    test_results.append(test_sse_endpoint("/live/stream"))
    
    # Print results
    print_results_table(test_results)
    
    # Return exit code based on results
    failed_count = sum(1 for r in test_results if not r['pass'])
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    exit(main())
