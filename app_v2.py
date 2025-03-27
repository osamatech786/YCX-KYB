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

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    model_options = {
        "LLaMA 3.3 70B Versatile": "llama-3.3-70b-versatile",
        "LLaMA 3.1 8B Instant": "llama-3.1-8b-instant",
        "LLaMA3 70B 8192": "llama3-70b-8192",
        "LLaMA3 8B 8192": "llama3-8b-8192",
    }
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()))
    
    api_key = st.text_input("Enter your Groq API Key", type="password")
    st.markdown("[Generate Groq API Key](https://console.groq.com/keys)")
    
    company_name = st.text_input("Company Name (Optional)", help="Enter for single company report.")
    company_website = st.text_input("Company Website (Optional)", help="Optional for single company report.")
    custom_prompt = st.text_area("Special Instructions (Optional)", help="E.g., 'Look for companies whose name starts with M'")
    
    run_button = st.button("Generate Report", type="primary")
    admin_login_button = st.button("Admin Login")

# Function definitions
def generate_kyb_report(company_name, company_website, api_key, model, u_user_prompt=None):
    """Generate a KYB report using the selected Groq model."""
    client = Groq(api_key=api_key)
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize: registration number, "
        "incorporation date, beneficial owners, key financial metrics, and public risk indicators. "
        "Output ONLY a valid JSON object with keys: company_name, registration_number, incorporation_date, "
        "beneficial_owners, financial_summary, risk_indicators."
    )
    
    user_prompt = f"Company Name: {company_name}\nWebsite: {company_website or 'N/A'}\n\nPlease research {company_name} and provide all available information in JSON format."
    if u_user_prompt:
        user_prompt += f"\n\nADDITIONAL REQUIREMENTS:\n{u_user_prompt}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with st.spinner(f"Generating report using {selected_model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=1024
            )
        output_text = response.choices[0].message.content
        json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(1)
        kyb_report = json.loads(output_text)
        
        # Normalize data
        if not isinstance(kyb_report.get('beneficial_owners', []), list):
            kyb_report['beneficial_owners'] = [] if kyb_report.get('beneficial_owners') == "Not publicly available" else [{"name": str(kyb_report.get('beneficial_owners', 'Unknown')), "ownership_percentage": "Unknown"}]
        if not isinstance(kyb_report.get('risk_indicators', []), list):
            kyb_report['risk_indicators'] = [] if kyb_report.get('risk_indicators') == "Not publicly available" else [str(kyb_report.get('risk_indicators', ''))]
        if not isinstance(kyb_report.get('financial_summary'), dict):
            kyb_report['financial_summary'] = {"details": str(kyb_report.get('financial_summary', 'Not publicly available'))}
        
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
    core_file = "knowYourAi - Company Details.csv"  # Adjust this filename as needed
    try:
        if os.path.exists(core_file):
            st.session_state.core_df = pd.read_csv(core_file)
            return st.session_state.core_df
        return None
    except Exception as e:
        st.error(f"Failed to load core dataset: {str(e)}")
        return None

def process_prompt(prompt, core_df, api_key, model):
    """Process custom prompt using Groq API if core dataset is unavailable."""
    client = Groq(api_key=api_key)
    system_prompt = "You are a business analyst. Provide a list of companies based on the prompt in JSON format with keys: company_name, website, and any relevant details."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    try:
        with st.spinner(f"Processing prompt using {selected_model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=1024
            )
        output_text = response.choices[0].message.content
        json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(1)
        result = json.loads(output_text)
        if isinstance(result, list):
            return pd.DataFrame(result)
        elif isinstance(result, dict) and "companies" in result:
            return pd.DataFrame(result["companies"])
        st.warning("API response not in expected list format.")
        return pd.DataFrame([result])
    except Exception as e:
        st.error(f"Failed to process prompt with API: {str(e)}")
        return None

def display_report(report_data):
    """Display the KYB report in a structured format"""
    st.header("KYB Report")
    
    # Basic Information
    st.subheader("Basic Information")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Company Name:** {report_data.get('company_name', 'N/A')}")
        st.write(f"**Registration Number:** {report_data.get('registration_number', 'N/A')}")
    with col2:
        st.write(f"**Incorporation Date:** {report_data.get('incorporation_date', 'N/A')}")
    
    # Financial Summary
    st.subheader("Financial Summary")
    financial_summary = report_data.get('financial_summary', {})
    if isinstance(financial_summary, dict):
        for key, value in financial_summary.items():
            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
    
    # Beneficial Owners
    st.subheader("Beneficial Owners")
    beneficial_owners = report_data.get('beneficial_owners', [])
    if beneficial_owners:
        for owner in beneficial_owners:
            if isinstance(owner, dict):
                st.write(f"- **{owner.get('name', 'Unknown')}** ({owner.get('ownership_percentage', 'Unknown')})")
            else:
                st.write(f"- {owner}")
    
    # Risk Indicators
    st.subheader("Risk Indicators")
    risk_indicators = report_data.get('risk_indicators', [])
    if risk_indicators:
        for risk in risk_indicators:
            st.write(f"- {risk}")
    
    # Raw JSON
    with st.expander("View Raw JSON"):
        st.json(report_data)

# Admin login
if admin_login_button:
    with st.form("admin_login"):
        st.subheader("Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username == "ycxadmin" and password == "ycxadmin":
                st.session_state.admin_logged_in = True
                st.success("Logged in as admin!")
            else:
                st.error("Invalid credentials.")

# Main logic
if st.session_state.admin_logged_in:
    st.header("Admin Dashboard")
    tabs = st.tabs(["KYB Reports", "Dashboard"])
    
    with tabs[0]:
        st.subheader("All Generated KYB Reports")
        report_files = glob.glob("*.json")
        if report_files:
            for file in report_files:
                try:
                    with open(file, 'r') as f:
                        report_data = json.load(f)
                    with st.expander(f"Report: {file}"):
                        st.json(report_data)
                except Exception as e:
                    st.error(f"Error loading {file}: {str(e)}")
        else:
            st.write("No reports found.")
    
    with tabs[1]:
        st.subheader("User Output CSV")
        if os.path.exists("user_output.csv"):
            try:
                df = pd.read_csv("user_output.csv")
                st.dataframe(df, use_container_width=True)
                st.download_button(
                    label="Download user_output.csv",
                    data=df.to_csv(index=False),
                    file_name="user_output.csv",
                    mime="text/csv"
                )
            except Exception as e:
                st.error(f"Error loading user_output.csv: {str(e)}")
        else:
            st.write("user_output.csv not found.")
    
    if st.button("Logout"):
        st.session_state.admin_logged_in = False
        st.rerun()  # Force rerun to refresh UI

elif input_choice == "Enter Company Name":
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not company_name:
        st.error("Please enter a Company Name.")
    else:
        try:
            # Load core dataset
            df = pd.read_csv(CORE_DATASET_PATH)
            
            # Process company
            with st.spinner(f"Processing {company_name}..."):
                # Pass the selected model from sidebar
                kyb_report = generate_kyb_report(
                    company_name=company_name,
                    company_website=company_website,
                    api_key=api_key,
                    model=model_options[selected_model]  # Add this parameter
                )
                if kyb_report:
                    # Save report
                    save_report(company_name, kyb_report)
                    # Update usage log
                    update_user_output(
                        api_key=api_key,
                        input_type="company_name",
                        input_text=company_name,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    # Display report
                    display_report(kyb_report)
        except Exception as e:
            st.error(f"Error: {e}")

elif input_choice == "Write Custom Prompt":
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not custom_prompt:
        st.error("Please enter your prompt.")
    else:
        try:
            # Process custom prompt using Groq API directly
            client = Groq(api_key=api_key)
            
            with st.spinner("Processing your prompt..."):
                response = client.chat.completions.create(
                    messages=[
                        {"role": "user", "content": custom_prompt}
                    ],
                    model=model_options[selected_model],
                    temperature=0.3,
                    max_tokens=1024
                )
                
                if response:
                    # Update usage log
                    update_user_output(
                        api_key=api_key,
                        input_type="custom_prompt",
                        input_text=custom_prompt,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    # Display response
                    st.write("Response:")
                    st.write(response.choices[0].message.content)
        except Exception as e:
            st.error(f"Error: {e}")

else:  # Admin View
    # Add authentication for admin view
    admin_password = st.text_input("Enter admin password", type="password")
    if admin_password == "ycxadmin":  # Replace with secure authentication
        st.header("Admin Dashboard")
        
        # Display user output log
        if os.path.exists(USER_OUTPUT_PATH):
            st.subheader("Usage Log")
            usage_df = pd.read_csv(USER_OUTPUT_PATH)
            st.dataframe(usage_df)
        
        # Display generated reports
        st.subheader("Generated Reports")
        for filename in os.listdir(REPORTS_DIR):
            if filename.endswith('.json'):
                with open(os.path.join(REPORTS_DIR, filename), 'r') as f:
                    report_data = json.load(f)
                    with st.expander(f"Report: {filename}"):
                        st.json(report_data)
    else:
        st.error("Please enter valid admin credentials to view this section.")