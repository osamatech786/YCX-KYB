import os
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime

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

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    # Model selection
    model_options = {
        "Groq - LLaMA 3.3 70B": "llama-3.3-70b-versatile",
        "Groq - Mixtral 8x7B": "mixtral-8x7b-32768",
        # Add more free models here when APIs are integrated (e.g., DeepSeek)
    }
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()), help="Choose the model to generate the report.")
    
    # API key input
    api_key = st.text_input("Enter your API Key", type="password")
    
    # API key signup links
    st.markdown("Need an API key?")
    st.markdown("[Sign up for Groq](https://console.groq.com/keys) | [Generate Groq API Key](https://console.groq.com/keys)")
    # Placeholder for other models
    st.markdown("*More model API links coming soon (DeepSeek, etc.)*")
    
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

# Function definitions
def generate_kyb_report(company_name, company_website, api_key, model, u_user_prompt=None):
    """Uses selected AI model to generate a KYB report."""
    client = Groq(api_key=api_key)  # Currently only Groq; extend for other APIs later
    
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
    
    # Base user prompt with optional company details
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
    
    # Append custom prompt if provided
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
    
    # Extract JSON from response
    json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
    if json_match:
        output_text = json_match.group(1)
    
    try:
        kyb_report = json.loads(output_text)
        
        # Normalize beneficial_owners
        if isinstance(kyb_report.get('beneficial_owners'), str):
            if kyb_report['beneficial_owners'] == "Not publicly available":
                kyb_report['beneficial_owners'] = []
            else:
                kyb_report['beneficial_owners'] = [{"name": kyb_report['beneficial_owners'], "ownership_percentage": "Unknown"}]
        
        # Normalize risk_indicators
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

# Initialize session state for dashboard data
if 'reports' not in st.session_state:
    st.session_state.reports = []

# Main app logic
if run_button:
    if not api_key:
        st.error("Please enter your API Key.")
    elif not custom_prompt:
        st.error("Please provide special instructions in the prompt field.")
    else:
        with st.spinner(f"Processing..."):
            model = model_options[selected_model]
            kyb_report = generate_kyb_report(company_name, company_website, api_key, model, custom_prompt)
            if kyb_report:
                enrichment_data = scrape_additional_data(company_name, company_website)
                full_profile = {**kyb_report, "web_data": enrichment_data}
                
                # Save report
                filename = save_report(full_profile, company_name)
                st.success(f"Report saved as {filename}")
                
                # Add to dashboard data
                st.session_state.reports.append({
                    "Company Name": kyb_report.get("company_name", "N/A"),
                    "Registration Number": kyb_report.get("registration_number", "Not publicly available"),
                    "Incorporation Date": kyb_report.get("incorporation_date", "Not publicly available"),
                    "Beneficial Owners": len(kyb_report.get("beneficial_owners", [])),
                    "Risk Indicators": len(kyb_report.get("risk_indicators", [])),
                    "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                # Display report
                tabs = st.tabs(["Report", "Dashboard"])
                
                with tabs[0]:
                    st.header(f"KYB Report for {kyb_report.get('company_name', 'Unknown')}")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Basic Information")
                        st.write(f"**Company Name:** {kyb_report.get('company_name', 'N/A')}")
                        st.write(f"**Website:** {company_website or 'N/A'}")
                        st.write(f"**Registration Number:** {kyb_report.get('registration_number', 'Not publicly available')}")
                        st.write(f"**Incorporation Date:** {kyb_report.get('incorporation_date', 'Not publicly available')}")
                    
                    with col2:
                        st.subheader("Financial Summary")
                        financial_summary = kyb_report.get('financial_summary', {})
                        if isinstance(financial_summary, dict) and financial_summary:
                            for key, value in financial_summary.items():
                                st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                        else:
                            st.write("Not publicly available")
                    
                    st.subheader("About")
                    st.write(enrichment_data.get('about_info', 'N/A'))
                    
                    st.subheader("Beneficial Owners")
                    owners = kyb_report.get('beneficial_owners', [])
                    if owners:
                        for i, owner in enumerate(owners, 1):
                            st.write(f"{i}. {owner.get('name', 'Unknown')} - {owner.get('ownership_percentage', 'Unknown')}")
                    else:
                        st.write("No beneficial owners identified")
                    
                    st.subheader("Risk Indicators")
                    risks = kyb_report.get('risk_indicators', [])
                    if risks:
                        for i, risk in enumerate(risks, 1):
                            st.write(f"{i}. {risk}")
                    else:
                        st.write("No risk indicators identified")
                    
                    st.download_button(
                        label="Download Report (JSON)",
                        data=json.dumps(full_profile, indent=2),
                        file_name=filename,
                        mime="application/json"
                    )
                
                with tabs[1]:
                    st.header("Dashboard - Generated Reports")
                    if st.session_state.reports:
                        df = pd.DataFrame(st.session_state.reports)
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.write("No reports generated yet.")

else:
    st.info("Enter your API key and special instructions, then click 'Generate KYB Report'.")
    st.markdown("### Examples of Special Instructions:")
    st.write("- 'Only include companies with founder ownership'")
    st.write("- 'Focus on European subsidiaries'")
    st.write("- 'Provide data for tech startups founded after 2015'")