import os
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime
import glob

# Set page config
st.set_page_config(
    page_title="KYB Due Diligence Tool",
    page_icon="🔍",
    layout="wide"
)

# App title and description
st.title("Know Your Business (KYB) Due Diligence Tool")
st.markdown("""
This application helps you perform KYB due diligence by gathering information about a company
from various sources and presenting it in a structured format.
""")

# Admin login state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    # Model selection with all Groq models
    model_options = {
        "Distil-Whisper Large V3 (English)": "distil-whisper-large-v3-en",
        "Gemma2 9B IT": "gemma2-9b-it",
        "LLaMA 3.3 70B Versatile": "llama-3.3-70b-versatile",
        "LLaMA 3.1 8B Instant": "llama-3.1-8b-instant",
        "LLaMA Guard 3 8B": "llama-guard-3-8b",
        "LLaMA3 70B 8192": "llama3-70b-8192",
        "LLaMA3 8B 8192": "llama3-8b-8192",
        "Whisper Large V3": "whisper-large-v3",
        "Whisper Large V3 Turbo": "whisper-large-v3-turbo",
        # Preview Models
        "PlayAI TTS": "playai-tts",
        "PlayAI TTS Arabic": "playai-tts-arabic",
        "Qwen QWQ 32B": "qwen-qwq-32b",
        "Mistral Saba 24B": "mistral-saba-24b",
        "Qwen 2.5 Coder 32B": "qwen-2.5-coder-32b",
        "Qwen 2.5 32B": "qwen-2.5-32b",
        "DeepSeek R1 Distill Qwen 32B": "deepseek-r1-distill-qwen-32b",
        "DeepSeek R1 Distill LLaMA 70B": "deepseek-r1-distill-llama-70b",
        "LLaMA 3.3 70B SpecDec": "llama-3.3-70b-specdec",
        "LLaMA 3.2 1B Preview": "llama-3.2-1b-preview",
        "LLaMA 3.2 3B Preview": "llama-3.2-3b-preview",
        "LLaMA 3.2 11B Vision Preview": "llama-3.2-11b-vision-preview",
        "LLaMA 3.2 90B Vision Preview": "llama-3.2-90b-vision-preview"
    }
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()), help="Choose the model to generate the report. Preview models are for evaluation only.")
    
    # API key input
    api_key = st.text_input("Enter your Groq API Key", type="password")
    
    # API key signup link
    st.markdown("[Generate Groq API Key](https://console.groq.com/keys)")
    
    # Company inputs (optional)
    company_name = st.text_input("Company Name (Optional)", "Brain Corp", help="Leave blank if using prompt only.")
    company_website = st.text_input("Company Website (Optional)", "https://www.braincorp.com", help="Leave blank if using prompt only.")
    
    # Prompt input field
    custom_prompt = st.text_area(
        "Special Instructions", 
        "Only include companies with founder ownership",  # Default example
        help="Examples: 'Only include companies with founder ownership', 'Focus on European subsidiaries'"
    )
    
    # Edit mode toggle
    edit_mode = st.checkbox("Enable Edit Mode", help="Manually correct report data")
    
    run_button = st.button("Generate KYB Report", type="primary")
    
    # Admin login button
    st.markdown("---")
    st.subheader("Admin Access")
    admin_login_button = st.button("Admin Login")

# Function definitions
def generate_kyb_report(company_name, company_website, api_key, model, u_user_prompt=None):
    """Uses selected Groq model to generate a KYB report."""
    client = Groq(api_key=api_key)
    
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website (or a custom prompt), gather and summarize: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and public risk indicators. Output ONLY a valid JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "For beneficial_owners, provide an array of objects with name and ownership_percentage when available. "
        "DO NOT include any explanatory text outside the JSON object. "
        "Ensure the response is properly formatted JSON that can be parsed by json.loads()."
    )
    
    user_prompt = ""
    if company_name and company_website:
        user_prompt = (
            f"Company Name: {company_name}\nWebsite: {company_website}\n\n"
            f"Please research {company_name} and provide all available information in JSON format. "
            f"Pay special attention to beneficial owners (with ownership percentages if available) "
            f"and risk indicators (e.g., regulatory issues, legal disputes, negative news, financial concerns). "
            f"If specific data points are not publicly available, use 'Not publicly available'."
        )
    else:
        user_prompt = "Please provide KYB due diligence information based on the following instructions:\n"
    
    if u_user_prompt:
        user_prompt += f"\n\nADDITIONAL REQUIREMENTS:\n{u_user_prompt}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with st.spinner(f"Generating KYB report using {selected_model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.3,
                top_p=1,
                max_tokens=1024
            )
        output_text = response.choices[0].message.content
    except Exception as e:
        st.error(f"Error during API call: {e}")
        return None
    
    json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
    if json_match:
        output_text = json_match.group(1)
    
    try:
        kyb_report = json.loads(output_text)
        
        if isinstance(kyb_report.get('beneficial_owners'), str):
            if kyb_report['beneficial_owners'] == "Not publicly available":
                kyb_report['beneficial_owners'] = []
            else:
                kyb_report['beneficial_owners'] = [{"name": kyb_report['beneficial_owners'], "ownership_percentage": "Unknown"}]
        
        if isinstance(kyb_report.get('risk_indicators'), str):
            if kyb_report['risk_indicators'] == "Not publicly available":
                kyb_report['risk_indicators'] = []
            else:
                kyb_report['risk_indicators'] = [item.strip() for item in kyb_report['risk_indicators'].split(',')]
        
        return kyb_report
    except json.JSONDecodeError:
        st.warning("Failed to decode JSON. Using fallback structure.")
        return {
            "company_name": company_name or "Unknown",
            "raw_data": output_text,
            "registration_number": "Not publicly available",
            "incorporation_date": "Not publicly available",
            "beneficial_owners": [],
            "financial_summary": {"details": "Not publicly available"},
            "risk_indicators": []
        }

def scrape_additional_data(company_name, company_website):
    """Scrapes the company's public website for additional information."""
    if not company_website:
        return {"about_info": "No website provided"}
    
    try:
        with st.spinner(f"Scraping data from {company_website}..."):
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
            res = requests.get(company_website, headers=headers, timeout=15)
            res.raise_for_status()
    except Exception as e:
        st.error(f"Error fetching {company_website}: {e}")
        return {"about_info": "Failed to retrieve website data"}
    
    soup = BeautifulSoup(res.text, 'html.parser')
    about_text = ""
    for selector in [
        soup.find(id=lambda x: x and 'about' in x.lower()),
        soup.find("section", {"class": lambda x: x and 'about' in x.lower()}),
        soup.find("div", {"class": lambda x: x and 'about' in x.lower()}),
        soup.find(string=lambda text: text and 'About Us' in text)
    ]:
        if selector and hasattr(selector, 'get_text'):
            about_text = selector.get_text(separator=" ", strip=True)
            break
        elif selector and selector.parent:
            about_text = selector.parent.get_text(separator=" ", strip=True)
            break
    
    if not about_text:
        meta_desc = soup.find("meta", {"name": "description"})
        about_text = meta_desc.get("content") if meta_desc else soup.get_text(separator=" ", strip=True)[:500] + "..."
    
    return {"about_info": about_text[:500]}

def save_report(report, company_name):
    """Saves the report as a JSON file with company name and date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{company_name.replace(' ', '_')}_{date_str}.json" if company_name else f"KYB_Report_{date_str}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    return filename

def update_user_output(company_name, company_website, kyb_report, enrichment_data):
    """Updates user_output.csv with new data."""
    output_file = "user_output.csv"
    columns = [
        "Company Name", "Website", "Registration Number", "Incorporation Date",
        "Beneficial Owners", "Financial Summary", "Risk Indicators", "About Info"
    ]
    
    if os.path.exists(output_file):
        df = pd.read_csv(output_file)
    else:
        df = pd.DataFrame(columns=columns)
    
    def flatten(value):
        if isinstance(value, list):
            if not value:
                return "None"
            if isinstance(value[0], dict):
                return ", ".join(f"{item.get('name', 'Unknown')} ({item.get('ownership_percentage', 'Unknown')})" for item in value)
            return ", ".join(str(item) for item in value)
        return str(value)
    
    new_row = {
        "Company Name": company_name or "Unknown",
        "Website": company_website or "N/A",
        "Registration Number": kyb_report.get("registration_number", "Not publicly available"),
        "Incorporation Date": kyb_report.get("incorporation_date", "Not publicly available"),
        "Beneficial Owners": flatten(kyb_report.get("beneficial_owners", [])),
        "Financial Summary": flatten(kyb_report.get("financial_summary", "Not publicly available")),
        "Risk Indicators": flatten(kyb_report.get("risk_indicators", [])),
        "About Info": enrichment_data.get("about_info", "N/A")
    }
    
    if company_name and company_name.lower() in df["Company Name"].str.lower().values:
        idx = df[df["Company Name"].str.lower() == company_name.lower()].index[0]
        df.loc[idx] = new_row
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    
    df.to_csv(output_file, index=False)

# Initialize session state for dashboard data
if 'reports' not in st.session_state:
    st.session_state.reports = []

# Admin login window
if admin_login_button:
    with st.form("admin_login"):
        st.subheader("Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username == "ycxadmin" and password == "ycxadmin":
                st.session_state.admin_logged_in = True