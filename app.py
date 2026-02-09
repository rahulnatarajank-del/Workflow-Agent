import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

# Load environment variables
load_dotenv()

# Get token from Streamlit secrets (cloud) or .env file (local)
try:
    # Try Streamlit Cloud secrets first
    if "HF_TOKEN" in st.secrets:
        hf_token = st.secrets["HF_TOKEN"]
    else:
        hf_token = None
except:
    # If secrets don't exist (local development), use .env
    hf_token = None

# Fallback to environment variable for local development
if not hf_token:
    hf_token = os.getenv("HF_TOKEN")

# Check if token exists BEFORE initializing client
if not hf_token:
    st.error("⚠️ HF_TOKEN not found! Please add it in Streamlit Cloud Settings.")
    st.info("""
    **To add your Hugging Face token:**
    1. Click 'Manage app' (bottom right)
    2. Go to 'Settings' → 'Secrets'
    3. Add this:
```
    HF_TOKEN = "your_hf_token_here"
```
    4. Click 'Save' and the app will restart
    """)
    st.stop()

# NOW initialize the client (only if token exists)
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=hf_token,
)

# Page config
st.set_page_config(
    page_title="HDC Workflow Agent",
    page_icon="🤖",
    layout="wide"
)

# Title
st.title("🤖 HDC Workflow Builder Agent")
st.markdown("*Your AI assistant for creating Health Data Connector workflows*")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": "Hello! I'm your HDC Workflow Builder assistant. I can help you create workflows to integrate health data between systems. What would you like to build today?"
    })

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

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
                # ENHANCED SYSTEM PROMPT WITH API RESPONSE TRANSFORMATION IN HTTPCALLSTEP INPUT
                system_prompt = {
                    "role": "system",
                    "content": """You are an expert assistant for Health Data Connector (HDC) workflows. You intelligently select and configure the appropriate workflow steps based on user requirements.

AVAILABLE STEP TYPES AND WHEN TO USE THEM:

1. **HL7TransformStep** - Use when:
   - User mentions "HL7 to JSON", "convert HL7", "parse HL7 message"
   - Need to transform HL7 message format to JSON
   - Requires: Data Transform configuration

2. **HttpCallStep** - Use when:
   - User mentions "call API", "fetch data from", "get data from endpoint"
   - Need to make HTTP request to external API
   - Can optionally transform the API response by adding transformId to step input
   - Requires: API configuration (and Template if POST/PUT with body, and Data Transform if response transformation needed)

3. **DeserializeObjectStep** - Use when:
   - Need to parse JSON string into object
   - Often follows HttpCallStep to convert response string to usable object
   - NOT needed if HttpCallStep has transformId in input (transformation handles deserialization)

4. **SetReturnDataStep** - Use when:
   - Final step to return data from workflow
   - Sets the output that will be returned when workflow completes

[REST OF YOUR SYSTEM PROMPT - KEEP ALL THE DETAILED INSTRUCTIONS YOU HAD]"""
                }

                messages = [system_prompt]
                messages.extend(st.session_state.messages)
                
                completion = client.chat.completions.create(
                    model="Qwen/Qwen2.5-Coder-32B-Instruct", 
                    messages=messages,
                    max_tokens=4000, 
                    temperature=0.2, 
                )
                
                assistant_response = completion.choices[0].message.content
                
                # Display response
                st.markdown(assistant_response)
                
                # Add to history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.info("Please check your Hugging Face token in the .env file")

# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown("""
    This AI agent helps you build HDC workflows by:
    - Understanding your requirements
    - Intelligently selecting workflow steps
    - Generating complete configurations
    - Creating production-ready JSONs
    
    **Supported Step Types:**
    - HL7TransformStep
    - HttpCallStep (with optional transformId in input)
    - DeserializeObjectStep
    - SetReturnDataStep
    
    **Supported Configurations:**
    - Workflows
    - APIs
    - Templates (request bodies)
    - Data Transforms (HL7 & API responses)
    
    **Supported Content Types:**
    - application/json
    - application/x-www-form-urlencoded
    - application/xml
    """)
    
    st.divider()
    
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.caption("POC Version 1.3 - API Response Transformation in HttpCallStep Input")