import streamlit as st
from groq import Groq
from dotenv import load_dotenv
import os
import re
import json
import requests

# Load environment variables
load_dotenv()

groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
hdc_base_url = st.secrets.get("HDC_BASE_URL") or os.getenv("HDC_BASE_URL")
hdc_api_key = st.secrets.get("HDC_API_KEY") or os.getenv("HDC_API_KEY")

# NOW initialize the client (only if token exists)
client = Groq(api_key=groq_api_key)

# HDC API headers
hdc_headers = {
    "Content-Type": "application/json",
    "x-api-key": hdc_api_key
}

def call_hdc_api(endpoint, payload):
    """Call HDC API and return success status and response"""
    try:
        url = f"{hdc_base_url}{endpoint}"
        response = requests.post(url, headers=hdc_headers, json=payload)
        
        if response.status_code in [200, 201, 204]:
            # Handle empty response body (still a success)
            if not response.text or response.text.strip() == "":
                return True, {"message": "Deployed successfully (no response body)"}
            try:
                return True, response.json()
            except Exception:
                return True, {"message": response.text}
        else:
            try:
                error_detail = response.json()
            except Exception:
                error_detail = response.text if response.text else "(empty response body)"
            return False, f"Status {response.status_code}: {error_detail}"
            
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection Error - Could not reach {url}. Detail: {str(e)}"
    except requests.exceptions.Timeout as e:
        return False, f"Timeout Error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected Error: {str(e)}"

def extract_json_blocks(text):
    """Extract all JSON blocks from assistant response"""
    pattern = r'```json\s*([\s\S]*?)\s*```'
    matches = re.findall(pattern, text)
    results = []
    for match in matches:
        try:
            parsed = json.loads(match)
            results.append(parsed)
        except:
            pass
    return results

def identify_config_type(config):
    """Identify what type of config a JSON block is"""
    if "workflowId" in config:
        return "workflow"
    elif "apiId" in config:
        return "api"
    elif "transformId" in config:
        return "transform"
    elif "applicationId" in config:
        return "application"
    elif "connectionId" in config:
        return "connection"
    return None

def deploy_configurations(configs):
    """Deploy all configurations to HDC and return results"""
    results = {}
    
    # Define endpoint mapping
    endpoint_map = {
        "application": "/api/v1/applications",
        "connection": "/api/v1/connections",
        "api": "/api/v1/apis",
        "transform": "/api/v1/transforms",
        "workflow": "/api/v1/workflows"
    }
    
    # Deploy in correct order: application → connection → api/transform → workflow
    order = ["application", "connection", "api", "transform", "workflow"]
    
    for config_type in order:
        if config_type in configs:
            endpoint = endpoint_map[config_type]
            success, response = call_hdc_api(endpoint, configs[config_type])
            results[config_type] = {
                "success": success,
                "response": response
            }
    
    return results

# Page config
st.set_page_config(
    page_title="HDC Workflow Agent",
    page_icon="🤖",
    layout="wide"
)

# Title
st.title("🤖 HDC Workflow Builder Agent")
st.markdown("*Your AI assistant for creating Health Data Connector workflows*")

# Initialize session state variables
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": """👋 Welcome to HDC Workflow Builder! I can help you create professional health data integration workflows. 

What type of workflow would you like to create today?

**1.** Call API and return raw response

**2.** Call API and transform the response  

**3.** Transform JSON to different formated JSON

**4.** Transform HL7 to JSON

Please select an option (1-4)"""
    })

if "workflow_type" not in st.session_state:
    st.session_state.workflow_type = None

if "workflow_name" not in st.session_state:
    st.session_state.workflow_name = None

if "last_configs" not in st.session_state:
    st.session_state.last_configs = {}

if "deploy_results" not in st.session_state:
    st.session_state.deploy_results = None

if "is_asking_questions" not in st.session_state:
    st.session_state.is_asking_questions = False

if "continue_to_workflow" not in st.session_state:
    st.session_state.continue_to_workflow = False

if "workflow_in_progress" not in st.session_state:
    st.session_state.workflow_in_progress = False

if "needs_connection" not in st.session_state:
    st.session_state.needs_connection = False

if "platform_type" not in st.session_state:
    st.session_state.platform_type = None

if "app_connection_deployed" not in st.session_state:
    st.session_state.app_connection_deployed = False

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# If user clicked Continue to Workflow, inject a trigger message automatically
if st.session_state.continue_to_workflow and not any(
    "workflow details" in m["content"].lower() and m["role"] == "assistant"
    for m in st.session_state.messages[-2:]
):
    trigger_message = "I want to continue to create the workflow now. Please ask me the workflow details."
    st.session_state.messages.append({"role": "user", "content": trigger_message})
    st.session_state.continue_to_workflow = False

    with st.chat_message("user"):
        st.markdown(trigger_message)

    with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    system_prompt_continue = """You are an expert assistant for Health Data Connector (HDC) workflows.
                    The user has already completed Application and Connection setup.
                    
                    Now ask them for workflow details in a SINGLE message following EXACTLY this format based on their workflow type:

                    For "Call API and return raw response", ask:
                    "Please provide the following details to configure your workflow:

                    **Workflow Details:**
                    1. Workflow name
                    2. API request method (GET / POST / PUT / DELETE)
                    3. API endpoint path (e.g., /patients/{patientId}?status={status}) — clearly indicate which are path params {} and which are query params ?key={value}

                    **Only if POST or PUT:**
                    4. Sample request body (as JSON)
                    5. Request content type

                    You can reply with all answers numbered."

                    For "Call API and transform the response", ask:
                    "Please provide the following details to configure your workflow:

                    **Workflow Details:**
                    1. Workflow name
                    2. API request method (GET / POST / PUT / DELETE)
                    3. API endpoint path (e.g., /patients/{patientId}?status={status}) — clearly indicate which are path params {} and which are query params ?key={value}

                    **Only if POST or PUT:**
                    4. Sample request body (as JSON)
                    5. Request content type

                    **Transformation Details:**
                    6. Sample raw API response (as JSON)
                    7. Desired output format (as JSON)

                    You can reply with all answers numbered."

                    CRITICAL: Always include Workflow name as question 1. Never deviate from these exact question formats."""
                    
                    messages_to_send = [{"role": "system", "content": system_prompt_continue}]
                    
                    if st.session_state.workflow_type:
                        messages_to_send.append({
                            "role": "system",
                            "content": f"The user selected workflow type: {st.session_state.workflow_type}"
                        })
                    
                    for msg in st.session_state.messages:
                        messages_to_send.append({"role": msg["role"], "content": msg["content"]})

                    completion = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=messages_to_send,
                        max_tokens=1000,
                        temperature=0.2,
                    )
                    response = completion.choices[0].message.content

                    if not isinstance(response, str) or not response:
                        response = "Please provide your workflow details so I can help you configure it."
                    
                    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

                    if not response:
                        response = "Please provide your workflow details so I can help you configure it."
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            st.rerun()

# Chat input
if prompt := st.chat_input("Describe the workflow you need..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # ENHANCED SYSTEM PROMPT WITH ATHENA/CERNER CONNECTION SUPPORT
                system_prompt = """You are an expert assistant for Health Data Connector (HDC) workflows. You follow a structured question flow based on the selected workflow type.

WORKFLOW TYPE DETECTION:
The user will select one of these workflow types:
1. "Call API and return raw response" - Simple API call without transformation
2. "Call API and transform the response" - API call with response transformation
3. "Transform JSON to different formated JSON" - Standalone JSON transformation without API
4. "Transform HL7 to JSON" - HL7 message transformation

CRITICAL: Detect which workflow type the user is referring to based on their messages. If they haven't selected a type yet, ask them to choose.

CONNECTION AND APPLICATION MANAGEMENT:

For Workflow Types 1 and 2 (API-based workflows), you MUST ask about Connection and Application setup BEFORE proceeding with API configuration questions.

**CONNECTION/APPLICATION QUESTION FLOW:**

1. First, ask: "Do you already have a Connection and Application configured for this API in HDC?"

2. If user says NO or wants to create new:
   a. Ask: "Which platform are you connecting to? (Athena or Cerner)"
   
   b. If platform is **Athena** or **Cerner**:
      - Proceed with Athena/Cerner Application & Connection creation flow (see below)
   
   c. If platform is **anything else** (Epic, OAuth2, etc.):
      - Respond: "Currently, we only support auto-generation for Athena and Cerner connections. For other platforms, please create the Connection and Application manually in your HDC configuration, then return here to continue with the workflow."
      - Wait for user to confirm they've created it manually
      - Then proceed with workflow questions

3. If user says YES (already have connection):
   - Skip connection/application creation
   - Proceed directly to workflow-specific questions

**ATHENA/CERNER APPLICATION & CONNECTION CREATION FLOW:**

When user wants to create Athena or Cerner connection, ask these questions IN ORDER (one at a time):

**Application & Connection Questions (Ask ALL at once in a single message):**

Send this single message asking everything together:

"To set up your [Athena/Cerner] Application and Connection, please provide the following details:

**Application Details:**
1. Organization name (used to generate IDs)
2. Secret ID from HDC Secret Manager (if you don't have one, go to HDC → Configuration → Secret Manager → Create New Secret, then provide only the Key/Secret ID here)
3. Client ID
4. Application type: Backend / ProviderLaunch / PatientLaunch
5. OAuth scopes (comma-separated, or leave empty if none)

**Connection Details:**
6. Base URL (e.g., https://api.preview.platform.athenahealth.com)
7. Environment: Dev / Test / Stage / Prod
8. Token endpoint URL (e.g., https://api.preview.platform.athenahealth.com/oauth2/v1/token)

You can reply with all answers numbered 1-8."

Wait for user to provide all 8 answers, then generate the Application and Connection JSONs.

**After collecting all Application & Connection info, generate:**

1. **Application JSON:**
```json
{
  "applicationId": "{Platform}-app-{organization}",
  "name": "{Platform}-app-{organization}",
  "appType": "{Backend|ProviderLaunch|PatientLaunch}",
  "clientId": "{user-client-id}",
  "clientSecretId": "{secret-id}",
  "scopes": ["{scope1}", "{scope2}"],
  "appInfo": {
    "privateKeyName": "{secret-id}",
    "basicAuthUserNameKey": "",
    "authSuccessWorkflowId": "",
    "authFailureWorkflowId": "",
    "clientId": "{user-client-id}",
    "isJkuOAuth": false,
    "keyContainerId": "",
    "scopes": ["{scope1}", "{scope2}"],
    "launchParameters": {}
  }
}
```

2. **Connection JSON:**
```json
{
  "connectionId": "{Platform}-con-{organization}",
  "baseUrl": "{user-base-url}",
  "env": "{Dev|Test|Stage|Prod}",
  "tokenEndPoint": "{user-token-endpoint}",
  "type": "{Athena|Cerner}",
  "applications": {
    "{Platform}-app-{organization}": {
      "privateKeyName": "{secret-id}",
      "basicAuthUserNameKey": "",
      "authSuccessWorkflowId": "",
      "authFailureWorkflowId": "",
      "clientId": "{user-client-id}",
      "isJkuOAuth": false,
      "keyContainerId": "",
      "scopes": ["{scope1}", "{scope2}"],
      "launchParameters": {}
    }
  }
}
```

**After generating Application & Connection, then proceed with workflow questions.**

STRUCTURED QUESTION FLOWS BY WORKFLOW TYPE:

**WORKFLOW TYPE 1: "Call API and return raw response"**
Ask ALL questions in a SINGLE message AFTER handling Connection/Application:

"Please provide the following details to configure your workflow:

**Workflow Details:**
1. Workflow name
2. API request method (GET / POST / PUT / DELETE)
3. API endpoint path (e.g., /patients/{patientId}?status={status}) — clearly indicate which are path params {} and which are query params ?key={value}

**Only if POST or PUT:**
4. Sample request body (as JSON)
5. Request content type 

You can reply with all answers numbered."

Wait for user to provide all answers, then generate all configurations at once.

CRITICAL:
- Do NOT ask questions one by one
- Do NOT display filler messages about skipped steps
- If user provides GET method, skip questions 4 and 5 silently without mentioning it

Then generate:
- Workflow JSON (HttpCallStep → DeserializeObjectStep → SetReturnDataStep)
- API Configuration JSON
- Template JSON (if POST/PUT)

**WORKFLOW TYPE 2: "Call API and transform the response"**
Ask ALL questions in a SINGLE message AFTER handling Connection/Application:

"Please provide the following details to configure your workflow:

**Workflow Details:**
1. Workflow name
2. API request method (GET / POST / PUT / DELETE)
3. API endpoint path (e.g., /patients/{patientId}?status={status}) — clearly indicate which are path params {} and which are query params ?key={value}

**Only if POST or PUT:**
4. Sample request body (as JSON)
5. Request content type 

**Transformation Details:**
6. Sample raw API response (as JSON)
7. Desired output format (as JSON)

You can reply with all answers numbered."

Wait for user to provide all answers, then generate all configurations at once.

CRITICAL: 
- Do NOT ask questions one by one for workflow configuration
- Do NOT display "Since you're using a GET request, there won't be a request body" or any similar filler messages
- Do NOT show step-by-step progress messages like "Step 5: Request Body"
- If user provides GET method, simply skip questions 4 and 5 silently without mentioning it
- Only ask for clarification if the user's response is genuinely ambiguous or missing required info

Then generate:
- Workflow JSON (HttpCallStep with transformId → SetReturnDataStep)
- API Configuration JSON
- Template JSON (if POST/PUT)
- Data Transform JSON

**WORKFLOW TYPE 3: "Transform JSON to different formated JSON"**
Ask ALL questions in a SINGLE message:

"Please provide the following details:

1. Workflow name
2. Input JSON sample
3. Desired output JSON format

You can reply with all answers numbered."

Wait for all answers, then generate configurations at once.

Then generate:
- Workflow JSON (DataTransformStep → SetReturnDataStep)
- Data Transform JSON

**WORKFLOW TYPE 4: "Transform HL7 to JSON"**
Ask ALL questions in a SINGLE message:

"Please provide the following details:

1. Workflow name
2. Sample HL7 message
3. Desired output JSON format

You can reply with all answers numbered."

Wait for all answers, then generate configurations at once.

Then generate:
- Workflow JSON (HL7TransformStep → SetReturnDataStep)
- Data Transform JSON

AVAILABLE STEP TYPES AND WHEN TO USE THEM:

1. **HL7TransformStep** - Use for Workflow Type 4
   - Transforms HL7 message format to JSON
   - Requires: Data Transform configuration

2. **DataTransformStep** - Use for Workflow Type 3
   - Transforms JSON data to different JSON format
   - CRITICAL: This is for STANDALONE data transformation (not combined with API calls)
   - Requires: Data Transform configuration

3. **HttpCallStep** - Use for Workflow Types 1 and 2
   - Makes HTTP request to external API
   - For Type 2: Add transformId to step input for response transformation
   - Requires: API configuration (and Template if POST/PUT with body)

4. **DeserializeObjectStep** - Use for Workflow Type 1
   - Parses JSON string into object
   - Follows HttpCallStep to convert response string to usable object
   - NOT needed if HttpCallStep has transformId (Type 2)

5. **SetReturnDataStep** - Use for ALL workflow types
   - Final step to return data from workflow

CONFIGURATION STRUCTURES:

**1. WORKFLOW JSON:**
{
  "workflowId": "{ProjectName}-WF",
  "description": "{Clear description}",
  "steps": [
    {
      "workflowStepId": "{unique-id}",
      "name": "{Human readable name}",
      "stepType": "{StepType}",
      "sequence": {0, 1, 2...},
      "input": {...},
      "output": {...},
      "redirect": {"baseUrl": "", "queryParameters": {}},
      "runRules": [],
      "validationRules": []
    }
  ]
}

**2. API CONFIGURATION JSON:**

**CRITICAL CONTENT TYPE RULES:**
- If user does NOT specify contentType, ALWAYS default to "application/json"
- If user does NOT specify acceptContentType, ALWAYS default to "application/json"
- Only use other content types (application/x-www-form-urlencoded, application/xml, application/fhir+json) if user explicitly specifies them
- For GET and DELETE requests: contentType is still "application/json" (no request body)

CRITICAL PATH PARAMETER RULES:
- apiPath contains ONLY the FIRST segment of the path (remove leading /)
- ALL REMAINING segments (both dynamic and literal) go in pathParameters array IN ORDER
- pathParameters builds the rest of the URL path after apiPath
- If the path is just a single segment (e.g., /patients), apiPath gets that segment and pathParameters is EMPTY []

CRITICAL: When a path has a literal segment followed by a dynamic value (e.g., patientname/{patientname}), you MUST create TWO separate entries:
1. First entry: the literal segment with valueType "Literal"
2. Second entry: the dynamic param with valueType "Value"

Example: /patients/{patientid}/patientname/{patientname}
{
  "apiPath": "patients",
  "pathParameters": [
    {"value": "patientid", "valueType": "Value"},
    {"value": "patientname", "valueType": "Literal"},
    {"value": "patientname", "valueType": "Value"}
  ]
}

Example: /patients/{patientid}/appointments/{appointmentid}
{
  "apiPath": "patients",
  "pathParameters": [
    {"value": "patientid", "valueType": "Value"},
    {"value": "appointments", "valueType": "Literal"},
    {"value": "appointmentid", "valueType": "Value"}
  ]
}

NEVER merge a literal segment and a dynamic segment into one entry.
ALWAYS check if a dynamic param is preceded by a same-named or different literal segment and split them accordingly.

Examples of apiPath extraction:
- "/patients" → apiPath: "patients", pathParameters: []
- "/patients/{patientid}/chat" → apiPath: "patients", pathParameters: [{patientid}, {chat}]
- "/v1/departments" → apiPath: "v1", pathParameters: [{departments}]
- "/appointments" → apiPath: "appointments", pathParameters: []

{
  "apiId": "{ProjectName}-API",
  "name": "{Descriptive API name}",
  "headerParameters": {},
  "dataFormat": "Json",
  "apiPath": "{base-path-only}",
  "requestMethod": "{GET|POST|PUT|DELETE}",
  "queryParameters": [
    {
      "key": "{parameterName}",
      "value": "{parameterName}",
      "operator": "",
      "optional": false,
      "valueType": "Value"
    }
  ],
  "bodyTemplateId": "{ProjectName}-Tem",
  "contentType": "application/json",
  "acceptContentType": "application/json",
  "pageJsonPath": "",
  "customHeaders": [],
  "pathParameters": [
    {
      "value": "{paramValue or literal segment}",
      "valueType": "{Value|Literal}"
    }
  ],
  "shouldUrlEncodeParameters": false
}

PATH PARAMETER RULES:
- apiPath = first segment only, no leading /
- All remaining segments go in pathParameters IN ORDER
- Dynamic segments: valueType "Value", Static segments: valueType "Literal"
- Literal segment followed by same-named dynamic = TWO entries (Literal first, then Value)
- /patients → apiPath: "patients", pathParameters: []
- /patients/{id}/appointments/{apptid} → apiPath: "patients", pathParameters: [{id,Value},{appointments,Literal},{apptid,Value}]
- /patient/{id}/patientname/{patientname} → apiPath: "patient", pathParameters: [{id,Value},{patientname,Literal},{patientname,Value}]

CRITICAL QUERY PARAMETER RULES:
- The "key" is the query parameter name as it appears in the URL (e.g., "patientage")
- The "value" must ALWAYS be the same as "key" (never empty)
- valueType is always "Value" for dynamic query parameters

**3. TEMPLATE JSON (for Request Body):**

CRITICAL: Template format MUST match the contentType from API Configuration!

**For contentType = "application/x-www-form-urlencoded":**
{
  "templateId": "{ProjectName}-Tem",
  "templateBody": "key1=value1&key2=%token2%&key3=%token3%",
  "escapeTokens": "None",
  "defaultTokenValue": "",
  "throwTokenException": true
}

Example:
{
  "templateId": "Athena-Create-Patient-Tem",
  "templateBody": "departmentid=180&firstname=%firstname%&lastname=%lastname%&dob=%dob%&homephone=%homephone%&mobilephone=%mobilephone%&email=%email%&address1=%address1%&address2=%address2%&city=%city%&state=%state%&zipcode=%zipcode%&workphone=%workphone%",
  "escapeTokens": "None",
  "defaultTokenValue": "",
  "throwTokenException": true
}

**For contentType = "application/json":**
{
  "templateId": "{ProjectName}-Tem",
  "templateBody": "{\"field1\": \"%token1%\", \"field2\": \"%token2%\", \"nested\": {\"field3\": \"%token3%\"}}",
  "escapeTokens": "Json",
  "defaultTokenValue": "",
  "throwTokenException": false
}

**For contentType = "application/xml":**
{
  "templateId": "{ProjectName}-Tem",
  "templateBody": "<Root><Field1>%token1%</Field1><Field2>%token2%</Field2></Root>",
  "escapeTokens": "Xml",
  "defaultTokenValue": "",
  "throwTokenException": false
}

**For contentType = "application/fhir+json":**
{
  "templateId": "{ProjectName}-Tem",
  "templateBody": "{\"resourceType\": \"%resourceType%\", \"field1\": \"%token1%\", \"field2\": \"%token2%\"}",
  "escapeTokens": "Json",
  "defaultTokenValue": "",
  "throwTokenException": false
}

**CRITICAL Template Rules by Content Type:**

1. **application/x-www-form-urlencoded:**
   - Format: key1=value1&key2=value2&key3=value3
   - escapeTokens: "None"
   - throwTokenException: true
   - All on one line, parameters separated by &

2. **application/json:**
   - Format: Valid JSON string with escaped quotes
   - escapeTokens: "Json"
   - throwTokenException: false
   - Entire JSON must be on one line with escaped quotes: {\"key\": \"value\"}

3. **application/xml:**
   - Format: Valid XML string
   - escapeTokens: "Xml"
   - throwTokenException: false

4. **application/fhir+json:**
   - Format: Valid FHIR JSON string with escaped quotes (same structure as application/json but for FHIR resources)
   - escapeTokens: "Json"
   - throwTokenException: false
   - Entire JSON must be on one line with escaped quotes: {\"resourceType\": \"Patient\", \"field\": \"%token%\"}
   - Used specifically for FHIR-compliant API requests

**4. DATA TRANSFORM JSON:**

CRITICAL ARRAY HANDLING RULES:
- NEVER create separate propertyGroups for each array index (e.g., [0], [1], [2])
- When the source data contains an array, use a SINGLE propertyGroup with:
  - "key": the output array field name (e.g., "patients")
  - "locator": the JSONPath to the source array (e.g., "$.patients")
  - Inside "properties": use paths RELATIVE to each array item (e.g., "$.name" not "$.patients[0].name")
- The locator automatically iterates over all array items

Example for ARRAY transformation:
{
  "transformId": "{ProjectName}-DT",
  "propertyGroups": [
    {
      "key": "patients",
      "locator": "$.patients",
      "propertyGroups": [],
      "properties": {
        "fullName": {
          "path": "$.name",
          "value": "",
          "map": "",
          "mapDefault": "",
          "valueType": "Path",
          "formatType": "FirstItem",
          "dateFormat": {"inputFormat": "", "outputFormat": "", "throwExceptions": false},
          "stringFormat": {"mappings": {}, "regularExpression": "", "replacement": "", "defaultMapping": "", "throwExceptions": false},
          "propertyGroups": [],
          "properties": {},
          "delimiter": ""
        }
      }
    }
  ]
}

Example for FLAT (non-array) transformation:
{
  "transformId": "{ProjectName}-DT",
  "propertyGroups": [
    {
      "key": "",
      "locator": "",
      "propertyGroups": [],
      "properties": {
        "OUTPUT_FIELD_NAME": {
          "path": "$.path.to.source.field",
          "value": "",
          "map": "",
          "mapDefault": "",
          "valueType": "Path",
          "formatType": "FirstItem",
          "dateFormat": {"inputFormat": "", "outputFormat": "", "throwExceptions": false},
          "stringFormat": {"mappings": {}, "regularExpression": "", "replacement": "", "defaultMapping": "", "throwExceptions": false},
          "propertyGroups": [],
          "properties": {},
          "delimiter": ""
        }
      }
    }
  ]
}

**Valid formatType Values:**
- "FirstItem" - Use this as the default for most fields
- DO NOT use "Array" - this is not a valid formatType value

**JSONPath Guidelines:**
- Root always starts with $
- Array access: $.array[0] for first item
- Filter: $.array[?(@.key=='value')] to find items matching condition
- Nested: $.level1.level2.level3

**CRITICAL OUTPUT VALUE RULES - MUST NEVER CHANGE:**

For HttpCallStep:
- output value MUST ALWAYS be "ResponseData" (never "RawResponse", "ApiResponse", or any other name)
- Correct: "rawApiResponse": "ResponseData"
- Wrong: "rawApiResponse": "RawResponse"

For DeserializeObjectStep:
- output value MUST ALWAYS be "OutputObject" (never "PractitionerData", "DeserializedData", or any other name)
- Correct: "deserializedData": "OutputObject"
- Wrong: "deserializedData": "PractitionerData"

For DataTransformStep:
- output value MUST ALWAYS be "TransformedData"
- Correct: "transformedData": "TransformedData"
- Wrong: "transformedData": "TransformedObject"

For HL7TransformStep:
- output value MUST ALWAYS be "TransformedData"
- Correct: "transformedData": "TransformedData"
- Wrong: "transformedData": "HL7Output"

These are FIXED system values that cannot be changed regardless of the workflow context.

STEP-SPECIFIC INPUT/OUTPUT PATTERNS:

**HL7TransformStep:**
{
  "stepType": "HL7TransformStep",
  "input": {
    "consistentArray": "true",
    "transformId": "{ProjectName}-HL7-DT",
    "transformDataInput": "$Body"
  },
  "output": {
    "transformedData": "TransformedData"
  }
}

**DataTransformStep:**
{
  "stepType": "DataTransformStep",
  "input": {
    "transformDataInput": "Body",
    "transformId": "{ProjectName}-DT"
  },
  "output": {
    "transformedData": "TransformedData"
  }
}

**HttpCallStep (WITHOUT response transformation):**
{
  "stepType": "HttpCallStep",
  "input": {
    "apiId": "{ProjectName}-API"
  },
  "output": {
    "rawApiResponse": "ResponseData"
  },
  "redirect": {"baseUrl": "", "queryParameters": {}},
  "runRules": [],
  "validationRules": []
}

CRITICAL: The output key "rawApiResponse" must be passed to the next step's input using the KEY name, not the value.

**HttpCallStep (WITH response transformation):**
{
  "stepType": "HttpCallStep",
  "input": {
    "apiId": "{ProjectName}-API",
    "transformId": "{ProjectName}-Response-DT"
  },
  "output": {
    "transformedData": "TransformedData",
    "rawApiResponse": "ResponseData"
  },
  "redirect": {"baseUrl": "", "queryParameters": {}},
  "runRules": [],
  "validationRules": []
}

CRITICAL: The output keys "transformedData" and "rawApiResponse" must be passed to the next step's input using the KEY names, not the values.

**DeserializeObjectStep:**
{
  "stepType": "DeserializeObjectStep",
  "input": {
    "data": "{outputKeyFromPreviousStep}"
  },
  "output": {
    "deserializedData": "OutputObject"
  },
  "redirect": {"baseUrl": "", "queryParameters": {}},
  "runRules": [],
  "validationRules": []
}

CRITICAL: 
- The input "data" field should reference the OUTPUT KEY from the previous step (e.g., "rawApiResponse"), NOT the output value.
- The output key "deserializedData" must be passed to the next step's input using the KEY name, not the value "OutputObject".

**SetReturnDataStep:**
{
  "stepType": "SetReturnDataStep",
  "input": {
    "{Descriptive Label}": "{outputKeyFromPreviousStep}"
  },
  "output": {},
  "redirect": {"baseUrl": "", "queryParameters": {}},
  "runRules": [],
  "validationRules": []
}

CRITICAL: The input value should reference the OUTPUT KEY from the previous step (e.g., "deserializedData" or "transformedData"), NOT the output value.

HL7 PATH EXTRACTION RULES:
- All paths start with: $.GenericMessageWrapper
- MSH simple fields: MSH[0].3[0], MSH[0].4[0], MSH[0].5[0]
- MSH timestamp: MSH[0].7[0].1
- MSH message type: MSH[0].9[0].1, MSH[0].9[0].2
- PID simple: PID[0].8[0] (gender), PID[0].19[0] (SSN)
- PID ID: PID[0].3[0].1
- PID name: PID[0].5[0].1.1 (last), PID[0].5[0].2 (first), PID[0].5[0].3 (middle)
- PID DOB: PID[0].7[0].1
- PID address: PID[0].11[0].1.1 (street), PID[0].11[0].3 (city), PID[0].11[0].4 (state), PID[0].11[0].5 (zip)
- PID phone: PID[0].13[0].1
- PID email: PID[0].13[0].4

USER INTERACTION GUIDELINES:

1. **Workflow Type Selection:**
   - If user hasn't indicated workflow type, ask them to choose from the 4 types
   - Be clear and concise when presenting options

2. **Connection/Application Flow (for Types 1 & 2):**
   - ALWAYS ask about existing connection first
   - If creating new, determine platform and proceed accordingly
   - For Athena/Cerner: Follow the complete application & connection question flow
   - For other platforms: Inform user to create manually and confirm when ready

3. **Question Flow:**
   - NEVER skip questions and jump directly to generating templates
   - ALWAYS ask questions ONE AT A TIME in the exact order specified
   - WAIT for the user's answer before proceeding to the next question
   - Follow the exact question order for the selected workflow type
   - DO NOT generate any configurations until ALL required questions have been answered
   - Be conversational and friendly
   - After the LAST question is answered, THEN generate the complete configurations

4. **Information Gathering:**
   - For API paths: Extract path parameters correctly into pathParameters array
   - For request bodies: Identify fields that need to become tokens
   - For transformations: Carefully analyze input and output structures to create accurate JSONPath mappings

5. **Configuration Generation:**
   - Only generate configs after ALL required questions are answered
   - For Athena/Cerner: Generate Application JSON, Connection JSON, then Workflow configs
   - Use the workflow name provided by the user in all IDs
   - Ensure all variable chaining is correct
   - Verify formatType is always "FirstItem" (never "Array")

SAMPLE INPUT GENERATION:

After generating all configurations, ALWAYS provide a sample input payload at the end showing all dynamic parameters that need to be passed at runtime.

The format must be:
{
  "payloadParams": {
    "paramName": "sampleValue"
  }
}

Include in payloadParams:
- All path parameters that have valueType "Value" (dynamic segments in the URL)
- All query parameters that have valueType "Value" (dynamic query params)
- All template tokens from the request body (fields wrapped in %token%)
- For DataTransformStep and HL7TransformStep: all dynamic input fields expected in $Body

Use realistic sample values based on the parameter names (e.g., patientid: "12345", firstname: "John", dob: "1990-01-01").

OUTPUT FORMAT:

For Athena/Cerner workflows (Types 1 & 2):
---
## Application Configuration
```json
{application json}
```

## Connection Configuration
```json
{connection json}
```

## Workflow Configuration
```json
{workflow json}
```

## API Configuration
```json
{api json}
```

## Template Configuration (for Request Body)
```json
{template json - only for POST/PUT}
```

## Data Transform Configuration
```json
{transform json - only for Type 2}
```
---

For non-API workflows (Types 3 & 4):
---
## Workflow Configuration
```json
{workflow json}
```

## Data Transform Configuration
```json
{transform json}
```
---

**CRITICAL VARIABLE CHAINING RULES:**
1. Each step's output defines KEY-VALUE pairs
2. The next step's input references the previous step's output KEY (not the value)
3. Example chain:
   - Step 1 output: {"rawApiResponse": "ResponseData"} 
   - Step 2 input: {"data": "rawApiResponse"} ← Uses the KEY
   - Step 2 output: {"deserializedData": "OutputObject"}
   - Step 3 input: {"Result": "deserializedData"} ← Uses the KEY
4. NEVER use the output VALUE (like "ResponseData" or "OutputObject") in the next step's input
5. ALWAYS use the output KEY (like "rawApiResponse" or "deserializedData") in the next step's input

CRITICAL RULES:
- NEVER generate configs until ALL questions are answered
- Generate complete, ready-to-use JSONs only
- For API workflows (Types 1 & 2): ALWAYS handle Connection/Application setup FIRST
- Only auto-generate Application & Connection for Athena and Cerner
- For Application & Connection: Ask ALL questions in a single message
- For workflow questions: Ask ALL at once in a single message
- Never show step labels or filler messages
- apiPath is ONLY the first path segment (no leading /)
- pathParameters must include ALL remaining segments in order
- Template format MUST match contentType
- formatType must always be "FirstItem"
- HttpCallStep with transformId returns TWO outputs
- NEVER index arrays manually in Data Transform, use locator
- Property paths inside locator are relative to each array item
- query param key and value must always be the same
- Application: {Platform}-app-{organization}, Connection: {Platform}-con-{organization}
- Secret ID used in both clientSecretId and privateKeyName
- ALWAYS end Application/Connection generation with ONLY: "Your Application and Connection configurations are ready. Please use the buttons below to either deploy now or continue to workflow setup."
- NEVER ask workflow questions after generating Application/Connection configs
- Only ask workflow questions when user explicitly requests to continue to workflow """

                messages = [{"role": "system", "content": system_prompt}]
                
                # Add workflow type context if selected
                if st.session_state.workflow_type:
                    context_message = {
                        "role": "system",
                        "content": f"The user has selected workflow type: {st.session_state.workflow_type}. Follow the question flow for this type."
                    }
                    messages.append(context_message)
                
                # Add platform context if selected
                if st.session_state.platform_type:
                    context_message = {
                        "role": "system",
                        "content": f"The user is connecting to platform: {st.session_state.platform_type}."
                    }
                    messages.append(context_message)
                
                # Add workflow name context if provided
                if st.session_state.workflow_name:
                    context_message = {
                        "role": "system",
                        "content": f"The workflow name is: {st.session_state.workflow_name}"
                    }
                    messages.append(context_message)
                
                # Convert session messages to Groq format
                for msg in st.session_state.messages:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
                
                completion = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=messages,
                    max_tokens=4000,
                    temperature=0.2,
                )
                
                # Safely extract response
                if not completion or not completion.choices or len(completion.choices) == 0:
                    assistant_response = "I'm sorry, I didn't get a response. Please try again."
                elif completion.choices[0].message is None:
                    assistant_response = "I'm sorry, the response was empty. Please try again."
                elif completion.choices[0].message.content is None:
                    # Sometimes model returns tool calls or empty content
                    assistant_response = "I'm sorry, I didn't receive a valid response. Please try again."
                else:
                    assistant_response = completion.choices[0].message.content

                if not isinstance(assistant_response, str):
                    assistant_response = "I'm sorry, I didn't receive a valid response. Please try again."
                else:
                    assistant_response = re.sub(r'<think>.*?</think>', '', assistant_response, flags=re.DOTALL).strip()
                    if not assistant_response:
                        assistant_response = "I'm sorry, I didn't get a response. Please try again."
                
                # Detect workflow type selection from user's message
                user_msg_lower = prompt.lower()
                if not st.session_state.workflow_type:
                    if "raw response" in user_msg_lower or "option 1" in user_msg_lower or "type 1" in user_msg_lower:
                        st.session_state.workflow_type = "Call API and return raw response"
                        st.session_state.needs_connection = True
                    elif "transform the response" in user_msg_lower or "option 2" in user_msg_lower or "type 2" in user_msg_lower:
                        st.session_state.workflow_type = "Call API and transform the response"
                        st.session_state.needs_connection = True
                    elif "transform json" in user_msg_lower or "option 3" in user_msg_lower or "type 3" in user_msg_lower:
                        st.session_state.workflow_type = "Transform JSON to different formated JSON"
                        st.session_state.needs_connection = False
                    elif "transform hl7" in user_msg_lower or "hl7 to json" in user_msg_lower or "option 4" in user_msg_lower or "type 4" in user_msg_lower:
                        st.session_state.workflow_type = "Transform HL7 to JSON"
                        st.session_state.needs_connection = False
                
                # Detect platform type
                if st.session_state.needs_connection and not st.session_state.platform_type:
                    if "athena" in user_msg_lower:
                        st.session_state.platform_type = "Athena"
                    elif "cerner" in user_msg_lower:
                        st.session_state.platform_type = "Cerner"
                
                # Detect workflow name from user's message
                if not st.session_state.workflow_name and "workflow name" in assistant_response.lower():
                    # Next user message will likely contain the workflow name
                    pass
                elif not st.session_state.workflow_name and len(st.session_state.messages) > 2:
                    # Try to extract workflow name from context
                    for msg in reversed(st.session_state.messages):
                        if msg["role"] == "assistant" and "workflow name" in msg["content"].lower():
                            # The next user message should be the workflow name
                            user_msgs = [m for m in st.session_state.messages if m["role"] == "user"]
                            if user_msgs:
                                potential_name = user_msgs[-1]["content"].strip()
                                if len(potential_name) < 50 and not potential_name.startswith("{"):
                                    st.session_state.workflow_name = potential_name
                            break
                
                # Display response
                override = st.session_state.get("messages_override")
                st.session_state.messages_override = None
                display_response = override if override is not None else assistant_response
                st.markdown(display_response)
                assistant_response = display_response
                
                # Extract and store configs from response
                extracted = extract_json_blocks(assistant_response)
                for config in extracted:
                    config_type = identify_config_type(config)
                    if config_type:
                        st.session_state.last_configs[config_type] = config

                # Check what types of configs were just generated in this response
                just_generated_configs = len(extracted) > 0
                just_generated_types = [identify_config_type(c) for c in extracted]
                only_app_connection = just_generated_configs and all(
                    t in ["application", "connection"] for t in just_generated_types if t
                )

                # If workflow config was just generated, workflow is complete
                if "workflow" in just_generated_types:
                    st.session_state.workflow_in_progress = False

                # If ONLY application/connection were just generated, strip everything after configs
                if only_app_connection:
                    closing_marker = "```"
                    last_code_block = assistant_response.rfind(closing_marker)
                    if last_code_block != -1:
                        assistant_response = assistant_response[:last_code_block + len(closing_marker)]
                    assistant_response += "\n\n✅ Your Application and Connection configurations are ready. Please use the buttons below to either deploy now or continue to workflow setup."
                    st.session_state.is_asking_questions = False
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": assistant_response
                    })
                    st.rerun()
                elif just_generated_configs:
                    st.session_state.is_asking_questions = False
                elif not st.session_state.last_configs:
                    st.session_state.is_asking_questions = True
                else:
                    st.session_state.is_asking_questions = False

                # Add to history for all non-rerun cases
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.info("Please check your Groq API key configuration")

# Show deployment success message in chat area if just deployed app/connection
if st.session_state.get("app_connection_deployed") and not st.session_state.get("workflow_in_progress"):
    st.success("✅ Application & Connection successfully deployed! Proceeding to workflow setup...")
    st.session_state.app_connection_deployed = False
    st.session_state.continue_to_workflow = True
    st.session_state.workflow_in_progress = True
    st.rerun()

# Show Deploy section
if st.session_state.last_configs and not st.session_state.is_asking_questions:

    has_app_or_connection = any(k in st.session_state.last_configs for k in ["application", "connection"])
    has_workflow = "workflow" in st.session_state.last_configs

    # Show app/connection buttons only when workflow is NOT yet created
    if has_app_or_connection and not has_workflow and not st.session_state.get("workflow_in_progress", False):
        st.divider()
        st.subheader("🚀 Deploy to HDC")
        st.write("The following configurations are ready:")
        for config_type in st.session_state.last_configs:
            st.write(f"✅ {config_type.capitalize()} configuration ready")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Deploy Application & Connection Now", type="secondary"):
                partial_configs = {k: v for k, v in st.session_state.last_configs.items() if k in ["application", "connection"]}
                with st.spinner("Deploying Application & Connection to HDC..."):
                    results = deploy_configurations(partial_configs)
                    all_success = all(r["success"] for r in results.values())
                    if all_success:
                        st.session_state.last_configs = {k: v for k, v in st.session_state.last_configs.items() if k not in ["application", "connection"]}
                        st.session_state.app_connection_deployed = True
                    else:
                        st.session_state.deploy_results = results
                st.rerun()
        with col2:
            if st.button("Continue to Workflow First", type="primary"):
                st.session_state.continue_to_workflow = True
                st.session_state.workflow_in_progress = True
                st.rerun()

        if st.session_state.deploy_results:
            st.subheader("📊 Deployment Results")
            for config_type, result in st.session_state.deploy_results.items():
                if result["success"]:
                    st.success(f"✅ {config_type.capitalize()} - Successfully deployed")
                else:
                    st.error(f"❌ {config_type.capitalize()} - Failed")
                    st.code(str(result["response"]), language="text")

    # Show full deploy button only when workflow is ready
    elif has_workflow:
        st.divider()
        st.subheader("🚀 Deploy to HDC")
        st.write("The following configurations are ready:")
        for config_type in st.session_state.last_configs:
            st.write(f"✅ {config_type.capitalize()} configuration ready")

        if st.button("Deploy All Configurations to HDC", type="primary"):
            with st.spinner("Deploying all configurations to HDC..."):
                results = deploy_configurations(st.session_state.last_configs)
                st.session_state.deploy_results = results

        if st.session_state.deploy_results:
            st.subheader("📊 Deployment Results")
            for config_type, result in st.session_state.deploy_results.items():
                if result["success"]:
                    st.success(f"✅ {config_type.capitalize()} - Successfully deployed")
                else:
                    st.error(f"❌ {config_type.capitalize()} - Failed")
                    st.code(str(result["response"]), language="text")

# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown("""
    This AI agent helps you build HDC workflows by:
    - Guiding you through structured questions
    - Intelligently selecting workflow steps
    - Generating complete configurations
    - Creating production-ready JSONs
    
    **Supported Workflow Types:**
    1. Call API and return raw response
    2. Call API and transform the response
    3. Transform JSON to different formated JSON
    4. Transform HL7 to JSON
    
    **Supported Platforms (Auto-generation):**
    - ✅ Athena (Application & Connection)
    - ✅ Cerner (Application & Connection)
    - ℹ️ Other platforms: Manual setup required
    
    **Supported Step Types:**
    - HL7TransformStep
    - DataTransformStep
    - HttpCallStep
    - DeserializeObjectStep
    - SetReturnDataStep
    
    **Supported Content Types:**
    - application/json
    - application/x-www-form-urlencoded
    - application/xml
    """)
    
    st.divider()
    
    # Show current workflow context
    if st.session_state.workflow_type:
        st.info(f"**Workflow Type:** {st.session_state.workflow_type}")
    if st.session_state.platform_type:
        st.success(f"**Platform:** {st.session_state.platform_type}")
    if st.session_state.workflow_name:
        st.success(f"**Project:** {st.session_state.workflow_name}")
    if st.session_state.needs_connection:
        st.warning("**Requires:** Connection & Application")
    
    st.divider()
    
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.workflow_type = None
        st.session_state.workflow_name = None
        st.session_state.needs_connection = False
        st.session_state.platform_type = None
        st.session_state.last_configs = {}
        st.session_state.deploy_results = None
        st.session_state.continue_to_workflow = False
        st.session_state.workflow_in_progress = False
        st.session_state.messages.append({
            "role": "assistant",
            "content": """👋 Welcome to HDC Workflow Builder! I can help you create professional health data integration workflows. 

What type of workflow would you like to create today?

**1.** Call API and return raw response

**2.** Call API and transform the response  

**3.** Transform JSON to different formated JSON

**4.** Transform HL7 to JSON

Please select an option (1-4)"""
        })
        st.rerun()
    
    st.divider()
    st.caption("POC Version 3.0 - With Athena/Cerner Connection Support")