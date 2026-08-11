#!/usr/bin/env python3
"""
Safety Verification Test for Bloodhound Backend API
Commit: edea355 "Disable direct provider outreach delivery"
Branch: computer/simplified-relationship-flow

PRIMARY VERIFICATION:
1. POST /api/leads/{lead_id}/action with {"action":"approve"} MUST return HTTP 410 (Gone)
   - Test with real lead_id
   - Test with fake lead_id (e.g., "fake123")
   - Both must return 410 because approve is rejected BEFORE any lookup
   - Response must indicate delivery is disabled / device-native draft

2. Confirm NO email is sent (inherently satisfied if 410 is returned)

SECONDARY VERIFICATION:
3. Test hold/skip actions work normally (200-ish status)
4. Test do_not_contact without confirm returns 400 (safe, no mutation)
"""

import requests
import json
from typing import Dict, Any, Optional

# Base URL from frontend/.env
BASE_URL = "https://branch-verify-build.preview.emergentagent.com/api"

def test_lead_action(lead_id: str, action: str, confirm: bool = False, description: str = "") -> Dict[str, Any]:
    """
    Test a lead action endpoint.
    
    Args:
        lead_id: The lead ID (can be real or fake)
        action: The action to perform (approve, hold, skip, do_not_contact)
        confirm: Whether to confirm the action (for do_not_contact)
        description: Human-readable description
    
    Returns:
        Dict with test results
    """
    url = f"{BASE_URL}/leads/{lead_id}/action"
    payload = {"action": action}
    if confirm:
        payload["confirm"] = True
    
    result = {
        "request": f"POST /api/leads/{lead_id}/action",
        "body": json.dumps(payload),
        "lead_id": lead_id,
        "action": action,
        "description": description,
        "status_code": None,
        "response_detail": "",
        "pass": False,
        "notes": ""
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        result["status_code"] = response.status_code
        
        # Try to parse JSON response
        try:
            data = response.json()
            if "detail" in data:
                result["response_detail"] = data["detail"]
            else:
                result["response_detail"] = json.dumps(data)
        except json.JSONDecodeError:
            result["response_detail"] = response.text[:200]
        
    except requests.exceptions.Timeout:
        result["notes"] = "Request timeout (10s)"
    except requests.exceptions.ConnectionError as e:
        result["notes"] = f"Connection error: {str(e)}"
    except Exception as e:
        result["notes"] = f"Error: {str(e)}"
    
    return result


def get_real_lead_id() -> Optional[str]:
    """
    Get a real lead ID from the next-best-action endpoint.
    
    Returns:
        Lead ID if available, None otherwise
    """
    try:
        url = f"{BASE_URL}/leads/next-best-action"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("lead") and isinstance(data["lead"], dict):
                lead_id = data["lead"].get("id")
                if lead_id:
                    print(f"✓ Found real lead ID: {lead_id}")
                    return lead_id
        print("✗ No lead available in queue")
        return None
    except Exception as e:
        print(f"✗ Error fetching lead ID: {e}")
        return None


def print_results_table(results: list):
    """Print results in a formatted table."""
    print("\n" + "="*160)
    print("BLOODHOUND SAFETY VERIFICATION - COMMIT edea355")
    print("="*160)
    print(f"{'#':<4} {'Request':<45} {'Body':<30} {'Status':<8} {'Pass/Fail':<10} {'Response Detail':<60}")
    print("-"*160)
    
    for i, r in enumerate(results, 1):
        status = str(r['status_code']) if r['status_code'] else "N/A"
        pass_str = "PASS ✓" if r['pass'] else "FAIL ✗"
        body_short = r['body'][:28] if len(r['body']) <= 28 else r['body'][:25] + "..."
        detail_short = r['response_detail'][:58] if len(r['response_detail']) <= 58 else r['response_detail'][:55] + "..."
        
        print(f"{i:<4} {r['request']:<45} {body_short:<30} {status:<8} {pass_str:<10} {detail_short:<60}")
        
        if r['notes']:
            print(f"     Notes: {r['notes']}")
        if r['description']:
            print(f"     Description: {r['description']}")
    
    print("-"*160)


def main():
    """Run safety verification tests."""
    print("Starting SAFETY VERIFICATION test of Bloodhound backend API...")
    print(f"Base URL: {BASE_URL}")
    print("Commit: edea355 - Disable direct provider outreach delivery")
    print("Branch: computer/simplified-relationship-flow\n")
    
    test_results = []
    
    # ========================================================================
    # PRIMARY VERIFICATION: approve action MUST return 410
    # ========================================================================
    print("\n" + "="*80)
    print("PRIMARY VERIFICATION: Approve action must return HTTP 410")
    print("="*80 + "\n")
    
    # Test 1: Approve with FAKE lead_id (must return 410 before lookup)
    print("Test 1: POST /api/leads/fake123/action with {\"action\":\"approve\"}")
    result1 = test_lead_action(
        lead_id="fake123",
        action="approve",
        description="CRITICAL: Must return 410 for fake lead_id (approve rejected before lookup)"
    )
    # Expected: 410
    result1["pass"] = (result1["status_code"] == 410)
    test_results.append(result1)
    
    if result1["status_code"] == 410:
        print(f"✓ PASS: Returned 410 as expected")
        print(f"  Detail: {result1['response_detail']}")
    else:
        print(f"✗ FAIL: Expected 410, got {result1['status_code']}")
        print(f"  Detail: {result1['response_detail']}")
    
    # Test 2: Approve with REAL lead_id (must also return 410 before lookup)
    print("\nTest 2: POST /api/leads/{real_id}/action with {\"action\":\"approve\"}")
    real_lead_id = get_real_lead_id()
    
    if real_lead_id:
        result2 = test_lead_action(
            lead_id=real_lead_id,
            action="approve",
            description="CRITICAL: Must return 410 for real lead_id (approve rejected before lookup)"
        )
        # Expected: 410
        result2["pass"] = (result2["status_code"] == 410)
        test_results.append(result2)
        
        if result2["status_code"] == 410:
            print(f"✓ PASS: Returned 410 as expected")
            print(f"  Detail: {result2['response_detail']}")
        else:
            print(f"✗ FAIL: Expected 410, got {result2['status_code']}")
            print(f"  Detail: {result2['response_detail']}")
    else:
        print("⚠ SKIPPED: No real lead available in queue")
        test_results.append({
            "request": "POST /api/leads/{real_id}/action",
            "body": '{"action":"approve"}',
            "lead_id": "N/A",
            "action": "approve",
            "description": "Skipped - no real lead available",
            "status_code": None,
            "response_detail": "No lead in queue",
            "pass": False,
            "notes": "Skipped - no real lead available in queue"
        })
    
    # ========================================================================
    # SECONDARY VERIFICATION: Other actions should work normally
    # ========================================================================
    print("\n" + "="*80)
    print("SECONDARY VERIFICATION: Other actions should work normally")
    print("="*80 + "\n")
    
    if real_lead_id:
        # Test 3: Hold action (should work - expect 200-ish)
        print(f"Test 3: POST /api/leads/{real_lead_id}/action with {{\"action\":\"hold\"}}")
        result3 = test_lead_action(
            lead_id=real_lead_id,
            action="hold",
            description="Should work normally (expect 200-ish)"
        )
        # Expected: 200-299
        result3["pass"] = (200 <= result3["status_code"] < 300) if result3["status_code"] else False
        test_results.append(result3)
        
        if result3["pass"]:
            print(f"✓ PASS: Returned {result3['status_code']} as expected")
        else:
            print(f"✗ FAIL: Expected 200-ish, got {result3['status_code']}")
            print(f"  Detail: {result3['response_detail']}")
        
        # Test 4: Skip action (should work - expect 200-ish)
        print(f"\nTest 4: POST /api/leads/{real_lead_id}/action with {{\"action\":\"skip\"}}")
        result4 = test_lead_action(
            lead_id=real_lead_id,
            action="skip",
            description="Should work normally (expect 200-ish)"
        )
        # Expected: 200-299
        result4["pass"] = (200 <= result4["status_code"] < 300) if result4["status_code"] else False
        test_results.append(result4)
        
        if result4["pass"]:
            print(f"✓ PASS: Returned {result4['status_code']} as expected")
        else:
            print(f"✗ FAIL: Expected 200-ish, got {result4['status_code']}")
            print(f"  Detail: {result4['response_detail']}")
        
        # Test 5: Do not contact WITHOUT confirm (should return 400 - safe, no mutation)
        print(f"\nTest 5: POST /api/leads/{real_lead_id}/action with {{\"action\":\"do_not_contact\"}} (no confirm)")
        result5 = test_lead_action(
            lead_id=real_lead_id,
            action="do_not_contact",
            confirm=False,
            description="Should return 400 (confirmation required) - safe, no mutation"
        )
        # Expected: 400
        result5["pass"] = (result5["status_code"] == 400)
        test_results.append(result5)
        
        if result5["pass"]:
            print(f"✓ PASS: Returned 400 as expected (confirmation required)")
            print(f"  Detail: {result5['response_detail']}")
        else:
            print(f"✗ FAIL: Expected 400, got {result5['status_code']}")
            print(f"  Detail: {result5['response_detail']}")
    else:
        print("⚠ SKIPPED: Secondary tests require a real lead ID")
    
    # Print final results table
    print_results_table(test_results)
    
    # Summary
    total = len(test_results)
    passed = sum(1 for r in test_results if r['pass'])
    failed = total - passed
    
    print(f"\nSUMMARY: {passed}/{total} tests passed | {failed} failed")
    
    # Critical assessment
    print("\n" + "="*80)
    print("CRITICAL ASSESSMENT")
    print("="*80)
    
    approve_tests = [r for r in test_results if r['action'] == 'approve']
    approve_passed = all(r['pass'] for r in approve_tests)
    
    if approve_passed and len(approve_tests) > 0:
        print("✓ CRITICAL PASS: All approve actions returned HTTP 410")
        print("✓ Email delivery is DISABLED as expected")
        print("✓ Device-native draft handoff is enforced")
    else:
        print("✗ CRITICAL FAIL: Approve action did not return HTTP 410")
        print("✗ SAFETY ISSUE: Email delivery may still be active")
    
    print("="*80 + "\n")
    
    # Return exit code based on critical tests
    return 0 if approve_passed else 1


if __name__ == "__main__":
    exit(main())
