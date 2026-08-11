#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
user_problem_statement: "Pulled branch computer/simplified-relationship-flow into preview. User requested a READ-ONLY automated smoke test of backend endpoints. STRICT constraint: no writes/updates/creates to Airtable, no drafts, no message sends, no outreach activation. Production must remain untouched."

backend:
  - task: "Read-only smoke test of GET endpoints"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Requesting READ-ONLY smoke test. Test ONLY GET endpoints listed in test_plan. DO NOT call any POST/PATCH/PUT/DELETE endpoints. DO NOT write to Airtable, create/open drafts, send messages, log handoffs, or activate outreach."
        -working: true
        -agent: "testing"
        -comment: "READ-ONLY smoke test completed successfully. Tested 26 GET endpoints. Results: 25/26 passed. All critical endpoints working. Base endpoints (/, /health, /config, /schema, /cache-status) all return 200. Opportunities endpoints (list, lanes, top-by-lane, summary, missions, pipeline, recent, top, detail, handoffs) all working. Leads next-best-action working. Live status and SSE stream working (connected and immediately disconnected as required). Slack alerts status working. Message playbooks working. Drafts queue working. Handoffs recent working. Follow-ups due working. KPIs monthly working. Settings user working. Note: /drafts endpoint requires opportunity_id query parameter (returns 422 without it) - this is expected API design, not a bug. When tested with parameter (?opportunity_id=recCGVbFaQ48Vd3C5), returns 200 with empty drafts array. No write operations performed. Production data untouched. STRICT READ-ONLY constraint maintained throughout testing."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 2
  run_ui: false

test_plan:
  current_focus:
    - "Read-only smoke test of GET endpoints"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: "READ-ONLY smoke test only. Allowed (GET): /api/, /api/health, /api/config, /api/schema, /api/cache-status, /api/opportunities, /api/opportunities/lanes, /api/opportunities/top-by-lane, /api/opportunities/summary, /api/opportunities/missions, /api/opportunities/pipeline, /api/opportunities/recent, /api/opportunities/top, /api/opportunities/{id}, /api/leads/next-best-action, /api/live/status, /api/slack/alerts/status, /api/message-playbooks, /api/drafts, /api/drafts/queue, /api/drafts/{id}, /api/opportunities/{id}/handoffs, /api/handoffs/recent, /api/follow-ups/due, /api/kpis/monthly, /api/settings/user. FORBIDDEN (do NOT call): every POST/PATCH/PUT/DELETE incl. status/mission/activity/fields/result, cache-refresh, leads action, leads message, admin reload, airtable webhook, live reregister, playbook patch, draft create/patch/delete, handoff POST, settings PATCH. For /api/live/stream (SSE) only confirm it connects then disconnect immediately; do not hold open."
    -agent: "testing"
    -message: "READ-ONLY smoke test completed successfully. All 26 GET endpoints tested. 25/26 passed with 200 status codes and valid JSON responses. The /drafts endpoint requires opportunity_id query parameter by design (not a bug). All critical functionality verified: opportunities data retrieval (49 opportunities found), lanes (3 lanes), pipeline views, KPIs, settings, live status, SSE streaming, Slack integration status, message playbooks (3 playbooks), drafts queue, handoffs, and follow-ups. No write operations performed. Production Airtable data remains untouched. STRICT READ-ONLY constraint maintained. Backend API is fully operational."
