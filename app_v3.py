import os
import sys
print("Python path:", sys.executable)
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime
import glob
from crewai import Agent, Task, Crew  # Import CrewAI
from transformers import pipeline  # For local LLM
import sys
import subprocess

# File paths
CORE_DATASET_PATH = "/home/opc/myenv/YCX-KYB/knowYourAi - Company Details.csv"
USER_OUTPUT_PATH = "/home/opc/myenv/YCX-KYB/user_output.csv"
REPORTS_DIR = "/home/opc/myenv/YCX-KYB/generated_reports"

# Create reports directory if it doesn't exist
os.makedirs(REPORTS_DIR, exist_ok=True)

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

# Initialize session state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'core_df' not in st.session_state:
    st.session_state.core_df = None

# Input method selection
input_choice = st.radio(
    "Choose your input method:",
    ["Enter Company Name", "Write Custom Prompt", "Admin View"]
)

# Simplified model_options with only the confirmed working models
model_options = {
    "LLaMA 3 70B": "llama3-70b-8192",
    "LLaMA 3 8B": "llama3-8b-8192",
    "LLaMA 3.3 70B Versatile": "llama-3.3-70b-versatile",
    "Mistral Saba 24B": "mistral-saba-24b"
}

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()))
    
    api_key = st.text_input("Enter your Groq API Key", type="password")
    st.markdown("[Generate Groq API Key](https://console.groq.com/keys)")
    
    company_name = st.text_input("Company Name (Optional)", help="Enter for single company report.")
    company_website = st.text_input("Company Website (Optional)", help="Optional for single company report.")
    custom_prompt = st.text_area("Special Instructions (Optional)", help="E.g., 'Look for companies whose name starts with M'")
    
    run_button = st.button("Generate Report", type="primary")

# Initialize the local LLM for CrewAI (Hugging Face model)
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# CrewAI Tools and Functions
def scrape_web_for_company(company_name):
    """Scrape additional data about the company from the web (e.g., news articles)."""
    try:
        # Example: Search for news articles or public info using a simple Google search simulation
        # In a real scenario, you might use a search API or scrape a specific site
        search_url = f"https://www.google.com/search?q={company_name}+news+site:*.org+site:*.gov+-inurl:(signup | login)"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(search_url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        snippets = soup.find_all('div', class_='BNeawe s3v9rd AP7Wnd')  # Google search snippet class
        text = ' '.join([snippet.get_text() for snippet in snippets[:3]])  # Take first 3 snippets
        if not text:
            return "No additional data found."
        return text
    except Exception as e:
        return f"Error scraping web: {str(e)}"

def process_data_with_llm(text):
    """Process the scraped data using a local LLM (summarization)."""
    try:
        summary = summarizer(text, max_length=100, min_length=30, do_sample=False)
        return summary[0]['summary_text']
    except Exception as e:
        return f"Error processing data: {str(e)}"

def save_to_core_dataset(company_name, processed_data):
    """Save the processed data into the core dataset CSV."""
    try:
        new_data = pd.DataFrame({
            "company_name": [company_name],
            "additional_info": [processed_data],
            "timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        })
        if os.path.exists(CORE_DATASET_PATH):
            existing_data = pd.read_csv(CORE_DATASET_PATH)
            updated_data = pd.concat([existing_data, new_data], ignore_index=True)
        else:
            updated_data = new_data
        updated_data.to_csv(CORE_DATASET_PATH, index=False)
        return f"Data saved to {CORE_DATASET_PATH}"
    except Exception as e:
        return f"Error saving to CSV: {str(e)}"

# Define CrewAI Agents
scraper_agent = Agent(
    role="Web Scraper",
    goal="Scrape additional data about a company from the web.",
    backstory="You are an expert web scraper with years of experience finding public information about companies.",
    verbose=True,
    allow_delegation=False
)

processor_agent = Agent(
    role="Data Processor",
    goal="Process and summarize scraped data using a local LLM.",
    backstory="You are a data analyst skilled in using LLMs to extract insights and summarize text.",
    verbose=True,
    allow_delegation=False
)

writer_agent = Agent(
    role="CSV Writer",
    goal="Save processed data into the core dataset CSV file.",
    backstory="You are a data engineer who ensures data is properly stored in CSV format.",
    verbose=True,
    allow_delegation=False
)

# Function definitions (unchanged from your original code)
def generate_kyb_report(company_name, company_website, api_key, model):
    """Generate a KYB report using the selected Groq model."""
    client = Groq(api_key=api_key)
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize: registration number, "
        "incorporation date, beneficial owners, key financial metrics, and public risk indicators. "
        "Output ONLY a valid JSON object with keys: company_name, registration_number, incorporation_date, "
        "beneficial_owners, financial_summary, risk_indicators. Ensure the JSON is properly formatted "
        "with correct commas and quotes. Use 'Not publicly available' for missing data."
    )
    
    user_prompt = f"Company Name: {company_name}\nWebsite: {company_website or 'N/A'}\n\n"
    user_prompt += "Please research the company and provide information in valid JSON format. Ensure all JSON syntax is correct."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with st.spinner(f"Generating report using {model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=1024
            )
            
        output_text = response.choices[0].message.content
        
        output_text = output_text.strip()
        if output_text.startswith("```json"):
            output_text = output_text.replace("```json", "").replace("```", "")
        
        output_text = output_text.replace("'", '"')
        output_text = re.sub(r',\s*}', '}', output_text)
        output_text = re.sub(r',\s*]', ']', output_text)
        
        try:
            kyb_report = json.loads(output_text)
        except json.JSONDecodeError as e:
            st.error(f"JSON parsing error: {str(e)}")
            st.text("Raw response:")
            st.code(output_text)
            return None
        
        kyb_report = {
            "company_name": company_name,
            "registration_number": kyb_report.get("registration_number", "Not publicly available"),
            "incorporation_date": kyb_report.get("incorporation_date", "Not publicly available"),
            "beneficial_owners": kyb_report.get("beneficial_owners", []),
            "financial_summary": kyb_report.get("financial_summary", {}),
            "risk_indicators": kyb_report.get("risk_indicators", [])
        }
        
        if not isinstance(kyb_report["beneficial_owners"], list):
            kyb_report["beneficial_owners"] = [kyb_report["beneficial_owners"]] if kyb_report["beneficial_owners"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["risk_indicators"], list):
            kyb_report["risk_indicators"] = [kyb_report["risk_indicators"]] if kyb_report["risk_indicators"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["financial_summary"], dict):
            kyb_report["financial_summary"] = {"details": str(kyb_report["financial_summary"])}
            
        return kyb_report
        
    except Exception as e:
        st.error(f"Failed to generate report: {str(e)}")
        return None

def scrape_additional_data(company_website):
    """Scrape additional data from the company website."""
    if not company_website:
        return {"about_info": "N/A"}
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
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
    except Exception as e:
        st.error(f"Scraping failed: {str(e)}")
        return {"about_info": "Failed to retrieve data"}

def save_report(company_name, report_data):
    """Save report to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{company_name.replace(' ', '_')}_{timestamp}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(report_data, f, indent=2)

def update_user_output(api_key, input_type, input_text, timestamp):
    """Update user_output.csv with usage data"""
    data = {
        'api_key': [api_key],
        'input_type': [input_type],
        'input_text': [input_text],
        'timestamp': [timestamp]
    }
    new_entry = pd.DataFrame(data)
    
    try:
        if os.path.exists(USER_OUTPUT_PATH):
            df = pd.read_csv(USER_OUTPUT_PATH)
            df = pd.concat([df, new_entry], ignore_index=True)
        else:
            df = new_entry
        df.to_csv(USER_OUTPUT_PATH, index=False)
    except Exception as e:
        st.error(f"Failed to update user_output.csv: {e}")

def load_core_dataset():
    """Load core dataset if it exists."""
    try:
        if os.path.exists(CORE_DATASET_PATH):
            st.session_state.core_df = pd.read_csv(CORE_DATASET_PATH)
            return st.session_state.core_df
        return None
    except Exception as e:
        st.error(f"Failed to load core dataset: {str(e)}")
        return None

print("Python path:", sys.executable)
print("Installed packages:")
subprocess.run([sys.executable, "-m", "pip", "list"])