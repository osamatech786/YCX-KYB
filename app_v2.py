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

# Initialize session state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'core_df' not in st.session_state:
    st.session_state.core_df = None

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

def save_report(report, company_name):
    """Save report as JSON."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{company_name.replace(' ', '_')}_{date_str}.json" if company_name else f"KYB_Report_{date_str}.json"
    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        return filename
    except Exception as e:
        st.error(f"Failed to save report: {str(e)}")
        return None

def update_user_output(company_name, company_website, kyb_report, enrichment_data):
    """Update user_output.csv with new data and return the new row."""
    output_file = "user_output.csv"
    columns = ["Company Name", "Website", "Registration Number", "Incorporation Date", "Beneficial Owners", "Financial Summary", "Risk Indicators", "About Info"]
    
    try:
        if os.path.exists(output_file):
            df = pd.read_csv(output_file)
        else:
            df = pd.DataFrame(columns=columns)
        
        new_row = {
            "Company Name": company_name or "Unknown",
            "Website": company_website or "N/A",
            "Registration Number": kyb_report.get("registration_number", "Not publicly available"),
            "Incorporation Date": kyb_report.get("incorporation_date", "Not publicly available"),
            "Beneficial Owners": ", ".join(f"{o.get('name', 'Unknown')} ({o.get('ownership_percentage', 'Unknown')})" for o in kyb_report.get("beneficial_owners", [])) or "None",
            "Financial Summary": json.dumps(kyb_report.get("financial_summary", {"details": "Not publicly available"})),
            "Risk Indicators": ", ".join(kyb_report.get("risk_indicators", [])) or "None",
            "About Info": enrichment_data.get("about_info", "N/A")
        }
        
        if company_name and company_name.lower() in df["Company Name"].str.lower().values:
            idx = df[df["Company Name"].str.lower() == company_name.lower()].index[0]
            df.loc[idx] = new_row
        else:
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
        df.to_csv(output_file, index=False)
        return pd.DataFrame([new_row])
    except Exception as e:
        st.error(f"Failed to update user_output.csv: {str(e)}")
        return None

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

elif run_button:
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not (company_name or custom_prompt):
        st.error("Please provide either a company name or special instructions.")
    else:
        model = model_options[selected_model]
        core_df = load_core_dataset()
        
        if company_name:  # Option 1: Single company report
            kyb_report = generate_kyb_report(company_name, company_website, api_key, model, custom_prompt)
            if kyb_report:
                enrichment_data = scrape_additional_data(company_website)
                full_profile = {**kyb_report, "web_data": enrichment_data}
                filename = save_report(full_profile, company_name)
                if filename:
                    st.success(f"Report saved as {filename}")
                
                new_row_df = update_user_output(company_name, company_website, kyb_report, enrichment_data)
                if new_row_df is not None:
                    tabs = st.tabs(["KYB Report", "Dashboard"])
                    
                    with tabs[0]:
                        st.header(f"KYB Report for {kyb_report.get('company_name', 'Unknown')}")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Company Name:** {kyb_report.get('company_name', 'N/A')}")
                            st.write(f"**Website:** {company_website or 'N/A'}")
                            st.write(f"**Registration Number:** {kyb_report.get('registration_number', 'Not publicly available')}")
                            st.write(f"**Incorporation Date:** {kyb_report.get('incorporation_date', 'Not publicly available')}")
                        with col2:
                            financial_summary = kyb_report.get('financial_summary', {})
                            st.write("**Financial Summary:**")
                            if isinstance(financial_summary, dict):
                                for k, v in financial_summary.items():
                                    st.write(f"{k.replace('_', ' ').title()}: {v}")
                            else:
                                st.write(financial_summary)
                        
                        st.write("**About:**", enrichment_data.get("about_info", "N/A"))
                        st.write("**Beneficial Owners:**")
                        for i, owner in enumerate(kyb_report.get("beneficial_owners", []), 1):
                            st.write(f"{i}. {owner.get('name', 'Unknown')} ({owner.get('ownership_percentage', 'Unknown')})")
                        st.write("**Risk Indicators:**")
                        for i, risk in enumerate(kyb_report.get("risk_indicators", []), 1):
                            st.write(f"{i}. {risk}")
                        if filename:
                            st.download_button(
                                label="Download Report (JSON)",
                                data=json.dumps(full_profile, indent=2),
                                file_name=filename,
                                mime="application/json"
                            )
                    
                    with tabs[1]:
                        st.subheader("Dashboard - New Row")
                        st.dataframe(new_row_df, use_container_width=True)
        
        elif custom_prompt:  # Option 2: Prompt-based query
            result_df = process_prompt(custom_prompt, core_df, api_key, model)
            if result_df is not None:
                st.subheader("Dashboard - Prompt Results")
                st.dataframe(result_df, use_container_width=True)
            else:
                st.warning("No results from prompt. Ensure the prompt is clear (e.g., 'Look for companies whose name starts with M').")
else:
    if not st.session_state.admin_logged_in:
        st.info("Enter your Groq API key and either a company name or special instructions, then click 'Generate Report'.")