import os
import json
import requests
import re
import time
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
This application helps you perform KYB due diligence by gathering information about companies
from various sources and presenting it in a structured format.
""")

# Function definitions
def generate_kyb_report(company_name, company_website, api_key):
    """Uses Groq API to generate a KYB report with enhanced prompt."""
    client = Groq(api_key=api_key)
    
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize the following details: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and any public risk indicators. Output ONLY a valid JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "For beneficial_owners, provide an array of objects with name and ownership_percentage when available. "
        "DO NOT include any explanatory text outside the JSON object. "
        "Ensure the response is properly formatted JSON that can be parsed by json.loads()."
    )
    
    user_prompt = (
        f"Company Name: {company_name}\nWebsite: {company_website}\n\n"
        f"Please research {company_name} and provide all available information in JSON format. "
        f"Pay special attention to beneficial owners (with their ownership percentages if available) "
        f"and any risk indicators such as regulatory issues, legal disputes, negative news, "
        f"or financial concerns. If specific data points are not publicly available, "
        f"use 'Not publicly available' as the value, but try to find as much information "
        f"as possible from public sources."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            top_p=1,
            max_tokens=1024
        )
        output_text = response.choices[0].message.content
        
        # Extract JSON from the response
        json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(1)
        
        kyb_report = json.loads(output_text)
        
        # Ensure required fields are present
        kyb_report['company_name'] = company_name
        kyb_report.setdefault('registration_number', 'Not publicly available')
        kyb_report.setdefault('incorporation_date', 'Not publicly available')
        kyb_report.setdefault('beneficial_owners', [])
        kyb_report.setdefault('financial_summary', 'Not publicly available')
        kyb_report.setdefault('risk_indicators', [])
        
        # Normalize beneficial_owners to list
        if isinstance(kyb_report['beneficial_owners'], str):
            if kyb_report['beneficial_owners'] == 'Not publicly available':
                kyb_report['beneficial_owners'] = []
            else:
                kyb_report['beneficial_owners'] = [{"name": kyb_report['beneficial_owners'], "ownership_percentage": "Unknown"}]
        
        # Normalize risk_indicators to list
        if isinstance(kyb_report['risk_indicators'], str):
            if kyb_report['risk_indicators'] == 'Not publicly available':
                kyb_report['risk_indicators'] = []
            else:
                kyb_report['risk_indicators'] = [kyb_report['risk_indicators']]
        
        return kyb_report
    except Exception as e:
        st.error(f"Error during Groq API call or JSON parsing: {e}")
        return {
            "company_name": company_name,
            "registration_number": "Not publicly available",
            "incorporation_date": "Not publicly available",
            "beneficial_owners": [],
            "financial_summary": "Not publicly available",
            "risk_indicators": []
        }

def scrape_additional_data(company_name, company_website):
    """Scrapes the company's public website for additional information."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        return {"about_info": f"Failed to retrieve website data: {e}"}
    
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
    
    return {"about_info": about_text[:500] + "..." if len(about_text) > 500 else about_text}

def search_duckduckgo(query, max_results=5):
    """Search DuckDuckGo without an API key, prioritizing official websites."""
    url = "https://duckduckgo.com/html/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
    params = {"q": query}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        company_name_lower = query.split()[0].lower()
        
        for link in soup.find_all('a', class_='result__url', href=True):
            href = link['href']
            if href.startswith('/l/?uddg='):
                actual_url_match = re.search(r'https?://[^\&]+', href)
                if actual_url_match:
                    actual_url = actual_url_match.group(0)
                    if re.search(rf'(www\.)?{re.escape(company_name_lower)}\.(com|org|co|net)', actual_url, re.IGNORECASE):
                        results.append(actual_url)
                        if len(results) >= max_results:
                            break
            else:
                if re.search(rf'(www\.)?{re.escape(company_name_lower)}\.(com|org|co|net)', href, re.IGNORECASE):
                    results.append(href)
                    if len(results) >= max_results:
                        break
        
        if not results:
            for link in soup.find_all('a', class_='result__url', href=True)[:1]:
                href = link['href']
                if href.startswith('/l/?uddg='):
                    actual_url_match = re.search(r'https?://[^\&]+', href)
                    if actual_url_match:
                        results.append(actual_url_match.group(0))
        
        return results
    except Exception as e:
        st.error(f"DuckDuckGo search failed: {e}")
        return []

def find_company_website(company_name):
    """Search for company's official website using DuckDuckGo."""
    query = f"{company_name} official website"
    results = search_duckduckgo(query, max_results=1)
    return results[0] if results else None

def process_and_update_database(company_name, company_website, kyb_report, enrichment_data, core_df):
    """Update user_output.csv with new company data, keeping core dataset unchanged."""
    columns = [
        'Company Name', 'Website', 'Registration Number', 'Incorporation Date', 
        'Beneficial Owners', 'Financial Summary', 'Risk Indicators', 'Company Description'
    ]
    
    output_file = "user_output.csv"
    if os.path.exists(output_file):
        user_df = pd.read_csv(output_file)
    else:
        user_df = pd.DataFrame(columns=columns)
    
    def flatten(value):
        if isinstance(value, list):
            if not value:
                return "None"
            if isinstance(value[0], dict):
                return ", ".join(f"{item.get('name', 'Unknown')} ({item.get('ownership_percentage', 'Unknown')})" for item in value)
            return ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            return ", ".join(f"{k}: {v}" for k, v in value.items())
        return str(value)
    
    new_data = {
        'Company Name': company_name,
        'Website': company_website,
        'Registration Number': flatten(kyb_report.get('registration_number', 'Not publicly available')),
        'Incorporation Date': flatten(kyb_report.get('incorporation_date', 'Not publicly available')),
        'Beneficial Owners': flatten(kyb_report.get('beneficial_owners', [])),
        'Financial Summary': flatten(kyb_report.get('financial_summary', 'Not publicly available')),
        'Risk Indicators': flatten(kyb_report.get('risk_indicators', [])),
        'Company Description': flatten(enrichment_data.get('about_info', 'Not publicly available'))
    }
    
    if company_name.lower() in user_df['Company Name'].str.lower().values:
        idx = user_df[user_df['Company Name'].str.lower() == company_name.lower()].index[0]
        user_df.loc[idx] = new_data
    else:
        user_df = pd.concat([user_df, pd.DataFrame([new_data])], ignore_index=True)
    
    user_df.to_csv(output_file, index=False)

def display_report(kyb_report, enrichment_data, company_website):
    """Display the KYB report in a user-friendly format with tabs."""
    company_name = kyb_report.get('company_name', 'Unknown')
    st.header(f"KYB Report for {company_name}")
    
    tab1, tab2, tab3 = st.tabs(["Company Overview", "Beneficial Owners", "Risk Indicators"])
    
    with tab1:
        st.subheader("Basic Information")
        cols = st.columns(2)
        with cols[0]:
            st.write(f"**Company Name:** {company_name}")
            st.write(f"**Website:** {company_website}")
            st.write(f"**Registration Number:** {kyb_report.get('registration_number', 'Not publicly available')}")
        with cols[1]:
            st.write(f"**Incorporation Date:** {kyb_report.get('incorporation_date', 'Not publicly available')}")
        
        st.subheader("Financial Summary")
        financial_summary = kyb_report.get('financial_summary', 'Not publicly available')
        if isinstance(financial_summary, dict):
            for key, value in financial_summary.items():
                st.write(f"**{key.replace('_', ' ').title()}:** {value}")
        else:
            st.write(financial_summary)
        
        st.subheader("Company Description")
        st.write(enrichment_data.get('about_info', 'Not publicly available'))
    
    with tab2:
        st.subheader("Beneficial Owners")
        beneficial_owners = kyb_report.get('beneficial_owners', [])
        if beneficial_owners:
            for i, owner in enumerate(beneficial_owners, 1):
                if isinstance(owner, dict):
                    st.write(f"**{i}. {owner.get('name', 'Unknown')}**")
                    st.write(f"Ownership Percentage: {owner.get('ownership_percentage', 'Unknown')}")
                    st.write("---")
                else:
                    st.write(f"**{i}.** {owner}")
        else:
            st.write("No beneficial owners identified")
    
    with tab3:
        st.subheader("Risk Indicators")
        risk_indicators = kyb_report.get('risk_indicators', [])
        if risk_indicators:
            for i, risk in enumerate(risk_indicators, 1):
                st.write(f"{i}. {risk}")
        else:
            st.write("No risk indicators identified")
    
    full_data = {**kyb_report, "web_data": enrichment_data}
    st.download_button(
        label="Download Report (JSON)",
        data=json.dumps(full_data, indent=2),
        file_name=f"{company_name.replace(' ', '_')}_kyb_report.json",
        mime="application/json"
    )

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Enter your Groq API Key", type="password")
    company_name = st.text_input("Company Name")
    run_button = st.button("Generate KYB Report", type="primary")

# Main app logic
if run_button:
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not company_name:
        st.error("Please enter a Company Name.")
    else:
        try:
            core_df = pd.read_csv("knowYourAi - Company Details.csv")
            company_data = core_df[core_df['Company Name'].str.lower() == company_name.lower()]
            
            if not company_data.empty:
                st.success(f"Found existing data for {company_name}")
                company_website = company_data.iloc[0]['Website'].split(' [')[0]
            else:
                st.info(f"Adding new company: {company_name}")
                company_website = find_company_website(company_name)
                if not company_website:
                    st.error("Could not find company website. Please try again.")
                    st.stop()
                st.success(f"Found company website: {company_website}")

            with st.spinner(f"Processing {company_name}..."):
                kyb_report = generate_kyb_report(company_name, company_website, api_key)
                if not kyb_report or "error" in kyb_report:
                    st.error("KYB report generation failed.")
                else:
                    enrichment_data = scrape_additional_data(company_name, company_website)
                    process_and_update_database(company_name, company_website, kyb_report, enrichment_data, core_df)
                    display_report(kyb_report, enrichment_data, company_website)

        except Exception as e:
            st.error(f"Error processing request: {e}")

else:
    st.info("Enter your Groq API key and company name, then click 'Generate KYB Report'.")